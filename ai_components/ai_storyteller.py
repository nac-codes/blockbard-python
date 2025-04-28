#!/usr/bin/env python3
import argparse
import requests
import time
import random
import sys
import threading
import os

# Add the parent directory to sys.path so we can import modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

class AIStoryteller:
    """
    A placeholder for a real AI agent that generates story contributions
    based on the current blockchain state.
    
    This simulates an AI agent by randomly selecting from predefined
    contributions or generating simple random text.
    """
    
    def __init__(self, node_url, author_id, mine_interval=5):
        self.node_url = node_url
        self.author_id = author_id
        self.mine_interval = mine_interval
        self.running = False
        self.story_thread = None
        
        # Sample story contributions that the "AI" can choose from
        self.story_templates = [
            "The {adj} {character} discovered a {object} hidden in the {location}.",
            "A {adj} storm swept across the {location}, forcing the {character} to seek shelter.",
            "The {character} revealed a secret about the {object} that changed everything.",
            "Using the {object}, the {character} was able to unlock the {location}.",
            "The {character} and the others gathered in the {location} to discuss their next move.",
            "A {adj} sound echoed from the {location}, alerting the {character}.",
            "The {character} remembered a legend about a {adj} {object} with incredible powers.",
            "Night fell over the {location}, and the {character} kept watch while the others slept.",
            "The {character} discovered that the {object} was not what it seemed.",
            "A message from the ancient {character} was found inscribed on the {object}."
        ]
        
        # Vocabulary for filling in the templates
        self.vocab = {
            "adj": ["mysterious", "ancient", "magical", "dark", "bright", "hidden", "sacred", "forgotten", 
                   "enchanted", "powerful", "strange", "glowing", "shadowy", "crystalline", "ethereal"],
            "character": ["wizard", "guardian", "traveler", "oracle", "warrior", "scholar", "healer", 
                         "artificer", "bard", "ranger", "mystic", "elder", "apprentice", "seer", "exile"],
            "object": ["artifact", "scroll", "key", "crystal", "book", "map", "amulet", "sword", "staff",
                      "orb", "ring", "pendant", "compass", "journal", "tablet", "relic", "gem"],
            "location": ["temple", "cave", "forest", "island", "tower", "ruins", "library", "sanctuary",
                        "labyrinth", "mountain", "valley", "palace", "village", "gateway", "observatory"]
        }
    
    def _get_current_story(self):
        """Get the current state of the story from the blockchain."""
        try:
            response = requests.get(f"{self.node_url}/get_chain", timeout=5)
            if response.status_code == 200:
                return response.json()
            else:
                print(f"Failed to get story state: {response.status_code}")
                return None
        except Exception as e:
            print(f"Error getting story state: {e}")
            return None
    
    def _generate_contribution(self, blockchain=None):
        """
        Generate a story contribution based on the current blockchain state.
        
        In a real implementation, this would analyze the existing story and
        generate a coherent continuation using an actual AI model.
        """
        # Get the current blockchain if not provided
        if blockchain is None:
            blockchain = self._get_current_story()
        
        # Extract existing story for context (would be used by a real AI)
        existing_story = []
        if blockchain:
            for block in blockchain:
                if block["index"] > 0:  # Skip genesis block
                    existing_story.append(block["data"])
        
        # In a real implementation, we would pass existing_story to an AI model
        # For this placeholder, just select a random template and fill it
        template = random.choice(self.story_templates)
        
        # Fill in the template with random vocabulary
        contribution = template.format(
            adj=random.choice(self.vocab["adj"]),
            character=random.choice(self.vocab["character"]),
            object=random.choice(self.vocab["object"]),
            location=random.choice(self.vocab["location"])
        )
        
        # Format with author attribution
        return f"Author {self.author_id} says: {contribution}"
    
    def _submit_contribution(self, contribution):
        """Submit a story contribution to the blockchain node."""
        try:
            response = requests.post(
                f"{self.node_url}/add_transaction",  # Using existing endpoint for compatibility
                json={"data": contribution},
                timeout=5
            )
            
            if response.status_code == 201:
                print(f"Contribution submitted: {contribution[:50]}...")
                return True
            else:
                print(f"Failed to submit contribution: {response.status_code}")
                return False
        except Exception as e:
            print(f"Error submitting contribution: {e}")
            return False
    
    def _storytelling_loop(self):
        """Background thread that periodically generates and submits story contributions."""
        while self.running:
            try:
                # Get current blockchain state
                blockchain = self._get_current_story()
                
                if blockchain:
                    # Generate a contribution based on the current state
                    contribution = self._generate_contribution(blockchain)
                    
                    # Submit the contribution to the node
                    self._submit_contribution(contribution)
                
                # Wait for the specified interval
                for _ in range(self.mine_interval * 2):  # Check running flag more frequently
                    if not self.running:
                        break
                    time.sleep(0.5)
                    
            except Exception as e:
                print(f"Error in storytelling loop: {e}")
                time.sleep(5)  # Wait longer after an error
    
    def start(self):
        """Start the AI storyteller agent."""
        if self.story_thread and self.story_thread.is_alive():
            print("Storyteller is already running")
            return
        
        print(f"Starting AI Storyteller (Author {self.author_id}) connected to {self.node_url}")
        self.running = True
        self.story_thread = threading.Thread(target=self._storytelling_loop, daemon=True)
        self.story_thread.start()
    
    def stop(self):
        """Stop the AI storyteller agent."""
        print(f"Stopping AI Storyteller (Author {self.author_id})")
        self.running = False
        if self.story_thread:
            self.story_thread.join(timeout=2)

def main():
    parser = argparse.ArgumentParser(description="Run an AI storyteller agent for the BlockBard blockchain")
    parser.add_argument("--node", default="http://localhost:5501", help="Node URL (default: http://localhost:5501)")
    parser.add_argument("--author", type=int, default=None, help="Author ID (random if not provided)")
    parser.add_argument("--interval", type=int, default=10, help="Interval between contributions in seconds (default: 10)")
    parser.add_argument("--duration", type=int, default=0, help="How long to run in seconds (0 = indefinitely, default: 0)")
    
    args = parser.parse_args()
    
    # Generate a random author ID if not provided
    author_id = args.author if args.author is not None else random.randint(1, 100)
    
    # Create and start the AI storyteller
    storyteller = AIStoryteller(
        node_url=args.node,
        author_id=author_id,
        mine_interval=args.interval
    )
    
    try:
        storyteller.start()
        
        if args.duration > 0:
            print(f"AI Storyteller will run for {args.duration} seconds")
            time.sleep(args.duration)
            storyteller.stop()
        else:
            print("AI Storyteller running indefinitely. Press Ctrl+C to stop.")
            while True:
                time.sleep(1)
                
    except KeyboardInterrupt:
        print("\nStopping AI Storyteller")
    finally:
        storyteller.stop()
    
    return 0

if __name__ == "__main__":
    sys.exit(main()) 