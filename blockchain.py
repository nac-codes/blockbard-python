import hashlib
import datetime
import json

class Block:
    def __init__(self, index, timestamp, data, previous_hash):
        self.index = index
        self.timestamp = timestamp
        self.data = data
        self.previous_hash = previous_hash
        self.hash = self.calculate_hash()

    def calculate_hash(self):
        """Calculates the SHA-256 hash of the block's contents."""
        block_string = json.dumps(
            {
                "index": self.index,
                "timestamp": str(self.timestamp),
                "data": self.data,
                "previous_hash": self.previous_hash,
            },
            sort_keys=True,
        ).encode()
        return hashlib.sha256(block_string).hexdigest()

    def __repr__(self):
        return f"Block(Index: {self.index}, Timestamp: {self.timestamp}, Data: {self.data[:20]}..., Prev Hash: {self.previous_hash[:8]}, Hash: {self.hash[:8]})"


class Blockchain:
    def __init__(self):
        self.chain = [self.create_genesis_block()]
        # In a real scenario, difficulty would adjust. Start fixed.
        self.difficulty = 2 # Number of leading zeros required for a valid hash

    def create_genesis_block(self):
        """Creates the first block in the chain."""
        # Use a fixed timestamp for the genesis block to ensure consistency
        genesis_timestamp = datetime.datetime(2025, 1, 1, 0, 0, 0)
        return Block(0, genesis_timestamp, "Genesis Block", "0")

    def get_latest_block(self):
        """Returns the most recent block in the chain."""
        return self.chain[-1]

    def mine_block(self, data):
        """
        Creates a new block to be added to the chain.
        In a real blockchain, this involves solving a computational puzzle (Proof-of-Work).
        Here, we simulate mining by creating a block and calculating its hash.
        We'll add Proof-of-Work later if needed.
        """
        previous_block = self.get_latest_block()
        new_index = previous_block.index + 1
        new_timestamp = datetime.datetime.now()
        new_block = Block(new_index, new_timestamp, data, previous_block.hash)
        # Basic Proof-of-Work simulation (we'll make this real later)
        # For now, we just create it. PoW would involve finding a 'nonce'
        # such that the block's hash meets the difficulty requirement.
        print(f"Simulated mining of block {new_index}")
        return new_block


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
        """Validates a new block."""
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

        # Later: Add Proof-of-Work validation here
        # if not new_block.hash.startswith('0' * self.difficulty):
        #     print(f"Validation Error: Block hash {new_block.hash} does not meet difficulty {self.difficulty}")
        #     return False

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
                "hash": block.hash
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
                previous_hash=block_data["previous_hash"]
                # Note: We trust the hash from the JSON for simplicity here.
                # In a real system, you might recalculate/verify.
            )
            # Manually set the hash from the loaded data
            block.hash = block_data["hash"]
            blockchain.chain.append(block)
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