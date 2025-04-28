#!/usr/bin/env python3
import argparse
import sys
import os
import time
import json
import getpass
import subprocess
import signal
import threading

# Add the parent directory to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Try to import yaml, handle specific error if missing
try:
    import yaml
except ImportError:
    print("Error: PyYAML package is missing. Please install it:")
    print("  pip install PyYAML")
    print("Or run: pip install -r requirements.txt")
    sys.exit(1)

from utils.dependency_check import ensure_dependencies

class DistributedStoryteller:
    def __init__(self, tracker_url, port=None, config_file=None):
        self.tracker_url = tracker_url
        self.port = port or self._get_random_port()
        self.config_file = config_file
        self.config = self._load_config()
        self.node_process = None
        self.ai_process = None
        self.running = True
    
    def _get_random_port(self):
        """Generate a random port number between 5501 and 6500."""
        import random
        return random.randint(5501, 6500)
    
    def _load_config(self):
        """Load configuration from file or use defaults."""
        default_config = {
            "auto_mine": True,
            "mine_interval": 5,
            "genesis_story": None,
            "api_key": os.environ.get("OPENAI_API_KEY", None),
            "model": "gpt-4.1-mini-2025-04-14",
            "system_prompt": None,
            "contribution_interval": 20,
            "max_context_words": 10000,
            "log_level": "INFO"
        }
        
        if not self.config_file:
            return default_config
        
        try:
            with open(self.config_file, 'r') as f:
                if self.config_file.endswith('.json'):
                    loaded_config = json.load(f)
                elif self.config_file.endswith(('.yaml', '.yml')):
                    loaded_config = yaml.safe_load(f)
                else:
                    print(f"Unsupported config file format: {self.config_file}")
                    return default_config
            
            # Merge loaded config with defaults
            for key, value in loaded_config.items():
                default_config[key] = value
                
            return default_config
        except FileNotFoundError:
            print(f"Error: Config file not found at {self.config_file}")
            print("Using default configuration.")
            return default_config
        except Exception as e:
            print(f"Error loading config file '{self.config_file}': {e}")
            print("Using default configuration.")
            return default_config
    
    def _get_api_key(self):
        """Get OpenAI API key from config, env var, or prompt."""
        if self.config["api_key"]:
            return self.config["api_key"]
        
        api_key = os.environ.get("OPENAI_API_KEY")
        if api_key:
            print("Using OpenAI API key from environment variable.")
            return api_key
        
        api_key = getpass.getpass("Enter your OpenAI API key: ")
        if not api_key:
            print("Error: OpenAI API key is required.")
            sys.exit(1)
        
        return api_key
    
    def _get_system_prompt(self):
        """Get the system prompt from config or prompt the user."""
        if self.config["system_prompt"]:
            return self.config["system_prompt"]
        
        print("\nNo system prompt found in config. Please enter one:")
        print("(This defines the personality and style of your AI storyteller)")
        
        default_prompt = (
            "You are a creative storyteller contributing to a collaborative "
            "blockchain-based story. Add compelling and contextually relevant "
            "continuations to the evolving narrative. Be concise but vivid, "
            "aiming for 2-3 sentences per contribution."
        )
        
        print(f"\nDefault prompt: {default_prompt}")
        
        use_default = input("Use default prompt? (y/n): ").lower() == 'y'
        if use_default:
            return default_prompt
        
        custom_prompt = input("Enter your custom system prompt: ")
        if not custom_prompt:
            print("Using default prompt.")
            return default_prompt
        
        return custom_prompt
    
    def start_node(self):
        """Start the blockchain node."""
        print(f"Starting blockchain node on port {self.port}...")
        
        # Create necessary directories
        os.makedirs("logs", exist_ok=True)
        os.makedirs("blockchain_states", exist_ok=True)
        
        # Build command
        cmd = [
            sys.executable, # Use the same python interpreter
            "main.py", "node",
            "--port", str(self.port),
            "--tracker", self.tracker_url
        ]
        
        # Add optional arguments
        if self.config["auto_mine"]:
            cmd.append("--auto-mine")
        
        if self.config["mine_interval"]:
            cmd.extend(["--mine-interval", str(self.config["mine_interval"])])
        
        if self.config["genesis_story"]:
            cmd.extend(["--genesis", self.config["genesis_story"]])
        
        print(f"Running command: {' '.join(cmd)}")
        
        # Start node process with both stdout and stderr piped
        self.node_process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=1,  # Line buffered
            universal_newlines=False  # Keep binary mode for consistent handling
        )
        
        print(f"Node started (PID: {self.node_process.pid}) on port {self.port}")
        print(f"Giving node time to connect to tracker...")
        time.sleep(5)  # Give node time to initialize
    
    def start_ai_storyteller(self):
        """Start the OpenAI storyteller."""
        print("Starting OpenAI storyteller...")
        
        # Get API key
        api_key = self._get_api_key()
        
        # Get system prompt
        system_prompt = self._get_system_prompt()
        
        # Build command
        cmd = [
            sys.executable, # Use the same python interpreter
            "ai_components/openai_storyteller.py",
            "--node", f"http://localhost:{self.port}",
            "--interval", str(self.config["contribution_interval"]),
            "--api-key", api_key,
            "--model", self.config["model"],
            "--max-context", str(self.config["max_context_words"]),
            "--system-prompt", system_prompt,
            "--log-level", self.config["log_level"]
        ]
        
        print(f"Running command: {' '.join(cmd).replace(api_key, '***API_KEY***')}")
        
        # Start AI process with both stdout and stderr piped
        self.ai_process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=1,  # Line buffered
            universal_newlines=False  # Keep binary mode for consistent handling
        )
        
        print(f"AI storyteller started (PID: {self.ai_process.pid}). Waiting for initialization...")
        time.sleep(2)  # Give AI time to initialize
    
    def monitor_processes(self):
        """Monitor the processes and restart if needed."""
        def log_output(process, name, stream_type):
            """Read and log the output from a process."""
            if stream_type == "stdout":
                stream = process.stdout
            else:
                stream = process.stderr
                
            while self.running:
                try:
                    output = stream.readline()
                    if output and self.running:
                        print(f"[{name}][{stream_type}] {output.decode('utf-8', errors='replace').strip()}")
                    elif not output and process.poll() is not None:
                        # Process has terminated
                        break
                    time.sleep(0.1)
                except Exception as e:
                    print(f"Error reading from {name} {stream_type}: {e}")
                    break # Exit thread on read error
            print(f"Log monitoring thread for {name} {stream_type} finished.")

        
        # Start threads to monitor stdout and stderr outputs for both processes
        node_stdout_thread = threading.Thread(target=log_output, args=(self.node_process, "NODE", "stdout"), daemon=True)
        node_stderr_thread = threading.Thread(target=log_output, args=(self.node_process, "NODE", "stderr"), daemon=True)
        ai_stdout_thread = threading.Thread(target=log_output, args=(self.ai_process, "AI", "stdout"), daemon=True)
        ai_stderr_thread = threading.Thread(target=log_output, args=(self.ai_process, "AI", "stderr"), daemon=True)
        
        threads = [node_stdout_thread, node_stderr_thread, ai_stdout_thread, ai_stderr_thread]
        for t in threads:
            t.start()
        
        print("\nStoryteller is now running. Press Ctrl+C to stop.")
        
        try:
            while self.running:
                # Check if processes are still running
                node_status = self.node_process.poll()
                ai_status = self.ai_process.poll()
                
                if node_status is not None:
                    print(f"Node process (PID: {self.node_process.pid}) stopped unexpectedly with code {node_status}.")
                    # Optionally, you could restart here, but for now, just exit
                    self.running = False
                    break
                
                if ai_status is not None:
                    print(f"AI process (PID: {self.ai_process.pid}) stopped unexpectedly with code {ai_status}.")
                    # Optionally, restart AI
                    self.running = False
                    break
                
                time.sleep(5)
        except KeyboardInterrupt:
            print("\nStopping storyteller...")
            self.running = False
        
        # Wait for logging threads to finish
        for t in threads:
            t.join(timeout=1)
    
    def cleanup(self):
        """Stop all processes."""
        self.running = False # Signal monitoring threads to stop
        if self.ai_process and self.ai_process.poll() is None:
            print(f"Stopping AI storyteller (PID: {self.ai_process.pid})...")
            try:
                self.ai_process.terminate()
                self.ai_process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.ai_process.kill()
        
        if self.node_process and self.node_process.poll() is None:
            print(f"Stopping blockchain node (PID: {self.node_process.pid})...")
            try:
                self.node_process.terminate()
                self.node_process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.node_process.kill()
        
        print("All processes stopped.")
    
    def run(self):
        """Run the distributed storyteller."""
        try:
            print("\n=== BlockBard Distributed Storyteller ===\n")
            print(f"Using Python interpreter: {sys.executable}")
            print(f"Connecting to tracker: {self.tracker_url}")
            print(f"Node port: {self.port}")
            if self.config_file:
                print(f"Using config file: {self.config_file}")
            
            self.start_node()
            self.start_ai_storyteller()
            self.monitor_processes()
            
            return 0
        except KeyboardInterrupt:
            print("\nStoryteller interrupted by user.")
            return 0
        except Exception as e:
            print(f"\nError running storyteller: {e}")
            return 1
        finally:
            self.cleanup()

def main():
    # Ensure dependencies are installed first
    ensure_dependencies()
    
    parser = argparse.ArgumentParser(description="Run a BlockBard distributed storyteller")
    parser.add_argument("tracker_url", help="URL of the tracker node (e.g., http://192.168.1.5:5500)")
    parser.add_argument("--port", type=int, help="Port to run the node on (default: random port)")
    parser.add_argument("--config", help="Path to configuration file (JSON or YAML)")
    parser.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
                        help="Logging level (default: INFO)")
    
    args = parser.parse_args()
    
    # Update config with command line parameters
    config_override = {}
    if args.log_level:
        config_override["log_level"] = args.log_level
    
    storyteller = DistributedStoryteller(
        tracker_url=args.tracker_url,
        port=args.port,
        config_file=args.config
    )
    
    # Override config with command line parameters
    for key, value in config_override.items():
        storyteller.config[key] = value
    
    return storyteller.run()

if __name__ == "__main__":
    sys.exit(main()) 