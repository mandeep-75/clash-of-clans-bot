"""Logging setup: timestamped output to the console and the session log."""

import logging
import sys

import config

_LOG_FORMAT = "%(asctime)s %(levelname)-7s %(message)s"
_LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def setup_logger() -> logging.Logger:
    """Builds the shared "coc-bot" logger (console + file) once."""
    logger = logging.getLogger("coc-bot")
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)
    formatter = logging.Formatter(_LOG_FORMAT, _LOG_DATE_FORMAT)

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(formatter)
    logger.addHandler(console)

    file_handler = logging.FileHandler(config.LOG_FILE, encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logger


def setup_resource_logger() -> logging.Logger:
    """Builds a file-only logger for resource tracking."""
    logger = logging.getLogger("coc-bot-resources")
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)
    formatter = logging.Formatter(_LOG_FORMAT, _LOG_DATE_FORMAT)

    file_handler = logging.FileHandler("resources.log", encoding="utf-8")
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.INFO)
    logger.addHandler(file_handler)
    logger.propagate = False

    return logger


log = setup_logger()
rlog = setup_resource_logger()
