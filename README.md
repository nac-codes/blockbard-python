# BlockBard Blockchain Network

A blockchain-based collaborative storytelling platform where AI agents compete to contribute to an evolving narrative through proof-of-work mining.

## Features

- Blockchain implementation with proof of work (PoW) mining
- Peer-to-peer network with tracker-based peer discovery
- Node-to-node synchronization and conflict resolution
- Blockchain state persistence
- Automatic mining with story contribution pool
- Simulated AI storytellers that generate story segments
- Comprehensive logging system
- Support for distributed deployment across multiple machines

## Requirements

- Python 3.6+
- Flask
- Requests

## Installation

1. Clone the repository:
   ```
   git clone https://github.com/yourusername/block_bard_v2.git
   cd block_bard_v2
   ```

2. Install dependencies:
   ```
   pip install flask requests
   ```

3. Make scripts executable (optional):
   ```
   chmod +x run_collaborative_story.py ai_storyteller.py add_story_contribution.py
   ```

## Concept: Collaborative Storytelling Blockchain

BlockBard implements a collaborative storytelling system where:

1. Multiple AI agents (or human users) connect to the blockchain network
2. Each agent reads the current story from the blockchain
3. Agents generate story contributions based on the existing narrative
4. Agents must mine (solve a proof-of-work challenge) to add their contribution
5. The first agent to solve the mining puzzle gets to add their contribution
6. All nodes synchronize to maintain consensus on the story
7. The process repeats, building a collaborative narrative

## Running the Collaborative Storytelling System

### Quick Start: Complete System

The easiest way to run the complete system is with the `run_collaborative_story.py` script:

```bash
# Run with default settings (3 storytellers, 5s mining interval, 300s duration)
./run_collaborative_story.py

# Run with custom settings
./run_collaborative_story.py --storytellers 5 --interval 3 --duration 600
```

This script:
1. Starts a tracker for node discovery
2. Launches multiple blockchain nodes with auto-mining enabled
3. Connects simulated AI storytellers to each node
4. Monitors the story as it develops
5. Displays storyteller statistics and the complete story at the end

### Manual Setup: Component by Component

Alternatively, you can start each component manually:

#### 1. Start the Tracker Node

```bash
python main.py tracker --port 5500
```

#### 2. Start Blockchain Nodes

```bash
# Start storyteller nodes with auto-mining enabled
python main.py node --port 5501 --tracker http://localhost:5500 --auto-mine --mine-interval 5
python main.py node --port 5502 --tracker http://localhost:5500 --auto-mine --mine-interval 5
python main.py node --port 5503 --tracker http://localhost:5500 --auto-mine --mine-interval 5
```

#### 3. Start AI Storytellers

```bash
# Start AI storytellers connected to each node
python ai_storyteller.py --node http://localhost:5501 --author 1 --interval 15
python ai_storyteller.py --node http://localhost:5502 --author 2 --interval 15
python ai_storyteller.py --node http://localhost:5503 --author 3 --interval 15
```

## Adding Story Contributions Manually

You can also add story contributions manually using the `add_story_contribution.py` script:

```bash
# Add a random story contribution
./add_story_contribution.py --node http://localhost:5501

# Add a specific contribution with a specified author ID
./add_story_contribution.py --node http://localhost:5501 --author 42 --contribution "The magical sword began to glow, revealing hidden inscriptions along its blade."

# Add multiple random contributions with a delay between them
./add_story_contribution.py --node http://localhost:5501 --count 5 --interval 3

# Add a contribution and display the current story
./add_story_contribution.py --node http://localhost:5501 --print-story
```

## Testing the System

### Collaborative Storytelling Test

Test the collaborative storytelling system with competing AI agents:

```bash
./run_collaborative_story.py --storytellers 3 --duration 120
```

### Proof of Work Competition Test

Test the proof of work mining competition without AI agents:

```bash
python test_pow_competition.py
```

## AI Storyteller Agents

The `ai_storyteller.py` script provides a placeholder for real AI agents. Current implementation:

- Simulates AI using predefined templates and vocabulary
- Randomly generates story contributions based on the templates
- Monitors the blockchain and creates contextually relevant content
- Submits contributions to be mined by its blockchain node

To run a standalone AI storyteller agent:

```bash
# Run indefinitely with default settings
python ai_storyteller.py --node http://localhost:5501 --author 1

# Run for a specific duration
python ai_storyteller.py --node http://localhost:5501 --author 1 --duration 300

# Run with a custom interval between contributions
python ai_storyteller.py --node http://localhost:5501 --author 1 --interval 20
```

## Architecture

- `blockchain.py`: Core blockchain implementation with proof of work
- `node.py`: Blockchain node with networking capabilities and auto-mining
- `tracker.py`: Central tracker for peer discovery
- `main.py`: Entry point script with command-line interface
- `blockchain_storage.py`: Persistence for blockchain states
- `logging_util.py`: Logging configuration
- `ai_storyteller.py`: Simulated AI agent for story generation
- `add_story_contribution.py`: Tool for manually adding story contributions
- `run_collaborative_story.py`: Script for running the complete storytelling system
- `run_competing_miners.py`: Script for testing storytelling competition
- `test_pow_competition.py`: Testing proof of work competition

## Logs and Blockchain States

- Logs are stored in the `logs/` directory
- Blockchain states are saved in the `blockchain_states/` directory

## Extending the System

### Implementing Real AI Agents

To implement real AI-based storytellers:

1. Modify the `_generate_contribution()` method in `ai_storyteller.py`
2. Connect to a real AI model (e.g., GPT API)
3. Feed the existing story as context to the AI
4. Use the AI-generated text as the new contribution

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Disclaimer

This is an educational implementation and is not intended for production use. It lacks many features and security measures necessary for a real-world blockchain. 