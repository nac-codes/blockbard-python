# BlockBard Distributed Storytelling System

This guide explains how to set up and run the BlockBard collaborative storytelling system across multiple computers. The system consists of a central tracker node and multiple storyteller nodes that connect to the network, each contributing to a shared blockchain-based story.

## Overview

The BlockBard system has three main components:

1. **Tracker Node**: The central registration point for all storyteller nodes. Runs on one computer.
2. **Blockchain Nodes**: The blockchain validators that mine story blocks. One runs on each storyteller computer.
3. **AI Storytellers**: OpenAI-powered story generators. One runs alongside each blockchain node.

In the distributed setup, you'll run the tracker on one computer, and a blockchain node + AI storyteller on each participant's computer.

## Requirements

- Python 3.6+
- Flask
- Requests
- OpenAI
- PyYAML (for YAML config files)

Install dependencies:

1. **Recommended:** Set up a Python virtual environment on each machine:
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # On Linux/macOS
   # or
   .\venv\Scripts\activate    # On Windows
   ```

2. Install using the requirements file:
   ```bash
   pip install -r requirements.txt
   ```

## Step 1: Start the Tracker Node

Choose one computer to serve as the tracker. This computer will be the central hub that all storyteller nodes connect to.

```bash
# On the tracker computer
python scripts/run_tracker.py
```

This will start the tracker and display connection information like:
```
=== BlockBard Tracker Node ===

Starting tracker on 0.0.0.0:5500...

Connection information for other nodes:
  Local URL: http://0.0.0.0:5500
  Network URL: http://192.168.1.10:5500

Share this URL with other nodes in your storytelling network.
```

**Important**: Note the Network URL - you'll need to share this with all storyteller participants.

## Step 2: Start Storyteller Nodes

On each participant's computer, start a storyteller node that connects to the tracker:

```bash
# On each storyteller's computer
python scripts/run_storyteller.py http://192.168.1.10:5500
```

Replace `http://192.168.1.10:5500` with the actual tracker URL from Step 1.

This will:
1. Start a blockchain node that connects to the tracker
2. Start an OpenAI storyteller agent
3. Prompt for any needed settings (OpenAI API key, system prompt, etc.)

## Using Configuration Files

Instead of entering settings each time, you can create a configuration file:

### YAML Config Example
```yaml
# storyteller_config.yaml
auto_mine: true
mine_interval: 5
genesis_story: "Once upon a time in a world where technology and magic intertwined..."
api_key: "your-openai-api-key"  # Or set via OPENAI_API_KEY environment variable
model: "gpt-4.1-mini-2025-04-14"
contribution_interval: 20
system_prompt: "You are a fantasy writer with a vivid imagination..."
```

### JSON Config Example
```json
{
  "auto_mine": true,
  "mine_interval": 5,
  "genesis_story": "Once upon a time...",
  "api_key": "your-openai-api-key",
  "model": "gpt-4.1-mini-2025-04-14",
  "contribution_interval": 20,
  "system_prompt": "You are a fantasy writer..."
}
```

Then run with the config file:
```bash
python scripts/run_storyteller.py http://192.168.1.10:5500 --config configs/storyteller_config.yaml
```

## Configuration Options

| Option | Description | Default |
|--------|-------------|---------|
| `auto_mine` | Whether to automatically mine blocks | `true` |
| `mine_interval` | Seconds between mining attempts | `5` |
| `genesis_story` | Custom story beginning (first node only) | `null` |
| `api_key` | OpenAI API key | From env var |
| `model` | OpenAI model to use | `gpt-4.1-mini-2025-04-14` |
| `contribution_interval` | Seconds between AI contributions | `20` |
| `max_context_words` | Max words of story to keep in context | `10000` |
| `system_prompt` | Instructions for the AI storyteller | Default prompt |

## Running the First Node

The first node to connect to the network should include a genesis story to start the narrative. You can do this by:

1. Setting `genesis_story` in the config file
2. Or using command-line arguments:
   ```bash
   python scripts/run_storyteller.py http://192.168.1.10:5500 --config configs/with_genesis.yaml
   ```

## Keeping the Story Going

The distributed BlockBard system is designed to be resilient:

- The tracker must stay running for new nodes to discover the network
- Individual storyteller nodes can join or leave at any time
- If all nodes disconnect, the story can continue when someone reconnects
- The blockchain state is saved locally on each computer

## Monitoring the Story

Each storyteller node shows the contributions from all participants. You can also view the full story by examining the blockchain on any node:

1. Note the port your node is running on (e.g., 5501)
2. Open a web browser to `http://localhost:5501/get_chain`
3. This will show the complete blockchain with all story contributions

## Troubleshooting

- **Can't connect to tracker**: Ensure the tracker IP is reachable from other computers
- **No peers found**: Make sure the tracker is running and ports are not blocked
- **No story progress**: Check that at least one node has auto-mining enabled
- **OpenAI API errors**: Verify your API key and internet connection

## Advanced: Custom Storyteller Personalities

Create different config files with unique system prompts to give each AI storyteller a distinct personality:

- A poet who contributes in verse
- A mystery writer who adds suspense
- A character-focused writer who explores emotions
- A world-builder who describes rich settings

This creates a more dynamic and varied collaborative story! 