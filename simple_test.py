#!/usr/bin/env python3
"""
Simple test script for BlockBard blockchain network.
This script tests the main.py implementation by:
1. Starting a tracker process
2. Starting two node processes
3. Mining a block on one node
4. Verifying the blockchain is synced across nodes
"""

import subprocess
import time
import os
import requests
import json
import signal
import sys

# Configuration
TRACKER_HOST = "localhost"
TRACKER_PORT = 5500
TRACKER_URL = f"http://{TRACKER_HOST}:{TRACKER_PORT}"

NODE1_HOST = "localhost"
NODE1_PORT = 5501
NODE1_URL = f"http://{NODE1_HOST}:{NODE1_PORT}"

NODE2_HOST = "localhost"
NODE2_PORT = 5502
NODE2_URL = f"http://{NODE2_HOST}:{NODE2_PORT}"

# Process list
processes = []

def cleanup():
    """Terminate all child processes."""
    print("\nCleaning up processes...")
    for p in processes:
        try:
            os.kill(p.pid, signal.SIGTERM)
            print(f"Terminated process {p.pid}")
        except:
            pass

def start_tracker():
    """Start a tracker process."""
    print(f"Starting tracker at {TRACKER_URL}...")
    cmd = ["python", "main.py", "tracker", "--host", TRACKER_HOST, "--port", str(TRACKER_PORT)]
    
    # Use subprocess.PIPE to capture output
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    processes.append(proc)
    print(f"Tracker process started (PID: {proc.pid}).")
    
    # Wait for tracker to start up
    time.sleep(3)
    
    # Test if tracker is running
    try:
        response = requests.get(TRACKER_URL, timeout=1)
        if response.status_code == 200:
            print(f"Tracker is running. Response: {response.json()}")
            return True
        else:
            print(f"Tracker responded with status {response.status_code}")
            return False
    except requests.exceptions.RequestException as e:
        print(f"Failed to connect to tracker: {e}")
        return False

def start_node(host, port, tracker_url):
    """Start a node process."""
    node_url = f"http://{host}:{port}"
    print(f"Starting node at {node_url}...")
    cmd = ["python", "main.py", "node", "--host", host, "--port", str(port), "--tracker", tracker_url]
    
    # Use subprocess.PIPE to capture output
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    processes.append(proc)
    print(f"Node process started (PID: {proc.pid}).")
    
    # Wait for node to start up
    time.sleep(3)
    
    # Test if node is running
    try:
        response = requests.get(f"{node_url}/get_chain", timeout=1)
        if response.status_code == 200:
            print(f"Node is running. Chain length: {len(json.loads(response.text))}")
            return True
        else:
            print(f"Node responded with status {response.status_code}")
            return False
    except requests.exceptions.RequestException as e:
        print(f"Failed to connect to node: {e}")
        return False

def mine_block(node_url, data):
    """Mine a block on a node."""
    print(f"\nMining block with data '{data}' on {node_url}...")
    try:
        response = requests.post(f"{node_url}/mine", json={"data": data}, timeout=5)
        if response.status_code == 202:
            print(f"Mining request accepted by {node_url}.")
            return True
        else:
            print(f"Error triggering mining: Status {response.status_code}, {response.text}")
            return False
    except requests.exceptions.RequestException as e:
        print(f"Error triggering mining: {e}")
        return False

def get_chain(node_url):
    """Get the blockchain from a node."""
    try:
        response = requests.get(f"{node_url}/get_chain", timeout=5)
        if response.status_code == 200:
            chain = json.loads(response.text)
            print(f"Retrieved chain from {node_url}, length: {len(chain)}")
            return chain
        else:
            print(f"Error fetching chain: Status {response.status_code}")
            return None
    except requests.exceptions.RequestException as e:
        print(f"Error fetching chain: {e}")
        return None

def main():
    """Main test procedure."""
    # Set up cleanup handler
    def signal_handler(sig, frame):
        cleanup()
        sys.exit(1)
    signal.signal(signal.SIGINT, signal_handler)
    
    try:
        # 1. Start tracker
        if not start_tracker():
            print("Failed to start tracker. Exiting.")
            return
        
        # 2. Start nodes
        if not start_node(NODE1_HOST, NODE1_PORT, TRACKER_URL):
            print("Failed to start Node 1. Exiting.")
            return
        
        if not start_node(NODE2_HOST, NODE2_PORT, TRACKER_URL):
            print("Failed to start Node 2. Exiting.")
            return
        
        # 3. Let nodes connect to each other
        print("\nWaiting for nodes to discover each other...")
        time.sleep(3)
        
        # 4. Mine a block on Node 1
        if not mine_block(NODE1_URL, "Test block from Node 1"):
            print("Failed to mine block. Exiting.")
            return
        
        # 5. Wait for block to propagate
        print("\nWaiting for block to propagate...")
        time.sleep(5)
        
        # 6. Check chains on both nodes
        chain1 = get_chain(NODE1_URL)
        chain2 = get_chain(NODE2_URL)
        
        if chain1 and chain2:
            if len(chain1) == len(chain2):
                print("\nSuccess: Both nodes have chains of the same length!")
                
                # Compare chain contents
                if chain1 == chain2:
                    print("Success: Both chains are identical!")
                else:
                    print("Warning: Chains have same length but different content.")
                    
                # Show the latest block
                latest_block = chain1[-1]
                print(f"\nLatest block: #{latest_block['index']}")
                print(f"  Data: {latest_block['data']}")
                print(f"  Hash: {latest_block['hash']}")
            else:
                print(f"\nFailure: Chain lengths differ! Node 1: {len(chain1)}, Node 2: {len(chain2)}")
        else:
            print("Failed to retrieve chains. Test inconclusive.")
    
    finally:
        # 7. Cleanup
        cleanup()

if __name__ == "__main__":
    main() 