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
- OpenAI
- PyYAML (for YAML config files)

## Installation

1. Clone the repository:
   ```
   git clone https://github.com/yourusername/block_bard_v2.git
   cd block_bard_v2
   ```

2. **Recommended:** Set up a Python virtual environment:
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # On Linux/macOS
   # or
   .\venv\Scripts\activate    # On Windows
   ```

3. Install dependencies using the requirements file:
   ```
   pip install -r requirements.txt
   ```

4. Make scripts executable (optional):
   ```
   chmod +x scripts/*.py ai_components/*.py
   ```

## Project Structure

```
block_bard_v2/
├── core/                     # Core blockchain implementation
│   ├── blockchain.py         # Blockchain data structure with PoW
│   ├── blockchain_storage.py # Blockchain persistence
│   ├── node.py               # Blockchain node implementation
│   └── tracker.py            # Node discovery tracker
├── ai_components/            # AI storytelling components
│   ├── ai_storyteller.py     # Simulated AI agent
│   └── add_story_contribution.py # Manual story contribution tool
├── scripts/                  # Executable scripts
│   ├── run_collaborative_story.py # Run complete storytelling system
│   ├── run_competing_miners.py    # Test competing miners
│   └── add_transaction.py         # Add transaction utility
├── tests/                    # Test scripts
│   ├── test_pow_competition.py    # Test PoW mining
│   ├── test_sync.py               # Test node synchronization
│   └── simple_test.py             # Basic functionality test
├── utils/                    # Utilities
│   ├── logging_util.py       # Logging configuration
│   └── cleanup.py            # Process cleanup utility
├── logs/                     # Log files directory
├── blockchain_states/        # Blockchain state snapshots
└── main.py                   # Main entry point
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
python scripts/run_collaborative_story.py

# Run with custom settings
python scripts/run_collaborative_story.py --storytellers 5 --interval 3 --duration 600
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
python ai_components/ai_storyteller.py --node http://localhost:5501 --author 1 --interval 15
python ai_components/ai_storyteller.py --node http://localhost:5502 --author 2 --interval 15
python ai_components/ai_storyteller.py --node http://localhost:5503 --author 3 --interval 15
```

## Adding Story Contributions Manually

You can also add story contributions manually using the `add_story_contribution.py` script:

```bash
# Add a random story contribution
python ai_components/add_story_contribution.py --node http://localhost:5501

# Add a specific contribution with a specified author ID
python ai_components/add_story_contribution.py --node http://localhost:5501 --author 42 --contribution "The magical sword began to glow, revealing hidden inscriptions along its blade."

# Add multiple random contributions with a delay between them
python ai_components/add_story_contribution.py --node http://localhost:5501 --count 5 --interval 3

# Add a contribution and display the current story
python ai_components/add_story_contribution.py --node http://localhost:5501 --print-story
```

## Testing the System

### Collaborative Storytelling Test

Test the collaborative storytelling system with competing AI agents:

```bash
python scripts/run_collaborative_story.py --storytellers 3 --duration 120
```

### Proof of Work Competition Test

Test the proof of work mining competition without AI agents:

```bash
python tests/test_pow_competition.py
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
python ai_components/ai_storyteller.py --node http://localhost:5501 --author 1

# Run for a specific duration
python ai_components/ai_storyteller.py --node http://localhost:5501 --author 1 --duration 300

# Run with a custom interval between contributions
python ai_components/ai_storyteller.py --node http://localhost:5501 --author 1 --interval 20
```

## Core Components

### Blockchain (`core/blockchain.py`)
Contains the `Block` and `Blockchain` classes that implement the core data structure with proof-of-work.

### Node (`core/node.py`)
Implements the blockchain node with networking, mining, and consensus capabilities.

### Tracker (`core/tracker.py`)
Provides node discovery and peer list management for the network.

### Blockchain Storage (`core/blockchain_storage.py`)
Handles saving and loading blockchain states to/from disk.

## Extending the System

### Implementing Real AI Agents

To implement real AI-based storytellers:

1. Modify the `_generate_contribution()` method in `ai_components/ai_storyteller.py`
2. Connect to a real AI model (e.g., GPT API)
3. Feed the existing story as context to the AI
4. Use the AI-generated text as the new contribution

## Logs and Blockchain States

- Logs are stored in the `logs/` directory
- Blockchain states are saved in the `blockchain_states/` directory

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Disclaimer

This is an educational implementation and is not intended for production use. It lacks many features and security measures necessary for a real-world blockchain. 