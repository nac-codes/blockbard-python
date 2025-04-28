#!/usr/bin/env python3
import os
import subprocess
import time
import signal
import argparse
import sys
import requests
import json
import random

class StorytellingBlockchainTest:
    def __init__(self, num_nodes=3, mine_interval=5, run_duration=120):
        self.tracker_process = None
        self.node_processes = []
        self.tracker_port = 5500
        self.tracker_url = f"http://localhost:{self.tracker_port}"
        self.base_node_port = 5501
        self.num_nodes = num_nodes
        self.mine_interval = mine_interval
        self.run_duration = run_duration
        self.story_contributions = [
            "Once upon a time in a digital realm, a group of AI storytellers gathered...",
            "The first AI, a specialist in fantasy, imagined a world of floating islands...",
            "Another AI, with expertise in mystery, added an enigmatic character to the scene...",
            "A third AI, focused on action, introduced a sudden storm that threatened the islands...",
            "The fourth AI, versed in romance, described two characters meeting amid the chaos...",
            "A fifth AI, knowledgeable in science fiction, explained the technology keeping the islands aloft...",
            "The fantasy-loving AI returned to describe magical creatures living beneath the islands...",
            "The mystery expert AI revealed clues about a hidden treasure somewhere in the realm...",
            "The action-oriented AI described a daring escape from a collapsing island structure...",
            "The romantic AI told of sacrifices made to save loved ones during the adventure...",
            "The sci-fi specialist AI introduced an ancient AI guardian protecting the realm...",
            "All the AIs collaborated on the climax, where the characters discovered the true nature of their world...",
            "The story concluded with a new beginning, as the characters decided to explore beyond their known universe..."
        ]
        
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
        
    def start_storyteller_nodes(self):
        """Start the storyteller nodes."""
        for i in range(self.num_nodes):
            node_port = self.base_node_port + i
            print(f"Starting storyteller {i+1} on port {node_port}...")
            
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
            
        print(f"All {self.num_nodes} storyteller nodes started.")

    def add_story_contributions(self, count=3):
        """Add story contributions to random nodes."""
        print(f"\nAdding {count} story contributions to the network...")
        
        for i in range(count):
            # Pick a random node
            node = random.choice(self.node_processes)
            node_url = node["url"]
            node_id = node["id"]
            
            # Generate a story contribution - either select from predefined list or generate random
            if i < len(self.story_contributions):
                contribution = self.story_contributions[i]
            else:
                contribution = f"Author {node_id} (Node {node_id}) contributes: " + \
                               f"{''.join(random.choice('abcdefghijklmnopqrstuvwxyz ') for _ in range(50))}"
            
            story_data = f"Author {node_id} (Node {node_id}) says: {contribution}"
            
            try:
                response = requests.post(
                    f"{node_url}/add_transaction",  # Keep endpoint name for compatibility
                    json={"data": story_data},
                    timeout=2
                )
                
                if response.status_code == 201:
                    print(f"Added story contribution from Author {node_id}: {story_data[:50]}...")
                else:
                    print(f"Failed to add contribution from Author {node_id}: {response.status_code}")
            except Exception as e:
                print(f"Error adding contribution from Author {node_id}: {e}")
            
            # Slightly longer delay between contributions to allow mining
            time.sleep(2)

    def monitor_story_blockchain(self, duration):
        """Monitor the story blockchain for the specified duration."""
        print(f"\nMonitoring story blockchain for {duration} seconds...")
        
        start_time = time.time()
        interval = 10  # Status check interval in seconds
        
        while time.time() - start_time < duration:
            print(f"\n--- Story Status at t+{int(time.time() - start_time)}s ---")
            
            # Get blockchain from a random node
            try:
                node = random.choice(self.node_processes)
                response = requests.get(f"{node['url']}/get_chain", timeout=2)
                if response.status_code == 200:
                    blockchain = json.loads(response.text)
                    print(f"Current story has {len(blockchain)} blocks")
                    
                    # Show the most recent parts of the story
                    recent_blocks = blockchain[-3:] if len(blockchain) > 3 else blockchain
                    print("\nMost recent story contributions:")
                    for block in recent_blocks:
                        if block["index"] > 0:  # Skip genesis block
                            print(f"Block {block['index']} (by Author with nonce {block['nonce']}):")
                            print(f"  {block['data'][:100]}...")
                            print(f"  [Hash: {block['hash'][:8]}]")
                    
                    # Get status from each node to see who's working on the next part
                    print("\nStoryteller node status:")
                    for node in self.node_processes:
                        status_response = requests.get(f"{node['url']}/status", timeout=2)
                        if status_response.status_code == 200:
                            status = status_response.json()
                            print(f"Author {node['id']}: Currently mining: {status['is_mining']}, " + 
                                  f"Contributions waiting: {status['transaction_pool_size']}")
                
            except Exception as e:
                print(f"Error getting story status: {e}")
            
            # Sleep until next check
            time.sleep(interval)
            
            # Add some new story contributions periodically
            if random.random() > 0.5:  # 50% chance each interval
                self.add_story_contributions(random.randint(1, 2))

    def print_complete_story(self):
        """Print the complete story from the blockchain."""
        print("\n==== THE COMPLETE STORY ====\n")
        
        try:
            # Get the blockchain from the first node
            node = self.node_processes[0]
            response = requests.get(f"{node['url']}/get_chain", timeout=2)
            
            if response.status_code == 200:
                blockchain = json.loads(response.text)
                
                # Skip genesis block and print each story contribution in order
                for block in blockchain:
                    if block["index"] > 0:  # Skip genesis block
                        print(f"Chapter {block['index']}:")
                        print(f"{block['data']}")
                        print()  # Empty line between contributions
                
                print(f"\nStory complete! {len(blockchain) - 1} contributions were made.")
            else:
                print(f"Failed to get the story: {response.status_code}")
        
        except Exception as e:
            print(f"Error retrieving complete story: {e}")

    def verify_consistency(self):
        """Verify that all nodes have a consistent view of the story blockchain."""
        print("\nVerifying story consistency across storyteller nodes...")
        
        chains = {}
        for node in self.node_processes:
            node_id = node["id"]
            try:
                response = requests.get(f"{node['url']}/get_chain", timeout=2)
                if response.status_code == 200:
                    chains[node_id] = response.text
                else:
                    print(f"Error getting chain from Author {node_id}: {response.status_code}")
            except Exception as e:
                print(f"Error connecting to Author {node_id}: {e}")
        
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
                print(f"⚠️ Inconsistency detected! Author {reference_node_id} and Author {node_id} have different versions of the story.")
                
                # Detailed comparison
                ref_chain = json.loads(reference_chain)
                node_chain = json.loads(chain_text)
                
                print(f"Author {reference_node_id}'s story length: {len(ref_chain)} blocks")
                print(f"Author {node_id}'s story length: {len(node_chain)} blocks")
                
                if len(ref_chain) == len(node_chain):
                    # Find the first block that differs
                    for idx, (ref_block, node_block) in enumerate(zip(ref_chain, node_chain)):
                        if ref_block['hash'] != node_block['hash']:
                            print(f"First difference at chapter {idx}:")
                            print(f"  Author {reference_node_id}: {ref_block['hash'][:8]}")
                            print(f"  Author {node_id}: {node_block['hash'][:8]}")
                            break
                
                consistent = False
        
        if consistent:
            print("✅ All storytellers have a consistent view of the story!")
            
            # Print the winner for each block
            chain_data = json.loads(reference_chain)
            if len(chain_data) > 1:  # If we have more than just the genesis block
                print("\nStory contribution winners:")
                for block in chain_data:
                    if block['index'] > 0:  # Skip genesis block
                        author = "Unknown"
                        # Try to extract author from the data field
                        if "Author" in block['data'] and "says:" in block['data']:
                            author_part = block['data'].split("says:")[0]
                            author = author_part.strip()
                        
                        print(f"Chapter {block['index']}: {author} (Nonce: {block['nonce']}, Difficulty: {block['difficulty']})")
        
        return consistent

    def cleanup(self):
        """Clean up all processes."""
        print("\nCleaning up processes...")
        
        for node in self.node_processes:
            print(f"Stopping storyteller node {node['id']}...")
            try:
                node["process"].terminate()
                node["process"].wait(timeout=2)
            except:
                node["process"].kill()
        
        if self.tracker_process:
            print("Stopping tracker...")
            try:
                self.tracker_process.terminate()
                self.tracker_process.wait(timeout=2)
            except:
                self.tracker_process.kill()
        
        print("All processes stopped.")

    def run(self):
        """Run the complete storytelling test."""
        try:
            self.start_tracker()
            self.start_storyteller_nodes()
            
            # Let the nodes connect and synchronize
            time.sleep(5)
            
            # Add some initial story contributions to start the storytelling
            self.add_story_contributions(3)
            
            # Monitor the blockchain as the story evolves
            self.monitor_story_blockchain(self.run_duration)
            
            # Print the final story
            self.print_complete_story()
            
            # Check final consistency
            return self.verify_consistency()
            
        except KeyboardInterrupt:
            print("\nStorytelling test interrupted by user.")
            return False
        finally:
            self.cleanup()

def main():
    parser = argparse.ArgumentParser(description="Run a collaborative storytelling blockchain test")
    parser.add_argument("--nodes", type=int, default=3, help="Number of storyteller nodes (default: 3)")
    parser.add_argument("--interval", type=int, default=5, help="Mining interval in seconds (default: 5)")
    parser.add_argument("--duration", type=int, default=120, help="Test duration in seconds (default: 120)")
    
    args = parser.parse_args()
    
    print("=== BlockBard Collaborative Storytelling Test ===")
    print(f"Starting {args.nodes} storyteller nodes, running for {args.duration} seconds")
    
    test = StorytellingBlockchainTest(
        num_nodes=args.nodes,
        mine_interval=args.interval,
        run_duration=args.duration
    )
    
    success = test.run()
    
    if success:
        print("\n🎉 Storytelling test completed successfully! All nodes maintained story consistency.")
        return 0
    else:
        print("\n⚠️ Storytelling test failed! Story inconsistencies were detected.")
        return 1

if __name__ == "__main__":
    sys.exit(main()) 