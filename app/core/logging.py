"""Application logging configuration."""

import logging
import sys


def setup_logging(debug: bool = False) -> logging.Logger:
    """Sets up standard structured logging."""
    log_level = logging.DEBUG if debug else logging.INFO

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-7s | %(name)s:%(lineno)d - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger("labelradar")
    root_logger.setLevel(log_level)
    if not root_logger.handlers:
        root_logger.addHandler(handler)

    return root_logger


logger = logging.getLogger("labelradar")

