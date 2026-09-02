from __future__ import annotations
import logging
import sys
from src.core.config import LOG_LEVEL, LOG_FILE_PATH


# Perhaps for audit or regulatory requirements (Traceability)
def setup_logger(name: str = "orbitmesh") -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        formatter = logging.Formatter(
            "[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

        stream_handler = logging.StreamHandler(sys.stderr)
        stream_handler.setFormatter(formatter)
        logger.addHandler(stream_handler)

        try:
            LOG_FILE_PATH.parent.mkdir(parents=True, exist_ok=True)
            file_handler = logging.FileHandler(str(LOG_FILE_PATH), encoding="utf-8")
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)
        except Exception:
            pass

    logger.setLevel(getattr(logging, LOG_LEVEL, logging.INFO))
    return logger


logger = setup_logger("orbitmesh")
