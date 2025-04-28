#!/usr/bin/env python3
import argparse
import sys
import os
import time
import socket
import requests

# Add the parent directory to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.dependency_check import ensure_dependencies

def get_local_ip():
    """Get the local IP address of this machine."""
    try:
        # Create a socket to a known external service (Google DNS)
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "localhost"

def run_tracker(host, port):
    """Run a tracker node and display connection information."""
    # Create necessary directories
    os.makedirs("logs", exist_ok=True)
    os.makedirs("blockchain_states", exist_ok=True)
    
    # Get the IP address for other computers to connect to
    local_ip = get_local_ip()
    
    print("\n=== BlockBard Tracker Node ===\n")
    print(f"Starting tracker on {host}:{port}...")
    print("\nConnection information for other nodes:")
    print(f"  Local URL: http://{host}:{port}")
    if host == "0.0.0.0":
        print(f"  Network URL: http://{local_ip}:{port}")
    print("\nShare this URL with other nodes in your storytelling network.")
    print("Keep this tracker running as long as you want the story network to exist.\n")
    print("Press Ctrl+C to stop the tracker.\n")
    
    try:
        # Import here to avoid circular imports and after dependency check
        from core.tracker import app
        app.run(host=host, port=port, threaded=True, debug=False)
    except KeyboardInterrupt:
        print("\nTracker node stopped.")
    except Exception as e:
        print(f"\nError running tracker: {e}")
        return 1
    
    return 0

def main():
    # Ensure dependencies are installed first
    ensure_dependencies()
    
    parser = argparse.ArgumentParser(description="Run a BlockBard tracker node")
    parser.add_argument("--host", default="0.0.0.0", help="Host address to bind to (default: 0.0.0.0 - all interfaces)")
    parser.add_argument("--port", type=int, default=5500, help="Port to bind to (default: 5500)")
    
    args = parser.parse_args()
    
    return run_tracker(args.host, args.port)

if __name__ == "__main__":
    sys.exit(main()) 