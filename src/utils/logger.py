import logging
import sys
from pythonjsonlogger import jsonlogger
from typing import Any, Dict
from src.utils.pii import mask_pii_in_dict

class PIIMaskingJsonFormatter(jsonlogger.JsonFormatter):
    def process_log_record(self, log_record: Dict[str, Any]) -> Dict[str, Any]:
        """Hook to modify the log record before it is serialized."""
        # Clean up any PII fields in the log record before output
        return mask_pii_in_dict(log_record)

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
    
    # Avoid adding handlers multiple times if logger already exists
    if logger.handlers:
        return logger

    logger.setLevel(getattr(logging, level.upper()))

    # Create handler
    handler = logging.StreamHandler(sys.stdout)

    # Create JSON formatter
    formatter = PIIMaskingJsonFormatter(
        '%(asctime)s %(name)s %(levelname)s %(message)s',
        timestamp=True
    )

    handler.setFormatter(formatter)
    logger.addHandler(handler)

    return logger
