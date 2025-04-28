#!/usr/bin/env python3
import argparse
import requests
import time
import random
import sys

# Sample story contributions that can be randomly selected
SAMPLE_CONTRIBUTIONS = [
    "The sun rose over the floating islands, casting long shadows across the crystalline structures.",
    "A mysterious figure appeared at the edge of the central island, cloaked in shimmering fabric.",
    "The ancient AI guardian activated its defense systems as the intruders approached.",
    "Two unlikely allies joined forces to navigate the treacherous path between the islands.",
    "A hidden map revealed the location of the realm's most precious artifact.",
    "The storm intensified, threatening to tear the smaller islands from their moorings.",
    "A forgotten technology was discovered in the ruins beneath the main island.",
    "The characters shared their stories around a magical fire that burned without fuel.",
    "A betrayal was revealed that changed the course of the adventure.",
    "The floating islands began to align, creating a pathway to a previously unseen location.",
    "An ancient prophecy began to unfold as the final piece of the puzzle was found.",
    "The characters faced their greatest fear in the heart of the island labyrinth.",
    "A sacrifice was made that saved the realm from certain destruction."
]

def generate_random_contribution(author_id):
    """Generate a random story contribution for testing purposes."""
    if SAMPLE_CONTRIBUTIONS:
        contribution = random.choice(SAMPLE_CONTRIBUTIONS)
    else:
        # Generate random text if no samples are available
        contribution = "".join(random.choice("abcdefghijklmnopqrstuvwxyz ,.!?") for _ in range(50))
    
    return f"Author {author_id} says: {contribution}"

def add_story_contribution(node_url, author_id=None, contribution=None):
    """Add a story contribution to a blockchain node."""
    if author_id is None:
        author_id = random.randint(1, 10)
        
    if not contribution:
        story_data = generate_random_contribution(author_id)
    else:
        story_data = f"Author {author_id} says: {contribution}"
    
    print(f"Adding story contribution to {node_url}:")
    print(f"  {story_data}")
    
    try:
        response = requests.post(
            f"{node_url}/add_transaction",  # Still using add_transaction endpoint for compatibility
            json={"data": story_data},
            timeout=5
        )
        
        if response.status_code == 201:
            print(f"Contribution added successfully: {response.json()}")
            return True
        else:
            print(f"Failed to add contribution. Status: {response.status_code}, Response: {response.text}")
            return False
    except Exception as e:
        print(f"Error adding contribution: {e}")
        return False

def get_story(node_url):
    """Get the current story from the blockchain."""
    try:
        response = requests.get(f"{node_url}/get_chain", timeout=5)
        if response.status_code == 200:
            blockchain = response.json()
            
            print("\n=== CURRENT STORY ===\n")
            # Skip genesis block and print each contribution
            for block in blockchain:
                if block["index"] > 0:  # Skip genesis block
                    print(f"Chapter {block['index']}:")
                    print(f"{block['data']}")
                    print()  # Empty line between contributions
            
            return True
        else:
            print(f"Failed to get story. Status: {response.status_code}")
            return False
    except Exception as e:
        print(f"Error getting story: {e}")
        return False

def main():
    parser = argparse.ArgumentParser(description="Add story contributions to the BlockBard blockchain")
    parser.add_argument("--node", default="http://localhost:5501", help="Node URL (default: http://localhost:5501)")
    parser.add_argument("--author", type=int, help="Author ID (random if not provided)")
    parser.add_argument("--contribution", help="Story contribution text (random if not provided)")
    parser.add_argument("--count", type=int, default=1, help="Number of contributions to add (default: 1)")
    parser.add_argument("--interval", type=float, default=2, help="Interval between contributions in seconds (default: 2)")
    parser.add_argument("--print-story", action="store_true", help="Print the current story after adding contributions")
    
    args = parser.parse_args()
    
    success_count = 0
    for i in range(args.count):
        if i > 0 and args.interval > 0:
            print(f"Waiting {args.interval} seconds before next contribution...")
            time.sleep(args.interval)
            
        if add_story_contribution(args.node, args.author, args.contribution):
            success_count += 1
    
    print(f"Added {success_count} out of {args.count} contributions successfully")
    
    if args.print_story:
        print("\nRetrieving current story...")
        get_story(args.node)
    
    return 0 if success_count == args.count else 1

if __name__ == "__main__":
    sys.exit(main()) 