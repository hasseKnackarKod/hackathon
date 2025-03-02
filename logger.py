import logging
import os

def setup_logger(name, log_file, level=logging.INFO):
    """Creates and returns a separate logger for each thread, logging to both file and console."""
    os.makedirs("logs", exist_ok=True)

    logger = logging.getLogger(name)  # Create a named logger
    logger.setLevel(level)

    # Remove existing handlers to prevent duplicates
    if logger.hasHandlers():
        logger.handlers.clear()

    # File Handler (writes to log file)
    file_handler = logging.FileHandler(log_file, mode='a', encoding='utf-8')
    file_handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))

    # Console Handler (prints to terminal)
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))

    # Add both handlers to the logger
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger
