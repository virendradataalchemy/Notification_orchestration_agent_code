import logging
import sys
from typing import Any, Dict

from colorama import Fore, Style, init
from pythonjsonlogger import jsonlogger

from src.utils.pii import mask_pii_in_dict

init(autoreset=True)


class PIIMaskingJsonFormatter(jsonlogger.JsonFormatter):
    def process_log_record(self, log_record: Dict[str, Any]) -> Dict[str, Any]:
        return mask_pii_in_dict(log_record)


class ColorConsoleFormatter(logging.Formatter):
    LEVEL_COLORS = {
        logging.DEBUG: Fore.CYAN,
        logging.INFO: Fore.GREEN,
        logging.WARNING: Fore.YELLOW,
        logging.ERROR: Fore.RED,
        logging.CRITICAL: Fore.MAGENTA,
    }
    LEVEL_LABELS = {
        logging.DEBUG: "DEBUG",
        logging.INFO: "INFO ",
        logging.WARNING: "WARN ",
        logging.ERROR: "ERROR",
        logging.CRITICAL: "CRIT ",
    }

    def format(self, record: logging.LogRecord) -> str:
        timestamp = self.formatTime(record, "%H:%M:%S")
        level_color = self.LEVEL_COLORS.get(record.levelno, "")
        level_label = self.LEVEL_LABELS.get(record.levelno, record.levelname[:5].upper())
        logger_name = record.name.rsplit(".", 1)[-1]
        message = record.getMessage()
        message = self._normalize_message(message)

        output = (
            f"{Style.DIM}{timestamp}{Style.RESET_ALL} "
            f"{level_color}{level_label}{Style.RESET_ALL} "
            f"{Fore.BLUE}{logger_name}{Style.RESET_ALL} "
            f"{message}"
        )

        if record.exc_info:
            output = f"{output}\n{self.formatException(record.exc_info)}"

        return output

    @staticmethod
    def _normalize_message(message: str) -> str:
        if len(message) > 220:
            return f"{message[:217]}..."
        return message


def configure_logging(level: str = "INFO") -> None:
    root_logger = logging.getLogger()
    numeric_level = getattr(logging, level.upper(), logging.INFO)
    formatter = ColorConsoleFormatter()

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger.handlers.clear()
    root_logger.setLevel(numeric_level)
    root_logger.addHandler(handler)

    for noisy_logger in (
        "uvicorn.access",
        "watchfiles.main",
        "asyncio",
        "sqlalchemy.engine",
        "sqlalchemy.pool",
    ):
        logging.getLogger(noisy_logger).setLevel(logging.WARNING)

    for app_logger in ("uvicorn", "uvicorn.error", "celery", "celery.app.trace"):
        logging.getLogger(app_logger).handlers.clear()
        logging.getLogger(app_logger).propagate = True


def setup_logger(name: str, level: str = "INFO") -> logging.Logger:
    configure_logging(level)
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    return logger
