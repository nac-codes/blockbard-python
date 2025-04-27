# BlockBard Blockchain Network

A simple, educational blockchain implementation with a peer-to-peer network architecture for distributed consensus and proof-of-work mining.

## Features

- Blockchain implementation with proof of work (PoW) mining
- Peer-to-peer network with tracker-based peer discovery
- Node-to-node synchronization and conflict resolution
- Blockchain state persistence
- Automatic mining with transaction pool
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

## Running the Blockchain Network

The blockchain network consists of a tracker node and multiple blockchain nodes. The tracker helps peers discover each other.

### Starting the Tracker Node

```bash
python main.py tracker --host 0.0.0.0 --port 5500
```

- Use `0.0.0.0` as the host to allow external connections
- Default port is 5500
- For local testing only, you can use `localhost` instead of `0.0.0.0`

### Starting Blockchain Nodes

#### Basic Node (Manual Mining)

```bash
# Start the first node
python main.py node --host 0.0.0.0 --port 5501 --tracker http://tracker-host:5500

# Start additional nodes (on the same or different machines)
python main.py node --host 0.0.0.0 --port 5502 --tracker http://tracker-host:5500
python main.py node --host 0.0.0.0 --port 5503 --tracker http://tracker-host:5500
```

#### Auto-Mining Node (Continuous Mining)

```bash
# Start a node with auto-mining enabled (default 10 second interval)
python main.py node --host 0.0.0.0 --port 5501 --tracker http://tracker-host:5500 --auto-mine

# Start a node with a custom mining interval (in seconds)
python main.py node --host 0.0.0.0 --port 5502 --tracker http://tracker-host:5500 --auto-mine --mine-interval 5
```

- Replace `tracker-host` with the actual hostname or IP address of the tracker
- Use `0.0.0.0` as the host to allow external connections
- If running on the same machine, use different port numbers for each node
- Auto-mining nodes will continuously mine new blocks when transactions are available in the pool

## Network Setup Examples

### Local Network (Single Machine)

1. Start the tracker:
   ```bash
   python main.py tracker --host localhost --port 5500
   ```

2. Start multiple nodes in separate terminals:
   ```bash
   # Node with manual mining
   python main.py node --host localhost --port 5501 --tracker http://localhost:5500
   
   # Nodes with auto-mining
   python main.py node --host localhost --port 5502 --tracker http://localhost:5500 --auto-mine
   python main.py node --host localhost --port 5503 --tracker http://localhost:5500 --auto-mine --mine-interval 3
   ```

### Distributed Network (Multiple Machines)

1. Start the tracker on Machine A (IP: 192.168.1.100):
   ```bash
   python main.py tracker --host 0.0.0.0 --port 5500
   ```

2. Start nodes on different machines:

   Machine B (IP: 192.168.1.101):
   ```bash
   python main.py node --host 0.0.0.0 --port 5501 --tracker http://192.168.1.100:5500 --auto-mine
   ```

   Machine C (IP: 192.168.1.102):
   ```bash
   python main.py node --host 0.0.0.0 --port 5501 --tracker http://192.168.1.100:5500 --auto-mine
   ```

## Interacting with the Blockchain

Once your nodes are running, you can interact with them through HTTP API endpoints:

### Manual Mining

```bash
curl -X POST -H "Content-Type: application/json" -d '{"data":"Your block data here"}' http://localhost:5501/mine
```

### Add Transaction to the Pool (For Auto-Mining)

```bash
curl -X POST -H "Content-Type: application/json" -d '{"data":"Your transaction data here"}' http://localhost:5501/add_transaction
```

### Get the Current Blockchain

```bash
curl http://localhost:5501/get_chain
```

### Get Node Status

```bash
curl http://localhost:5501/status
```

### Toggle Auto-Mining

```bash
# Enable auto-mining with custom interval
curl -X POST -H "Content-Type: application/json" -d '{"enable":true,"interval":5}' http://localhost:5501/auto_mine

# Disable auto-mining
curl -X POST -H "Content-Type: application/json" -d '{"enable":false}' http://localhost:5501/auto_mine
```

### View Node's Peer List

```bash
curl http://tracker-host:5500/peers
```

## Utility Scripts

### Adding Transactions

Use the `add_transaction.py` script to add transactions to the transaction pool:

```bash
# Add a single random transaction
python add_transaction.py --node http://localhost:5501

# Add a specific transaction
python add_transaction.py --node http://localhost:5501 --data "Transfer 5 coins from Alice to Bob"

# Add multiple transactions
python add_transaction.py --node http://localhost:5501 --count 10 --interval 0.5
```

### Running Competing Miners Test

The `run_competing_miners.py` script demonstrates how multiple miners compete in the network:

```bash
# Run with default settings (3 miners, 5s interval, 120s duration)
python run_competing_miners.py

# Run with custom settings
python run_competing_miners.py --nodes 5 --interval 3 --duration 300
```

This script:
1. Starts a tracker and multiple auto-mining nodes
2. Adds transactions to random nodes
3. Monitors the blockchain as it grows
4. Verifies that all nodes maintain consensus
5. Reports detailed information about the mining competition

## Testing

The repository includes test scripts to validate different aspects of the blockchain:

```bash
# Test node synchronization
python test_sync.py

# Test proof of work with competing miners
python test_pow_competition.py
```

## Logs and Blockchain States

- Logs are stored in the `logs/` directory
- Blockchain states are saved in the `blockchain_states/` directory

## Architecture

- `blockchain.py`: Core blockchain implementation with proof of work
- `node.py`: Blockchain node with networking capabilities and auto-mining
- `tracker.py`: Central tracker for peer discovery
- `main.py`: Entry point script with command-line interface
- `blockchain_storage.py`: Persistence for blockchain states
- `logging_util.py`: Logging configuration
- `add_transaction.py`: Utility for adding transactions
- `run_competing_miners.py`: Script for running competing miners
- `test_pow_competition.py`: Testing proof of work competition
- `test_sync.py`: Testing blockchain synchronization

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Disclaimer

This is an educational implementation and is not intended for production use. It lacks many features and security measures necessary for a real-world blockchain. 