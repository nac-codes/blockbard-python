# BlockBard Blockchain Network

A simple, educational blockchain implementation with a peer-to-peer network architecture for distributed consensus.

## Features

- Blockchain implementation with basic validation
- Peer-to-peer network with tracker-based peer discovery
- Node-to-node synchronization and conflict resolution
- Blockchain state persistence
- Simulated mining mechanism
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

```bash
# Start the first node
python main.py node --host 0.0.0.0 --port 5501 --tracker http://tracker-host:5500

# Start additional nodes (on the same or different machines)
python main.py node --host 0.0.0.0 --port 5502 --tracker http://tracker-host:5500
python main.py node --host 0.0.0.0 --port 5503 --tracker http://tracker-host:5500
```

- Replace `tracker-host` with the actual hostname or IP address of the tracker
- Use `0.0.0.0` as the host to allow external connections
- If running on the same machine, use different port numbers for each node

## Network Setup Examples

### Local Network (Single Machine)

1. Start the tracker:
   ```bash
   python main.py tracker --host localhost --port 5500
   ```

2. Start multiple nodes in separate terminals:
   ```bash
   python main.py node --host localhost --port 5501 --tracker http://localhost:5500
   python main.py node --host localhost --port 5502 --tracker http://localhost:5500
   python main.py node --host localhost --port 5503 --tracker http://localhost:5500
   ```

### Distributed Network (Multiple Machines)

1. Start the tracker on Machine A (IP: 192.168.1.100):
   ```bash
   python main.py tracker --host 0.0.0.0 --port 5500
   ```

2. Start nodes on different machines:

   Machine B (IP: 192.168.1.101):
   ```bash
   python main.py node --host 0.0.0.0 --port 5501 --tracker http://192.168.1.100:5500
   ```

   Machine C (IP: 192.168.1.102):
   ```bash
   python main.py node --host 0.0.0.0 --port 5501 --tracker http://192.168.1.100:5500
   ```

## Interacting with the Blockchain

Once your nodes are running, you can interact with them through HTTP API endpoints:

### Mine a New Block

```bash
curl -X POST -H "Content-Type: application/json" -d '{"data":"Your block data here"}' http://localhost:5501/mine
```

### Get the Current Blockchain

```bash
curl http://localhost:5501/get_chain
```

### View Node's Peer List

This is an internal endpoint the tracker uses to update peers, but can be useful for debugging:

```bash
curl http://tracker-host:5500/peers
```

## Testing

The repository includes a test script to validate node synchronization:

```bash
python test_sync.py
```

This script:
1. Starts a tracker and three nodes
2. Makes nodes mine blocks
3. Verifies synchronization across all nodes

## Logs and Blockchain States

- Logs are stored in the `logs/` directory
- Blockchain states are saved in the `blockchain_states/` directory

## Architecture

- `blockchain.py`: Core blockchain implementation
- `node.py`: Blockchain node with networking capabilities
- `tracker.py`: Central tracker for peer discovery
- `main.py`: Entry point script with command-line interface
- `blockchain_storage.py`: Persistence for blockchain states
- `logging_util.py`: Logging configuration
- `test_sync.py`: Testing script for blockchain synchronization

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Disclaimer

This is an educational implementation and is not intended for production use. It lacks many features and security measures necessary for a real-world blockchain. 