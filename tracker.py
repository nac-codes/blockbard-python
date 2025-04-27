import json
from flask import Flask, request, jsonify
import requests
import threading
import logging
from logging_util import setup_logger

# In-memory store for peer addresses (e.g., 'http://localhost:5001')
peers = set()
peers_lock = threading.Lock() # To handle concurrent access

app = Flask(__name__)
# Disable Flask's default logging to avoid conflicts with our logging system
app.logger.disabled = True
log = logging.getLogger('werkzeug')
log.disabled = True

# Set up our custom logger
logger = setup_logger('tracker')

def broadcast_peers():
    """Sends the current list of peers to all registered peers."""
    global peers
    with peers_lock:
        peer_list = list(peers) # Create a snapshot
    
    if not peer_list:
        logger.info("No peers to broadcast to")
        return
    
    logger.info(f"Broadcasting peer list ({len(peer_list)} peers) to all nodes")
    logger.debug(f"Full peer list: {peer_list}")
    
    for peer in peer_list:
        try:
            # Add a check to avoid sending the list to itself if the tracker is also a peer (not the case here)
            # if peer == request.host_url: # Careful with exact URL matching
            #     continue
            update_url = f"{peer}/update_peers" # Peers need an endpoint to receive this
            logger.debug(f"Sending peer list to {peer}")
            response = requests.post(update_url, json={'peers': peer_list}, timeout=1) # Short timeout
            logger.debug(f"Response from {peer}: {response.status_code}")
        except requests.exceptions.RequestException as e:
            logger.warning(f"Failed to send peer list update to {peer}: {e}. Removing peer.")
            # If a peer is unreachable, remove it from the list
            with peers_lock:
                 # Check if it's still in the set before removing
                if peer in peers:
                    peers.remove(peer)
                    logger.info(f"Removed unreachable peer: {peer}")
                    # Optionally, broadcast again after removal, or wait for next update cycle
                    # Consider adding a more robust heartbeat/cleanup mechanism later

@app.route('/')
def home():
    """Root endpoint for testing connectivity."""
    logger.debug("Received request to root endpoint")
    return jsonify({
        "status": "ok",
        "service": "BlockBard Tracker",
        "endpoints": [
            {"path": "/", "method": "GET", "description": "This endpoint"},
            {"path": "/register", "method": "POST", "description": "Register a new peer"},
            {"path": "/peers", "method": "GET", "description": "Get list of known peers"},
            {"path": "/unregister", "method": "POST", "description": "Unregister a peer"}
        ],
        "peer_count": len(peers)
    })

@app.route('/register', methods=['POST'])
def register_peer():
    """Registers a new peer and broadcasts the updated list."""
    global peers
    logger.debug(f"Received registration request: {request.data}")
    
    try:
        data = request.get_json()
        logger.debug(f"Parsed JSON data: {data}")
        peer_address = data.get('address')

        if not peer_address:
            logger.warning("Registration failed: Missing peer address")
            return jsonify({"error": "Peer address required"}), 400

        logger.info(f"Registering peer: {peer_address}")
        should_broadcast = False
        with peers_lock:
            if peer_address not in peers:
                peers.add(peer_address)
                should_broadcast = True # Only broadcast if the list actually changed
                logger.info(f"Peer list after addition: {peers}")
            else:
                logger.info(f"Peer {peer_address} already registered")

        response_data = {"message": "Registration successful", "peers": list(peers)}
        logger.debug(f"Registration response data: {response_data}")

        # Broadcast outside the lock to avoid holding it during network calls
        if should_broadcast:
            # Run broadcast in a separate thread to avoid blocking the response
            threading.Thread(target=broadcast_peers, daemon=True).start()
        
        # Otherwise, make sure the newly registered peer gets the current peer list
        else:
            try:
                update_url = f"{peer_address}/update_peers"
                logger.debug(f"Sending current peer list directly to newly registered peer: {peer_address}")
                with peers_lock:
                    current_peers = list(peers)
                requests.post(update_url, json={'peers': current_peers}, timeout=1)
            except requests.exceptions.RequestException as e:
                logger.warning(f"Failed to send peer list to newly registered peer {peer_address}: {e}")

        return jsonify(response_data), 200
    except Exception as e:
        logger.error(f"Error processing registration request: {e}", exc_info=True)
        return jsonify({"error": "Internal server error"}), 500


@app.route('/peers', methods=['GET'])
def get_peers():
    """Returns the current list of known peers."""
    logger.debug("Received request for peer list")
    with peers_lock:
        peer_list = list(peers)
    logger.debug(f"Returning peer list: {peer_list}")
    return jsonify({"peers": peer_list})

# Optional: Add an endpoint for graceful unregistering
@app.route('/unregister', methods=['POST'])
def unregister_peer():
    """Unregisters a peer and broadcasts the updated list."""
    global peers
    logger.debug(f"Received unregister request: {request.data}")
    
    try:
        data = request.get_json()
        peer_address = data.get('address')

        if not peer_address:
            logger.warning("Unregistration failed: Missing peer address")
            return jsonify({"error": "Peer address required"}), 400

        logger.info(f"Unregistering peer: {peer_address}")
        should_broadcast = False
        with peers_lock:
            if peer_address in peers:
                peers.remove(peer_address)
                should_broadcast = True

        # Broadcast outside the lock
        if should_broadcast:
            threading.Thread(target=broadcast_peers, daemon=True).start()

        return jsonify({"message": "Unregistration successful", "peers": list(peers)}), 200
    except Exception as e:
        logger.error(f"Error processing unregistration request: {e}", exc_info=True)
        return jsonify({"error": "Internal server error"}), 500


if __name__ == '__main__':
    # Print all registered routes for debugging
    logger.info("Registered routes:")
    for rule in app.url_map.iter_rules():
        logger.info(f"Route: {rule.rule}, Methods: {rule.methods}")
    
    # Example: Run tracker on port 5500
    tracker_port = 5500
    logger.info(f"Tracker node running on http://localhost:{tracker_port}")
    # Use threaded=True for handling multiple requests concurrently
    # Use debug=False for production/testing stability
    # Use host='0.0.0.0' to be accessible externally if needed, localhost for local testing
    app.run(host='0.0.0.0', port=tracker_port, threaded=True) 