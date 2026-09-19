"""Configuration du logging de l'application."""

import logging
import logging.config
import os


def configure_logging() -> None:
    """Configure les logs applicatifs et ceux d'Uvicorn selon la variable LOG_LEVEL."""
    level = os.getenv("LOG_LEVEL", "INFO").upper()
    is_development = os.getenv("ZENHOME_ENV", "production").lower() in {"development", "dev"}
    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "default": {
                    "format": "%(asctime)s %(levelname)s %(name)s: %(message)s",
                },
            },
            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "formatter": "default",
                    "stream": "ext://sys.stdout",
                },
            },
            "root": {
                "level": level,
                "handlers": ["console"],
            },
            "loggers": {
                "sqlalchemy.engine": {
                    "level": "INFO" if is_development else "WARNING",
                    "handlers": ["console"],
                    "propagate": False,
                },
                "uvicorn": {"level": level, "handlers": ["console"], "propagate": False},
                "uvicorn.error": {"level": level, "handlers": ["console"], "propagate": False},
                "uvicorn.access": {"level": level, "handlers": ["console"], "propagate": False},
            },
        }
    )
