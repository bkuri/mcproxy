"""Logging configuration for MCProxy.

Provides syslog and stdout logging options.
"""

import logging
import logging.handlers
import sys
from typing import Optional


def setup_logging(use_stdout: bool = False, log_level: int = logging.INFO) -> None:
    """Configure logging for MCProxy.

    Args:
        use_stdout: If True, log to stdout. Otherwise, use syslog.
        log_level: Logging level (default: INFO)
    """
    if use_stdout:
        handler: logging.Handler = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    else:
        handler = logging.handlers.SysLogHandler(address="/dev/log")
        formatter = logging.Formatter(
            "%(name)s[%(process)d]: [%(levelname)s] %(message)s"
        )

    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    root_logger.addHandler(handler)

    # Reduce noise from third-party libraries
    logging.getLogger("uvicorn").setLevel(logging.WARNING)
    logging.getLogger("fastapi").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance for the given module name.

    Args:
        name: Module name (typically __name__)

    Returns:
        Configured logger instance
    """
    return logging.getLogger(name)
