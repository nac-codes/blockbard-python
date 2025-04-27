import json
import os
from pathlib import Path
import datetime
from blockchain import Blockchain

# Directory for storing blockchain states
BLOCKCHAIN_DIR = "blockchain_states"
Path(BLOCKCHAIN_DIR).mkdir(exist_ok=True)

def save_blockchain(blockchain, node_identifier):
    """
    Save a blockchain state to a file.
    
    Args:
        blockchain: The Blockchain instance to save
        node_identifier: Identifier for the node (e.g., 'node_5001')
        
    Returns:
        Path to the saved file
    """
    timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f"{node_identifier}_{timestamp}.json"
    filepath = os.path.join(BLOCKCHAIN_DIR, filename)
    
    with open(filepath, 'w') as f:
        f.write(blockchain.to_json())
    
    return filepath

def load_blockchain(filepath):
    """
    Load a blockchain state from a file.
    
    Args:
        filepath: Path to the blockchain JSON file
        
    Returns:
        A Blockchain instance
    """
    with open(filepath, 'r') as f:
        chain_json = f.read()
        
    return Blockchain.from_json(chain_json)

def list_blockchain_files(node_identifier=None):
    """
    List all blockchain state files, optionally filtered by node identifier.
    
    Args:
        node_identifier: Optional filter for node (e.g., 'node_5001')
        
    Returns:
        List of filepaths
    """
    all_files = [os.path.join(BLOCKCHAIN_DIR, f) for f in os.listdir(BLOCKCHAIN_DIR) 
                 if f.endswith('.json')]
    
    if node_identifier:
        return [f for f in all_files if node_identifier in f]
    return all_files

def get_latest_blockchain(node_identifier):
    """
    Get the most recent blockchain state for a specific node.
    
    Args:
        node_identifier: Node identifier (e.g., 'node_5001')
        
    Returns:
        Path to the most recent blockchain file, or None if none exists
    """
    files = list_blockchain_files(node_identifier)
    if not files:
        return None
        
    # Sort by timestamp (which is part of the filename)
    return sorted(files)[-1]

def compare_blockchains(node_identifiers, timestamp=None):
    """
    Compare blockchains from different nodes.
    
    Args:
        node_identifiers: List of node identifiers to compare
        timestamp: Optional timestamp to filter files
        
    Returns:
        A dictionary with comparison results
    """
    results = {
        "blockchains": {},
        "identical": True,
        "differences": []
    }
    
    reference_blockchain = None
    
    for node_id in node_identifiers:
        filepath = get_latest_blockchain(node_id)
        if not filepath:
            results["differences"].append(f"No blockchain file found for {node_id}")
            results["identical"] = False
            continue
            
        blockchain = load_blockchain(filepath)
        results["blockchains"][node_id] = {
            "filepath": filepath,
            "length": len(blockchain.chain),
            "blocks": [{"index": block.index, "hash": block.hash} for block in blockchain.chain]
        }
        
        if reference_blockchain is None:
            reference_blockchain = blockchain
        else:
            # Compare with reference blockchain
            if len(blockchain.chain) != len(reference_blockchain.chain):
                results["differences"].append(
                    f"Chain length mismatch: {node_id} has {len(blockchain.chain)} blocks vs reference {len(reference_blockchain.chain)}"
                )
                results["identical"] = False
            else:
                for i, (block, ref_block) in enumerate(zip(blockchain.chain, reference_blockchain.chain)):
                    if block.hash != ref_block.hash:
                        results["differences"].append(
                            f"Block {i} hash mismatch in {node_id}: {block.hash[:8]} vs reference {ref_block.hash[:8]}"
                        )
                        results["identical"] = False
    
    return results 