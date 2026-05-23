import logging
import json
import time
from contextvars import ContextVar
from datetime import datetime

# Context variable to hold the current scan_id
current_scan_id: ContextVar[str] = ContextVar("current_scan_id", default="")

class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        # Exclude secrets
        msg = record.getMessage()
        if msg:
            # Mask common secret patterns if they accidentally slip in
            # We already redact in reporter, but this is a fallback for logs
            if "ghp_" in msg:
                msg = msg.replace("ghp_", "ghp_***")
            if "sk-" in msg:
                msg = msg.replace("sk-", "sk-***")
                
        log_obj = {
            "timestamp": datetime.fromtimestamp(record.created).isoformat() + "Z",
            "level": record.levelname,
            "message": msg,
            "module": record.module,
            "funcName": record.funcName,
        }
        
        scan_id = current_scan_id.get()
        if scan_id:
            log_obj["scan_id"] = scan_id
            
        if record.exc_info:
            log_obj["exception"] = self.formatException(record.exc_info)
            
        return json.dumps(log_obj)

def setup_logger(name: str = "aegis") -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        handler = logging.StreamHandler()
        handler.setFormatter(JsonFormatter())
        logger.addHandler(handler)
    return logger

log = setup_logger()
