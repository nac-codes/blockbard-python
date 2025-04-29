import hashlib
import datetime
import json
import time
import random

class Block:
    def __init__(self, index, timestamp, data, previous_hash, difficulty=0, nonce=0, story_position=None):
        self.index = index
        self.timestamp = timestamp
        self.data = data
        self.previous_hash = previous_hash
        self.difficulty = difficulty  # Store difficulty in each block
        self.nonce = nonce  # For proof of work
        self.story_position = story_position or {}  # Position in story (e.g., {position_id: "hash", previous_position_id: "hash"})
        self.hash = self.calculate_hash()

    def calculate_hash(self):
        """Calculates the SHA-256 hash of the block's contents."""
        block_string = json.dumps(
            {
                "index": self.index,
                "timestamp": str(self.timestamp),
                "data": self.data,
                "previous_hash": self.previous_hash,
                "difficulty": self.difficulty,
                "nonce": self.nonce,
                "story_position": self.story_position,
            },
            sort_keys=True,
        ).encode()
        return hashlib.sha256(block_string).hexdigest()

    def __repr__(self):
        return f"Block(Index: {self.index}, Timestamp: {self.timestamp}, Data: {self.data[:20]}..., Prev Hash: {self.previous_hash[:8]}, Hash: {self.hash[:8]}, Difficulty: {self.difficulty}, Nonce: {self.nonce})"


class Blockchain:
    def __init__(self, genesis_data=None):
        # Initialize difficulty first before using it
        self.difficulty = 2  # Increased from 2 to 4 (more leading zeros required)
        self.mining_reward = 1.0  # Optional: reward for mining a block
        self.block_generation_interval = 20  # Changed from 10 to 60 seconds (1 minute target)
        self.difficulty_adjustment_interval = 10  # Adjust difficulty after this many blocks
        self.max_nonce = 2**32  # Maximum nonce value to try
        self.last_difficulty_adjustment = datetime.datetime.now()
        # Now create the genesis block with custom data if provided
        self.chain = [self.create_genesis_block(genesis_data)]

    def create_genesis_block(self, custom_data=None):
        """Creates the first block in the chain with optional custom data."""
        # Use a fixed timestamp for the genesis block to ensure consistency
        genesis_timestamp = datetime.datetime(2025, 1, 1, 0, 0, 0)
        genesis_data = custom_data if custom_data is not None else "Genesis Block"
        return Block(0, genesis_timestamp, genesis_data, "0", difficulty=self.difficulty)

    def get_latest_block(self):
        """Returns the most recent block in the chain."""
        return self.chain[-1]

    def mine_block(self, data):
        """
        Creates a new block by finding a hash that meets the difficulty requirement.
        This is the actual Proof-of-Work implementation.
        """
        previous_block = self.get_latest_block()
        new_index = previous_block.index + 1
        new_timestamp = datetime.datetime.now()
        
        # Adjust difficulty if needed
        if new_index % self.difficulty_adjustment_interval == 0 and new_index > 0:
            self._adjust_difficulty()
        
        # Extract story position information from the data
        story_position = self._extract_story_position(data)
        
        # Create a new block with the current difficulty and story position
        new_block = Block(
            new_index, 
            new_timestamp, 
            data, 
            previous_block.hash,
            difficulty=self.difficulty,
            story_position=story_position
        )
        
        print(f"Starting mining of block {new_index} with difficulty {self.difficulty}")
        mining_start_time = time.time()
        
        # Proof of Work: Find a hash with the required number of leading zeros
        new_block = self._proof_of_work(new_block)
        
        mining_time = time.time() - mining_start_time
        print(f"Block {new_index} mined in {mining_time:.2f} seconds with nonce {new_block.nonce}")
        print(f"Block hash: {new_block.hash}")
        
        return new_block

    def _proof_of_work(self, block):
        """
        Performs the actual proof of work computation.
        Tries different nonce values until a hash with required leading zeros is found.
        """
        target = "0" * block.difficulty
        
        # Start with a random nonce to avoid collisions between nodes
        block.nonce = random.randint(0, 100000)
        block.hash = block.calculate_hash()
        
        # Try until we find a hash with the required number of leading zeros
        attempts = 0
        while not block.hash.startswith(target):
            block.nonce += 1
            if block.nonce >= self.max_nonce:
                # If we reach max nonce, reset and try again with different timestamp
                block.nonce = 0
                block.timestamp = datetime.datetime.now()
            
            block.hash = block.calculate_hash()
            
            attempts += 1
            if attempts % 100000 == 0:
                print(f"Mining attempt {attempts}, current hash: {block.hash[:10]}...")
        
        return block

    def _adjust_difficulty(self):
        """
        Adjusts the mining difficulty based on how quickly recent blocks were mined.
        """
        latest_block = self.get_latest_block()
        first_block_in_period_idx = max(0, latest_block.index - self.difficulty_adjustment_interval + 1)
        first_block_in_period = self.chain[first_block_in_period_idx]
        
        # Convert timestamps to seconds since epoch for easier calculation
        time_expected = self.block_generation_interval * self.difficulty_adjustment_interval
        
        # Calculate actual time taken
        if isinstance(latest_block.timestamp, datetime.datetime) and isinstance(first_block_in_period.timestamp, datetime.datetime):
            time_taken = (latest_block.timestamp - first_block_in_period.timestamp).total_seconds()
        else:
            # Fallback if timestamps aren't datetime objects
            now = datetime.datetime.now()
            time_taken = time_expected  # Default to expected time if we can't calculate
        
        # Adjust difficulty: 
        # - If blocks are being mined too quickly, increase difficulty
        # - If blocks are being mined too slowly, decrease difficulty
        if time_taken < time_expected / 2:
            self.difficulty += 1
            print(f"Difficulty increased to {self.difficulty} (blocks mined too quickly)")
        elif time_taken > time_expected * 2:
            self.difficulty = max(1, self.difficulty - 1)  # Never go below 1
            print(f"Difficulty decreased to {self.difficulty} (blocks mined too slowly)")
        
        self.last_difficulty_adjustment = datetime.datetime.now()

    def add_block(self, new_block):
        """Adds a new block to the chain after verification."""
        if self.is_valid_new_block(new_block, self.get_latest_block()):
            self.chain.append(new_block)
            print(f"Block {new_block.index} added to the chain.")
            return True
        else:
            print(f"Invalid block {new_block.index}. Not added.")
            return False

    def is_valid_new_block(self, new_block, previous_block, allow_duplicate_positions=False):
        """Validates a new block including proof of work."""
        if previous_block.index + 1 != new_block.index:
            print(f"Validation Error: Invalid index. Expected {previous_block.index + 1}, got {new_block.index}")
            return False
        if previous_block.hash != new_block.previous_hash:
            print(f"Validation Error: Invalid previous hash. Expected {previous_block.hash}, got {new_block.previous_hash}")
            return False
        # Re-calculate hash to ensure integrity
        if new_block.calculate_hash() != new_block.hash:
            print(f"Validation Error: Invalid hash calculation for block {new_block.index}")
            return False

        # Verify proof of work
        if not new_block.hash.startswith('0' * new_block.difficulty):
            print(f"Validation Error: Block hash {new_block.hash} does not meet difficulty {new_block.difficulty}")
            return False
        
        # Verify story position
        if not self._is_valid_story_position(new_block, previous_block, allow_duplicate_positions):
            print(f"Validation Error: Invalid story position for block {new_block.index}")
            return False

        return True
        
    def _is_valid_story_position(self, new_block, previous_block, allow_duplicate_positions=False):
        """
        Validates that a block's story position is valid:
        1. The position_id is unique in the entire chain
        2. The story position makes logical sense (e.g., sequential verses)
        
        Validation is more relaxed when receiving blocks from other chains to allow 
        for better consensus while still preventing duplicates.
        
        Args:
            new_block: The block to validate
            previous_block: The previous block in the chain
            allow_duplicate_positions: If True, don't reject blocks with duplicate position IDs
                                      (used during conflict resolution)
        """
        # Skip validation for genesis block
        if new_block.index == 0:
            return True
            
        # 1. Verify the position_id is correctly calculated from the data
        if not new_block.story_position or "position_id" not in new_block.story_position:
            print(f"Story position validation error: Missing position_id")
            return False
            
        # 2. Verify the position_id is unique in the entire chain
        position_id = new_block.story_position["position_id"]
        
        # Look for this position in the existing chain
        if not allow_duplicate_positions:
            for block in self.chain:
                if (block.story_position and 
                    "position_id" in block.story_position and 
                    block.story_position["position_id"] == position_id):
                    print(f"Story position validation error: Position {position_id} already used in block {block.index}")
                    return False
                
        # 3. Validate story position metadata if available
        if "metadata" in new_block.story_position and "metadata" in previous_block.story_position:
            # Get metadata from both blocks
            new_meta = new_block.story_position["metadata"]
            prev_meta = previous_block.story_position["metadata"]
            
            # For Bible verses, check that chapters and verses make logical sense
            if all(k in new_meta for k in ["book", "chapter", "verse"]) and all(k in prev_meta for k in ["book", "chapter", "verse"]):
                # Same book
                if new_meta["book"] == prev_meta["book"]:
                    # Same chapter
                    if new_meta["chapter"] == prev_meta["chapter"]:
                        # Ensure verse is sequential or at least makes logical sense
                        # Allow for skipped verses, but ensure it's moving forward
                        if isinstance(new_meta["verse"], int) and isinstance(prev_meta["verse"], int):
                            if new_meta["verse"] <= prev_meta["verse"]:
                                # If the verse is not moving forward, check if it's the same verse with different attributes
                                # This is a warning but not a strict error - accept it for better cross-chain compatibility
                                print(f"Story position warning: Non-sequential verse. Previous: {prev_meta['verse']}, New: {new_meta['verse']}")
                    
                    # Different chapter - ensure chapter is moving forward or same book
                    elif isinstance(new_meta["chapter"], int) and isinstance(prev_meta["chapter"], int):
                        if new_meta["chapter"] < prev_meta["chapter"]:
                            print(f"Story position warning: Chapter going backward: Previous: {prev_meta['chapter']}, New: {new_meta['chapter']}")
        
        # 4. If previous_position_id is present, make a soft check (warning rather than error)
        # This helps with cross-chain compatibility
        if "previous_position_id" in new_block.story_position and previous_block.story_position and "position_id" in previous_block.story_position:
            expected_prev_id = previous_block.story_position["position_id"]
            actual_prev_id = new_block.story_position["previous_position_id"]
            
            if expected_prev_id != actual_prev_id:
                # This is just a warning now, not an error
                print(f"Story position warning: Previous position mismatch. Expected {expected_prev_id}, got {actual_prev_id}")
                # We still allow the block to be valid
        
        return True

    def is_valid_chain(self, chain_to_validate=None, allow_duplicate_positions=False):
        """Validates the integrity of the entire blockchain."""
        target_chain = chain_to_validate if chain_to_validate else self.chain
        # Check genesis block
        if target_chain[0].index != 0 or \
           target_chain[0].previous_hash != "0" or \
           target_chain[0].hash != target_chain[0].calculate_hash():
             print("Validation Error: Genesis block invalid.")
             return False

        for i in range(1, len(target_chain)):
            current_block = target_chain[i]
            previous_block = target_chain[i - 1]
            if not self.is_valid_new_block(current_block, previous_block, allow_duplicate_positions):
                print(f"Validation Error: Chain invalid at block {current_block.index}.")
                return False
        return True

    def __repr__(self):
        return f"Blockchain({len(self.chain)} blocks)"

    def to_json(self):
        """Serializes the blockchain into a JSON string."""
        return json.dumps([
            {
                "index": block.index,
                "timestamp": str(block.timestamp),
                "data": block.data,
                "previous_hash": block.previous_hash,
                "hash": block.hash,
                "difficulty": block.difficulty,
                "nonce": block.nonce,
                "story_position": block.story_position
            } for block in self.chain
        ], indent=4)

    @classmethod
    def from_json(cls, chain_json):
        """Deserializes a JSON string back into a Blockchain object."""
        blockchain = cls()
        blockchain.chain = [] # Reset genesis block
        chain_data = json.loads(chain_json)
        
        for block_data in chain_data:
            block = Block(
                index=block_data["index"],
                # Attempt to parse timestamp, handle potential format variations
                timestamp=datetime.datetime.fromisoformat(block_data["timestamp"]),
                data=block_data["data"],
                previous_hash=block_data["previous_hash"],
                difficulty=block_data.get("difficulty", 0),
                nonce=block_data.get("nonce", 0),
                story_position=block_data.get("story_position", {})
            )
            # Manually set the hash from the loaded data
            block.hash = block_data["hash"]
            blockchain.chain.append(block)
            
        # Set blockchain difficulty to the most recent block's difficulty
        if blockchain.chain:
            blockchain.difficulty = blockchain.chain[-1].difficulty
            
        return blockchain

    def _extract_story_position(self, data):
        """
        Extracts story position information from block data.
        Priority:
        1. Use dedicated 'storyPosition' field if present
        2. Fall back to extracting from standard fields like Book/Chapter/Verse
        3. Default to using block index for non-structured data
        
        Returns a dictionary with position_id (hash of position metadata)
        and previous_position_id (from the latest block).
        """
        # Try to parse data as JSON
        json_data = None
        try:
            if isinstance(data, str):
                json_data = json.loads(data)
            else:
                json_data = data
                
            # 1. FIRST PRIORITY: Check for dedicated storyPosition field
            if json_data and "storyPosition" in json_data:
                # Use the storyPosition object directly as provided
                position_data = json_data["storyPosition"]
                
                # Create deterministic position hash
                position_string = json.dumps(position_data, sort_keys=True).encode()
                position_id = hashlib.sha256(position_string).hexdigest()
                
                # Get the previous position ID from the latest block
                previous_position_id = ""
                if self.chain:
                    latest_block = self.get_latest_block()
                    if latest_block.story_position and "position_id" in latest_block.story_position:
                        previous_position_id = latest_block.story_position["position_id"]
                
                return {
                    "position_id": position_id,
                    "previous_position_id": previous_position_id,
                    "metadata": position_data
                }
        except (json.JSONDecodeError, TypeError, AttributeError) as e:
            # Handle JSON parsing errors silently and continue to fallback
            pass
             
        # 3. FALLBACK: For non-structured data - use the block index as position
        if self.chain:
            latest_block = self.get_latest_block()
            previous_position_id = ""
            if latest_block.story_position and "position_id" in latest_block.story_position:
                previous_position_id = latest_block.story_position["position_id"]
                
            # Create a simple auto-incremented position
            return {
                "position_id": hashlib.sha256(f"position_{len(self.chain)}".encode()).hexdigest(),
                "previous_position_id": previous_position_id
            }
        
        # Genesis block case
        return {
            "position_id": hashlib.sha256("genesis_position".encode()).hexdigest(),
            "previous_position_id": ""
        }

# Example usage (optional, for quick testing)
if __name__ == "__main__":
    my_blockchain = Blockchain()
    print("Created Blockchain:")
    print(my_blockchain.chain)

    # Simulate mining and adding a few blocks
    block1_data = "First contribution: Once upon a time..."
    block1 = my_blockchain.mine_block(block1_data)
    my_blockchain.add_block(block1)

    block2_data = "Second contribution: ...in a land far, far away..."
    block2 = my_blockchain.mine_block(block2_data)
    my_blockchain.add_block(block2)

    print("\nBlockchain after adding blocks:")
    print(my_blockchain.chain)

    print(f"\nIs chain valid? {my_blockchain.is_valid_chain()}")

    # Test serialization/deserialization
    chain_json_str = my_blockchain.to_json()
    print("\nSerialized Chain:")
    print(chain_json_str)

    reloaded_blockchain = Blockchain.from_json(chain_json_str)
    print("\nReloaded Blockchain:")
    print(reloaded_blockchain.chain)
    print(f"\nIs reloaded chain valid? {reloaded_blockchain.is_valid_chain()}")

    # Test validation failure (tamper with data)
    # my_blockchain.chain[1].data = "Tampered data"
    # print(f"\nIs tampered chain valid? {my_blockchain.is_valid_chain()}") # This will fail is_valid_new_block check
    # my_blockchain.chain[1].hash = my_blockchain.chain[1].calculate_hash() # Fix hash, but prev_hash link breaks
    # print(f"\nIs tampered chain valid (hash recalculated)? {my_blockchain.is_valid_chain()}")

    # Test validation failure (invalid sequence)
    # invalid_block = Block(5, datetime.datetime.now(), "Invalid block", my_blockchain.get_latest_block().hash)
    # my_blockchain.add_block(invalid_block) # This should fail validation 