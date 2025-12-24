"""Centralized logging configuration setup."""

import logging
import os
from logging.handlers import RotatingFileHandler


def setup_logging(log_dir: str = "logs", log_level: str = "INFO") -> None:
    """
    Configure application-wide logging.

    Creates logs directory if it doesn't exist, sets up rotating file handler,
    and configures log format and levels.

    Args:
        log_dir: Directory for log files (default: "logs")
        log_level: Logging level (default: "INFO")
    """
    # Create logs directory if it doesn't exist
    os.makedirs(log_dir, exist_ok=True)

    # Get root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))

    # Remove existing handlers to avoid duplicates
    root_logger.handlers.clear()

    # Create rotating file handler
    log_file = os.path.join(log_dir, "app.log")
    file_handler = RotatingFileHandler(
        log_file, maxBytes=10 * 1024 * 1024, backupCount=5  # 10MB
    )
    file_handler.setLevel(getattr(logging, log_level.upper(), logging.INFO))

    # Create formatter
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler.setFormatter(formatter)

    # Add handler to root logger
    root_logger.addHandler(file_handler)

    # Configure wpm library logger if available
    try:
        wpm_logger = logging.getLogger("wpm")
        wpm_logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))
        if not wpm_logger.handlers:
            wpm_logger.addHandler(file_handler)
            wpm_logger.propagate = False
    except Exception:
        # If wpm logger doesn't exist or can't be configured, continue
        pass

    logging.info(f"Logging configured: level={log_level}, log_dir={log_dir}")

