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

class CompetingMinersTest:
    def __init__(self, num_nodes=3, mine_interval=5, run_duration=120):
        self.tracker_process = None
        self.node_processes = []
        self.tracker_port = 5500
        self.tracker_url = f"http://localhost:{self.tracker_port}"
        self.base_node_port = 5501
        self.num_nodes = num_nodes
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
        
    def start_miners(self):
        """Start the mining nodes."""
        for i in range(self.num_nodes):
            node_port = self.base_node_port + i
            print(f"Starting miner {i+1} on port {node_port}...")
            
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
            
        print(f"All {self.num_nodes} miners started.")

    def add_transactions(self, count=10):
        """Add random transactions to random nodes."""
        print(f"Adding {count} random transactions...")
        
        for _ in range(count):
            # Pick a random node
            node = random.choice(self.node_processes)
            node_url = node["url"]
            
            # Generate a random transaction
            tx_data = f"TX-{time.time()}: User{random.randint(1, 100)} sent {random.randint(1, 100)} coins to User{random.randint(1, 100)}"
            
            try:
                response = requests.post(
                    f"{node_url}/add_transaction",
                    json={"data": tx_data},
                    timeout=2
                )
                
                if response.status_code == 201:
                    print(f"Added transaction to node {node['id']}: {tx_data[:30]}...")
                else:
                    print(f"Failed to add transaction to node {node['id']}: {response.status_code}")
            except Exception as e:
                print(f"Error adding transaction to node {node['id']}: {e}")
            
            # Slight delay between transactions
            time.sleep(0.5)

    def monitor_blockchain(self, duration):
        """Monitor the blockchain for the specified duration."""
        print(f"\nMonitoring blockchain for {duration} seconds...")
        
        start_time = time.time()
        interval = 10  # Status check interval in seconds
        
        while time.time() - start_time < duration:
            print(f"\n--- Status at t+{int(time.time() - start_time)}s ---")
            
            # Get status from each node
            for node in self.node_processes:
                try:
                    response = requests.get(f"{node['url']}/status", timeout=2)
                    if response.status_code == 200:
                        status = response.json()
                        print(f"Node {node['id']}: Chain length {status['chain_length']}, " + 
                              f"Last block: {status['latest_block']['hash']}, " +
                              f"Mining: {status['is_mining']}, " + 
                              f"TX pool: {status['transaction_pool_size']}")
                    else:
                        print(f"Node {node['id']}: Error getting status - {response.status_code}")
                except Exception as e:
                    print(f"Node {node['id']}: Error - {e}")
            
            # Sleep until next check
            time.sleep(interval)
            
            # Add some random transactions periodically
            if random.random() > 0.5:  # 50% chance each interval
                self.add_transactions(random.randint(1, 3))

    def verify_consistency(self):
        """Verify that all nodes have a consistent view of the blockchain."""
        print("\nVerifying blockchain consistency across nodes...")
        
        chains = {}
        for node in self.node_processes:
            node_id = node["id"]
            try:
                response = requests.get(f"{node['url']}/get_chain", timeout=2)
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
                print(f"⚠️ Inconsistency detected! Node {reference_node_id} and Node {node_id} have different chains.")
                
                # Detailed comparison
                ref_chain = json.loads(reference_chain)
                node_chain = json.loads(chain_text)
                
                print(f"Node {reference_node_id} chain length: {len(ref_chain)}")
                print(f"Node {node_id} chain length: {len(node_chain)}")
                
                if len(ref_chain) == len(node_chain):
                    # Find the first block that differs
                    for idx, (ref_block, node_block) in enumerate(zip(ref_chain, node_chain)):
                        if ref_block['hash'] != node_block['hash']:
                            print(f"First difference at block {idx}:")
                            print(f"  Node {reference_node_id}: {ref_block['hash'][:8]}")
                            print(f"  Node {node_id}: {node_block['hash'][:8]}")
                            break
                
                consistent = False
        
        if consistent:
            print("✅ All nodes have consistent blockchains!")
            
            # Print chain details
            chain_data = json.loads(reference_chain)
            print(f"Chain length: {len(chain_data)}")
            print("Last 3 blocks:")
            for block in chain_data[-3:] if len(chain_data) >= 3 else chain_data:
                print(f"  Block {block['index']}: hash={block['hash'][:8]}, nonce={block['nonce']}, difficulty={block['difficulty']}")
        
        return consistent

    def cleanup(self):
        """Clean up all processes."""
        print("\nCleaning up processes...")
        
        for node in self.node_processes:
            print(f"Stopping miner {node['id']}...")
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
        """Run the complete test."""
        try:
            self.start_tracker()
            self.start_miners()
            
            # Let the nodes connect and synchronize
            time.sleep(5)
            
            # Add some initial transactions to get things moving
            self.add_transactions(5)
            
            # Monitor the blockchain as it evolves
            self.monitor_blockchain(self.run_duration)
            
            # Check final consistency
            return self.verify_consistency()
            
        except KeyboardInterrupt:
            print("\nTest interrupted by user.")
            return False
        finally:
            self.cleanup()

def main():
    parser = argparse.ArgumentParser(description="Run competing blockchain miners")
    parser.add_argument("--nodes", type=int, default=3, help="Number of mining nodes (default: 3)")
    parser.add_argument("--interval", type=int, default=5, help="Mining interval in seconds (default: 5)")
    parser.add_argument("--duration", type=int, default=120, help="Test duration in seconds (default: 120)")
    
    args = parser.parse_args()
    
    print("=== BlockBard Competing Miners Test ===")
    print(f"Starting {args.nodes} competing miners, running for {args.duration} seconds")
    
    test = CompetingMinersTest(
        num_nodes=args.nodes,
        mine_interval=args.interval,
        run_duration=args.duration
    )
    
    success = test.run()
    
    if success:
        print("\n🎉 Test completed successfully! All nodes maintained blockchain consistency.")
        return 0
    else:
        print("\n⚠️ Test failed! Blockchain inconsistencies were detected.")
        return 1

if __name__ == "__main__":
    sys.exit(main()) 