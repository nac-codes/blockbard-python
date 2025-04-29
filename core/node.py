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
                    nonce=block_data.get('nonce', 0),
                    story_position=block_data.get('story_position', {})
                )
                block.hash = block_data['hash'] # Trust the hash for now

                self.logger.info(f"Received block {block.index} with hash {block.hash[:8]} from peer")
                
                # Check this block's story position for uniqueness before proceeding
                unique_check_failed = False
                with self.lock:
                    if block.story_position and "position_id" in block.story_position:
                        position_id = block.story_position["position_id"]
                        # Check if this position already exists in our chain
                        for existing_block in self.blockchain.chain:
                            if (hasattr(existing_block, 'story_position') and 
                                existing_block.story_position and 
                                "position_id" in existing_block.story_position and
                                existing_block.story_position["position_id"] == position_id):
                                
                                self.logger.warning(f"Rejecting block {block.index}: Story position {position_id} already exists in our chain at block {existing_block.index}")
                                unique_check_failed = True
                                break
                
                if unique_check_failed:
                    return jsonify({
                        "error": "Story position already exists in the blockchain",
                        "position_id": position_id,
                    }), 409  # Conflict
                

                with self.lock:
                    # Check if this is a block we're currently trying to mine
                    current_last_block = self.blockchain.get_latest_block()
                    
                    # If we receive a valid block for the same position we're trying to mine,
                    # we should stop mining and accept this one (assuming it's valid)
                    if block.index == current_last_block.index + 1 and self.is_mining:
                        self.logger.info(f"Received block {block.index} while mining. Stopping mining.")
                        self.stop_mining()
                    
                    # Ensure the block index is reasonable for our chain
                    if block.index > current_last_block.index + 1:
                        # This block is too far ahead - we're missing blocks
                        self.logger.warning(f"Block {block.index} is ahead of our chain (current: {current_last_block.index}). Running sync.")
                        # Trigger a sync in background
                        threading.Thread(target=self.sync_chain, daemon=True).start()
                        return jsonify({"error": "Block is ahead of our chain"}), 409
                    
                    # If this is an older block but still valid and helps our chain quality, 
                    # consider inserting it at the right position
                    if block.index < current_last_block.index:
                        self.logger.info(f"Received older block {block.index} (our latest: {current_last_block.index}). Checking if it improves our chain.")
                        
                        # See if we can rebuild our chain including this block
                        potential_insertion = False
                        
                        # Check if this block's previous hash matches the block at index-1
                        if block.index > 0 and block.index < len(self.blockchain.chain):
                            prev_block = self.blockchain.chain[block.index - 1]
                            if prev_block.hash == block.previous_hash:
                                # This could potentially be inserted
                                potential_insertion = True
                        
                        if potential_insertion:
                            # Create a copy of our current chain
                            original_chain = self.blockchain.chain.copy()
                            
                            # Try inserting this block
                            # Simple case: replace the block at this index
                            if block.index < len(self.blockchain.chain):
                                test_chain = original_chain.copy()
                                test_chain[block.index] = block
                                
                                # Now rebuild the chain from this point
                                # This is a simplified approach - a real implementation would be more complex
                                for i in range(block.index + 1, len(test_chain)):
                                    test_chain[i].previous_hash = test_chain[i-1].hash
                                    test_chain[i].hash = test_chain[i].calculate_hash()
                                
                                # Evaluate the quality of this new chain
                                test_quality, test_hash = self._evaluate_chain_quality(test_chain)
                                current_quality, current_hash = self._evaluate_chain_quality(original_chain)
                                
                                if test_quality > current_quality or (test_quality == current_quality and test_hash < current_hash):
                                    self.logger.info(f"Inserting block {block.index} improves chain quality ({current_quality} -> {test_quality}) or has better hash")
                                    self.blockchain.chain = test_chain
                                    self._save_blockchain_state(f"chain_improved_{block.index}")
                                    return jsonify({"message": f"Block {block.index} inserted and chain improved"}), 201
                        
                        # If we can't insert it, just say it's not needed
                        return jsonify({"message": "Block not needed for current chain"}), 409
                    
                    # Try to add the block (standard case for next block in sequence)
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

                # Require previous_hash in transaction
                if 'previous_hash' not in data:
                    self.logger.warning("Add transaction failed: Missing 'previous_hash' field")
                    return jsonify({"error": "Missing 'previous_hash' field in request body"}), 400

                transaction_data = data['data']
                previous_hash = data['previous_hash']
                
                # Verify the previous hash matches our latest block
                with self.lock:
                    latest_block = self.blockchain.get_latest_block()
                    latest_hash = latest_block.hash
                    
                    # If the previous hash doesn't match, reject the transaction
                    if previous_hash != latest_hash:
                        self.logger.warning(f"Transaction rejected: Previous hash mismatch. Expected {latest_hash}, got {previous_hash}")
                        return jsonify({
                            "error": "Previous hash mismatch. Your chain may be out of date.",
                            "expected_hash": latest_hash,
                            "latest_block_index": latest_block.index
                        }), 409  # Conflict

                    # Check for story position duplication before adding to pool
                    try:
                        # Extract the story position from the transaction data
                        story_position = self.blockchain._extract_story_position(transaction_data)
                        
                        if story_position and "position_id" in story_position:
                            position_id = story_position["position_id"]
                            
                            # Check if this position already exists in the chain
                            for block in self.blockchain.chain:
                                if (hasattr(block, 'story_position') and 
                                    block.story_position and 
                                    "position_id" in block.story_position and
                                    block.story_position["position_id"] == position_id):
                                    
                                    self.logger.warning(f"Transaction rejected: Story position {position_id} already exists in block {block.index}")
                                    return jsonify({
                                        "error": "Story position already exists in the blockchain",
                                        "position_id": position_id,
                                        "block_index": block.index
                                    }), 409  # Conflict
                            
                            # Check if this position is already in the transaction pool
                            for existing_tx in self.transaction_pool:
                                existing_position = self.blockchain._extract_story_position(existing_tx)
                                if (existing_position and 
                                    "position_id" in existing_position and 
                                    existing_position["position_id"] == position_id):
                                    
                                    self.logger.warning(f"Transaction rejected: Story position {position_id} already in pool")
                                    return jsonify({
                                        "error": "Story position already in transaction pool",
                                        "position_id": position_id
                                    }), 409  # Conflict
                                    
                            self.logger.info(f"Story position {position_id} validated, not a duplicate")
                    except Exception as e:
                        # Log but continue if we can't extract or validate the position
                        self.logger.warning(f"Could not validate story position: {e}")

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
            
            # Use our robust request method for more reliable registration
            response = self._make_robust_request('post', 
                                               register_url, 
                                               json={'address': self.address}, 
                                               max_retries=3,
                                               base_timeout=5)
            
            if not response:
                self.logger.error(f"Failed to connect to tracker at {self.tracker_url} after multiple attempts")
                return
                
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
                    test_response = self._make_robust_request('get', self.tracker_url, max_retries=1)
                    if test_response:
                        self.logger.debug(f"Test GET to tracker root: Status {test_response.status_code}")
                    else:
                        self.logger.error("Could not reach tracker at all with test request")
                except Exception as test_e:
                    self.logger.error(f"Error testing tracker connection: {test_e}")
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
            "nonce": block.nonce,
            "story_position": block.story_position
        }

        self.logger.info(f"Broadcasting block {block.index} with hash {block.hash[:8]} to {len(target_peers)} specific peers")
        
        success_count = 0
        rejection_count = 0
        
        # Hold blocks that were rejected to try with more context later
        rejected_peers = []
        
        for peer in target_peers:
            try:
                broadcast_url = f"{peer}/add_block"
                self.logger.debug(f"Sending block to {peer}")
                
                # Use our robust request method for more reliable broadcasting
                response = self._make_robust_request('post', broadcast_url, 
                                                    json=block_data, 
                                                    max_retries=2)
                
                if response:
                    self.logger.debug(f"Response from {peer}: {response.status_code}")
                    if response.status_code in (200, 201):
                        success_count += 1
                    elif response.status_code == 409:  # Conflict
                        rejection_count += 1
                        rejected_peers.append(peer)
                else:
                    self.logger.warning(f"Failed to broadcast block to {peer} after retries")
            except Exception as e:
                self.logger.warning(f"Unexpected error broadcasting block to {peer}: {e}")
        
        # If we have rejected peers but also had some successes, try a second approach
        # This can help with partial network synchronization
        if rejected_peers and success_count > 0:
            self.logger.info(f"Block {block.index} rejected by {len(rejected_peers)} peers. Attempting to provide context.")
            
            # Try sending the peer our entire chain (or a part of it)
            # This helps them understand the context of our block
            for peer in rejected_peers:
                try:
                    # First, trigger a sync on their side
                    discover_url = f"{peer}/discover"
                    discover_payload = {"address": self.address}
                    
                    self.logger.debug(f"Sending discovery and chain info to {peer}")
                    discover_response = self._make_robust_request('post', discover_url, 
                                                          json=discover_payload, 
                                                          max_retries=1)
                    
                    if discover_response and discover_response.status_code == 200:
                        self.logger.debug(f"Successfully sent discovery data to {peer}")
                        
                        # Now try the block again - it might work now that they've seen our chain
                        retry_response = self._make_robust_request('post', f"{peer}/add_block", 
                                                             json=block_data, 
                                                             max_retries=1)
                        
                        if retry_response and retry_response.status_code in (200, 201):
                            success_count += 1
                            self.logger.info(f"Successfully added block to {peer} on second attempt")
                except Exception as e:
                    self.logger.warning(f"Error in second broadcast attempt to {peer}: {e}")
        
        self.logger.info(f"Block {block.index} broadcast completed: {success_count}/{len(target_peers)} peers successful, {rejection_count} rejections")

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
                    added_peers = new_peers - old_peers
                    if added_peers:
                        self.logger.info(f"Added new peers during refresh: {added_peers}")
                        
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

    def _check_for_position_duplicates(self, chain):
        """
        Checks a blockchain for duplicate story positions.
        Returns True if duplicates are found, False otherwise.
        """
        position_ids = set()
        for block in chain:
            # Skip genesis block
            if block.index == 0:
                continue
                
            if hasattr(block, 'story_position') and block.story_position:
                position_id = block.story_position.get('position_id')
                if position_id:
                    if position_id in position_ids:
                        self.logger.warning(f"Duplicate story position found: {position_id} in block {block.index}")
                        return True
                    position_ids.add(position_id)
                    
        return False

    def _evaluate_chain_quality(self, chain):
        """
        Evaluates the quality of a chain based on story coherence and other factors.
        Returns a quality score (higher is better).
        """
        # Start with base score equal to chain length
        score = len(chain)
        
        # Check for story position duplicates (major negative factor)
        if self._check_for_position_duplicates(chain):
            score -= 10000  # Severe penalty for duplicates
            
        # Analyze story position sequence
        verse_errors = 0
        last_book = None
        last_chapter = None
        last_verse = None
        
        for block in sorted(chain, key=lambda b: b.index):
            if block.index == 0:  # Skip genesis
                continue
                
            if hasattr(block, 'story_position') and block.story_position and 'metadata' in block.story_position:
                metadata = block.story_position['metadata']
                
                # Check for Bible verse sequence
                if all(k in metadata for k in ['book', 'chapter', 'verse']):
                    book = metadata['book']
                    chapter = metadata['chapter']
                    verse = metadata['verse']
                    
                    # First block sets the initial values
                    if last_book is None:
                        last_book = book
                        last_chapter = chapter
                        last_verse = verse
                        continue
                    
                    # Check for logical progression
                    if book == last_book:
                        if chapter == last_chapter:
                            # Same chapter - verse should increase
                            if verse <= last_verse:
                                verse_errors += 1
                        elif chapter < last_chapter:
                            # Chapter going backward
                            verse_errors += 2
                    
                    # Update for next iteration
                    last_book = book
                    last_chapter = chapter
                    last_verse = verse
        
        # Subtract points for verse sequence errors
        score -= verse_errors * 5
        
        return score, self._calculate_chain_hash_value(chain)
    
    def _calculate_chain_hash_value(self, chain):
        """
        Calculate a deterministic value based on the chain's hash to use as a tiebreaker.
        Returns a string that can be compared lexicographically.
        """
        # Use the hash of the last block as a tiebreaker
        if not chain:
            return ""
        return chain[-1].hash

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
                
                # Use our robust request method with longer timeout for chain fetching
                response = self._make_robust_request('get', f'{node}/get_chain', 
                                                    max_retries=3, 
                                                    base_timeout=10)
                
                if not response:
                    self.logger.warning(f"Failed to fetch chain from {node} after retries")
                    continue
                    
                if response.status_code == 200:
                    chain_json = response.text # Get raw JSON string
                    chain_data = json.loads(chain_json)
                    length = len(chain_data)
                    self.logger.debug(f"Received chain from {node}, length: {length}")

                    # Consider chains of equal or greater length for tie-breaking
                    # Relaxed check to allow for more chains to be considered
                    if length >= max(1, current_chain_length - 2):
                        self.logger.debug(f"Found potentially viable chain ({length} blocks), validating...")
                        
                        # Validate the chain
                        potential_blockchain = Blockchain.from_json(chain_json)
                        
                        if potential_blockchain.is_valid_chain(allow_duplicate_positions=True):
                            # Evaluate the chain quality with tiebreaker hash value
                            chain_quality, chain_hash_value = self._evaluate_chain_quality(potential_blockchain.chain)
                            
                            # Check for story position duplicates
                            has_duplicates = self._check_for_position_duplicates(potential_blockchain.chain)
                            
                            # Get the last block for tie-breaking
                            last_block = potential_blockchain.get_latest_block()
                            self.logger.info(f"Found valid chain (length {length}) from {node}, quality score: {chain_quality}, has duplicates: {has_duplicates}")
                            
                            valid_chains[node] = {
                                'blockchain': potential_blockchain,
                                'length': length,
                                'last_block': last_block,
                                'has_duplicates': has_duplicates,
                                'quality_score': chain_quality,
                                'hash_value': chain_hash_value
                            }
                        else:
                            self.logger.warning(f"Chain from {node} (length {length}) is invalid")
                    else:
                        self.logger.debug(f"Chain from {node} (length {length}) significantly shorter than current chain ({current_chain_length})")
                else:
                    self.logger.warning(f"Unexpected status code fetching chain from {node}: {response.status_code}")
            except json.JSONDecodeError as e:
                self.logger.error(f"Failed to decode chain JSON from {node}: {e}")
            except Exception as e:
                self.logger.error(f"Error processing chain from {node}: {e}", exc_info=True)
        
        # Select the best chain based on quality, length, and other factors
        if valid_chains:
            # First, strongly prefer chains without duplicates
            chains_without_duplicates = {
                node: data for node, data in valid_chains.items()
                if not data['has_duplicates']
            }
            
            selected_chains = chains_without_duplicates if chains_without_duplicates else valid_chains
            
            if not chains_without_duplicates and any(data['has_duplicates'] for data in valid_chains.values()):
                self.logger.warning("All available chains have story position duplicates. Quality may be compromised.")
            
            # Now select based on chain quality and length
            best_chain = None
            best_score = float('-inf')
            best_hash_value = ""
            best_node = None
            
            for node, data in selected_chains.items():
                quality_score = data['quality_score']
                hash_value = data['hash_value']
                
                # Primary criteria: quality score
                # Secondary criteria (tiebreaker): lexicographically smaller hash
                if (quality_score > best_score) or (quality_score == best_score and hash_value < best_hash_value):
                    best_score = quality_score
                    best_hash_value = hash_value
                    best_chain = data
                    best_node = node
            
            if best_chain:
                longest_blockchain = best_chain['blockchain']
                longest_length = best_chain['length']
                has_duplicates = best_chain['has_duplicates']
                
                with self.lock:
                    # Evaluate our current chain
                    current_chain_quality, current_hash_value = self._evaluate_chain_quality(self.blockchain.chain)
                    current_has_duplicates = self._check_for_position_duplicates(self.blockchain.chain)
                    
                    self.logger.info(f"Our chain: length={len(self.blockchain.chain)}, quality={current_chain_quality}, hash={current_hash_value}, duplicates={current_has_duplicates}")
                    self.logger.info(f"Best chain: length={longest_length}, quality={best_score}, hash={best_hash_value}, duplicates={has_duplicates}")
                    
                    # Adopt the new chain if:
                    # 1. It has a higher quality score, OR
                    # 2. Same quality but better hash value tiebreaker
                    if (best_score > current_chain_quality) or (best_score == current_chain_quality and best_hash_value < current_hash_value):
                        old_chain_length = len(self.blockchain.chain)
                        self.blockchain.chain = longest_blockchain.chain
                        self.blockchain.difficulty = longest_blockchain.difficulty  # Update our difficulty too
                        
                        # Stop mining if we were mining (we're building on an outdated chain)
                        if self.is_mining:
                            self.logger.info("Stopping mining due to chain replacement")
                            self.stop_mining()
                        
                        self.logger.info(f"Replaced local chain (length {old_chain_length}, quality {current_chain_quality}) with chain from {best_node} (length {longest_length}, quality {best_score})")
                        # Save blockchain state after chain replacement
                        self._save_blockchain_state(f"replaced_chain_{longest_length}")
                        return True
                    else:
                        self.logger.info(f"Keeping our chain - it has higher quality ({current_chain_quality} vs {best_score}) or better hash value ({current_hash_value} vs {best_hash_value})")
            else:
                self.logger.info("No viable chains found from peers")
        else:
            self.logger.info("No valid chains found from peers")
        
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
            
            # Send discovery request to the target peer using robust request
            response = self._make_robust_request('post', 
                                               f"{target_peer}/discover",
                                               json={"address": self.address},
                                               max_retries=2)
            
            if not response:
                self.logger.warning(f"Failed to send discovery request to {target_peer} after retries")
                return False
                
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

            self.logger.info(f"Starting server at {self.address}")
            
            # Instead of Flask's built-in server, use Waitress for better concurrency
            # Import here to avoid affecting module-level dependencies
            try:
                from waitress import serve
                # Use 8 threads by default - adjust based on system capabilities
                num_threads = 8
                self.logger.info(f"Using Waitress server with {num_threads} threads")
                serve(self.app, host=self.host, port=self.port, threads=num_threads, 
                      ident=f"BlockBard_Node_{self.port}", url_scheme='http')
            except ImportError:
                # Fallback to Flask's built-in server if Waitress isn't available
                self.logger.warning("Waitress not available. Using Flask's built-in server instead.")
                self.logger.warning("This may lead to poor concurrency during mining. Install waitress for better performance.")
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

    def _make_robust_request(self, method, url, **kwargs):
        """
        Makes a network request with robust retry logic and exponential backoff.
        
        Args:
            method: 'get' or 'post'
            url: The URL to request
            **kwargs: Additional arguments to pass to requests
            
        Returns:
            The response object if successful, None otherwise
        """
        max_retries = kwargs.pop('max_retries', 3)
        backoff_factor = kwargs.pop('backoff_factor', 1.5) 
        base_timeout = kwargs.pop('base_timeout', 5)
        
        retry_count = 0
        request_func = getattr(requests, method.lower())
        
        while retry_count < max_retries:
            try:
                # Increase timeout slightly with each retry
                if 'timeout' not in kwargs:
                    kwargs['timeout'] = base_timeout + (retry_count * 2)
                
                self.logger.debug(f"Making {method.upper()} request to {url} (timeout: {kwargs.get('timeout')}s)")
                response = request_func(url, **kwargs)
                
                # Log the response status
                self.logger.debug(f"Response status: {response.status_code}")
                
                # Return the response regardless of status code
                # The caller should handle non-200 responses
                return response
                
            except requests.exceptions.Timeout:
                retry_count += 1
                if retry_count >= max_retries:
                    self.logger.error(f"Timeout error after {max_retries} attempts: {url}")
                    return None
                
                wait_time = backoff_factor ** retry_count
                self.logger.warning(f"Request timeout. Retrying in {wait_time:.2f}s (attempt {retry_count+1}/{max_retries}): {url}")
                time.sleep(wait_time)
                
            except requests.exceptions.ConnectionError:
                retry_count += 1
                if retry_count >= max_retries:
                    self.logger.error(f"Connection error after {max_retries} attempts: {url}")
                    return None
                
                wait_time = backoff_factor ** retry_count
                self.logger.warning(f"Connection error. Retrying in {wait_time:.2f}s (attempt {retry_count+1}/{max_retries}): {url}")
                time.sleep(wait_time)
                
            except Exception as e:
                self.logger.error(f"Error making request to {url}: {str(e)}")
                retry_count += 1
                if retry_count >= max_retries:
                    self.logger.error(f"Failed after {max_retries} attempts due to errors")
                    return None
                    
                wait_time = backoff_factor ** retry_count
                self.logger.warning(f"Request error. Retrying in {wait_time:.2f}s (attempt {retry_count+1}/{max_retries}): {url}")
                time.sleep(wait_time)
                
        return None

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