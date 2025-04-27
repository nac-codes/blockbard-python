#!/usr/bin/env python3
import subprocess
import time
import requests
import json
import threading
import os
import signal
import sys
from datetime import datetime

class BlockchainTest:
    def __init__(self):
        self.tracker_process = None
        self.node_processes = []
        self.tracker_port = 5500
        self.tracker_url = f"http://localhost:{self.tracker_port}"
        self.base_node_port = 5501
        self.num_nodes = 3  # Test with 3 competing nodes
        self.test_data = [
            "First block data: The quick brown fox jumps over the lazy dog",
            "Second block data: Lorem ipsum dolor sit amet",
            "Third block data: Blockchain is a distributed ledger technology",
            "Fourth block data: Proof of Work requires computational effort",
            "Fifth block data: Consensus algorithms maintain network integrity"
        ]
    
    def setup(self):
        """Start the tracker and nodes"""
        print(f"\n[{self._timestamp()}] 🚀 Starting test environment...")
        
        # Create necessary directories
        os.makedirs("logs", exist_ok=True)
        os.makedirs("blockchain_states", exist_ok=True)
        
        # Start tracker
        print(f"[{self._timestamp()}] Starting tracker on port {self.tracker_port}...")
        tracker_cmd = ["python", "main.py", "tracker", "--port", str(self.tracker_port)]
        self.tracker_process = subprocess.Popen(
            tracker_cmd, 
            stdout=subprocess.PIPE, 
            stderr=subprocess.PIPE
        )
        
        # Wait longer for tracker to initialize
        time.sleep(5)
        
        # Start nodes
        for i in range(self.num_nodes):
            node_port = self.base_node_port + i
            print(f"[{self._timestamp()}] Starting node {i+1} on port {node_port}...")
            
            node_cmd = [
                "python", "main.py", "node", 
                "--port", str(node_port),
                "--tracker", self.tracker_url
            ]
            
            node_process = subprocess.Popen(
                node_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            
            self.node_processes.append({
                "id": i+1,
                "port": node_port,
                "process": node_process,
                "url": f"http://localhost:{node_port}"
            })
            
            # Give each node more time to start and register
            time.sleep(3)
        
        # Additional time for initial sync
        print(f"[{self._timestamp()}] Waiting for nodes to synchronize...")
        time.sleep(10)
    
    def _timestamp(self):
        """Generate a timestamp for logging"""
        return datetime.now().strftime("%H:%M:%S")
    
    def test_competing_mining(self):
        """Test mining competition between nodes"""
        print(f"\n[{self._timestamp()}] 🧪 Testing competing mining between {self.num_nodes} nodes...")
        
        # Verify node availability before starting tests
        print(f"[{self._timestamp()}] Verifying node availability...")
        all_available = True
        for node in self.node_processes:
            node_id = node["id"]
            node_url = node["url"]
            try:
                response = requests.get(f"{node_url}/get_chain", timeout=2)
                if response.status_code == 200:
                    print(f"[{self._timestamp()}] Node {node_id} is available.")
                else:
                    print(f"[{self._timestamp()}] Node {node_id} response status: {response.status_code}")
                    all_available = False
            except Exception as e:
                print(f"[{self._timestamp()}] Node {node_id} is not responding: {e}")
                all_available = False
        
        if not all_available:
            print(f"[{self._timestamp()}] ⚠️ Not all nodes are available. Test may fail.")
            # Wait some extra time before continuing
            time.sleep(5)
        
        # Get initial blockchain state from all nodes
        print(f"[{self._timestamp()}] Checking initial chain state...")
        initial_chains = self._get_all_chains()
        
        for node_id, chain in initial_chains.items():
            chain_length = len(json.loads(chain))
            print(f"[{self._timestamp()}] Node {node_id} initial chain length: {chain_length}")
        
        # Verify all nodes have the same initial chain (should be just genesis block)
        self._verify_chain_consistency(initial_chains)
        
        # Test parallel mining
        # We'll trigger mining on all nodes with the same data to create a competition
        print(f"\n[{self._timestamp()}] Starting mining competition for block 1...")
        mining_threads = []
        
        for node in self.node_processes:
            thread = threading.Thread(
                target=self._trigger_mining,
                args=(node, self.test_data[0])
            )
            mining_threads.append(thread)
            thread.start()
        
        # Wait for all mining operations to complete
        for thread in mining_threads:
            thread.join()
        
        # Give more time for mining and propagation
        print(f"[{self._timestamp()}] Waiting for mining and block propagation...")
        time.sleep(20)
        
        # Check chains after first competition
        chains_after_competition = self._get_all_chains()
        print(f"\n[{self._timestamp()}] Chain state after competition:")
        for node_id, chain in chains_after_competition.items():
            chain_length = len(json.loads(chain))
            print(f"[{self._timestamp()}] Node {node_id} chain length: {chain_length}")
        
        # Verify all nodes have consistent chains
        self._verify_chain_consistency(chains_after_competition)
        
        # Mine second block with competition
        print(f"\n[{self._timestamp()}] Starting mining competition for block 2...")
        mining_threads = []
        
        for node in self.node_processes:
            thread = threading.Thread(
                target=self._trigger_mining,
                args=(node, self.test_data[1])
            )
            mining_threads.append(thread)
            thread.start()
        
        # Wait for all mining operations to complete
        for thread in mining_threads:
            thread.join()
        
        # Give more time for mining and propagation
        print(f"[{self._timestamp()}] Waiting for mining and block propagation...")
        time.sleep(20)
        
        # Check chains after second competition
        final_chains = self._get_all_chains()
        print(f"\n[{self._timestamp()}] Final chain state:")
        for node_id, chain in final_chains.items():
            chain_data = json.loads(chain)
            chain_length = len(chain_data)
            print(f"[{self._timestamp()}] Node {node_id} chain length: {chain_length}")
            
            # Print details of the last block
            if chain_length > 0:
                last_block = chain_data[-1]
                print(f"[{self._timestamp()}] Node {node_id} last block: index={last_block['index']}, hash={last_block['hash'][:8]}, nonce={last_block['nonce']}")
        
        # Verify all nodes have consistent chains
        success = self._verify_chain_consistency(final_chains)
        
        # Mine one more block with node 1
        print(f"\n[{self._timestamp()}] Mining one additional block with Node 1...")
        self._trigger_mining(self.node_processes[0], self.test_data[2])
        
        # Give more time for mining and propagation
        print(f"[{self._timestamp()}] Waiting for mining and block propagation...")
        time.sleep(20)
        
        # Check chains after separate mining
        final_chains = self._get_all_chains()
        print(f"\n[{self._timestamp()}] Chain state after additional block:")
        for node_id, chain in final_chains.items():
            chain_data = json.loads(chain)
            chain_length = len(chain_data)
            print(f"[{self._timestamp()}] Node {node_id} chain length: {chain_length}")
            
            # Print details of the last block
            if chain_length > 0:
                last_block = chain_data[-1]
                print(f"[{self._timestamp()}] Node {node_id} last block: index={last_block['index']}, hash={last_block['hash'][:8]}, nonce={last_block['nonce']}")
        
        # Final consistency check
        success = self._verify_chain_consistency(final_chains)
        
        return success
    
    def _trigger_mining(self, node, data):
        """Trigger mining on a specific node"""
        try:
            node_id = node["id"]
            node_url = node["url"]
            print(f"[{self._timestamp()}] Triggering mining on Node {node_id}...")
            
            response = requests.post(
                f"{node_url}/mine",
                json={"data": data},
                timeout=5
            )
            
            if response.status_code == 202:
                print(f"[{self._timestamp()}] Mining triggered on Node {node_id}: {response.json()}")
                return True
            else:
                print(f"[{self._timestamp()}] Failed to trigger mining on Node {node_id}: {response.status_code}")
                return False
        except Exception as e:
            print(f"[{self._timestamp()}] Error triggering mining on Node {node_id}: {e}")
            return False
    
    def _get_all_chains(self):
        """Get blockchain data from all nodes"""
        chains = {}
        for node in self.node_processes:
            node_id = node["id"]
            node_url = node["url"]
            try:
                response = requests.get(f"{node_url}/get_chain", timeout=5)
                if response.status_code == 200:
                    chains[node_id] = response.text
                else:
                    print(f"[{self._timestamp()}] Failed to get chain from Node {node_id}: {response.status_code}")
            except Exception as e:
                print(f"[{self._timestamp()}] Error getting chain from Node {node_id}: {e}")
        
        return chains
    
    def _verify_chain_consistency(self, chains):
        """Verify all nodes have consistent chains"""
        if not chains:
            print(f"[{self._timestamp()}] ❌ No chains to verify!")
            return False
        
        reference_chain = None
        reference_node_id = None
        
        for node_id, chain_json in chains.items():
            if reference_chain is None:
                reference_chain = chain_json
                reference_node_id = node_id
                continue
            
            if chain_json != reference_chain:
                print(f"[{self._timestamp()}] ❌ Chain inconsistency detected!")
                print(f"[{self._timestamp()}] Node {reference_node_id} and Node {node_id} have different chains")
                
                # Print chain differences
                ref_chain_data = json.loads(reference_chain)
                node_chain_data = json.loads(chain_json)
                
                print(f"[{self._timestamp()}] Node {reference_node_id} chain length: {len(ref_chain_data)}")
                print(f"[{self._timestamp()}] Node {node_id} chain length: {len(node_chain_data)}")
                
                return False
        
        print(f"[{self._timestamp()}] ✅ All nodes have consistent chains!")
        return True
    
    def teardown(self):
        """Cleanup processes"""
        print(f"\n[{self._timestamp()}] 🧹 Cleaning up test environment...")
        
        for node in self.node_processes:
            node_id = node["id"]
            process = node["process"]
            print(f"[{self._timestamp()}] Stopping Node {node_id}...")
            
            try:
                process.terminate()
                process.wait(timeout=5)
            except:
                process.kill()
        
        if self.tracker_process:
            print(f"[{self._timestamp()}] Stopping Tracker...")
            try:
                self.tracker_process.terminate()
                self.tracker_process.wait(timeout=5)
            except:
                self.tracker_process.kill()
        
        print(f"[{self._timestamp()}] Cleanup complete.")

def main():
    test = BlockchainTest()
    
    try:
        test.setup()
        success = test.test_competing_mining()
        if success:
            print(f"\n[{test._timestamp()}] 🎉 Test successful! Proof of Work competition works correctly.")
        else:
            print(f"\n[{test._timestamp()}] ❌ Test failed! There were inconsistencies in the blockchain.")
    except KeyboardInterrupt:
        print("\nTest interrupted by user.")
    except Exception as e:
        print(f"\nTest error: {e}")
    finally:
        test.teardown()

if __name__ == "__main__":
    main() 