"""
Centralized Logging Configuration

Provides consistent logging setup across all modules.
All logs are written to logs/ directory with both file and console output.
"""

import logging
import os
from datetime import datetime
from typing import Optional


def setup_logging(
    name: str = "app",
    level: int = logging.INFO,
    log_to_file: bool = True
) -> logging.Logger:
    """
    Setup logging with consistent configuration.
    
    Args:
        name: Logger name (used in log filename)
        level: Logging level (DEBUG, INFO, WARNING, ERROR)
        log_to_file: Whether to write logs to file
    
    Returns:
        Configured logger instance
    """
    # Ensure logs directory exists
    os.makedirs('logs', exist_ok=True)
    
    # Create logger
    logger = logging.getLogger(name)
    logger.setLevel(level)
    
    # Avoid duplicate handlers if logger already configured
    if logger.handlers:
        return logger
    
    # Format: 2024-12-01 15:30:45 - module_name - INFO - Message
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Console handler (always enabled)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # File handler (optional)
    if log_to_file:
        date_str = datetime.now().strftime("%Y%m%d")
        log_file = f"logs/{name}_{date_str}.log"
        
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    
    return logger


def get_logger(name: str) -> logging.Logger:
    """
    Get an existing logger or create a new one.
    
    Args:
        name: Logger name
    
    Returns:
        Logger instance
    """
    return logging.getLogger(name)
