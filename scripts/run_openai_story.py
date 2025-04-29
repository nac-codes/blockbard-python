#!/usr/bin/env python3
import os
import subprocess
import time
import signal
import argparse
import sys
import random
import requests
import json
import threading
import getpass
import re
import traceback
import hashlib

# Add the parent directory to sys.path so we can import modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.dependency_check import ensure_dependencies
from core.blockchain_storage import list_blockchain_files, load_blockchain, compare_blockchains

class OpenAICollaborativeStorySystem:
    def __init__(self, num_storytellers=3, mine_interval=5, run_duration=300, genesis_story=None):
        self.tracker_process = None
        self.node_processes = []
        self.ai_storyteller_processes = []
        self.tracker_port = 5500
        self.tracker_url = f"http://localhost:{self.tracker_port}"
        self.base_node_port = 5501
        self.num_storytellers = num_storytellers
        self.mine_interval = mine_interval
        self.run_duration = run_duration
        self.genesis_story = genesis_story
        self.api_key = None
        self.system_prompts = []
        self.process_outputs = [] # Store process objects and their names
        
    def prompt_for_api_key(self):
        """Prompt for OpenAI API key if not set as environment variable."""
        if os.environ.get("OPENAI_API_KEY"):
            print("Using OpenAI API key from environment variable.")
            self.api_key = os.environ.get("OPENAI_API_KEY")
        else:
            self.api_key = getpass.getpass("Enter your OpenAI API key: ")
            if not self.api_key:
                print("Error: OpenAI API key is required.")
                sys.exit(1)
                
    def create_system_prompts(self):
        """Create custom system prompts for each storyteller."""
        # Default prompts with different personalities
        default_prompts = [
            "You are a devout Protestant translator from the 17th century. Translate Bible verses in a traditional Protestant style, emphasizing individual faith, sola scriptura, and salvation by faith alone. Use archaic, King James-style English. Maintain reverence for God's word while staying true to Protestant theological principles. Format your contributions as JSON with Book, Chapter, Verse, Author, Node_URL, and Content fields.",
            
            "You are a strict Calvinist translator from the 17th century. Translate Bible verses with an emphasis on God's sovereignty, predestination, and the total depravity of man. Use precise, theological language that reflects the TULIP doctrines. Be scholarly but devout in your approach. Format your contributions as JSON with Book, Chapter, Verse, Author, Node_URL, and Content fields.",
            
            "You are a traditional Catholic translator from the 17th century. Translate Bible verses in accordance with Catholic doctrine, emphasizing Church tradition, sacraments, and the authority of the Magisterium. Use reverent language that honors the saints and the Virgin Mary where appropriate. Format your contributions as JSON with Book, Chapter, Verse, Author, Node_URL, and Content fields.",
            
            "You are a Bible translator in the spirit of Martin Luther. Emphasize grace, faith, and direct access to scripture. Challenge traditions that contradict scriptural authority. Use plain, forceful language that the common person can understand. Format your contributions as JSON with Book, Chapter, Verse, Author, Node_URL, and Content fields.",
            
            "You are an Eastern Orthodox translator. Translate Bible verses with emphasis on divine mysteries, liturgical worship, and theosis (deification). Use language that reflects the rich symbolism and tradition of Eastern Orthodoxy. Format your contributions as JSON with Book, Chapter, Verse, Author, Node_URL, and Content fields."
        ]
        
        # Use default prompts if we have more storytellers than prompts
        while len(default_prompts) < self.num_storytellers:
            default_prompts.append(f"You are Author {len(default_prompts) + 1}, a Bible translator with your unique perspective. Each response should be a JSON object with Book, Chapter, Verse, Author, Node_URL, and Content fields.")
        
        # Use the default prompts for each storyteller
        self.system_prompts = default_prompts[:self.num_storytellers]
        
        # Ask if user wants to customize any prompts
        print("\nDefault system prompts for each storyteller:")
        for i, prompt in enumerate(self.system_prompts):
            print(f"Storyteller {i+1}: {prompt[:60]}...")
        
        customize = input("\nWould you like to customize any of the storyteller prompts? (y/n): ").lower() == 'y'
        
        if customize:
            for i in range(self.num_storytellers):
                change = input(f"\nCustomize prompt for Storyteller {i+1}? (y/n): ").lower() == 'y'
                if change:
                    print(f"Current prompt: {self.system_prompts[i]}")
                    new_prompt = input("Enter new prompt: ")
                    if new_prompt:
                        self.system_prompts[i] = new_prompt
    
    def _extract_verse_data(self, blockchain):
        """Extract verse data from a blockchain, handling both JSON and text formats."""
        verses = []
        
        for block in blockchain.chain:
            if block.index == 0 and "Genesis Block" in block.data:
                continue  # Skip genesis block
                
            try:
                # Try to parse as JSON first
                data = json.loads(block.data) if isinstance(block.data, str) else block.data
                
                # Check if it has the expected Bible verse structure
                if all(k in data for k in ["Book", "Chapter", "Verse"]):
                    verse = {
                        "block_index": block.index,
                        "book": data["Book"],
                        "chapter": data["Chapter"],
                        "verse": data["Verse"],
                        "author": data.get("Author", "Unknown"),
                        "content": data.get("Content", ""),
                        "hash": block.hash,
                    }
                    verses.append(verse)
            except (json.JSONDecodeError, TypeError, KeyError):
                # Try to extract verse information from text format
                text = block.data
                verse_match = re.search(r'(\w+)\s+(\d+):(\d+)', text)
                
                if verse_match:
                    verse = {
                        "block_index": block.index,
                        "book": verse_match.group(1),
                        "chapter": int(verse_match.group(2)),
                        "verse": int(verse_match.group(3)),
                        "author": "Unknown",
                        "content": text,
                        "hash": block.hash,
                    }
                    verses.append(verse)
                
        return verses

    def start_tracker(self):
        """Start the tracker node."""
        print(f"Starting tracker on port {self.tracker_port}...")
        
        os.makedirs("logs", exist_ok=True)
        os.makedirs("blockchain_states", exist_ok=True)
        
        self.tracker_process = subprocess.Popen(
            [sys.executable, "main.py", "tracker", "--port", str(self.tracker_port)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=1,
            universal_newlines=False
        )
        self.process_outputs.append((self.tracker_process, "TRACKER"))
        
        # Give the tracker time to start
        time.sleep(3)
        print(f"Tracker started.")
        
    def start_blockchain_nodes(self):
        """Start the blockchain nodes for each storyteller."""
        for i in range(self.num_storytellers):
            node_port = self.base_node_port + i
            print(f"Starting storyteller node {i+1} on port {node_port}...")
            
            # Start the node with auto-mining enabled
            cmd = [
                sys.executable, "main.py", "node",
                "--port", str(node_port),
                "--tracker", self.tracker_url,
                "--auto-mine",
                "--mine-interval", str(self.mine_interval)
            ]
            
            # Add genesis story if provided and this is the first node
            if self.genesis_story and i == 0:
                cmd.extend(["--genesis", self.genesis_story])
            
            node_process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                bufsize=1,
                universal_newlines=False
            )
            
            self.node_processes.append({
                "id": i+1,
                "port": node_port,
                "process": node_process,
                "url": f"http://localhost:{node_port}"
            })
            self.process_outputs.append((node_process, f"NODE-{i+1}"))
            
            # Give each node time to start
            print(f"Giving node {i+1} time to start...")
            time.sleep(5)
            
        print(f"All {self.num_storytellers} blockchain nodes started.")
    
    def start_ai_storytellers(self):
        """Start the OpenAI storytellers, one per blockchain node."""
        for i, node in enumerate(self.node_processes):
            print(f"Starting OpenAI Storyteller {i+1} connected to node on port {node['port']}...")
            
            # Get the system prompt for this storyteller
            system_prompt = self.system_prompts[i]
            
            # Each AI gets a unique author ID matching its node ID
            cmd = [
                sys.executable, "ai_components/openai_storyteller.py",
                "--node", node["url"],
                "--author", str(node["id"]),
                "--interval", str(random.randint(15, 30)),  # Random interval for variety
                "--api-key", self.api_key,
                "--system-prompt", system_prompt,
                "--log-level", "INFO" # Can make this configurable if needed
            ]
            
            ai_process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                bufsize=1,
                universal_newlines=False
            )
            
            self.ai_storyteller_processes.append({
                "id": node["id"],
                "process": ai_process,
                "node_url": node["url"],
                "system_prompt": system_prompt
            })
            self.process_outputs.append((ai_process, f"AI-{i+1}"))
            
            # Give each AI time to start
            print(f"Giving AI {i+1} time to start...")
            time.sleep(30)
            
        print(f"All {self.num_storytellers} OpenAI storytellers started.")
    
    def start_output_logging(self):
        """Starts threads to log output from all managed processes."""
        def log_output(process, name, stream_type):
            stream = process.stdout if stream_type == "stdout" else process.stderr
            while True:
                try:
                    output = stream.readline()
                    if output:
                        print(f"[{name}][{stream_type}] {output.decode('utf-8', errors='replace').strip()}")
                    elif process.poll() is not None:
                        break # Process finished
                    time.sleep(0.1)
                except Exception as e:
                    print(f"Error reading from {name} {stream_type}: {e}")
                    break
            print(f"Log thread for {name} {stream_type} finished.")
        
        self.log_threads = []
        for process, name in self.process_outputs:
            t_out = threading.Thread(target=log_output, args=(process, name, "stdout"), daemon=True)
            t_err = threading.Thread(target=log_output, args=(process, name, "stderr"), daemon=True)
            self.log_threads.extend([t_out, t_err])
            t_out.start()
            t_err.start()
        print(f"Started {len(self.log_threads)} log monitoring threads.")
        
    def monitor_story_progress(self):
        """Monitor the story as it develops (without printing logs)."""
        print(f"\nMonitoring story progress for {self.run_duration} seconds...")
        
        start_time = time.time()
        check_interval = 20  # Status check interval in seconds
        
        while time.time() - start_time < self.run_duration:
            elapsed = int(time.time() - start_time)
            remaining = self.run_duration - elapsed
            print(f"\n--- Story Status at {elapsed}s (remaining: {remaining}s) ---")
            
            try:
                # Use the first node to get the blockchain
                if not self.node_processes:
                    print("No nodes running, cannot check status.")
                    break
                
                node = self.node_processes[0]
                response = requests.get(f"{node['url']}/get_chain", timeout=3)
                
                if response.status_code == 200:
                    blockchain = json.loads(response.text)
                    story_length = len(blockchain) - 1  # Subtract genesis block
                    
                    print(f"Current story length: {story_length} contributions")
                    
                    # Show latest additions
                    if story_length > 0:
                        recent_blocks = blockchain[-3:] if len(blockchain) > 3 else blockchain[1:]
                        print("\nLatest story contributions:")
                        for block in recent_blocks:
                            if block["index"] > 0:  # Skip genesis block
                                try:
                                    # Try to parse as JSON first
                                    verse_data = json.loads(block["data"])
                                    print(f"Block {block['index']} - {verse_data['Book']} {verse_data['Chapter']}:{verse_data['Verse']}")
                                    print(f"  Author: {verse_data.get('Author', 'Unknown')}")
                                    print(f"  Content: {verse_data.get('Content', '')[:80]}...")
                                except:
                                    # Fallback to text format
                                    print(f"Block {block['index']} (hash: {block['hash'][:8]}, nonce: {block['nonce']}):")
                                    print(f"  {block['data'][:80]}...") # Print snippet
                else:
                    print(f"Error fetching chain from node {node['id']}: {response.status_code}")
                
                # Get overall mining statistics
                if elapsed % 60 == 0:  # Every minute, show mining statistics
                    print("\nStoryteller mining statistics:")
                    author_counts = {}
                    
                    if len(blockchain) > 1:
                        for block in blockchain:
                            if block["index"] > 0:  # Skip genesis block
                                try:
                                    # Try to parse as JSON to get the author
                                    verse_data = json.loads(block["data"])
                                    author = verse_data.get("Author", "Unknown")
                                except:
                                    # Fallback to text parsing
                                    author = "Unknown"
                                    if "Author" in block["data"] and "says:" in block["data"]:
                                        author_part = block["data"].split("says:")[0]
                                        author = author_part.strip()
                                
                                if author in author_counts:
                                    author_counts[author] += 1
                                else:
                                    author_counts[author] = 1
                        
                        for author, count in author_counts.items():
                            print(f"  {author}: {count} contributions")
            
            except Exception as e:
                print(f"Error monitoring story: {e}")
            
            # Check if any process has terminated
            active_processes = sum(1 for p, _ in self.process_outputs if p.poll() is None)
            if active_processes < len(self.process_outputs):
                print("Warning: One or more processes have terminated.")
                # Consider stopping if critical process (like tracker) dies
                if self.tracker_process and self.tracker_process.poll() is not None:
                    print("Tracker process terminated. Shutting down.")
                    break
            
            # Sleep until next check if we're not done yet
            if time.time() - start_time < self.run_duration:
                sleep_time = min(check_interval, remaining)
                time.sleep(sleep_time)
    
    def verify_consistency_with_blockchain_storage(self):
        """
        Verify that all nodes have consistent blockchain state and check for verse overlaps.
        
        Returns:
            tuple: (is_consistent, verse_overlaps, node_verse_data) where:
                - is_consistent (bool): True if all nodes have identical blockchain state
                - verse_overlaps (list): List of verse overlaps found (if any)
                - node_verse_data (dict): Dictionary mapping node IDs to their verse data
        """
        self.logger.info("Verifying consistency with blockchain storage")
        
        # Dictionary to store blockchain data for each node
        node_blockchain_data = {}
        # Dictionary to store verse data for each node
        node_verse_data = {}
        
        # For each node, read its blockchain file
        for node_id in self.node_ports:
            blockchain_file = os.path.join(self.blockchain_dir, f"{node_id}_blockchain.json")
            
            try:
                # Read the blockchain file for this node
                if not os.path.exists(blockchain_file):
                    self.logger.warning(f"Blockchain file not found for node {node_id}: {blockchain_file}")
                    continue
                    
                with open(blockchain_file, 'r') as f:
                    blockchain_data = json.load(f)
                
                # Store the entire blockchain data
                node_blockchain_data[node_id] = blockchain_data
                
                # Extract verse data from the blockchain
                verses = self._extract_verse_data_from_json(blockchain_data)
                node_verse_data[node_id] = verses
                
                self.logger.info(f"Node {node_id}: Read {len(verses)} verses from blockchain")
                
            except Exception as e:
                self.logger.error(f"Error reading blockchain for node {node_id}: {e}")
        
        # Check if all blockchains are identical by comparing their hash
        blockchain_hashes = {}
        for node_id, data in node_blockchain_data.items():
            # Convert to string and hash to compare
            data_str = json.dumps(data, sort_keys=True)
            blockchain_hash = hashlib.sha256(data_str.encode()).hexdigest()
            blockchain_hashes[node_id] = blockchain_hash
        
        # Check if all hashes are the same
        is_consistent = len(set(blockchain_hashes.values())) <= 1
        
        if is_consistent:
            self.logger.info("All blockchains are consistent across nodes")
        else:
            self.logger.warning("Blockchain inconsistency detected between nodes")
            for node_id, hash_val in blockchain_hashes.items():
                self.logger.debug(f"Node {node_id} blockchain hash: {hash_val}")
        
        # Check for verse overlaps
        verse_overlaps = self._check_for_verse_overlaps(node_verse_data)
        
        if verse_overlaps:
            self.logger.warning(f"Found {len(verse_overlaps)} verse overlaps")
        else:
            self.logger.info("No verse overlaps found")
            
        return is_consistent, verse_overlaps, node_verse_data
    
    def _check_for_verse_overlaps(self, node_verse_data):
        """
        Check for verse overlaps between nodes, where multiple nodes have translated
        the same verse location but with different translations.
        
        Args:
            node_verse_data (dict): Dictionary mapping node IDs to their verse data
            
        Returns:
            list: List of overlap details, each containing:
                - location: The verse location (book, chapter, verse)
                - nodes: List of nodes that have this verse
                - translations: Dictionary mapping node IDs to their translations
        """
        if not node_verse_data:
            return []
            
        # Organize verses by location for quick lookup
        verses_by_location = {}
        
        # Process each node's verses
        for node_id, verses in node_verse_data.items():
            for verse in verses:
                # Extract location details
                if not all(k in verse for k in ["book", "chapter", "verse"]):
                    self.logger.warning(f"Verse missing location data: {verse}")
                    continue
                    
                location = (verse.get("book"), verse.get("chapter"), verse.get("verse"))
                
                # Initialize the location entry if it doesn't exist
                if location not in verses_by_location:
                    verses_by_location[location] = {"nodes": [], "translations": {}}
                
                # Add this node to the list of nodes with this verse
                verses_by_location[location]["nodes"].append(node_id)
                
                # Store this node's translation for this verse
                translation = verse.get("translation", "")
                verses_by_location[location]["translations"][node_id] = translation
        
        # Find locations where multiple nodes have translated the same verse
        overlaps = []
        
        for location, data in verses_by_location.items():
            # Only consider it an overlap if more than one node has translated this verse
            # AND there are different translations (if all translations are identical, it's not an issue)
            if len(data["nodes"]) > 1 and len(set(data["translations"].values())) > 1:
                book, chapter, verse = location
                
                overlap_details = {
                    "location": {
                        "book": book,
                        "chapter": chapter,
                        "verse": verse
                    },
                    "nodes": data["nodes"],
                    "translations": data["translations"]
                }
                
                overlaps.append(overlap_details)
        
        return overlaps
            
    def _extract_verse_data_from_json(self, json_data):
        """
        Extract verse data from blockchain JSON data.
        
        Args:
            json_data (dict): Loaded JSON data from blockchain file
            
        Returns:
            list: List of dictionaries containing verse data
        """
        verses = []
        try:
            # Extract chain from JSON
            chain = json_data.get("chain", [])
            
            for block in chain:
                # Skip genesis block or blocks without valid transaction data
                if not block or "data" not in block or not block["data"]:
                    continue
                
                # Process only valid verse transactions
                transaction = block["data"]
                if "type" in transaction and transaction["type"] == "verse":
                    # Extract verse data
                    if all(k in transaction for k in ["book", "chapter", "verse", "content", "author"]):
                        verses.append({
                            "book": transaction["book"],
                            "chapter": transaction["chapter"],
                            "verse": transaction["verse"],
                            "content": transaction["content"],
                            "author": transaction["author"]
                        })
                    else:
                        self.logger.warning(f"Skipping transaction with missing fields: {transaction}")
                        
        except Exception as e:
            self.logger.error(f"Error extracting verse data: {e}")
            
        return verses
    
    def print_final_story(self):
        """
        Print the final story and perform quality assurance checks.
        
        This method verifies:
        1. Blockchain consistency across nodes
        2. Story completeness (no missing verses or translations)
        3. Verse numbering integrity (no gaps in verse numbers)
        4. Translation quality (no empty translations)
        5. No overlapping verse contributions
        """
        self.logger.info("=" * 80)
        self.logger.info("FINAL STORY AND QUALITY ASSURANCE REPORT")
        self.logger.info("=" * 80)
        
        # Load the most recent story
        story = self.load_most_recent_story()
        if not story:
            self.logger.error("Failed to load the final story for QA checks")
            return
            
        # Print the story title and content
        self.logger.info(f"Title: {story['title']}")
        self.logger.info("-" * 80)
        
        if not story['verses']:
            self.logger.warning("Story has no verses!")
            return
            
        # Print each verse with its location and translation
        for verse in sorted(story['verses'], key=lambda v: (v['book'], v['chapter'], v['verse'])):
            verse_loc = f"[{verse['book']}:{verse['chapter']}:{verse['verse']}]"
            self.logger.info(f"{verse_loc} {verse['translation']}")
            
            # Check for empty translations
            if not verse['translation'] or verse['translation'].strip() == "":
                self.logger.error(f"QUALITY ISSUE: {verse_loc} has an empty translation")
                
        self.logger.info("-" * 80)
        
        # Perform blockchain consistency check
        self.logger.info("CHECKING BLOCKCHAIN CONSISTENCY...")
        is_consistent = self.verify_blockchain_consistency()
        if is_consistent:
            self.logger.info("✓ All nodes have consistent blockchains")
        else:
            self.logger.error("✗ Nodes have inconsistent blockchains - story may be incomplete or corrupted")
            
        # Check for verse overlaps
        self.logger.info("CHECKING FOR VERSE OVERLAPS...")
        overlaps = self.check_for_verse_overlaps()
        if overlaps:
            self.logger.error("✗ Found overlapping verse contributions:")
            for overlap in overlaps:
                self.logger.error(f"  - Verse {overlap['verse_loc']} has {overlap['count']} overlapping contributions")
        else:
            self.logger.info("✓ No verse overlaps detected")
            
        # Check story completeness
        self.logger.info("CHECKING STORY COMPLETENESS...")
        self.check_story_completeness(story)
        
        self.logger.info("=" * 80)
        
    def verify_blockchain_consistency(self):
        """
        Verify that all nodes have consistent blockchains.
        
        Returns:
            bool: True if consistent, False if inconsistent
        """
        try:
            # Get node ports from tracker
            node_ports = self._fetch_node_ports_from_tracker()
            if not node_ports:
                self.logger.error("No nodes available to check blockchain consistency")
                return False
                
            node_chains = {}
            
            # Fetch blockchain from each node
            for port in node_ports:
                try:
                    node_url = f"http://localhost:{port}"
                    chain_response = requests.get(f"{node_url}/chain", timeout=5)
                    
                    if chain_response.status_code == 200:
                        node_chains[port] = chain_response.json().get("chain", [])
                    else:
                        self.logger.warning(f"Failed to get chain from node {port}: HTTP {chain_response.status_code}")
                        
                except Exception as e:
                    self.logger.warning(f"Error fetching chain from node {port}: {e}")
                    
            if not node_chains:
                self.logger.error("Failed to fetch chains from any node")
                return False
                
            # Check if all chains have the same length and hash
            chain_lengths = {port: len(chain) for port, chain in node_chains.items()}
            unique_lengths = set(chain_lengths.values())
            
            if len(unique_lengths) > 1:
                self.logger.warning("Nodes have chains of different lengths:")
                for port, length in chain_lengths.items():
                    self.logger.warning(f"  - Node {port}: {length} blocks")
                return False
                
            # Compare chain hashes (compare the last block hash as a simple check)
            if len(node_chains) > 1:
                reference_port = list(node_chains.keys())[0]
                reference_chain = node_chains[reference_port]
                
                if not reference_chain:
                    self.logger.warning("Reference chain is empty")
                    return False
                    
                reference_last_hash = reference_chain[-1].get("hash", "")
                
                for port, chain in node_chains.items():
                    if port == reference_port:
                        continue
                        
                    if not chain:
                        self.logger.warning(f"Chain from node {port} is empty")
                        return False
                        
                    last_hash = chain[-1].get("hash", "")
                    
                    if last_hash != reference_last_hash:
                        self.logger.warning(f"Node {port} has different last block hash than reference node {reference_port}")
                        return False
                        
            return True
            
        except Exception as e:
            self.logger.error(f"Error verifying blockchain consistency: {e}")
            traceback.print_exc()
            return False
            
    def check_for_verse_overlaps(self):
        """
        Check if multiple blocks contain contributions for the same verse.
        
        Returns:
            list: List of overlapping verse information
        """
        try:
            # Get node ports
            node_ports = self._fetch_node_ports_from_tracker()
            if not node_ports:
                self.logger.error("No nodes available to check for verse overlaps")
                return []
                
            # Use the first available node to get the chain
            for port in node_ports:
                try:
                    node_url = f"http://localhost:{port}"
                    chain_response = requests.get(f"{node_url}/chain", timeout=5)
                    
                    if chain_response.status_code != 200:
                        continue
                        
                    chain = chain_response.json().get("chain", [])
                    
                    # Find all story blocks and extract verse locations
                    verse_locations = {}
                    
                    for block in chain:
                        block_data = block.get("data", {})
                        if block_data.get("type") != "story":
                            continue
                            
                        content = block_data.get("content", "")
                        if not content:
                            continue
                            
                        # Extract verse locations from content
                        for line in content.split("\n"):
                            verse_match = re.search(r'\[(\d+):(\d+):(\d+)\]', line)
                            if verse_match:
                                verse_loc = verse_match.group(0)
                                verse_locations[verse_loc] = verse_locations.get(verse_loc, 0) + 1
                                
                    # Find overlaps (verse locations that appear more than once)
                    overlaps = [
                        {"verse_loc": loc, "count": count}
                        for loc, count in verse_locations.items()
                        if count > 1
                    ]
                    
                    return overlaps
                    
                except Exception as e:
                    self.logger.warning(f"Error checking for verse overlaps from node {port}: {e}")
                    continue
                    
            self.logger.error("Failed to check for verse overlaps from any node")
            return []
            
        except Exception as e:
            self.logger.error(f"Error checking for verse overlaps: {e}")
            traceback.print_exc()
            return []
            
    def check_story_completeness(self, story):
        """
        Check if the story is complete with no missing verses or translations.
        
        Args:
            story (dict): The story with title and verses
        """
        if not story['verses']:
            self.logger.error("✗ Story has no verses!")
            return
            
        # Sort verses by book, chapter, verse
        sorted_verses = sorted(story['verses'], key=lambda v: (v['book'], v['chapter'], v['verse']))
        
        # Check for empty translations
        empty_translations = [
            f"[{v['book']}:{v['chapter']}:{v['verse']}]"
            for v in sorted_verses
            if not v['translation'] or v['translation'].strip() == ""
        ]
        
        if empty_translations:
            self.logger.error(f"✗ Found {len(empty_translations)} verses with empty translations:")
            for verse_loc in empty_translations[:5]:  # Show first 5 to avoid overwhelming output
                self.logger.error(f"  - {verse_loc}")
            if len(empty_translations) > 5:
                self.logger.error(f"  - ... and {len(empty_translations) - 5} more")
        else:
            self.logger.info("✓ All verses have non-empty translations")
            
        # Check for gaps in verse numbering
        previous_verse = None
        gaps = []
        
        for verse in sorted_verses:
            current_loc = (verse['book'], verse['chapter'], verse['verse'])
            
            if previous_verse:
                prev_book, prev_chapter, prev_verse_num = previous_verse
                
                # If we're in the same book and chapter, check for verse gaps
                if current_loc[0] == prev_book and current_loc[1] == prev_chapter:
                    expected_verse = prev_verse_num + 1
                    if current_loc[2] != expected_verse:
                        gaps.append((prev_book, prev_chapter, prev_verse_num, current_loc[2]))
                        
            previous_verse = current_loc
            
        if gaps:
            self.logger.error(f"✗ Found {len(gaps)} gaps in verse numbering:")
            for gap in gaps[:5]:  # Show first 5
                book, chapter, from_verse, to_verse = gap
                self.logger.error(f"  - Gap between [{book}:{chapter}:{from_verse}] and [{book}:{chapter}:{to_verse}]")
            if len(gaps) > 5:
                self.logger.error(f"  - ... and {len(gaps) - 5} more")
        else:
            self.logger.info("✓ No gaps detected in verse numbering")
            
        # Calculate overall completeness
        total_checks = 2  # Translation presence and verse continuity
        passed_checks = 2
        
        if empty_translations:
            passed_checks -= 1
        if gaps:
            passed_checks -= 1
            
        completeness_pct = (passed_checks / total_checks) * 100
        self.logger.info(f"Story completeness: {completeness_pct:.1f}%")
    
    def verify_consistency(self):
        """Verify that all nodes have a consistent view of the story."""
        print("\nVerifying story consistency across all nodes...")
        
        chains = {}
        for node_data in self.node_processes:
            node_id = node_data["id"]
            # Check if process is still running
            if node_data['process'].poll() is not None:
                print(f"Node {node_id} process is not running. Skipping consistency check for this node.")
                continue
                
            try:
                response = requests.get(f"{node_data['url']}/get_chain", timeout=3)
                if response.status_code == 200:
                    chains[node_id] = response.text
                else:
                    print(f"Error getting chain from node {node_id}: {response.status_code}")
            except Exception as e:
                print(f"Error connecting to node {node_id}: {e}")
        
        if not chains or len(chains) < 2:
            print("Not enough active nodes to verify consistency.")
            return len(chains) > 0 # Consider consistent if only one node remains
        
        # Compare all chains to the first one
        reference_node_id = next(iter(chains.keys()))
        reference_chain = chains[reference_node_id]
        consistent = True
        
        for node_id, chain_text in chains.items():
            if node_id == reference_node_id:
                continue
                
            if chain_text != reference_chain:
                print(f"⚠️ Inconsistency detected! Node {reference_node_id} and Node {node_id} have different versions of the story.")
                consistent = False
        
        if consistent:
            print("✅ All active nodes have a consistent view of the story!")
        
        return consistent
    
    def cleanup(self):
        """Clean up all processes."""
        print("\nShutting down the collaborative story system...")
        
        # Reverse order: AI -> Nodes -> Tracker
        processes_to_stop = self.process_outputs[::-1]
        
        for process, name in processes_to_stop:
            if process and process.poll() is None:
                print(f"Stopping {name} (PID: {process.pid})...")
                try:
                    process.terminate()
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    print(f"Process {name} did not terminate gracefully, killing...")
                    process.kill()
                except Exception as e:
                    print(f"Error stopping {name}: {e}")
        
        print("All processes stopped.")
    
    def run(self):
        """Run the complete collaborative storytelling system."""
        try:
            print("=== Starting BlockBard OpenAI Collaborative Storytelling System ===")
            
            # Get API key
            self.prompt_for_api_key()
            
            # Setup system prompts
            self.create_system_prompts()
            
            # Get genesis story
            if not self.genesis_story:
                use_custom_genesis = input("\nWould you like to start with a custom genesis story? (y/n): ").lower() == 'y'
                if use_custom_genesis:
                    self.genesis_story = input("Enter your genesis story: ")
                    if not self.genesis_story:
                        genesis_json = {
                            "Book": "Genesis",
                            "Chapter": 1,
                            "Verse": 1,
                            "Author": "Genesis",
                            "Node_URL": "genesis",
                            "Content": "In the beginning God created the heaven and the earth."
                        }
                        self.genesis_story = json.dumps(genesis_json)
            
            # Start components
            self.start_tracker()
            self.start_blockchain_nodes()
            
            # Give nodes time to connect and synchronize
            print("Allowing nodes time to connect and synchronize...")
            time.sleep(5)
            
            # Start AI storytellers
            self.start_ai_storytellers()
            
            # Start logging process outputs
            self.start_output_logging()
            
            # Monitor the story development
            self.monitor_story_progress()
            
            # Print the final story with quality assurance
            self.print_final_story()
            
            # Verify consistency across nodes using blockchain_storage
            consistency_result, _, _ = self.verify_consistency_with_blockchain_storage()
            return consistency_result
            
        except KeyboardInterrupt:
            print("\nCollaborative storytelling system interrupted by user.")
            return False
        finally:
            self.cleanup()

    def load_most_recent_story(self):
        """
        Load the most recent story from the blockchain.
        
        Returns:
            dict: The story with title and verses, or None if failed
        """
        try:
            # Try to get the story from the storyteller first
            self.logger.info("Attempting to load the most recent story from the storyteller")
            story = self.storyteller.get_current_story()
            
            if story:
                # Parse the story into structured format
                return self._parse_story(story)
                
            # If storyteller method failed, try to get directly from a node's blockchain
            # Get node ports
            self.logger.info("Attempting to load the story directly from nodes")
            node_ports = self._fetch_node_ports_from_tracker()
            
            if not node_ports:
                self.logger.error("No nodes found via the tracker")
                return None
                
            # Try to get the story from each node until successful
            for port in node_ports:
                try:
                    node_url = f"http://localhost:{port}"
                    chain_response = requests.get(f"{node_url}/chain", timeout=5)
                    
                    if chain_response.status_code == 200:
                        chain_data = chain_response.json()
                        # Extract story blocks from the chain
                        story_blocks = [
                            block.get("data", {})
                            for block in chain_data.get("chain", [])
                            if block.get("data", {}).get("type") == "story"
                        ]
                        
                        if story_blocks:
                            # Get the most recent story block
                            latest_story = story_blocks[-1]
                            return self._parse_story(latest_story.get("content", ""))
                
                except Exception as e:
                    self.logger.warning(f"Failed to get story from node at port {port}: {e}")
                    continue
                    
            self.logger.error("Failed to load story from any node")
            return None
                
        except Exception as e:
            self.logger.error(f"Error loading story: {e}")
            traceback.print_exc()
            return None
            
    def _parse_story(self, story_content):
        """
        Parse a story string into a structured format.
        
        Args:
            story_content (str): The raw story content
            
        Returns:
            dict: A structured story with title and verses
        """
        if not story_content or not isinstance(story_content, str):
            return {"title": "Untitled", "verses": []}
            
        # Extract title and verses
        lines = story_content.strip().split("\n")
        
        # First non-empty line is the title
        title = "Untitled"
        verses = []
        
        for i, line in enumerate(lines):
            line = line.strip()
            if not line:
                continue
                
            if i == 0:
                title = line
                continue
                
            # Try to parse verse location and content
            verse_match = re.search(r'\[(\d+):(\d+):(\d+)\] (.*)', line)
            if verse_match:
                book, chapter, verse, translation = verse_match.groups()
                verses.append({
                    "book": int(book),
                    "chapter": int(chapter),
                    "verse": int(verse),
                    "translation": translation
                })
            else:
                # If it doesn't match the format, just add as a verse with unknown location
                verses.append({
                    "book": 0,
                    "chapter": 0,
                    "verse": len(verses) + 1,
                    "translation": line
                })
                
        return {"title": title, "verses": verses}
        
    def _fetch_node_ports_from_tracker(self):
        """
        Fetch the list of active node ports from the tracker.
        
        Returns:
            list: List of port numbers or empty list if failed
        """
        try:
            tracker_url = f"http://localhost:{self.tracker_port}"
            nodes_response = requests.get(f"{tracker_url}/nodes", timeout=5)
            
            if nodes_response.status_code == 200:
                nodes_data = nodes_response.json()
                return [node.get("port") for node in nodes_data.get("nodes", [])]
            else:
                self.logger.error(f"Failed to fetch nodes from tracker: {nodes_response.status_code}")
                return []
                
        except Exception as e:
            self.logger.error(f"Error fetching nodes from tracker: {e}")
            return []

def main():
    # Ensure dependencies are installed first
    ensure_dependencies()
    
    parser = argparse.ArgumentParser(description="Run the BlockBard OpenAI collaborative storytelling system")
    parser.add_argument("--storytellers", type=int, default=3, help="Number of storytellers (default: 3)")
    parser.add_argument("--interval", type=int, default=45, help="Mining interval in seconds (default: 45)")
    parser.add_argument("--duration", type=int, default=600, help="Duration in seconds (default: 600)")
    parser.add_argument("--genesis", help="Custom genesis story to start with")
    
    args = parser.parse_args()
    
    system = OpenAICollaborativeStorySystem(
        num_storytellers=args.storytellers,
        mine_interval=args.interval,
        run_duration=args.duration,
        genesis_story=args.genesis
    )
    
    success = system.run()
    
    if success:
        print("\n🎉 Collaborative storytelling finished successfully! The story is complete and consistent.")
        return 0
    else:
        print("\n⚠️ There were issues with the collaborative storytelling system.")
        return 1

if __name__ == "__main__":
    sys.exit(main()) 