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

# Add the parent directory to sys.path so we can import modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

class CollaborativeStorySystem:
    def __init__(self, num_storytellers=3, mine_interval=5, run_duration=300):
        self.tracker_process = None
        self.node_processes = []
        self.ai_storyteller_processes = []
        self.tracker_port = 5500
        self.tracker_url = f"http://localhost:{self.tracker_port}"
        self.base_node_port = 5501
        self.num_storytellers = num_storytellers
        self.mine_interval = mine_interval
        self.run_duration = run_duration
        
    def start_tracker(self):
        """Start the tracker node."""
        print(f"Starting tracker on port {self.tracker_port}...")
        
        os.makedirs("logs", exist_ok=True)
        os.makedirs("blockchain_states", exist_ok=True)
        
        self.tracker_process = subprocess.Popen(
            ["python", "main.py", "tracker", "--port", str(self.tracker_port)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        
        # Give the tracker time to start
        time.sleep(3)
        print(f"Tracker started.")
        
    def start_blockchain_nodes(self):
        """Start the blockchain nodes for each storyteller."""
        for i in range(self.num_storytellers):
            node_port = self.base_node_port + i
            print(f"Starting storyteller node {i+1} on port {node_port}...")
            
            # Start the node with auto-mining enabled
            node_process = subprocess.Popen(
                [
                    "python", "main.py", "node",
                    "--port", str(node_port),
                    "--tracker", self.tracker_url,
                    "--auto-mine",
                    "--mine-interval", str(self.mine_interval)
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            
            self.node_processes.append({
                "id": i+1,
                "port": node_port,
                "process": node_process,
                "url": f"http://localhost:{node_port}"
            })
            
            # Give each node time to start
            time.sleep(2)
            
        print(f"All {self.num_storytellers} blockchain nodes started.")
    
    def start_ai_storytellers(self):
        """Start the AI storytellers, one per blockchain node."""
        for i, node in enumerate(self.node_processes):
            print(f"Starting AI Storyteller {i+1} connected to node on port {node['port']}...")
            
            # Each AI gets a unique author ID matching its node ID
            ai_process = subprocess.Popen(
                [
                    "python", "ai_components/ai_storyteller.py",
                    "--node", node["url"],
                    "--author", str(node["id"]),
                    "--interval", str(random.randint(10, 30))  # Random interval for variety
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            
            self.ai_storyteller_processes.append({
                "id": node["id"],
                "process": ai_process,
                "node_url": node["url"]
            })
            
            # Give each AI time to start
            time.sleep(1)
            
        print(f"All {self.num_storytellers} AI storytellers started.")
    
    def monitor_story_progress(self):
        """Monitor the story as it develops."""
        print(f"\nMonitoring story progress for {self.run_duration} seconds...")
        
        start_time = time.time()
        check_interval = 20  # Status check interval in seconds
        
        while time.time() - start_time < self.run_duration:
            elapsed = int(time.time() - start_time)
            remaining = self.run_duration - elapsed
            print(f"\n--- Story Status at {elapsed}s (remaining: {remaining}s) ---")
            
            try:
                # Use the first node to get the blockchain
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
                                print(f"  {block['data']}")
                
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
            
            # Sleep until next check if we're not done yet
            if time.time() - start_time < self.run_duration:
                sleep_time = min(check_interval, remaining)
                time.sleep(sleep_time)
    
    def print_final_story(self):
        """Print the complete story at the end."""
        print("\n\n====== THE COLLABORATIVE STORY ======\n")
        
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
        for node in self.node_processes:
            node_id = node["id"]
            try:
                response = requests.get(f"{node['url']}/get_chain", timeout=3)
                if response.status_code == 200:
                    chains[node_id] = response.text
                else:
                    print(f"Error getting chain from node {node_id}: {response.status_code}")
            except Exception as e:
                print(f"Error connecting to node {node_id}: {e}")
        
        if not chains:
            print("No chains retrieved. Can't verify consistency.")
            return False
        
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
            print("✅ All nodes have a consistent view of the story!")
        
        return consistent
    
    def cleanup(self):
        """Clean up all processes."""
        print("\nShutting down the collaborative story system...")
        
        # First stop AI storytellers
        for ai in self.ai_storyteller_processes:
            print(f"Stopping AI Storyteller {ai['id']}...")
            try:
                ai["process"].terminate()
                ai["process"].wait(timeout=2)
            except:
                ai["process"].kill()
        
        # Then stop blockchain nodes
        for node in self.node_processes:
            print(f"Stopping blockchain node {node['id']}...")
            try:
                node["process"].terminate()
                node["process"].wait(timeout=2)
            except:
                node["process"].kill()
        
        # Finally stop the tracker
        if self.tracker_process:
            print("Stopping tracker...")
            try:
                self.tracker_process.terminate()
                self.tracker_process.wait(timeout=2)
            except:
                self.tracker_process.kill()
        
        print("All processes stopped.")
    
    def run(self):
        """Run the complete collaborative storytelling system."""
        try:
            print("=== Starting BlockBard Collaborative Storytelling System ===")
            
            # Start components
            self.start_tracker()
            self.start_blockchain_nodes()
            
            # Give nodes time to connect and synchronize
            print("Allowing nodes time to connect and synchronize...")
            time.sleep(5)
            
            # Start AI storytellers
            self.start_ai_storytellers()
            
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
    parser = argparse.ArgumentParser(description="Run the BlockBard collaborative storytelling system")
    parser.add_argument("--storytellers", type=int, default=3, help="Number of storytellers (default: 3)")
    parser.add_argument("--interval", type=int, default=5, help="Mining interval in seconds (default: 5)")
    parser.add_argument("--duration", type=int, default=300, help="Duration in seconds (default: 300)")
    
    args = parser.parse_args()
    
    system = CollaborativeStorySystem(
        num_storytellers=args.storytellers,
        mine_interval=args.interval,
        run_duration=args.duration
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