import datetime
import json
import threading
import time
import requests
from flask import Flask, request, jsonify
import logging
from logging_util import setup_logger
from blockchain_storage import save_blockchain

from blockchain import Blockchain, Block # Import necessary classes

# --- Node Configuration ---
# These would typically come from args or config file
# NODE_HOST = "localhost"
# NODE_PORT = 5001 # Default, will be overridden
# TRACKER_URL = "http://localhost:5000"

class Node:
    def __init__(self, host, port, tracker_url):
        self.host = host
        self.port = port
        self.address = f"http://{self.host}:{self.port}"
        self.tracker_url = tracker_url
        self.blockchain = Blockchain()
        self.peers = set() # Set of peer addresses (e.g., 'http://localhost:5002')
        self.lock = threading.Lock() # Lock for accessing shared resources like blockchain and peers
        
        # Set up our custom logger
        self.logger = setup_logger(f'node:{self.port}')
        self.logger.info(f"Initializing node on {self.address} with tracker {self.tracker_url}")
        
        # Create Flask app
        self.app = self._create_flask_app()
        
        # Save initial blockchain state
        self._save_blockchain_state("init")

    def _save_blockchain_state(self, event_type):
        """Save the current blockchain state to a file with a descriptive event type."""
        try:
            filepath = save_blockchain(self.blockchain, f"node_{self.port}_{event_type}")
            self.logger.debug(f"Saved blockchain state to {filepath}")
            return filepath
        except Exception as e:
            self.logger.error(f"Failed to save blockchain state: {e}", exc_info=True)
            return None

    def _create_flask_app(self):
        app = Flask(__name__)
        # Disable Flask's default logging
        app.logger.disabled = True
        log = logging.getLogger('werkzeug')
        log.disabled = True

        @app.route('/get_chain', methods=['GET'])
        def get_chain():
            """Returns the node's current blockchain."""
            self.logger.debug("Received request for blockchain")
            with self.lock:
                # We need to serialize the chain data properly
                chain_data = self.blockchain.to_json() # Use the existing method
            self.logger.debug(f"Returning chain with {len(self.blockchain.chain)} blocks")
            return chain_data, 200 # Return raw JSON string with correct mimetype later

        @app.route('/add_block', methods=['POST'])
        def add_block():
            """Receives a new block from a peer, validates it, and adds it."""
            self.logger.debug(f"Received add_block request: {request.data}")
            
            try:
                block_data = request.get_json()
                if not block_data:
                    self.logger.warning("Add block failed: Invalid block data")
                    return jsonify({"error": "Invalid block data"}), 400

                # Reconstruct the block object
                block = Block(
                    index=block_data['index'],
                    timestamp=datetime.datetime.fromisoformat(block_data['timestamp']),
                    data=block_data['data'],
                    previous_hash=block_data['previous_hash']
                )
                block.hash = block_data['hash'] # Trust the hash for now

                self.logger.info(f"Received block {block.index} with hash {block.hash[:8]} from peer")

                with self.lock:
                    added = self.blockchain.add_block(block)

                if added:
                    self.logger.info(f"Successfully added block {block.index} to chain")
                    self._save_blockchain_state(f"add_block_{block.index}")
                    return jsonify({"message": f"Block {block.index} added"}), 201
                else:
                    self.logger.warning(f"Failed to add block {block.index}. Running conflict resolution.")
                    # Maybe the block was old or invalid based on our current chain
                    # Check if we need to sync (resolve fork)
                    self.resolve_conflicts() # Check if other chains are longer
                    return jsonify({"message": "Block invalid or already present"}), 409 # Conflict
            except Exception as e:
                self.logger.error(f"Error processing received block: {e}", exc_info=True)
                return jsonify({"error": "Failed to process block"}), 500

        @app.route('/update_peers', methods=['POST'])
        def update_peers():
            """Receives updated peer list from the tracker."""
            self.logger.debug(f"Received update_peers request: {request.data}")
            
            try:
                data = request.get_json()
                new_peers = data.get('peers', [])
                self.logger.debug(f"Parsed peer list: {new_peers}")
                
                with self.lock:
                    # Get current peers
                    old_peers = set(self.peers)
                    # Add new peers (excluding self)
                    new_peer_set = set(p for p in new_peers if p != self.address)
                    # Combine with existing peers (union)
                    self.peers = old_peers.union(new_peer_set)
                    
                    # Log peer changes
                    added_peers = new_peer_set - old_peers
                    if added_peers:
                        self.logger.info(f"Added new peers: {added_peers}")
                
                self.logger.info(f"Updated peers list: {self.peers}")
                
                # If peers were added, synchronize the chain
                if added_peers:
                    # This helps nodes sync with the network when the peer list changes
                    self.logger.info("New peers detected, triggering chain synchronization")
                    # Run sync in a separate thread to avoid blocking response
                    threading.Thread(target=self.sync_chain, daemon=True).start()
                
                # This is the fix: If we have a non-genesis chain, broadcast our latest block to new peers
                # This helps late-joining nodes sync up
                with self.lock:
                    if len(self.blockchain.chain) > 1 and added_peers:
                        latest_block = self.blockchain.get_latest_block()
                        self.logger.info(f"Broadcasting latest block {latest_block.index} to newly added peers: {added_peers}")
                        # Use a separate thread to avoid blocking response
                        threading.Thread(
                            target=self.broadcast_block_to_specific_peers, 
                            args=(latest_block, list(added_peers)),
                            daemon=True
                        ).start()
                
                return jsonify({"message": "Peers updated"}), 200
            except Exception as e:
                self.logger.error(f"Error updating peers: {e}", exc_info=True)
                return jsonify({"error": "Failed to update peers"}), 500

        @app.route('/mine', methods=['POST'])
        def trigger_mining():
            """Triggers the node to mine a new block."""
            self.logger.debug(f"Received mining request: {request.data}")
            
            try:
                data = request.get_json()
                if not data or 'data' not in data:
                    self.logger.warning("Mining failed: Missing 'data' field")
                    return jsonify({"error": "Missing 'data' field in request body"}), 400

                block_data = data['data']
                self.logger.info(f"Starting mining with data: {block_data}")

                # Run mining in a background thread so the HTTP request returns quickly
                threading.Thread(target=self.simulate_mining, args=(block_data,), daemon=True).start()

                return jsonify({"message": "Mining triggered"}), 202 # Accepted
            except Exception as e:
                self.logger.error(f"Error triggering mining: {e}", exc_info=True)
                return jsonify({"error": "Failed to trigger mining"}), 500

        @app.route('/discover', methods=['POST'])
        def discover():
            """Direct peer-to-peer discovery endpoint."""
            self.logger.debug(f"Received discovery request: {request.data}")
            
            try:
                # Get the address of the node making the discovery request
                data = request.get_json()
                peer_address = data.get('address')
                
                if not peer_address:
                    return jsonify({"error": "Peer address required"}), 400
                
                # Add the requestor to our peer list if it's not already there and not ourselves
                if peer_address != self.address:
                    with self.lock:
                        old_peers = set(self.peers)
                        self.peers.add(peer_address)
                        if peer_address not in old_peers:
                            self.logger.info(f"Added new peer via direct discovery: {peer_address}")
                            
                    # If this is a new peer and we have a chain, broadcast our latest block
                    if peer_address not in old_peers and len(self.blockchain.chain) > 1:
                        latest_block = self.blockchain.get_latest_block()
                        threading.Thread(
                            target=self.broadcast_block_to_specific_peers,
                            args=(latest_block, [peer_address]),
                            daemon=True
                        ).start()
                
                # Return our peer list (excluding the requestor)
                with self.lock:
                    response_peers = [p for p in self.peers if p != peer_address]
                    
                return jsonify({
                    "message": "Discovery successful",
                    "peers": response_peers,
                    "chain_length": len(self.blockchain.chain)
                }), 200
                
            except Exception as e:
                self.logger.error(f"Error handling discovery request: {e}", exc_info=True)
                return jsonify({"error": "Failed to process discovery"}), 500

        return app

    def register_with_tracker(self):
        """Registers this node with the central tracker."""
        register_url = f"{self.tracker_url}/register"
        self.logger.info(f"Registering with tracker at {register_url}")
        
        try:
            # Log full details of the request we're about to make
            self.logger.debug(f"Sending registration request to: {register_url}")
            self.logger.debug(f"Request data: {{'address': '{self.address}'}}")
            self.logger.debug(f"Full tracker URL: {self.tracker_url}")
            
            # Make the request
            response = requests.post(register_url, json={'address': self.address}, timeout=5)
            self.logger.debug(f"Registration response status: {response.status_code}")
            
            if response.status_code == 200:
                # Update local peer list initially from tracker response
                response_data = response.json()
                self.logger.debug(f"Registration response data: {response_data}")
                peers_list = response_data.get('peers', [])
                
                with self.lock:
                    self.peers = set(p for p in peers_list if p != self.address)
                
                self.logger.info(f"Successfully registered with tracker. Peers: {self.peers}")
            else:
                self.logger.error(f"Failed to register with tracker. Status: {response.status_code}, Response: {response.text}")
                # Try to get more information about what went wrong
                self.logger.debug(f"Response headers: {response.headers}")
                # Try a GET request to see if tracker is functioning at all
                try:
                    test_response = requests.get(self.tracker_url, timeout=1)
                    self.logger.debug(f"Test GET to tracker root: Status {test_response.status_code}")
                except Exception as test_e:
                    self.logger.error(f"Could not reach tracker at all: {test_e}")
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Could not connect to tracker at {self.tracker_url}: {e}")
        except Exception as e:
            self.logger.error(f"Unexpected error during registration: {e}", exc_info=True)

    def broadcast_block_to_specific_peers(self, block, target_peers):
        """Sends a block to specific peers."""
        if not target_peers:
            self.logger.debug("No target peers to broadcast to")
            return

        block_data = {
            "index": block.index,
            "timestamp": str(block.timestamp),
            "data": block.data,
            "previous_hash": block.previous_hash,
            "hash": block.hash,
        }

        self.logger.info(f"Broadcasting block {block.index} with hash {block.hash[:8]} to {len(target_peers)} specific peers")
        
        for peer in target_peers:
            try:
                broadcast_url = f"{peer}/add_block"
                self.logger.debug(f"Sending block to {peer}")
                response = requests.post(broadcast_url, json=block_data, timeout=1)
                self.logger.debug(f"Response from {peer}: {response.status_code}")
            except requests.exceptions.RequestException as e:
                self.logger.warning(f"Failed to broadcast block to {peer}: {e}")

    def broadcast_block(self, new_block):
        """Sends a newly mined block to all known peers."""
        with self.lock:
            peers_to_broadcast = list(self.peers) # Snapshot
            
        self.logger.info(f"Broadcasting block {new_block.index} to {len(peers_to_broadcast)} peers from peer list: {peers_to_broadcast}")
        # Use the helper method with all peers
        return self.broadcast_block_to_specific_peers(new_block, peers_to_broadcast)

    def simulate_mining(self, data):
        """Simulates mining a block and adds/broadcasts it."""
        self.logger.info(f"Starting simulated mining for data: {data}")
        # In real PoW, this would take time and effort
        try:
            with self.lock:
                new_block = self.blockchain.mine_block(data)
                added = self.blockchain.add_block(new_block)

            if added:
                self.logger.info(f"Successfully mined and added block {new_block.index} with hash {new_block.hash[:8]}")
                # Save blockchain state after mining
                self._save_blockchain_state(f"mined_{new_block.index}")
                
                # Get latest peer list from tracker and try direct discovery
                self._refresh_peer_list()
                self.discover_from_all_peers()
                
                # Broadcast after adding locally and refreshing peers
                # Run broadcast in a separate thread to avoid blocking if mining is part of a loop
                threading.Thread(target=self.broadcast_block, args=(new_block,), daemon=True).start()
                
                # Wait a moment and then trigger another round of discovery
                def delayed_discovery():
                    time.sleep(1)
                    self.logger.info("Running delayed discovery after mining")
                    self.discover_from_all_peers()
                
                threading.Thread(target=delayed_discovery, daemon=True).start()
            else:
                self.logger.warning(f"Mined block {new_block.index} but failed to add locally (validation failed?)")
        except Exception as e:
            self.logger.error(f"Error during mining: {e}", exc_info=True)
            
    def _refresh_peer_list(self):
        """Get the latest peer list from the tracker."""
        try:
            self.logger.debug("Refreshing peer list from tracker")
            response = requests.get(f"{self.tracker_url}/peers", timeout=2)
            if response.status_code == 200:
                peer_data = response.json()
                peer_list = peer_data.get('peers', [])
                
                with self.lock:
                    old_peers = set(self.peers)
                    # Merge new peers rather than replace
                    new_peers = set(p for p in peer_list if p != self.address)
                    # Union of old and new peers
                    self.peers = old_peers.union(new_peers)
                    
                    # Log changes
                    added = new_peers - old_peers
                    if added:
                        self.logger.info(f"Added new peers during refresh: {added}")
                        
                self.logger.debug(f"Current peer list after refresh: {self.peers}")
                
                # If the peer list is empty, try to register again
                if not self.peers:
                    self.logger.info("Peer list is empty, attempting to re-register with tracker")
                    self.register_with_tracker()
                
                return True
            else:
                self.logger.warning(f"Failed to refresh peer list: Status {response.status_code}")
                return False
        except Exception as e:
            self.logger.error(f"Error refreshing peer list: {e}")
            return False

    def resolve_conflicts(self):
        """Consensus Algorithm: Replaces chain with the longest valid chain in the network."""
        self.logger.info("Starting conflict resolution to find the longest valid chain")
        with self.lock:
            peers = list(self.peers)
            current_chain_length = len(self.blockchain.chain)
            self.logger.debug(f"Current chain length: {current_chain_length}, checking {len(peers)} peers: {peers}")

        if not peers:
            self.logger.info("No peers available for conflict resolution")
            return False

        # Dictionary to keep track of valid chains from peers
        valid_chains = {}
        
        # Fetch chains from all peers
        for node in peers:
            try:
                self.logger.debug(f"Requesting chain from {node}")
                response = requests.get(f'{node}/get_chain', timeout=5)  # Increased timeout
                if response.status_code == 200:
                    chain_json = response.text # Get raw JSON string
                    chain_data = json.loads(chain_json)
                    length = len(chain_data)
                    self.logger.debug(f"Received chain from {node}, length: {length}")

                    # Only consider longer chains
                    if length > current_chain_length:
                        self.logger.debug(f"Found potentially longer chain ({length} > {current_chain_length}), validating...")
                        
                        # Validate the chain
                        potential_blockchain = Blockchain.from_json(chain_json)
                        if potential_blockchain.is_valid_chain():
                            self.logger.info(f"Found valid chain (length {length}) from {node}")
                            valid_chains[node] = {
                                'blockchain': potential_blockchain,
                                'length': length
                            }
                        else:
                            self.logger.warning(f"Chain from {node} (length {length}) is invalid")
                    else:
                        self.logger.debug(f"Chain from {node} (length {length}) not longer than current chain ({current_chain_length})")
            except requests.exceptions.RequestException as e:
                self.logger.warning(f"Could not fetch chain from peer {node}: {e}")
            except json.JSONDecodeError as e:
                self.logger.error(f"Failed to decode chain JSON from {node}: {e}")
            except Exception as e:
                self.logger.error(f"Error processing chain from {node}: {e}", exc_info=True)
        
        # Select the longest valid chain
        if valid_chains:
            # Sort by chain length (descending)
            sorted_chains = sorted(valid_chains.items(), 
                                 key=lambda x: x[1]['length'],
                                 reverse=True)
            
            # Take the longest valid chain
            longest_node, longest_chain_data = sorted_chains[0]
            longest_blockchain = longest_chain_data['blockchain']
            longest_length = longest_chain_data['length']
            
            with self.lock:
                # Double check current length again inside lock before replacing
                if longest_length > len(self.blockchain.chain):
                    old_chain_length = len(self.blockchain.chain)
                    self.blockchain.chain = longest_blockchain.chain
                    self.logger.info(f"Replaced local chain (length {old_chain_length}) with longer valid chain (length {longest_length}) from {longest_node}")
                    # Save blockchain state after chain replacement
                    self._save_blockchain_state(f"replaced_chain_{longest_length}")
                    return True
                else:
                    self.logger.info(f"Longer chain found, but local chain grew concurrently. No replacement needed.")
        else:
            self.logger.info("No longer valid chains found from peers")
        
        self.logger.info(f"Conflict resolution finished. Current chain length: {len(self.blockchain.chain)}")
        return False

    def sync_chain(self):
        """Wrapper for conflict resolution used at startup or periodically."""
        self.logger.info("Attempting to synchronize chain with network")
        
        # In case we have no peers, try to refresh the list first
        self._refresh_peer_list()
        
        # Now resolve conflicts with all available peers
        result = self.resolve_conflicts()
        # Save state after sync attempt regardless of outcome
        self._save_blockchain_state("after_sync")
        return result

    def discover_peers(self, target_peer):
        """Directly contact a known peer to discover other peers."""
        try:
            self.logger.info(f"Attempting direct discovery with peer: {target_peer}")
            
            # Send discovery request to the target peer
            response = requests.post(
                f"{target_peer}/discover",
                json={"address": self.address},
                timeout=2
            )
            
            if response.status_code == 200:
                data = response.json()
                new_peers = data.get('peers', [])
                remote_chain_length = data.get('chain_length', 0)
                
                self.logger.info(f"Discovery successful. Received {len(new_peers)} peers from {target_peer}. Remote chain length: {remote_chain_length}")
                
                # Add new peers
                with self.lock:
                    old_peers = set(self.peers)
                    for peer in new_peers:
                        if peer != self.address:
                            self.peers.add(peer)
                            
                    added_peers = self.peers - old_peers
                    if added_peers:
                        self.logger.info(f"Added peers via discovery: {added_peers}")
                
                # If remote node has a longer chain, sync with it
                if remote_chain_length > len(self.blockchain.chain):
                    self.logger.info(f"Remote peer has longer chain ({remote_chain_length} > {len(self.blockchain.chain)}). Syncing...")
                    threading.Thread(target=self.sync_chain, daemon=True).start()
                    
                return True
            else:
                self.logger.warning(f"Discovery request failed: {response.status_code}")
                return False
        except Exception as e:
            self.logger.error(f"Error during peer discovery with {target_peer}: {e}")
            return False

    def discover_from_all_peers(self):
        """Try to discover peers from all known peers."""
        with self.lock:
            current_peers = list(self.peers)
            
        if not current_peers:
            self.logger.info("No peers to discover from. Trying to refresh from tracker.")
            # If we have no peers, refresh from tracker
            self._refresh_peer_list()
            return False
            
        success = False
        for peer in current_peers:
            if self.discover_peers(peer):
                success = True
                
        return success

    def run(self):
        """Starts the node's Flask server and registers with the tracker."""
        try:
            # Register first before starting the server to ensure the tracker knows about it
            self.register_with_tracker()

            # Initial sync attempt after a short delay to allow peers to register
            # In a real system, syncing might be triggered differently or periodically
            self.logger.info("Waiting briefly before initial sync...")
            time.sleep(2) # Give tracker/peers time to settle
            
            # Start discovery and sync in background thread
            def discovery_and_sync_loop():
                max_attempts = 3
                for attempt in range(max_attempts):
                    self.logger.info(f"Running discovery and sync (attempt {attempt+1}/{max_attempts})")
                    
                    # First, try to sync with existing peers
                    self.sync_chain()
                    
                    # Then, try to discover more peers directly
                    if self.discover_from_all_peers():
                        # If we found new peers, try syncing again
                        self.sync_chain()
                    
                    # Sleep between attempts
                    if attempt < max_attempts - 1:
                        time.sleep(2)
                
                self.logger.info(f"Initial discovery and sync complete. Peer count: {len(self.peers)}, Chain length: {len(self.blockchain.chain)}")
            
            # Start discovery in background
            threading.Thread(target=discovery_and_sync_loop, daemon=True).start()

            self.logger.info(f"Starting Flask server at {self.address}")
            # Run Flask app. Use threaded=True for concurrent request handling.
            # Use debug=False and use_reloader=False for stability when running multiple processes.
            self.app.run(host=self.host, port=self.port, threaded=True, debug=False, use_reloader=False)
        except Exception as e:
            self.logger.error(f"Error running node: {e}", exc_info=True)
            raise

# Example usage (typically run from a main script)
if __name__ == '__main__':
    import sys
    if len(sys.argv) != 4:
        print("Usage: python node.py <host> <port> <tracker_url>")
        print("Example: python node.py localhost 5001 http://localhost:5000")
        sys.exit(1)

    host_arg = sys.argv[1]
    port_arg = int(sys.argv[2])
    tracker_arg = sys.argv[3]

    node = Node(host=host_arg, port=port_arg, tracker_url=tracker_arg)
    node.run() 