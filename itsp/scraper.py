"""Incident listesi ve kayıt detayı okuma (salt-okunur çekirdek)."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from playwright.sync_api import Frame, Page, TimeoutError as PWTimeoutError

from . import config as cfg

logger = logging.getLogger(__name__)

# ServiceNow ekranlarında karşılaşılan yaygın tarih formatları.
_DATE_FORMATS = [
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%d-%m-%Y %H:%M:%S",
    "%m/%d/%Y %H:%M:%S",
    "%d/%m/%Y %H:%M:%S",
    "%Y-%m-%d",
]


@dataclass
class Incident:
    number: str
    status: str = ""
    priority: str = ""
    assignment_group: str = ""
    last_comment_date: Optional[datetime] = None
    last_comment_date_raw: str = ""
    last_comment_author: str = ""
    last_comment_type: str = ""  # "comments" (müşteriye görünür) / "work_notes"
    url: str = ""
    # remind akışı tarafından doldurulan alanlar:
    side: str = ""              # "Us" / "Customer" / ""
    working_days_since: Optional[int] = None
    reminder_stage: str = ""    # "1. hatırlatma" vb.
    action: str = ""

    raw_cells: dict = field(default_factory=dict)


def parse_datetime(text: str) -> Optional[datetime]:
    """Serbest metin tarihi datetime'a çevirmeye çalışır."""
    text = (text or "").strip()
    if not text:
        return None
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    logger.debug("Tarih ayrıştırılamadı: %r", text)
    return None


def _content_root(page: Page, conf: cfg.Config) -> Frame | Page:
    """Classic UI'da içerik gsft_main iframe'inde olabilir; uygun kökü döndürür."""
    iframe_sel = conf.get("selectors.iframe")
    if not iframe_sel:
        return page
    try:
        element = page.wait_for_selector(iframe_sel, timeout=5000)
        frame = element.content_frame() if element else None
        if frame:
            logger.debug("İçerik iframe'ine geçildi: %s", iframe_sel)
            return frame
    except PWTimeoutError:
        logger.debug("iframe bulunamadı (%s); ana sayfada aranıyor.", iframe_sel)
    return page


def _cell_text(row, selector: str) -> str:
    if not selector:
        return ""
    try:
        loc = row.locator(selector).first
        if loc.count() == 0:
            return ""
        return (loc.inner_text(timeout=3000) or "").strip()
    except Exception:  # noqa: BLE001
        return ""


def scrape_incidents(page: Page, conf: cfg.Config) -> list[Incident]:
    """Incident liste sayfasını dolaşıp her kayıt için alanları toplar."""
    list_url = conf.require("incident_list_url")
    logger.info("Incident listesi açılıyor: %s", list_url)
    page.goto(list_url, wait_until="domcontentloaded")

    max_incidents = int(conf.get("limits.max_incidents", 200))
    next_selector = conf.get("pagination.next_selector")
    sel = conf.get("selectors", {})

    incidents: list[Incident] = []
    seen_numbers: set[str] = set()
    page_index = 0

    while len(incidents) < max_incidents:
        root = _content_root(page, conf)
        try:
            root.wait_for_selector(sel.get("row"), timeout=conf.get("timeouts.selector", 15000))
        except PWTimeoutError:
            logger.warning("Liste satırı bulunamadı (sayfa %d). Seçicileri kontrol edin.", page_index)
            break

        rows = root.locator(sel.get("row"))
        count = rows.count()
        logger.info("Sayfa %d: %d satır bulundu.", page_index, count)

        for i in range(count):
            if len(incidents) >= max_incidents:
                break
            row = rows.nth(i)
            number = _cell_text(row, sel.get("number"))
            if not number or number in seen_numbers:
                continue
            seen_numbers.add(number)

            inc = Incident(
                number=number,
                status=_cell_text(row, sel.get("status")),
                priority=_cell_text(row, sel.get("priority")),
                assignment_group=_cell_text(row, sel.get("assignment_group")),
            )
            incidents.append(inc)

        # Pagination
        if not next_selector:
            break
        try:
            nxt = page.locator(next_selector).first
            if nxt.count() == 0 or not nxt.is_enabled(timeout=2000):
                break
            nxt.click()
            page.wait_for_load_state("domcontentloaded")
            page_index += 1
        except Exception:  # noqa: BLE001
            break

    logger.info("Toplam %d incident listelendi. Son yorum detayları okunuyor...", len(incidents))

    # Her incident için kayıt detayından son yorumu oku.
    for inc in incidents:
        try:
            _read_last_comment(page, conf, inc)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Son yorum okunamadı (%s): %s", inc.number, exc)

    return incidents


def _read_last_comment(page: Page, conf: cfg.Config, inc: Incident) -> None:
    """Incident kaydını okuma amaçlı açıp Activity stream'in en yeni girdisini alır."""
    sel = conf.get("selectors", {})
    base = conf.require("base_url").rstrip("/")
    record_url = f"{base}/incident.do?sysparm_query=number={inc.number}"
    inc.url = record_url
    page.goto(record_url, wait_until="domcontentloaded")

    root = _content_root(page, conf)
    entry_sel = sel.get("activity_entry")
    if not entry_sel:
        return
    try:
        root.wait_for_selector(entry_sel, timeout=conf.get("timeouts.selector", 15000))
    except PWTimeoutError:
        logger.debug("Activity girdisi bulunamadı: %s", inc.number)
        return

    newest = root.locator(entry_sel).first
    inc.last_comment_date_raw = _cell_text(newest, sel.get("activity_date"))
    inc.last_comment_date = parse_datetime(inc.last_comment_date_raw)
    inc.last_comment_author = _cell_text(newest, sel.get("activity_author"))
    inc.last_comment_type = _cell_text(newest, sel.get("activity_type"))
