import hashlib
import datetime
import json
import time
import random

class Block:
    def __init__(self, index, timestamp, data, previous_hash, difficulty=0, nonce=0):
        self.index = index
        self.timestamp = timestamp
        self.data = data
        self.previous_hash = previous_hash
        self.difficulty = difficulty  # Store difficulty in each block
        self.nonce = nonce  # For proof of work
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
            },
            sort_keys=True,
        ).encode()
        return hashlib.sha256(block_string).hexdigest()

    def __repr__(self):
        return f"Block(Index: {self.index}, Timestamp: {self.timestamp}, Data: {self.data[:20]}..., Prev Hash: {self.previous_hash[:8]}, Hash: {self.hash[:8]}, Difficulty: {self.difficulty}, Nonce: {self.nonce})"


class Blockchain:
    def __init__(self, genesis_data=None):
        # Initialize difficulty first before using it
        self.difficulty = 2  # Number of leading zeros required for a valid hash
        self.mining_reward = 1.0  # Optional: reward for mining a block
        self.block_generation_interval = 10  # Target time between blocks in seconds
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
        
        # Create a new block with the current difficulty
        new_block = Block(
            new_index, 
            new_timestamp, 
            data, 
            previous_block.hash,
            difficulty=self.difficulty
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

    def is_valid_new_block(self, new_block, previous_block):
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

        return True

    def is_valid_chain(self, chain_to_validate=None):
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
            if not self.is_valid_new_block(current_block, previous_block):
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
                "nonce": block.nonce
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
                nonce=block_data.get("nonce", 0)
            )
            # Manually set the hash from the loaded data
            block.hash = block_data["hash"]
            blockchain.chain.append(block)
            
        # Set blockchain difficulty to the most recent block's difficulty
        if blockchain.chain:
            blockchain.difficulty = blockchain.chain[-1].difficulty
            
        return blockchain

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