import logging
import sys
import json
from datetime import datetime, timezone
from typing import Any, Dict

class StructuredFormatter(logging.Formatter):
    """Formats log records as structured JSON for production observability."""
    def format(self, record: logging.LogRecord) -> str:
        log_data: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if hasattr(record, "request_id"):
            log_data["request_id"] = getattr(record, "request_id")
        if hasattr(record, "latency_ms"):
            log_data["latency_ms"] = getattr(record, "latency_ms")
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_data)

def setup_logger(name: str = "rag_pipeline") -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(StructuredFormatter())
        logger.addHandler(handler)
    return logger

logger = setup_logger()
