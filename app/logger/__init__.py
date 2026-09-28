"""
Logger module providing centralized logging functionality.

Standardized usage (preferred):
    from src.logger.logging import logger
    logger.info("This is an info message")
    logger.error("This is an error message")

Legacy usage (for backwards compatibility):
    from src.logger import logger
    logger.info("This is an info message")

The logger is automatically configured when imported and supports:
- Console output with colors
- File logging with rotation
- Different log levels
- Automatic error tracking
"""

import logging


from .logging import logger

# Export the logger instance and utility functions
__all__ = ["logger"]  # For backwards compatibility
