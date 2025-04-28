import datetime
import json
import threading
import time
import random
import requests
from flask import Flask, request, jsonify
import logging
from utils.logging_util import setup_logger
from core.blockchain_storage import save_blockchain

from core.blockchain import Blockchain, Block # Import necessary classes

# --- Node Configuration ---
# These would typically come from args or config file
# NODE_HOST = "localhost"
# NODE_PORT = 5001 # Default, will be overridden
# TRACKER_URL = "http://localhost:5000"

class Node:
    def __init__(self, host, port, tracker_url, auto_mine=False, mine_interval=10, genesis_data=None):
        self.host = host
        self.port = port
        self.address = f"http://{self.host}:{self.port}"
        self.tracker_url = tracker_url
        self.blockchain = Blockchain(genesis_data)
        self.peers = set() # Set of peer addresses (e.g., 'http://localhost:5002')
        self.lock = threading.Lock() # Lock for accessing shared resources like blockchain and peers
        
        # Mining control
        self.is_mining = False
        self.mining_thread = None
        self.pending_transactions = []  # Queue of transactions waiting to be mined
        
        # Auto-mining settings
        self.auto_mine = auto_mine
        self.mine_interval = mine_interval  # Time between auto-mining attempts in seconds
        self.auto_mining_thread = None
        self.stop_auto_mining = False
        self.transaction_pool = []  # Pool of transactions to include in blocks
        
        # Set up our custom logger
        self.logger = setup_logger(f'node:{self.port}')
        self.logger.info(f"Initializing node on {self.address} with tracker {self.tracker_url}")
        self.logger.info(f"Auto-mining: {self.auto_mine}, interval: {self.mine_interval}s")
        if genesis_data:
            self.logger.info(f"Using custom genesis data: {genesis_data[:30]}...")
        
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
                    previous_hash=block_data['previous_hash'],
                    difficulty=block_data.get('difficulty', 0),
                    nonce=block_data.get('nonce', 0)
                )
                block.hash = block_data['hash'] # Trust the hash for now

                self.logger.info(f"Received block {block.index} with hash {block.hash[:8]} from peer")

                with self.lock:
                    # Check if this is a block we're currently trying to mine
                    current_last_block = self.blockchain.get_latest_block()
                    
                    # If we receive a valid block for the same position we're trying to mine,
                    # we should stop mining and accept this one (assuming it's valid)
                    if block.index == current_last_block.index + 1 and self.is_mining:
                        self.logger.info(f"Received block {block.index} while mining. Stopping mining.")
                        self.stop_mining()
                    
                    # Try to add the block
                    added = self.blockchain.add_block(block)

                if added:
                    self.logger.info(f"Successfully added block {block.index} to chain")
                    self._save_blockchain_state(f"add_block_{block.index}")
                    
                    # Restart mining with next data if we have any pending transactions
                    if self.pending_transactions and not self.is_mining:
                        self.logger.info("Restarting mining with next pending transaction")
                        next_data = self.pending_transactions.pop(0)
                        threading.Thread(target=self.start_mining, args=(next_data,), daemon=True).start()
                        
                    # For auto-mining mode, check if we should continue mining
                    if self.auto_mine and not self.is_mining:
                        self._schedule_next_auto_mining()
                        
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

                # If we're already mining, add this to the pending queue
                if self.is_mining:
                    self.logger.info(f"Already mining. Adding data to pending queue: {block_data}")
                    self.pending_transactions.append(block_data)
                    return jsonify({
                        "message": "Mining already in progress, transaction queued",
                        "queue_position": len(self.pending_transactions)
                    }), 202
                
                # Start mining in a background thread
                threading.Thread(target=self.start_mining, args=(block_data,), daemon=True).start()

                return jsonify({"message": "Mining started"}), 202 # Accepted
            except Exception as e:
                self.logger.error(f"Error triggering mining: {e}", exc_info=True)
                return jsonify({"error": "Failed to trigger mining"}), 500

        @app.route('/add_transaction', methods=['POST'])
        def add_transaction():
            """Add a transaction to the pool for mining."""
            self.logger.debug(f"Received add_transaction request: {request.data}")
            
            try:
                data = request.get_json()
                if not data or 'data' not in data:
                    self.logger.warning("Add transaction failed: Missing 'data' field")
                    return jsonify({"error": "Missing 'data' field in request body"}), 400

                transaction_data = data['data']
                
                # Add to transaction pool
                self.transaction_pool.append(transaction_data)
                self.logger.info(f"Added transaction to pool: {transaction_data}")
                
                # If auto-mining is enabled and we're not already mining, consider starting mining
                if self.auto_mine and not self.is_mining and not self.stop_auto_mining:
                    self._check_and_trigger_mining()
                
                return jsonify({
                    "message": "Transaction added to pool",
                    "pool_size": len(self.transaction_pool)
                }), 201
            except Exception as e:
                self.logger.error(f"Error adding transaction: {e}", exc_info=True)
                return jsonify({"error": "Failed to add transaction"}), 500

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

        @app.route('/auto_mine', methods=['POST'])
        def toggle_auto_mine():
            """Toggle automatic mining mode."""
            self.logger.debug(f"Received auto_mine toggle request: {request.data}")
            
            try:
                data = request.get_json()
                enable = data.get('enable', True)
                interval = data.get('interval', self.mine_interval)
                
                with self.lock:
                    previous_state = self.auto_mine
                    self.auto_mine = enable
                    self.mine_interval = interval
                    
                    if enable and not previous_state:
                        # Starting auto-mining
                        self.stop_auto_mining = False
                        self.logger.info(f"Auto-mining enabled with interval {interval}s")
                        threading.Thread(target=self._auto_mining_loop, daemon=True).start()
                    elif not enable and previous_state:
                        # Stopping auto-mining
                        self.stop_auto_mining = True
                        self.logger.info("Auto-mining disabled")
                
                return jsonify({
                    "message": f"Auto-mining {'enabled' if enable else 'disabled'}",
                    "interval": interval,
                    "transaction_pool_size": len(self.transaction_pool)
                }), 200
            except Exception as e:
                self.logger.error(f"Error toggling auto-mining: {e}", exc_info=True)
                return jsonify({"error": "Failed to toggle auto-mining"}), 500

        @app.route('/status', methods=['GET'])
        def get_status():
            """Get node status information."""
            with self.lock:
                chain_length = len(self.blockchain.chain)
                mining_status = self.is_mining
                auto_mining = self.auto_mine
                peer_count = len(self.peers)
                tx_pool_size = len(self.transaction_pool)
                pending_tx = len(self.pending_transactions)
                
                latest_block = self.blockchain.get_latest_block()
                latest_block_info = {
                    "index": latest_block.index,
                    "hash": latest_block.hash[:8],
                    "timestamp": str(latest_block.timestamp),
                    "difficulty": latest_block.difficulty
                }
                
            return jsonify({
                "chain_length": chain_length,
                "latest_block": latest_block_info,
                "is_mining": mining_status,
                "auto_mining": auto_mining,
                "mine_interval": self.mine_interval,
                "peer_count": peer_count,
                "transaction_pool_size": tx_pool_size,
                "pending_transactions": pending_tx,
                "address": self.address
            }), 200

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
            "difficulty": block.difficulty,
            "nonce": block.nonce
        }

        self.logger.info(f"Broadcasting block {block.index} with hash {block.hash[:8]} to {len(target_peers)} specific peers")
        
        for peer in target_peers:
            try:
                broadcast_url = f"{peer}/add_block"
                self.logger.debug(f"Sending block to {peer}")
                response = requests.post(broadcast_url, json=block_data, timeout=3)
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
    
    def start_mining(self, data):
        """Starts the mining process with appropriate synchronization."""
        self.logger.info(f"Starting mining process for data: {data}")
        
        with self.lock:
            if self.is_mining:
                self.logger.warning("Mining already in progress, not starting again")
                return False
            
            # Set mining flag
            self.is_mining = True
        
        try:
            # Sync with network before mining to ensure we're building on the latest block
            self.logger.info("Syncing chain before mining...")
            self.sync_chain()
            
            # Perform the actual mining
            with self.lock:
                new_block = self.blockchain.mine_block(data)
                
                # Double-check our blockchain before adding to ensure we didn't miss updates
                # during the mining process
                if new_block.previous_hash != self.blockchain.get_latest_block().hash:
                    self.logger.warning("Chain changed during mining, discarding mined block")
                    self.is_mining = False
                    
                    # Re-queue the data for mining after sync
                    self.pending_transactions.insert(0, data)
                    
                    # Try to sync again
                    threading.Thread(target=self.sync_chain, daemon=True).start()
                    return False
                
                # Add the block to our local chain
                added = self.blockchain.add_block(new_block)
            
            if added:
                self.logger.info(f"Successfully mined and added block {new_block.index} with hash {new_block.hash[:8]}")
                # Save blockchain state after mining
                self._save_blockchain_state(f"mined_{new_block.index}")
                
                # Refresh peers before broadcasting
                self._refresh_peer_list()
                
                # Broadcast immediately to reduce chance of conflicts
                self.broadcast_block(new_block)
                
                # Also run discovery to find any new peers
                threading.Thread(target=self.discover_from_all_peers, daemon=True).start()
                
                # Process next pending transaction if any
                if self.pending_transactions:
                    next_data = self.pending_transactions.pop(0)
                    self.logger.info(f"Processing next pending transaction: {next_data}")
                    # Reset mining flag before starting next
                    self.is_mining = False
                    threading.Thread(target=self.start_mining, args=(next_data,), daemon=True).start()
                else:
                    # Reset mining flag
                    self.is_mining = False
                    
                    # If auto-mining is enabled, schedule next mining attempt
                    if self.auto_mine and not self.stop_auto_mining:
                        self._schedule_next_auto_mining()
                
                return True
            else:
                self.logger.warning(f"Failed to add mined block {new_block.index} locally")
                self.is_mining = False
                return False
                
        except Exception as e:
            self.logger.error(f"Error during mining process: {e}", exc_info=True)
            self.is_mining = False
            return False
    
    def stop_mining(self):
        """Stop the current mining process."""
        self.logger.info("Stopping mining process")
        # Just set the flag - the mining loop will exit at the next iteration
        self.is_mining = False
    
    def simulate_mining(self, data):
        """Legacy method - now forwards to the real mining implementation."""
        self.logger.info(f"Simulate_mining called, forwarding to real mining implementation: {data}")
        return self.start_mining(data)
        
    def _auto_mining_loop(self):
        """Background thread that handles automatic mining."""
        self.logger.info("Starting automatic mining loop")
        
        while self.auto_mine and not self.stop_auto_mining:
            try:
                self._check_and_trigger_mining()
                
                # Sleep until next mining attempt
                for _ in range(self.mine_interval):
                    if self.stop_auto_mining or not self.auto_mine:
                        break
                    time.sleep(1)
                    
            except Exception as e:
                self.logger.error(f"Error in auto mining loop: {e}", exc_info=True)
                time.sleep(5)  # Sleep longer after an error
                
        self.logger.info("Automatic mining loop ended")
        
    def _check_and_trigger_mining(self):
        """Check if we should start mining and trigger it if appropriate."""
        with self.lock:
            # Skip if already mining
            if self.is_mining:
                return
                
            # Skip if no transactions in pool
            if not self.transaction_pool and not self.pending_transactions:
                self.logger.debug("No transactions in pool, skipping auto-mining")
                return
                
            # Pick a transaction from the pool or pending queue
            if self.transaction_pool:
                # Use some random selection or prioritization logic here
                # For simplicity, just take the first transaction in pool
                data = self.transaction_pool.pop(0)
            elif self.pending_transactions:
                data = self.pending_transactions.pop(0)
            else:
                return
                
            self.logger.info(f"Auto-mining triggered with data: {data}")
            
        # Start mining in a new thread (outside of lock)
        threading.Thread(target=self.start_mining, args=(data,), daemon=True).start()
    
    def _schedule_next_auto_mining(self):
        """Schedule the next auto-mining attempt."""
        if self.auto_mine and not self.stop_auto_mining:
            def delayed_mining():
                time.sleep(self.mine_interval)
                self._check_and_trigger_mining()
                
            threading.Thread(target=delayed_mining, daemon=True).start()
            self.logger.debug(f"Scheduled next auto-mining in {self.mine_interval} seconds")

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
            current_last_hash = self.blockchain.get_latest_block().hash
            self.logger.debug(f"Current chain length: {current_chain_length}, last hash: {current_last_hash}, checking {len(peers)} peers: {peers}")

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

                    # Consider chains of equal or greater length for tie-breaking
                    if length >= current_chain_length:
                        self.logger.debug(f"Found potentially longer/equal chain ({length} >= {current_chain_length}), validating...")
                        
                        # Validate the chain
                        potential_blockchain = Blockchain.from_json(chain_json)
                        
                        if potential_blockchain.is_valid_chain():
                            # Get the last block for tie-breaking
                            last_block = potential_blockchain.get_latest_block()
                            self.logger.info(f"Found valid chain (length {length}) from {node}, last hash: {last_block.hash[:8]}")
                            
                            valid_chains[node] = {
                                'blockchain': potential_blockchain,
                                'length': length,
                                'last_block': last_block
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
        
        # Select the longest valid chain with tie-breaking
        if valid_chains:
            # First, find the longest chain length
            max_length = max(data['length'] for data in valid_chains.values())
            
            # Filter for chains of the max length only
            chains_with_max_length = {
                node: data for node, data in valid_chains.items() 
                if data['length'] == max_length
            }
            
            # If there's a tie for length, use the one with the lexicographically smaller hash as a tie-breaker
            if len(chains_with_max_length) > 1:
                self.logger.info(f"Found {len(chains_with_max_length)} chains with equal length {max_length}. Using hash tie-breaker.")
                
                # Sort by hash (lexicographically smaller hash wins)
                sorted_chains = sorted(
                    chains_with_max_length.items(),
                    key=lambda x: x[1]['last_block'].hash
                )
                
                longest_node, longest_chain_data = sorted_chains[0]
                self.logger.info(f"Selected chain from {longest_node} with hash {longest_chain_data['last_block'].hash[:8]} as tie-breaker winner")
            else:
                # No tie, just take the first (only) one
                longest_node, longest_chain_data = next(iter(chains_with_max_length.items()))
            
            longest_blockchain = longest_chain_data['blockchain']
            longest_length = longest_chain_data['length']
            
            with self.lock:
                # In case of equal length and different hash, and our hash is lexicographically smaller, keep our chain
                if longest_length == len(self.blockchain.chain) and \
                   longest_chain_data['last_block'].hash > self.blockchain.get_latest_block().hash:
                    self.logger.info(f"Equal length chain but our hash is smaller. Keeping our chain.")
                    return False
                    
                # Now do the replacement
                current_chain_length = len(self.blockchain.chain)  # Re-check
                if longest_length > current_chain_length or \
                   (longest_length == current_chain_length and longest_chain_data['last_block'].hash < self.blockchain.get_latest_block().hash):
                    old_chain_length = len(self.blockchain.chain)
                    self.blockchain.chain = longest_blockchain.chain
                    self.blockchain.difficulty = longest_blockchain.difficulty  # Update our difficulty too
                    
                    # Stop mining if we were mining (we're building on an outdated chain)
                    if self.is_mining:
                        self.logger.info("Stopping mining due to chain replacement")
                        self.stop_mining()
                    
                    self.logger.info(f"Replaced local chain (length {old_chain_length}) with chain from {longest_node} (length {longest_length})")
                    # Save blockchain state after chain replacement
                    self._save_blockchain_state(f"replaced_chain_{longest_length}")
                    return True
                else:
                    self.logger.info(f"Chain replacement not needed")
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
                
                # Begin periodic chain sync in the background
                self._start_periodic_sync()
                
                # Start auto-mining if enabled
                if self.auto_mine:
                    self.logger.info("Starting automatic mining")
                    threading.Thread(target=self._auto_mining_loop, daemon=True).start()
            
            # Start discovery in background
            threading.Thread(target=discovery_and_sync_loop, daemon=True).start()

            self.logger.info(f"Starting Flask server at {self.address}")
            # Run Flask app. Use threaded=True for concurrent request handling.
            # Use debug=False and use_reloader=False for stability when running multiple processes.
            self.app.run(host=self.host, port=self.port, threaded=True, debug=False, use_reloader=False)
        except Exception as e:
            self.logger.error(f"Error running node: {e}", exc_info=True)
            raise
            
    def _start_periodic_sync(self):
        """Start a background thread to periodically sync with the network."""
        def sync_thread():
            sync_interval = 30  # seconds
            self.logger.info(f"Starting periodic sync every {sync_interval} seconds")
            
            while True:
                try:
                    time.sleep(sync_interval)
                    
                    # Skip sync if we're currently mining
                    if self.is_mining:
                        self.logger.debug("Skipping periodic sync while mining")
                        continue
                    
                    # Otherwise, do the sync
                    self.logger.debug("Running periodic sync")
                    self.sync_chain()
                    
                except Exception as e:
                    self.logger.error(f"Error in periodic sync: {e}")
                
        # Start the periodic sync thread
        threading.Thread(target=sync_thread, daemon=True).start()
        
    def _generate_dummy_transaction(self):
        """Generate a dummy transaction for testing auto-mining."""
        transaction = f"TX-{time.time()}: Transfer from User{random.randint(1, 100)} to User{random.randint(1, 100)}"
        return transaction

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