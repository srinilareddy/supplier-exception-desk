import json
import logging
from datetime import UTC, datetime

logger = logging.getLogger("desk.events")
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)
logger.setLevel(logging.INFO)
logger.propagate = False


def event(name: str, *, level: int = logging.INFO, **fields) -> None:
    payload = {
        "timestamp": datetime.now(UTC).isoformat(),
        "event": name,
        "level": logging.getLevelName(level),
    }
    logger.log(level, json.dumps(payload | fields, separators=(",", ":")))
