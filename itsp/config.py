"""config.yaml + .env yükleme ve basit doğrulama."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

# Proje kök dizini (bu dosyanın bir üstü).
ROOT = Path(__file__).resolve().parent.parent

DEFAULT_CONFIG_PATH = ROOT / "config.yaml"
BROWSER_PROFILE_DIR = ROOT / "browser_profile"
SCREENSHOTS_DIR = ROOT / "screenshots"
STATE_FILE = ROOT / "reminder_state.json"
AUDIT_LOG = ROOT / "reminders_log.csv"
REPORT_FILE = ROOT / "incident_report.xlsx"


class Config:
    """config.yaml içeriğine noktalı erişim sağlayan ince sarmalayıcı."""

    def __init__(self, data: dict[str, Any]):
        self._data = data

    def get(self, path: str, default: Any = None) -> Any:
        """Noktalı yol ile değer döndürür. Örn: get('reminder.max_per_run')."""
        node: Any = self._data
        for part in path.split("."):
            if isinstance(node, dict) and part in node:
                node = node[part]
            else:
                return default
        return node

    def require(self, path: str) -> Any:
        """Zorunlu alanı döndürür; yoksa hata fırlatır."""
        sentinel = object()
        value = self.get(path, sentinel)
        if value is sentinel or value in (None, ""):
            raise ValueError(f"config.yaml içinde zorunlu alan eksik: '{path}'")
        return value

    @property
    def data(self) -> dict[str, Any]:
        return self._data


def load_config(path: Path | str | None = None) -> Config:
    """config.yaml'ı yükler ve .env değerleriyle ezer."""
    load_dotenv(ROOT / ".env")

    config_path = Path(path) if path else DEFAULT_CONFIG_PATH
    if not config_path.exists():
        raise FileNotFoundError(f"Yapılandırma dosyası bulunamadı: {config_path}")

    with config_path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}

    # .env override (yalnızca non-secret değerler).
    env_base = os.getenv("ITSP_BASE_URL")
    if env_base:
        data["base_url"] = env_base

    return Config(data)
