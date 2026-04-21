import logging
import sys
from pythonjsonlogger import jsonlogger


def setup_logger(name: str, level: str = "INFO") -> logging.Logger:
    """
    Set up JSON structured logging.

    Args:
        name: Logger name
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)

    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, level.upper()))

    # Create handler
    handler = logging.StreamHandler(sys.stdout)

    # Create JSON formatter
    formatter = jsonlogger.JsonFormatter(
        '%(asctime)s %(name)s %(levelname)s %(message)s',
        timestamp=True
    )

    handler.setFormatter(formatter)
    logger.addHandler(handler)

    return logger
