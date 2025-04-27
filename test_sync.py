import multiprocessing
import time
import requests
import sys
import os
import signal
import json
import logging
from logging_util import setup_logger
from blockchain_storage import compare_blockchains, list_blockchain_files
from pathlib import Path
import subprocess

# Set up test logger
logger = setup_logger('test_sync')

# Configuration
TRACKER_HOST = "localhost"
TRACKER_PORT = 5500
TRACKER_URL = f"http://{TRACKER_HOST}:{TRACKER_PORT}"
NODE_HOST = "localhost"
NODE_PORTS = [5501, 5502, 5503]
NODE_URLS = [f"http://{NODE_HOST}:{port}" for port in NODE_PORTS]
NODE_IDENTIFIERS = [f"node_{port}" for port in NODE_PORTS]

# Create results directory
RESULTS_DIR = "test_results"
Path(RESULTS_DIR).mkdir(exist_ok=True)

# Process list to manage child processes
processes = []

def cleanup_ports():
    """Run cleanup.py to ensure ports are available."""
    logger.info("Running port cleanup script")
    try:
        subprocess.run([sys.executable, "cleanup.py"], check=True)
        logger.info("Port cleanup completed")
        time.sleep(1)  # Give system time to fully release ports
    except subprocess.CalledProcessError as e:
        logger.error(f"Port cleanup failed: {e}")
    except Exception as e:
        logger.error(f"Error during port cleanup: {e}", exc_info=True)

def run_tracker():
    """Starts the tracker node in a separate process."""
    logger.info(f"Starting tracker at {TRACKER_URL}...")
    try:
        # Use sys.executable to ensure using the same Python interpreter
        proc = multiprocessing.Process(
            target=os.system,
            args=(f"{sys.executable} tracker.py",)
        )
        proc.start()
        processes.append(proc)
        logger.info(f"Tracker process started (PID: {proc.pid}).")
        
        # Give tracker time to start up
        logger.info("Waiting for tracker to initialize...")
        max_retries = 10
        retry_count = 0
        success = False
        
        while retry_count < max_retries and not success:
            try:
                time.sleep(1)  # Short wait between retries
                response = requests.get(f"{TRACKER_URL}", timeout=1)
                if response.status_code == 200:
                    logger.info(f"Tracker is running. Response: {response.json()}")
                    success = True
                else:
                    logger.warning(f"Tracker responded with status {response.status_code}: {response.text}")
                    retry_count += 1
            except requests.exceptions.RequestException as e:
                logger.warning(f"Retry {retry_count+1}/{max_retries}: Tracker not ready yet: {e}")
                retry_count += 1
        
        if not success:
            logger.error(f"Failed to connect to tracker after {max_retries} attempts.")
            return False
            
        # Check registered endpoints
        try:
            # Test the /register endpoint specifically
            test_data = {'address': 'http://test.endpoint'}
            test_response = requests.post(f"{TRACKER_URL}/register", json=test_data, timeout=1)
            if test_response.status_code == 200:
                logger.info("Successfully tested tracker /register endpoint")
                # Clean up test registration
                requests.post(f"{TRACKER_URL}/unregister", json=test_data, timeout=1)
            else:
                logger.error(f"Tracker /register endpoint test failed: {test_response.status_code}")
                return False
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to test tracker /register endpoint: {e}")
            return False
            
        logger.info("Tracker is fully operational")
        return True
            
    except Exception as e:
        logger.error(f"Failed to start tracker process: {e}", exc_info=True)
        return False

def run_node(port):
    """Starts a peer node in a separate process."""
    logger.info(f"Starting node on port {port}...")
    try:
        proc = multiprocessing.Process(
            target=os.system,
            args=(f"{sys.executable} node.py {NODE_HOST} {port} {TRACKER_URL}",)
        )
        proc.start()
        processes.append(proc)
        logger.info(f"Node process started for port {port} (PID: {proc.pid}).")
        return proc
    except Exception as e:
        logger.error(f"Failed to start node process for port {port}: {e}", exc_info=True)
        return None

def cleanup_processes():
    """Terminates all child processes."""
    logger.info("\nCleaning up processes...")
    for p in processes:
        if p.is_alive():
            try:
                # Send SIGTERM first for graceful shutdown
                os.kill(p.pid, signal.SIGTERM)
                logger.info(f"Sent SIGTERM to process {p.pid}")
            except ProcessLookupError:
                logger.debug(f"Process {p.pid} already terminated.")
            except Exception as e:
                logger.error(f"Error sending SIGTERM to process {p.pid}: {e}")
                try:
                    # Force kill if SIGTERM failed or wasn't sufficient
                    p.kill() # or os.kill(p.pid, signal.SIGKILL)
                    logger.info(f"Force killed process {p.pid}")
                except Exception as kill_e:
                    logger.error(f"Error force killing process {p.pid}: {kill_e}")

    # Wait briefly for processes to terminate
    time.sleep(2)
    for p in processes:
        if p.is_alive():
            logger.warning(f"Process {p.pid} did not terminate gracefully. May require manual cleanup.")

def get_node_chain(node_url):
    """Fetches the blockchain from a specific node."""
    try:
        logger.debug(f"Requesting chain from {node_url}")
        response = requests.get(f"{node_url}/get_chain", timeout=5)
        if response.status_code == 200:
            # The response body is the JSON string, directly loadable
            chain_data = json.loads(response.text)
            logger.debug(f"Received chain from {node_url}, length: {len(chain_data)}")
            return chain_data
        else:
            logger.error(f"Error fetching chain from {node_url}: Status {response.status_code}")
            return None
    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching chain from {node_url}: {e}")
        return None
    except json.JSONDecodeError as e:
        logger.error(f"Error decoding chain JSON from {node_url}: {e}")
        return None

def trigger_node_mining(node_url, block_data):
    """Sends a request to a node to mine a block."""
    try:
        logger.info(f"\nRequesting {node_url} to mine block: '{block_data}'")
        response = requests.post(f"{node_url}/mine", json={"data": block_data}, timeout=3)
        if response.status_code == 202: # 202 Accepted
            logger.info(f"Mining request accepted by {node_url}.")
            return True
        else:
            logger.error(f"Error triggering mining on {node_url}: Status {response.status_code}, {response.text}")
            return False
    except requests.exceptions.RequestException as e:
        logger.error(f"Error triggering mining on {node_url}: {e}")
        return False

def save_final_results(chains, all_synced):
    """Save test results and comparison to a file."""
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    results_file = os.path.join(RESULTS_DIR, f"test_results_{timestamp}.json")
    
    # Compare blockchain states from files
    comparison = compare_blockchains(NODE_IDENTIFIERS)
    
    results = {
        "timestamp": timestamp,
        "all_synced": all_synced,
        "api_chains": {
            node_url: {
                "length": len(chain) if chain else 0,
                "blocks": [{"index": block.get("index"), "hash": block.get("hash")} for block in (chain or [])]
            } for node_url, chain in chains.items()
        },
        "blockchain_files": list_blockchain_files(),
        "blockchain_comparison": comparison
    }
    
    with open(results_file, 'w') as f:
        json.dump(results, f, indent=4)
    
    logger.info(f"Test results saved to {results_file}")
    return results_file

if __name__ == "__main__":
    # Ensure cleanup happens even if script is interrupted
    original_sigint_handler = signal.getsignal(signal.SIGINT)
    original_sigterm_handler = signal.getsignal(signal.SIGTERM)

    def signal_handler(signum, frame):
        logger.info(f"\nSignal {signum} received, initiating cleanup...")
        cleanup_processes()
        # Restore original handlers and exit
        signal.signal(signal.SIGINT, original_sigint_handler)
        signal.signal(signal.SIGTERM, original_sigterm_handler)
        sys.exit(1)

    signal.signal(signal.SIGINT, signal_handler) # Handle Ctrl+C
    signal.signal(signal.SIGTERM, signal_handler) # Handle termination signals

    try:
        # Run port cleanup first
        cleanup_ports()
        
        # 1. Start Tracker
        logger.info("Starting tracker node...")
        tracker_started = run_tracker()
        
        if not tracker_started:
            logger.error("Failed to start tracker or tracker is unreachable. Exiting.")
            sys.exit(1)
            
        # 2. Start Node 1 and Node 2
        node1_proc = run_node(NODE_PORTS[0]) # Start node on 5501
        logger.info("Waiting for Node 1 to start up...")
        time.sleep(2) # Give Node 1 time to start
        
        node2_proc = run_node(NODE_PORTS[1]) # Start node on 5502
        
        logger.info("\nWaiting for nodes 1 and 2 to register and perform initial sync...")
        time.sleep(10) # Allow more time for registration, discovery and initial sync

        # Check if nodes are running
        for i, url in enumerate(NODE_URLS[:2]):
            try:
                response = requests.get(f"{url}/get_chain", timeout=1)
                if response.status_code == 200:
                    logger.info(f"Node {i+1} ({url}) is running. Chain length: {len(json.loads(response.text))}")
                else:
                    logger.warning(f"Node {i+1} ({url}) returned status {response.status_code}")
            except requests.exceptions.RequestException as e:
                logger.error(f"Node {i+1} ({url}) is not responding: {e}")

        # 3. Node 1 mines two blocks
        mined1 = trigger_node_mining(NODE_URLS[0], "Block 1 data from Node 1")
        time.sleep(5) # Give more time for mining and broadcast
        mined2 = trigger_node_mining(NODE_URLS[0], "Block 2 data from Node 1")

        logger.info("\nWaiting for blocks to propagate and Node 2 to sync...")
        time.sleep(15) # Allow more time for broadcast, validation, and potential conflict resolution

        # 4. Start Node 3 (Late Joiner)
        logger.info("\nStarting Node 3 (late joiner)...")
        node3_proc = run_node(NODE_PORTS[2]) # Start node on 5503

        logger.info("\nWaiting for Node 3 to register and sync...")
        time.sleep(15) # Allow more time for registration and sync via resolve_conflicts

        # 5. Verify Chains
        logger.info("\n--- Verifying Final Blockchain States ---")
        chains = {}
        all_synced = True

        for i, url in enumerate(NODE_URLS):
            logger.info(f"Fetching chain from Node {i+1} ({url})...")
            chain = get_node_chain(url)
            if chain:
                chains[url] = chain
                logger.info(f"Node {i+1} chain length: {len(chain)}")
                # print(json.dumps(chain, indent=2)) # Uncomment to see full chain
            else:
                logger.error(f"Failed to fetch chain from Node {i+1}")
                all_synced = False

        if len(chains) == len(NODE_URLS):
            first_chain = chains[NODE_URLS[0]]
            for i in range(1, len(NODE_URLS)):
                if chains[NODE_URLS[i]] != first_chain:
                    logger.error(f"\nError: Chain mismatch between Node 1 and Node {i+1}!")
                    # Detailed comparison
                    logger.debug(f"Node 1 Chain Length: {len(first_chain)}")
                    logger.debug(f"Node {i+1} Chain Length: {len(chains[NODE_URLS[i]])}")
                    
                    # Find the first mismatch
                    min_len = min(len(first_chain), len(chains[NODE_URLS[i]]))
                    for j in range(min_len):
                        if first_chain[j] != chains[NODE_URLS[i]][j]:
                            logger.error(f"First mismatch at block {j}:")
                            logger.error(f"Node 1 Block {j}: {first_chain[j]}")
                            logger.error(f"Node {i+1} Block {j}: {chains[NODE_URLS[i]][j]}")
                            break
                    
                    all_synced = False
                    break # No need to check further if one mismatch found
            if all_synced:
                logger.info("\nSuccess: All nodes have the same blockchain!")
                logger.info(f"Final chain length: {len(first_chain)}")
        else:
            logger.error("\nError: Could not retrieve chains from all nodes for comparison.")
            all_synced = False

        # Save test results
        results_file = save_final_results(chains, all_synced)
        logger.info(f"Detailed test results saved to {results_file}")

    except Exception as e:
        logger.error(f"\nAn error occurred during the test: {e}", exc_info=True)
    finally:
        # 6. Cleanup
        cleanup_processes()
        # Restore original signal handlers
        signal.signal(signal.SIGINT, original_sigint_handler)
        signal.signal(signal.SIGTERM, original_sigterm_handler)

    if all_synced:
        logger.info("\nTest completed successfully.")
    else:
        logger.error("\nTest completed with errors (nodes not synced). Check logs and diagnostic files.")
        sys.exit(1) # Exit with error code if not synced 