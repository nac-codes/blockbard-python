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

# Add the parent directory to sys.path so we can import modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.dependency_check import ensure_dependencies

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
            "You are a devout Protestant translator from the 17th century. Translate Bible verses in a traditional Protestant style, emphasizing individual faith, sola scriptura, and salvation by faith alone. Use archaic, King James-style English. Maintain reverence for God's word while staying true to Protestant theological principles. Format your contributions as 'Protestant Translation: [your translation]'.",
            
            "You are a strict Calvinist translator from the 17th century. Translate Bible verses with an emphasis on God's sovereignty, predestination, and the total depravity of man. Use precise, theological language that reflects the TULIP doctrines. Be scholarly but devout in your approach. Format your contributions as 'Calvinist Translation: [your translation]'.",
            
            "You are a traditional Catholic translator from the 17th century. Translate Bible verses in accordance with Catholic doctrine, emphasizing Church tradition, sacraments, and the authority of the Magisterium. Use reverent language that honors the saints and the Virgin Mary where appropriate. Format your contributions as 'Catholic Translation: [your translation]'.",
            
            "You are a Bible translator in the spirit of Martin Luther. Emphasize grace, faith, and direct access to scripture. Challenge traditions that contradict scriptural authority. Use plain, forceful language that the common person can understand. Format your contributions as 'Lutheran Translation: [your translation]'.",
            
            "You are an Eastern Orthodox translator. Translate Bible verses with emphasis on divine mysteries, liturgical worship, and theosis (deification). Use language that reflects the rich symbolism and tradition of Eastern Orthodoxy. Format your contributions as 'Orthodox Translation: [your translation]'."
        ]
        
        # Use default prompts if we have more storytellers than prompts
        while len(default_prompts) < self.num_storytellers:
            default_prompts.append(f"You are Author {len(default_prompts) + 1}, a creative storyteller. Add compelling and contextually relevant contributions to move the story forward in interesting ways.")
        
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
            time.sleep(2)
            
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
            time.sleep(1)
            
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
                                print(f"Chapter {block['index']} (hash: {block['hash'][:8]}, nonce: {block['nonce']}):")
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
    
    def print_final_story(self):
        """Print the complete story at the end."""
        print("\n\n====== THE COLLABORATIVE STORY ======\n")
        
        if not self.node_processes:
            print("No nodes available to fetch the story.")
            return
            
        try:
            # Use the first node to get the final blockchain
            node = self.node_processes[0]
            response = requests.get(f"{node['url']}/get_chain", timeout=3)
            
            if response.status_code == 200:
                blockchain = json.loads(response.text)
                
                # Skip genesis block
                story_blocks = [block for block in blockchain if block["index"] > 0]
                
                if not story_blocks:
                    print("No story has been created yet.")
                    return
                
                # Print the full story
                # Include genesis block if custom
                if self.genesis_story:
                    print("Genesis:")
                    print(f"{blockchain[0]['data']}")
                    print()
                
                for block in story_blocks:
                    print(f"Chapter {block['index']}:")
                    print(f"{block['data']}")
                    print()  # Empty line between chapters
                
                # Print statistics
                author_counts = {}
                for block in story_blocks:
                    author = "Unknown"
                    if "Author" in block["data"] and "says:" in block["data"]:
                        author_part = block["data"].split("says:")[0]
                        author = author_part.strip()
                    
                    if author in author_counts:
                        author_counts[author] += 1
                    else:
                        author_counts[author] = 1
                
                print("\n--- Story Statistics ---")
                print(f"Total chapters: {len(story_blocks)}")
                print("Contributions by author:")
                for author, count in author_counts.items():
                    percentage = (count / len(story_blocks)) * 100
                    print(f"  {author}: {count} chapters ({percentage:.1f}%)")
                
            else:
                print(f"Failed to get the story: {response.status_code}")
        
        except Exception as e:
            print(f"Error printing final story: {e}")
    
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
                        self.genesis_story = "Once upon a time in a world where technology and magic intertwined..."
            
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
            
            # Print the final story
            self.print_final_story()
            
            # Verify consistency across nodes
            return self.verify_consistency()
            
        except KeyboardInterrupt:
            print("\nCollaborative storytelling system interrupted by user.")
            return False
        finally:
            self.cleanup()

def main():
    # Ensure dependencies are installed first
    ensure_dependencies()
    
    parser = argparse.ArgumentParser(description="Run the BlockBard OpenAI collaborative storytelling system")
    parser.add_argument("--storytellers", type=int, default=3, help="Number of storytellers (default: 3)")
    parser.add_argument("--interval", type=int, default=5, help="Mining interval in seconds (default: 5)")
    parser.add_argument("--duration", type=int, default=300, help="Duration in seconds (default: 300)")
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