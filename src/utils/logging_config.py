# src/utils/logging_config.py (Robust Version)

import logging
import json
from datetime import datetime
from pathlib import Path
from typing import Any

LOG_DIR = Path("logs")
LOG_DIR.mkdir(parents=True, exist_ok=True)

LOG_FILE = LOG_DIR / f"interactions_{datetime.now().strftime('%Y-%m-%d')}.log"


def safe_serialize(obj: Any) -> str:
    """Safely convert any object to string for logging"""
    if obj is None:
        return "null"
    if isinstance(obj, (str, int, float, bool)):
        return str(obj)
    if isinstance(obj, (list, tuple)):
        return ", ".join(str(item) for item in obj)
    if isinstance(obj, dict):
        return json.dumps(obj, default=str)
    return str(obj)


class JSONFormatter(logging.Formatter):
    """Structured JSON logging formatter"""
    
    def format(self, record):
        log_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": record.levelname,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno
        }
        
        # Add extra fields safely (convert any lists to strings)
        extra_fields = [
            'session_id', 'query', 'symptoms', 'severity', 
            'matched_count', 'matched_conditions', 'intent', 
            'response_len', 'total_time_ms', 'error', 'error_type',
            'profile_age', 'history_count'
        ]
        
        for field in extra_fields:
            if hasattr(record, field):
                value = getattr(record, field)
                # Convert lists/tuples to strings
                if isinstance(value, (list, tuple)):
                    log_entry[field] = ", ".join(str(v) for v in value)
                elif isinstance(value, dict):
                    log_entry[field] = json.dumps(value)
                else:
                    log_entry[field] = value
        
        return json.dumps(log_entry, ensure_ascii=False)


class CustomLogger:
    """Simple wrapper for logging with extra fields"""
    
    def __init__(self, logger):
        self.logger = logger
    
    def _log(self, level, msg, **kwargs):
        # Get extra data
        extra = kwargs.get('extra', {})
        
        # Create log record
        record = self.logger.makeRecord(
            name=self.logger.name,
            level=level,
            fn=self.logger.findCaller()[0],
            lno=self.logger.findCaller()[1],
            msg=msg,
            args=(),
            exc_info=None,
            func=self.logger.findCaller()[2],
            extra=extra
        )
        
        # Add extra fields as attributes (already done by makeRecord)
        self.logger.handle(record)
    
    def info(self, msg, **kwargs):
        self._log(logging.INFO, msg, **kwargs)
    
    def error(self, msg, **kwargs):
        self._log(logging.ERROR, msg, **kwargs)
    
    def debug(self, msg, **kwargs):
        self._log(logging.DEBUG, msg, **kwargs)
    
    def warning(self, msg, **kwargs):
        self._log(logging.WARNING, msg, **kwargs)


def setup_logger():
    """Setup logging with JSON and console handlers"""
    logger = logging.getLogger("medical_assistant")
    logger.setLevel(logging.INFO)
    
    # Clear existing handlers
    if logger.handlers:
        logger.handlers.clear()
    
    # Console handler (simple)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(
        logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(funcName)s → %(message)s",
            datefmt="%H:%M:%S"
        )
    )
    
    # File handler (JSON structured logs)
    file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(JSONFormatter())
    
    logger.addHandler(console_handler)
    logger.addHandler(file_handler)
    
    return logger


# Create global logger instance
_logger = setup_logger()
logger = CustomLogger(_logger)


def get_logger():
    """Get the global logger instance"""
    return logger