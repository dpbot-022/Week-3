import logging
import sys
import json
from datetime import datetime, timezone
from typing import Any, Dict

class PIIScrubFilter(logging.Filter):
    """Ensures no sensitive PII strings ever escape into stdout/stderr logs."""
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            from src.guardrails.pii_guard import pii_guard
            if isinstance(record.msg, str):
                record.msg, _ = pii_guard.redact(record.msg)
            if record.args:
                new_args = []
                for a in record.args:
                    if isinstance(a, str):
                        clean_a, _ = pii_guard.redact(a)
                        new_args.append(clean_a)
                    else:
                        new_args.append(a)
                record.args = tuple(new_args)
        except Exception:
            pass
        return True

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
        handler.addFilter(PIIScrubFilter())
        logger.addHandler(handler)
        logger.addFilter(PIIScrubFilter())
    return logger

logger = setup_logger()
