from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger("intellidocs.run")


def log_run_event(event: str, **fields: Any) -> None:
    payload = {"event": event, **fields}
    logger.info(json.dumps(payload, sort_keys=True, default=str))
