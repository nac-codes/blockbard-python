import logging
import os
import datetime
from pathlib import Path

LOG_DIR = "logs"
# Create log directory if it doesn't exist
Path(LOG_DIR).mkdir(exist_ok=True)

# Format: timestamp - level - component:port - message
LOG_FORMAT = '%(asctime)s - %(levelname)s - %(name)s - %(message)s'

def setup_logger(component_name, console_level=logging.INFO, file_level=logging.DEBUG):
    """
    Set up a logger with console and file handlers.
    
    Args:
        component_name: Name of the component (e.g., 'tracker', 'node:5001')
        console_level: Logging level for console output
        file_level: Logging level for file output
        
    Returns:
        A configured logger
    """
    # Create unique log file name with timestamp
    timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    log_file = os.path.join(LOG_DIR, f"{component_name.replace(':', '_')}_{timestamp}.log")
    
    # Create logger
    logger = logging.getLogger(component_name)
    logger.setLevel(min(console_level, file_level))  # Set to the more verbose level
    
    # Create console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(console_level)
    console_format = logging.Formatter(LOG_FORMAT)
    console_handler.setFormatter(console_format)
    
    # Create file handler
    file_handler = logging.FileHandler(log_file)
    file_handler.setLevel(file_level)
    file_format = logging.Formatter(LOG_FORMAT)
    file_handler.setFormatter(file_format)
    
    # Add handlers to logger
    logger.addHandler(console_handler)
    logger.addHandler(file_handler)
    
    logger.info(f"Logger initialized. Log file: {log_file}")
    return logger 