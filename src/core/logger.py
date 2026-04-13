"""
Colorized, structured logger for the notification orchestration platform.
Outputs to both console (colored) and a rotating log file.
"""

from __future__ import annotations

import logging
import logging.handlers
import os
import sys
from datetime import datetime
from pathlib import Path

# ── ANSI color codes ──────────────────────────────────────────────────────────
RESET   = "\033[0m"
BOLD    = "\033[1m"
DIM     = "\033[2m"

BLACK   = "\033[30m"
RED     = "\033[31m"
GREEN   = "\033[32m"
YELLOW  = "\033[33m"
BLUE    = "\033[34m"
MAGENTA = "\033[35m"
CYAN    = "\033[36m"
WHITE   = "\033[37m"

BRIGHT_RED     = "\033[91m"
BRIGHT_GREEN   = "\033[92m"
BRIGHT_YELLOW  = "\033[93m"
BRIGHT_BLUE    = "\033[94m"
BRIGHT_MAGENTA = "\033[95m"
BRIGHT_CYAN    = "\033[96m"
BRIGHT_WHITE   = "\033[97m"

LEVEL_COLORS = {
    "DEBUG":    DIM + WHITE,
    "INFO":     BRIGHT_GREEN,
    "WARNING":  BRIGHT_YELLOW,
    "ERROR":    BRIGHT_RED,
    "CRITICAL": BOLD + RED,
}

LEVEL_ICONS = {
    "DEBUG":    "·",
    "INFO":     "✓",
    "WARNING":  "⚠",
    "ERROR":    "✗",
    "CRITICAL": "☠",
}


class ColorFormatter(logging.Formatter):
    """Console formatter with colors and icons."""

    def format(self, record: logging.LogRecord) -> str:
        level = record.levelname
        color = LEVEL_COLORS.get(level, WHITE)
        icon  = LEVEL_ICONS.get(level, " ")

        ts    = datetime.fromtimestamp(record.created).strftime("%H:%M:%S")
        name  = record.name.split(".")[-1][:16]          # last segment, max 16 chars

        # Color the level badge
        level_badge = f"{color}{BOLD}{icon} {level:<8}{RESET}"

        # Dim timestamp, colored name
        header = f"{DIM}{ts}{RESET}  {level_badge}  {CYAN}{name:<16}{RESET}"

        msg = record.getMessage()

        # Highlight HTTP status codes
        if "200" in msg:
            msg = msg.replace("200", f"{BRIGHT_GREEN}200{RESET}")
        elif any(c in msg for c in ("400", "401", "403", "404", "500")):
            for code in ("400", "401", "403", "404", "500"):
                msg = msg.replace(code, f"{BRIGHT_RED}{code}{RESET}")

        # Highlight durations
        import re
        msg = re.sub(r"(\d+\.\d+s)", f"{BRIGHT_YELLOW}\\1{RESET}", msg)

        line = f"{header}  {msg}"

        if record.exc_info:
            line += "\n" + self.formatException(record.exc_info)

        return line


class PlainFormatter(logging.Formatter):
    """Plain formatter for log file (no ANSI codes)."""
    def format(self, record: logging.LogRecord) -> str:
        ts   = datetime.fromtimestamp(record.created).strftime("%Y-%m-%d %H:%M:%S")
        line = f"{ts}  {record.levelname:<8}  {record.name}  {record.getMessage()}"
        if record.exc_info:
            line += "\n" + self.formatException(record.exc_info)
        return line


def setup_logging(log_level: str = "INFO", log_dir: str = "logs") -> None:
    """Configure root logger with console + rotating file handlers."""

    level = getattr(logging, log_level.upper(), logging.INFO)

    # ── Root logger ───────────────────────────────────────────────────────────
    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()

    # ── Console handler (colored) ─────────────────────────────────────────────
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(level)
    console.setFormatter(ColorFormatter())
    root.addHandler(console)

    # ── File handler (rotating, plain) ────────────────────────────────────────
    Path(log_dir).mkdir(exist_ok=True)
    log_file = os.path.join(log_dir, "app.log")
    file_handler = logging.handlers.RotatingFileHandler(
        log_file,
        maxBytes=5 * 1024 * 1024,   # 5 MB
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(PlainFormatter())
    root.addHandler(file_handler)

    # ── Silence noisy third-party loggers ─────────────────────────────────────
    for noisy in ("httpx", "httpcore", "uvicorn.access", "hpack"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    # Keep uvicorn error logs
    logging.getLogger("uvicorn.error").setLevel(logging.INFO)

    logging.getLogger(__name__).info(
        f"Logging initialised  level={log_level}  file={log_file}"
    )
