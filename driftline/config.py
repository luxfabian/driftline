"""Paths, host/port and logging setup (architecture §4.4)."""

from __future__ import annotations

import logging
import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

HOST = "127.0.0.1"  # fixed, not overridable [NFR-02]
DEFAULT_PORT = 8050
DEFAULT_DATA_DIR = Path.home() / ".driftline"

ENV_DATA_DIR = "DRIFTLINE_DATA_DIR"
ENV_PORT = "DRIFTLINE_PORT"

LOGGER_NAME = "driftline"


@dataclass(frozen=True)
class Config:
    data_dir: Path
    host: str
    port: int

    @property
    def db_path(self) -> Path:
        return self.data_dir / "driftline.db"

    @property
    def backup_dir(self) -> Path:
        return self.data_dir / "backups"

    @property
    def log_path(self) -> Path:
        return self.data_dir / "driftline.log"


def load_config(env: Mapping[str, str] | None = None) -> Config:
    """Build the configuration from defaults and environment overrides."""
    env = os.environ if env is None else env

    data_dir_raw = env.get(ENV_DATA_DIR, "").strip()
    data_dir = Path(data_dir_raw).expanduser() if data_dir_raw else DEFAULT_DATA_DIR

    port_raw = env.get(ENV_PORT, "").strip()
    if port_raw:
        try:
            port = int(port_raw)
        except ValueError as exc:
            raise ValueError(f"{ENV_PORT} must be an integer, got {port_raw!r}") from exc
        if not 1 <= port <= 65535:
            raise ValueError(f"{ENV_PORT} must be between 1 and 65535, got {port}")
    else:
        port = DEFAULT_PORT

    return Config(data_dir=data_dir, host=HOST, port=port)


def setup_logging(config: Config, level: int = logging.INFO) -> logging.Logger:
    """Log to ``<data>/driftline.log`` and the console. Safe to call twice."""
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(level)
    if getattr(logger, "_driftline_configured", False):
        return logger

    config.data_dir.mkdir(parents=True, exist_ok=True)
    fmt = logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s")

    file_handler = logging.FileHandler(config.log_path, encoding="utf-8")
    file_handler.setFormatter(fmt)
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(fmt)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    logger._driftline_configured = True  # type: ignore[attr-defined]
    return logger
