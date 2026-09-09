"""
Logging module with structured logging and health check support
"""

import logging
import sys
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional


class StructuredFormatter(logging.Formatter):
    """JSON formatter for structured logging"""
    
    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            'timestamp': datetime.utcnow().isoformat() + 'Z',
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
            'module': record.module,
            'function': record.funcName,
            'line': record.lineno
        }
        
        if record.exc_info:
            log_data['exception'] = self.formatException(record.exc_info)
        
        # Add extra fields if present
        for key, value in record.__dict__.items():
            if key not in ('args', 'asctime', 'created', 'exc_info', 'exc_text',
                          'filename', 'funcName', 'levelname', 'levelno', 'lineno',
                          'module', 'msecs', 'message', 'msg', 'name', 'pathname',
                          'process', 'processName', 'relativeCreated', 'stack_info',
                          'thread', 'threadName'):
                log_data[key] = value
        
        return json.dumps(log_data, ensure_ascii=False)


def setup_logging(config: Optional[Dict[str, Any]] = None, 
                  structured: bool = False) -> logging.Logger:
    """
    Setup logging with optional structured JSON output.
    
    Args:
        config: Logging configuration dict with keys:
            - level: Log level (default: INFO)
            - file: Log file path (default: logs/app.log)
            - format: Log format string (ignored if structured=True)
            - structured: Enable JSON structured logging (default: False)
        structured: Enable structured logging (overrides config)
    
    Returns:
        Configured logger instance
    """
    if config is None:
        config = {}
    
    log_level_str = config.get('level', 'INFO')
    log_level = getattr(logging, log_level_str.upper(), logging.INFO)
    log_file = config.get('file', 'logs/app.log')
    log_format = config.get('format', '%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    use_structured = config.get('structured', structured)
    
    # Create log directory
    log_path = Path(log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Get root logger
    logger = logging.getLogger()
    logger.setLevel(log_level)
    
    # Clear existing handlers
    logger.handlers.clear()
    
    # Choose formatter
    if use_structured:
        formatter = StructuredFormatter()
    else:
        formatter = logging.Formatter(log_format)
    
    # File handler
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setLevel(log_level)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    
    # Console handler (slightly less verbose)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    if not use_structured:
        console_formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        console_handler.setFormatter(console_formatter)
    else:
        console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # Capture warnings
    logging.captureWarnings(True)
    
    return logger


class HealthChecker:
    """Health check utility for monitoring"""
    
    def __init__(self):
        self.start_time = datetime.now()
        self.checks: Dict[str, bool] = {}
        self.last_check_time: Optional[datetime] = None
    
    def register_check(self, name: str, status: bool) -> None:
        """Register a health check result"""
        self.checks[name] = status
        self.last_check_time = datetime.now()
    
    def get_status(self) -> Dict[str, Any]:
        """Get overall health status"""
        all_healthy = all(self.checks.values()) if self.checks else True
        
        return {
            'status': 'healthy' if all_healthy else 'unhealthy',
            'uptime_seconds': (datetime.now() - self.start_time).total_seconds(),
            'checks': self.checks,
            'last_check': self.last_check_time.isoformat() if self.last_check_time else None,
            'timestamp': datetime.now().isoformat()
        }
    
    def is_healthy(self) -> bool:
        """Check if all systems are healthy"""
        return all(self.checks.values()) if self.checks else True


# Global health checker instance
health_checker = HealthChecker()


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance with the given name"""
    return logging.getLogger(name)
