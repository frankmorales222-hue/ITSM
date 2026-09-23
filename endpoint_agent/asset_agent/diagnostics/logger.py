import json
import logging
from pathlib import Path


def configure_logging(path: Path) -> logging.Logger:
    path.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("northstar_agent")
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        handler = logging.FileHandler(path, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
        logger.addHandler(handler)
    return logger


def event(logger: logging.Logger, name: str, **safe_fields) -> None:
    logger.info(json.dumps({"event": name, **safe_fields}, separators=(",", ":"), default=str))
