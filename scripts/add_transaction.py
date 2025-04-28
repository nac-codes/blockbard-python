#!/usr/bin/env python3
import argparse
import requests
import time
import random
import sys
import os

# Add the parent directory to sys.path so we can import modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def generate_random_transaction():
    """Generate a random transaction for testing purposes."""
    sender = f"User{random.randint(1, 100)}"
    receiver = f"User{random.randint(1, 100)}"
    amount = round(random.uniform(0.1, 100.0), 2)
    return f"TX-{time.time()}: {sender} sent {amount} coins to {receiver}"

def add_transaction(node_url, data=None):
    """Add a transaction to a blockchain node."""
    if not data:
        data = generate_random_transaction()
    
    print(f"Adding transaction to {node_url}: {data}")
    
    try:
        response = requests.post(
            f"{node_url}/add_transaction",
            json={"data": data},
            timeout=5
        )
        
        if response.status_code == 201:
            print(f"Transaction added successfully: {response.json()}")
            return True
        else:
            print(f"Failed to add transaction. Status: {response.status_code}, Response: {response.text}")
            return False
    except Exception as e:
        print(f"Error adding transaction: {e}")
        return False

def main():
    parser = argparse.ArgumentParser(description="Add transactions to a blockchain node")
    parser.add_argument("--node", default="http://localhost:5501", help="Node URL (default: http://localhost:5501)")
    parser.add_argument("--data", help="Transaction data (if not provided, random data will be generated)")
    parser.add_argument("--count", type=int, default=1, help="Number of transactions to add (default: 1)")
    parser.add_argument("--interval", type=float, default=0, help="Interval between transactions in seconds (default: 0)")
    
    args = parser.parse_args()
    
    success_count = 0
    for i in range(args.count):
        if i > 0 and args.interval > 0:
            time.sleep(args.interval)
            
        data = args.data if args.data else generate_random_transaction()
        if add_transaction(args.node, data):
            success_count += 1
    
    print(f"Added {success_count} out of {args.count} transactions successfully")
    return 0 if success_count == args.count else 1

if __name__ == "__main__":
    sys.exit(main()) 