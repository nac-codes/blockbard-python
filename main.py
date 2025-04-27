#!/usr/bin/env python3
import argparse
import sys
import os
from pathlib import Path

def create_dirs():
    """Create necessary directories if they don't exist."""
    Path("logs").mkdir(exist_ok=True)
    Path("blockchain_states").mkdir(exist_ok=True)

def run_tracker(host, port):
    """Run a tracker node."""
    print(f"Starting tracker node on {host}:{port}")
    # Import here to avoid circular imports
    from tracker import app
    app.run(host=host, port=port, threaded=True, debug=False)

def run_node(host, port, tracker_url, auto_mine=False, mine_interval=10):
    """Run a blockchain node."""
    print(f"Starting blockchain node on {host}:{port} connected to tracker {tracker_url}")
    print(f"Auto-mining: {'Enabled' if auto_mine else 'Disabled'}, interval: {mine_interval}s")
    # Import here to avoid circular imports
    from node import Node
    node = Node(host=host, port=port, tracker_url=tracker_url, auto_mine=auto_mine, mine_interval=mine_interval)
    node.run()

def main():
    parser = argparse.ArgumentParser(description="BlockBard Blockchain Network")
    subparsers = parser.add_subparsers(dest="mode", help="Operation mode", required=True)

    # Tracker mode parser
    tracker_parser = subparsers.add_parser("tracker", help="Run as a tracker node")
    tracker_parser.add_argument("--host", default="localhost", help="Host address to bind to (default: localhost)")
    tracker_parser.add_argument("--port", type=int, default=5500, help="Port to bind to (default: 5500)")

    # Node mode parser
    node_parser = subparsers.add_parser("node", help="Run as a blockchain node")
    node_parser.add_argument("--host", default="localhost", help="Host address to bind to (default: localhost)")
    node_parser.add_argument("--port", type=int, default=5501, help="Port to bind to (default: 5501)")
    node_parser.add_argument("--tracker", required=True, help="Tracker URL (e.g., http://localhost:5500)")
    node_parser.add_argument("--auto-mine", action="store_true", help="Enable automatic mining")
    node_parser.add_argument("--mine-interval", type=int, default=10, help="Auto-mining interval in seconds (default: 10)")
    
    # Parse arguments
    args = parser.parse_args()
    
    # Create necessary directories
    create_dirs()
    
    # Run in the selected mode
    if args.mode == "tracker":
        run_tracker(args.host, args.port)
    elif args.mode == "node":
        run_node(args.host, args.port, args.tracker, args.auto_mine, args.mine_interval)
    else:
        parser.print_help()
        sys.exit(1)

if __name__ == "__main__":
    main() 