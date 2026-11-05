import json
import logging


class EventFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return json.dumps({"time": self.formatTime(record), "level": record.levelname,
                           "component": record.name, "event": record.getMessage()},
                          ensure_ascii=False)


def configure_logging(level: str) -> None:
    logger = logging.getLogger("fashion_ai")
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(EventFormatter())
        logger.addHandler(handler)
    logger.setLevel(level.upper())
    logger.propagate = False
