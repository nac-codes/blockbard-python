#!/usr/bin/env python3
import argparse
import requests
import time
import random
import sys
import threading
import os
import json
import logging
from openai import OpenAI
from datetime import datetime

# Add the parent directory to sys.path so we can import modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

class OpenAIStoryteller:
    """
    An AI storyteller that uses OpenAI's GPT model to generate story contributions
    based on the current blockchain state.
    """
    
    def __init__(self, node_url, author_id, api_key=None, system_prompt=None, mine_interval=15, model="gpt-4.1-mini-2025-04-14", max_context_words=10000, log_level="INFO"):
        self.node_url = node_url
        self.author_id = author_id
        self.mine_interval = mine_interval
        self.model = model
        self.max_context_words = max_context_words
        self.running = False
        self.story_thread = None
        
        # Set up logging
        self._setup_logging(log_level)
        
        self.logger.info(f"Initializing OpenAI Storyteller (Author {self.author_id})")
        self.logger.info(f"Connected to node: {self.node_url}")
        self.logger.info(f"Using model: {self.model}")
        self.logger.info(f"Mine interval: {self.mine_interval} seconds")
        
        # Set OpenAI API key from provided key or environment variable
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY")
        if not self.api_key:
            self.logger.error("OpenAI API key not found in parameters or environment")
            raise ValueError("OpenAI API key is required. Either pass it directly or set OPENAI_API_KEY environment variable.")
        
        self.logger.debug("API key found, initializing OpenAI client")
        # Create the OpenAI client
        self.client = OpenAI(api_key=self.api_key)
        
        # Default system prompt if none provided
        self.system_prompt = system_prompt or (
            f"You are Author {self.author_id}, a creative storyteller contributing to a collaborative "
            f"blockchain-based story. Your task is to add compelling and contextually relevant "
            f"continuations to the evolving narrative. Each contribution should move the story forward "
            f"in interesting ways. Be concise but vivid, aiming for 2-3 sentences per contribution."
        )
        self.logger.info(f"System prompt: {self.system_prompt[:50]}...")
    
    def _setup_logging(self, log_level):
        """Set up the logging configuration."""
        # Create logs directory if it doesn't exist
        os.makedirs("logs", exist_ok=True)
        
        # Set up logger
        self.logger = logging.getLogger(f"storyteller_{self.author_id}")
        self.logger.setLevel(getattr(logging, log_level.upper()))
        
        # Clear any existing handlers
        if self.logger.hasHandlers():
            self.logger.handlers.clear()
        
        # Add console handler
        console_handler = logging.StreamHandler()
        console_handler.setLevel(getattr(logging, log_level.upper()))
        console_format = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        console_handler.setFormatter(console_format)
        self.logger.addHandler(console_handler)
        
        # Add file handler
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        file_handler = logging.FileHandler(f"logs/storyteller_{self.author_id}_{timestamp}.log")
        file_handler.setLevel(getattr(logging, log_level.upper()))
        file_format = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        file_handler.setFormatter(file_format)
        self.logger.addHandler(file_handler)
    
    def _get_current_story(self, max_retries=5, backoff_factor=1.5):
        """
        Get the current state of the story from the blockchain with robust error handling.
        Uses exponential backoff for retries to handle temporary network issues or node busy states.
        """
        self.logger.debug(f"Fetching current story from {self.node_url}/get_chain")
        
        base_timeout = 5  # Base timeout in seconds
        retry_count = 0
        
        while retry_count < max_retries:
            try:
                # Increase timeout slightly with each retry
                current_timeout = base_timeout + (retry_count * 2)
                
                # Make the request with the current timeout
                response = requests.get(f"{self.node_url}/get_chain", timeout=current_timeout)
                
                if response.status_code == 200:
                    blockchain = response.json()
                    self.logger.debug(f"Successfully fetched blockchain with {len(blockchain)} blocks")
                    return blockchain
                else:
                    # Non-200 response - log and retry
                    self.logger.warning(f"Failed to get story state: HTTP {response.status_code}")
                    self.logger.debug(f"Response: {response.text}")
                    
                    # Increment retry counter
                    retry_count += 1
                    
                    if retry_count >= max_retries:
                        self.logger.error(f"Failed to get blockchain after {max_retries} attempts")
                        return None
                    
                    # Calculate backoff time
                    wait_time = backoff_factor ** retry_count
                    self.logger.info(f"Retrying in {wait_time:.2f} seconds (attempt {retry_count+1}/{max_retries})")
                    time.sleep(wait_time)
            
            except requests.exceptions.Timeout:
                retry_count += 1
                if retry_count >= max_retries:
                    self.logger.error(f"Timeout error fetching blockchain after {max_retries} attempts")
                    return None
                
                # Calculate backoff time for timeout
                wait_time = backoff_factor ** retry_count
                self.logger.warning(f"Timeout fetching blockchain. Retrying in {wait_time:.2f} seconds (attempt {retry_count+1}/{max_retries})")
                time.sleep(wait_time)
                
            except requests.exceptions.ConnectionError:
                retry_count += 1
                if retry_count >= max_retries:
                    self.logger.error(f"Connection error fetching blockchain after {max_retries} attempts")
                    return None
                
                # Calculate backoff time for connection error
                wait_time = backoff_factor ** retry_count
                self.logger.warning(f"Connection error fetching blockchain. Retrying in {wait_time:.2f} seconds (attempt {retry_count+1}/{max_retries})")
                time.sleep(wait_time)
                
            except Exception as e:
                self.logger.error(f"Error getting story state: {str(e)}", exc_info=True)
                
                retry_count += 1
                if retry_count >= max_retries:
                    self.logger.error(f"Failed to get blockchain after {max_retries} attempts due to errors")
                    return None
                
                # Calculate backoff time
                wait_time = backoff_factor ** retry_count
                self.logger.warning(f"Error fetching blockchain. Retrying in {wait_time:.2f} seconds (attempt {retry_count+1}/{max_retries})")
                time.sleep(wait_time)
        
        # This should never be reached if max_retries > 0
        return None
    
    def _prepare_context(self, blockchain):
        """Extract story text from blockchain and limit to max_context_words."""
        self.logger.debug("Preparing story context from blockchain")
        story_text = []
        
        if not blockchain:
            self.logger.warning("No blockchain data available for context preparation")
            return ""
            
        # Add blocks in order, starting from genesis
        for block in blockchain:
            # Skip genesis block unless it contains actual story content
            if block["index"] == 0 and "Genesis Block" in block["data"]:
                self.logger.debug("Skipping standard genesis block")
                continue
            
            self.logger.debug(f"Adding block {block['index']} to context")
            story_text.append(block["data"])
        
        # Join all story contributions
        full_story = "\n\n".join(story_text)
        
        # Limit to max_context_words
        words = full_story.split()
        word_count = len(words)
        self.logger.debug(f"Story context has {word_count} words")
        
        if word_count > self.max_context_words:
            # Keep the most recent words up to the limit
            self.logger.info(f"Truncating context from {word_count} to {self.max_context_words} words")
            words = words[-self.max_context_words:]
            full_story = " ".join(words)
            
        return full_story
    
    def _generate_contribution(self, blockchain=None):
        """Generate a Bible verse translation using OpenAI's GPT model.
        Returns a tuple of (contribution_text, previous_hash) to ensure consistency."""
        self.logger.info("Generating new Bible verse translation")
        
        # Get the current blockchain if not provided
        if blockchain is None:
            self.logger.debug("No blockchain provided, fetching current state")
            blockchain = self._get_current_story()
        
        if not blockchain:
            self.logger.warning("No blockchain data available, using fallback Genesis 1:1")
            return (f"Author {self.author_id} says: In the beginning God created the heaven and the earth.", None)
        
        # Store the hash of the latest block - this is the previous hash for our new contribution
        latest_block = blockchain[-1]
        previous_hash = latest_block["hash"]
        self.logger.debug(f"Generating contribution based on previous hash: {previous_hash}")
        
        # Prepare the story context
        self.logger.debug("Preparing context for OpenAI")
        bible_context = self._prepare_context(blockchain)
        
        # Determine which verse comes next
        current_verse = "Genesis 1:1"
        next_verse = "Genesis 1:2"
        
        # Check the last verse in the blockchain
        if len(blockchain) > 1:  # If we have more than just genesis
            last_block = blockchain[-1]
            last_content = last_block["data"]
            
            # Try to extract verse reference
            if "Genesis 1:" in last_content:
                try:
                    # Look for "Genesis 1:X" pattern
                    import re
                    verse_match = re.search(r'Genesis 1:(\d+)', last_content)
                    if verse_match:
                        last_verse_num = int(verse_match.group(1))
                        next_verse_num = last_verse_num + 1
                        next_verse = f"Genesis 1:{next_verse_num}"
                        self.logger.info(f"Detected last verse was {last_verse_num}, next is {next_verse}")
                except Exception as e:
                    self.logger.warning(f"Error determining next verse: {e}")
                    # Default to Genesis 1:2 if we can't determine
                    next_verse = "Genesis 1:2"
        
        try:
            # Call the OpenAI API using the client-based approach
            self.logger.info(f"Calling OpenAI API with model {self.model}")
            start_time = time.time()
            
            messages = [
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": f"Here are the previous Bible translations:\n\n{bible_context}\n\nPlease provide your translation of {next_verse} according to your denomination's theological perspective. Be accurate but reflect your unique religious viewpoint."}
            ]
            self.logger.debug(f"Sending message with {len(bible_context)} characters of context")
            
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=200,
                temperature=0.7
            )
            
            elapsed_time = time.time() - start_time
            self.logger.info(f"OpenAI response received in {elapsed_time:.2f} seconds")
            
            # Extract the generated text
            contribution = response.choices[0].message.content.strip()
            self.logger.debug(f"Generated contribution: {contribution}")
            
            # If contribution doesn't include the verse reference, add it
            if next_verse not in contribution:
                contribution = f"{next_verse} - {contribution}"
            
            return (contribution, previous_hash)
            
        except Exception as e:
            self.logger.error(f"Error generating contribution with OpenAI: {str(e)}", exc_info=True)
            # Fallback to a simple contribution
            fallback = f"Author {self.author_id} says: {next_verse} - And the earth was without form, and void; and darkness was upon the face of the deep."
            self.logger.info(f"Using fallback contribution: {fallback}")
            return (fallback, previous_hash)
    
    def _submit_contribution(self, contribution_data, max_retries=3, backoff_factor=1.5):
        """
        Submit a story contribution to the blockchain node with robust retry logic.
        contribution_data is a tuple of (contribution_text, previous_hash)
        """
        # Unpack the contribution data
        contribution, previous_hash = contribution_data
        
        self.logger.info(f"Submitting contribution to node: {self.node_url}")
        self.logger.debug(f"Full contribution: {contribution}")
        self.logger.debug(f"Using previous hash: {previous_hash}")
        
        # If we don't have a previous hash, we can't submit
        if previous_hash is None:
            self.logger.error("Cannot submit contribution: No previous hash available")
            return False
        
        # Include previous_hash in the payload
        payload = {
            "data": contribution,
            "previous_hash": previous_hash
        }
        self.logger.debug(f"Payload with previous hash: {json.dumps(payload)}")
        
        # Initialize retry counters
        retry_count = 0
        base_timeout = 5  # Base timeout in seconds
        
        while retry_count < max_retries:
            try:
                # Increase timeout slightly with each retry
                current_timeout = base_timeout + (retry_count * 2)
                
                self.logger.debug(f"Sending POST request to {self.node_url}/add_transaction (timeout: {current_timeout}s)")
                start_time = time.time()
                
                response = requests.post(
                    f"{self.node_url}/add_transaction", 
                    json=payload,
                    timeout=current_timeout
                )
                
                elapsed_time = time.time() - start_time
                self.logger.info(f"Response received in {elapsed_time:.2f} seconds: {response.status_code}")
                self.logger.debug(f"Response body: {response.text}")
                
                if response.status_code == 201:
                    self.logger.info(f"Contribution successfully submitted")
                    return True
                elif response.status_code == 409:  # Conflict - chain has changed
                    # This is an expected error case - the blockchain has moved on
                    # Don't retry in this case as we need to regenerate the contribution
                    self.logger.warning("Contribution rejected due to chain state change")
                    try:
                        error_data = response.json()
                        self.logger.info(f"Expected hash: {error_data.get('expected_hash')}, Latest block: {error_data.get('latest_block_index')}")
                    except:
                        pass
                    return False
                else:
                    # Other HTTP errors - retry with backoff
                    self.logger.warning(f"Failed to submit contribution: HTTP {response.status_code}")
                    retry_count += 1
                    
                    if retry_count >= max_retries:
                        self.logger.error(f"Failed to submit contribution after {max_retries} attempts")
                        return False
                    
                    # Calculate backoff time
                    wait_time = backoff_factor ** retry_count
                    self.logger.info(f"Retrying submission in {wait_time:.2f} seconds (attempt {retry_count+1}/{max_retries})")
                    time.sleep(wait_time)
                    
            except requests.exceptions.Timeout:
                retry_count += 1
                if retry_count >= max_retries:
                    self.logger.error(f"Timeout error submitting contribution after {max_retries} attempts")
                    return False
                
                # Calculate backoff time for timeout
                wait_time = backoff_factor ** retry_count
                self.logger.warning(f"Timeout submitting contribution. Retrying in {wait_time:.2f} seconds (attempt {retry_count+1}/{max_retries})")
                time.sleep(wait_time)
                
            except requests.exceptions.ConnectionError:
                retry_count += 1
                if retry_count >= max_retries:
                    self.logger.error(f"Connection error submitting contribution after {max_retries} attempts")
                    return False
                
                # Calculate backoff time for connection error
                wait_time = backoff_factor ** retry_count
                self.logger.warning(f"Connection error submitting contribution. Retrying in {wait_time:.2f} seconds (attempt {retry_count+1}/{max_retries})")
                time.sleep(wait_time)
                
            except Exception as e:
                self.logger.error(f"Error submitting contribution: {str(e)}", exc_info=True)
                
                retry_count += 1
                if retry_count >= max_retries:
                    self.logger.error(f"Failed to submit contribution after {max_retries} attempts due to errors")
                    return False
                
                # Calculate backoff time
                wait_time = backoff_factor ** retry_count
                self.logger.warning(f"Error submitting contribution. Retrying in {wait_time:.2f} seconds (attempt {retry_count+1}/{max_retries})")
                time.sleep(wait_time)
        
        # This should never be reached if max_retries > 0
        return False
    
    def _storytelling_loop(self):
        """Background thread that periodically generates and submits story contributions."""
        self.logger.info("Starting storytelling loop")
        
        while self.running:
            try:
                # Get current blockchain state once at the beginning of the cycle
                self.logger.debug("Fetching current blockchain state")
                blockchain = self._get_current_story()
                
                if not blockchain:
                    self.logger.warning("Could not retrieve blockchain state")
                    time.sleep(5)  # Brief pause before retrying
                    continue
                
                self.logger.info(f"Current blockchain has {len(blockchain)} blocks")
                
                # Attempt to generate and submit a contribution using the blockchain state
                submission_successful = False
                max_attempts = 3  # Maximum attempts per cycle
                
                for attempt in range(max_attempts):
                    if attempt > 0:
                        self.logger.info(f"Retrying with fresh blockchain state (attempt {attempt+1}/{max_attempts})")
                        # Get updated blockchain state for the retry
                        blockchain = self._get_current_story()
                        if not blockchain:
                            self.logger.warning("Failed to get updated blockchain for retry")
                            break
                        
                    # Generate a contribution based on the current blockchain state
                    # This returns a tuple of (contribution_text, previous_hash)
                    contribution_data = self._generate_contribution(blockchain)
                    contribution_text, previous_hash = contribution_data
                    
                    self.logger.info(f"Generated contribution for blockchain with latest hash: {previous_hash}")
                    
                    # Submit the contribution with its associated previous hash
                    if self._submit_contribution(contribution_data):
                        submission_successful = True
                        
                        # Wait for mining to complete or fail
                        self.logger.info("Contribution accepted. Waiting for mining to complete...")
                        original_chain_length = len(blockchain)
                        
                        mining_success = False
                        for i in range(30):  # Wait up to 60 seconds (30 * 2)
                            if not self.running:
                                self.logger.info("Storyteller stopped during mining wait")
                                break
                            
                            # Check if our contribution was added
                            time.sleep(2)
                            new_blockchain = self._get_current_story()
                            
                            if not new_blockchain:
                                self.logger.warning("Failed to get blockchain update")
                                continue
                                
                            if len(new_blockchain) > original_chain_length:
                                # New block was added
                                latest_block = new_blockchain[-1]
                                
                                if contribution_text in latest_block["data"]:
                                    self.logger.info(f"Our contribution was successfully mined in block {latest_block['index']}")
                                    mining_success = True
                                    break
                                else:
                                    self.logger.info("Someone else's contribution was mined. Will generate a new one in next cycle.")
                                    break
                        
                        if not mining_success and self.running:
                            self.logger.warning("Mining wait period expired without confirmation")
                        
                        # Break the retry loop if submission was successful
                        break
                    else:
                        # If submission failed (likely due to hash mismatch/409 error), we'll try again
                        self.logger.warning(f"Submission failed - blockchain state likely changed. Will regenerate with fresh state.")
                        time.sleep(1)  # Brief pause before retry
                
                if not submission_successful:
                    self.logger.warning(f"Failed to submit contribution after {max_attempts} attempts")
                
                # Wait for the specified interval before trying again
                wait_time = self.mine_interval
                self.logger.info(f"Waiting {wait_time} seconds before next contribution")
                
                for _ in range(wait_time):
                    if not self.running:
                        break
                    time.sleep(1)
                    
            except Exception as e:
                self.logger.error(f"Error in storytelling loop: {str(e)}", exc_info=True)
                self.logger.info("Waiting 10 seconds before retrying after error")
                time.sleep(10)  # Wait longer after an error
    
    def start(self):
        """Start the AI storyteller agent."""
        if self.story_thread and self.story_thread.is_alive():
            self.logger.warning("Storyteller is already running")
            return
        
        self.logger.info(f"Starting OpenAI Storyteller (Author {self.author_id})")
        self.running = True
        self.story_thread = threading.Thread(target=self._storytelling_loop, daemon=True)
        self.story_thread.start()
        self.logger.info("Storyteller thread started")
    
    def stop(self):
        """Stop the AI storyteller agent."""
        self.logger.info(f"Stopping OpenAI Storyteller (Author {self.author_id})")
        self.running = False
        if self.story_thread:
            self.logger.debug("Waiting for storyteller thread to join")
            self.story_thread.join(timeout=2)
            self.logger.info("Storyteller thread stopped")

def main():
    parser = argparse.ArgumentParser(description="Run an OpenAI GPT storyteller agent for the BlockBard blockchain")
    parser.add_argument("--node", default="http://localhost:5501", help="Node URL (default: http://localhost:5501)")
    parser.add_argument("--author", type=int, default=None, help="Author ID (random if not provided)")
    parser.add_argument("--interval", type=int, default=15, help="Interval between contributions in seconds (default: 15)")
    parser.add_argument("--duration", type=int, default=0, help="How long to run in seconds (0 = indefinitely, default: 0)")
    parser.add_argument("--model", default="gpt-4.1-mini-2025-04-14", help="OpenAI model to use (default: gpt-4.1-mini-2025-04-14)")
    parser.add_argument("--api-key", help="OpenAI API key (defaults to OPENAI_API_KEY environment variable)")
    parser.add_argument("--max-context", type=int, default=10000, help="Maximum number of words to keep in context (default: 10000)")
    parser.add_argument("--system-prompt", help="System prompt for defining the AI's personality and role")
    parser.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"], 
                        help="Logging level (default: INFO)")
    
    args = parser.parse_args()
    
    # Set up basic logging before we create the storyteller
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    logger = logging.getLogger("main")
    
    # Generate a random author ID if not provided
    author_id = args.author if args.author is not None else random.randint(1, 100)
    logger.info(f"Using author ID: {author_id}")
    
    try:
        # Create and start the OpenAI storyteller
        storyteller = OpenAIStoryteller(
            node_url=args.node,
            author_id=author_id,
            api_key=args.api_key,
            system_prompt=args.system_prompt,
            mine_interval=args.interval,
            model=args.model,
            max_context_words=args.max_context,
            log_level=args.log_level
        )
        
        storyteller.start()
        
        if args.duration > 0:
            logger.info(f"OpenAI Storyteller will run for {args.duration} seconds")
            time.sleep(args.duration)
            storyteller.stop()
        else:
            logger.info("OpenAI Storyteller running indefinitely. Press Ctrl+C to stop.")
            while True:
                time.sleep(1)
                
    except KeyboardInterrupt:
        logger.info("\nStopping OpenAI Storyteller")
        if 'storyteller' in locals():
            storyteller.stop()
    except Exception as e:
        logger.error(f"Error in main: {str(e)}", exc_info=True)
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(main()) 