"""reminder_state.json: gönderilen hatırlatma kayıtlarının kalıcı durumu."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from . import config as cfg

logger = logging.getLogger(__name__)


class ReminderState:
    """Incident bazında hangi kademe hatırlatmanın gönderildiğini tutar.

    Yapı:
        {
          "INC0010001": {
            "stage": 1,
            "last_reminder_sent_at": "2026-06-16T09:00:00+00:00",
            "last_seen_comment_at": "2026-06-14T09:00:00+00:00"
          }
        }
    """

    def __init__(self, data: dict[str, Any] | None = None):
        self._data: dict[str, Any] = data or {}

    @classmethod
    def load(cls) -> "ReminderState":
        if cfg.STATE_FILE.exists():
            try:
                with cfg.STATE_FILE.open("r", encoding="utf-8") as fh:
                    return cls(json.load(fh))
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning("State dosyası okunamadı (%s); sıfırdan başlanıyor.", exc)
        return cls({})

    def save(self) -> None:
        with cfg.STATE_FILE.open("w", encoding="utf-8") as fh:
            json.dump(self._data, fh, indent=2, ensure_ascii=False)

    def get_stage(self, number: str) -> int:
        """Bu incident'a en son gönderilen hatırlatma kademesi (0 = hiç)."""
        return int(self._data.get(number, {}).get("stage", 0))

    def last_reminder_sent_at(self, number: str) -> datetime | None:
        raw = self._data.get(number, {}).get("last_reminder_sent_at")
        return _parse_iso(raw) if raw else None

    def record_sent(self, number: str, stage: int, comment_at: datetime | None) -> None:
        self._data[number] = {
            "stage": stage,
            "last_reminder_sent_at": datetime.now(timezone.utc).isoformat(),
            "last_seen_comment_at": comment_at.isoformat() if comment_at else None,
        }

    def reset(self, number: str) -> None:
        """Müşteri yanıt verdiyse döngüyü sıfırla."""
        if number in self._data:
            logger.info("State sıfırlanıyor (müşteri yanıtı): %s", number)
            del self._data[number]


def _parse_iso(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value)
    except (ValueError, TypeError):
        return None
