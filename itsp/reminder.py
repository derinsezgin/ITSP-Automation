"""Hatırlatıcı kademe mantığı, 'bizim taraf' kontrolü ve yorum gönderimi.

DİKKAT: Bu modüldeki YAZMA işlevleri yalnızca `remind` modunda kullanılır ve
sadece Activity stream'in "Additional comments" alanına yorum POST eder.
Assign / close / resolve / state değişimi YAPMAZ (tam form Save kullanılmaz).
"""

from __future__ import annotations

import csv
import logging
from datetime import datetime, timezone
from typing import Optional

from playwright.sync_api import Page, TimeoutError as PWTimeoutError

from . import config as cfg
from .scraper import Incident, _content_root
from .state import ReminderState
from .workdays import parse_holidays, working_days_between

logger = logging.getLogger(__name__)

# Kademe -> Excel/log için okunabilir etiket.
STAGE_LABELS = {1: "1. hatırlatma", 2: "2. hatırlatma (kapanış uyarılı)"}


def classify_side(inc: Incident, conf: cfg.Config) -> str:
    """Son yorum 'bizim taraf' mı (Us) yoksa müşteri mi (Customer)?

    Bizim taraf = yazar config.internal_users içinde VEYA incident'ın atandığı
    grup config.internal_groups içinde.
    """
    author = (inc.last_comment_author or "").strip().lower()
    if not author:
        return ""

    internal_users = {u.strip().lower() for u in (conf.get("internal_users") or [])}
    internal_groups = {g.strip().lower() for g in (conf.get("internal_groups") or [])}

    if author in internal_users:
        return "Us"
    if (inc.assignment_group or "").strip().lower() in internal_groups:
        # Atanan grup bizim grubumuz; son yorum yazarı da bu gruba ait kabul edilir.
        return "Us"
    return "Customer"


def status_in_scope(inc: Incident, conf: cfg.Config) -> bool:
    """Incident, hatırlatma için hedef statülerden birinde mi?"""
    targets = [s.strip().lower() for s in (conf.get("reminder.target_statuses") or [])]
    if not targets:  # boş = tüm statüler kapsamda
        return True
    return (inc.status or "").strip().lower() in targets


def activity_contains_marker(page: Page, conf: cfg.Config) -> bool:
    """Açık olan kayıtta daha önce bizim gönderdiğimiz hatırlatma var mı?

    İdempotensi: state dosyası silinmiş olsa bile Activity stream'de imza
    (signature_marker) aranarak çift gönderim engellenir.
    """
    marker = (conf.get("reminder.signature_marker") or "").strip()
    if not marker:
        return False
    root = _content_root(page, conf)
    try:
        text = root.content()  # Frame veya Page içeriği
    except Exception:  # noqa: BLE001
        return False
    return marker in text


def decide_stage(
    inc: Incident,
    state: ReminderState,
    conf: cfg.Config,
    now: Optional[datetime] = None,
) -> tuple[int, str]:
    """Gönderilecek hatırlatma kademesini belirler.

    Döner: (stage, reason)
      stage 0 -> gönderme; reason açıklaması Excel 'action' için kullanılır.
      stage 1 -> 1. hatırlatma; stage 2 -> 2. hatırlatma.
    """
    now = now or datetime.now()
    holidays = parse_holidays(conf.get("workdays.holidays"))

    # 1) Statü kapsamı
    if not status_in_scope(inc, conf):
        return 0, "Atlandı (statü kapsam dışı)"

    # 2) Bizim taraf mı? Değilse hatırlatma yok + state sıfırla.
    side = classify_side(inc, conf)
    inc.side = side
    if side != "Us":
        state.reset(inc.number)
        return 0, "Atlandı (son yorum bizden değil)"

    # 3) Tarih var mı?
    if inc.last_comment_date is None:
        return 0, "Atlandı (son yorum tarihi okunamadı)"

    prev_stage = state.get_stage(inc.number)

    # 4) Kademe seçimi
    first_after = int(conf.get("reminder.first_after_workdays", 2))
    second_after = int(conf.get("reminder.second_after_workdays", 2))

    if prev_stage >= 2:
        return 0, "Atlandı (2. hatırlatma zaten gönderildi — kapatma manuel)"

    if prev_stage == 0:
        wd = working_days_between(inc.last_comment_date, now, holidays)
        inc.working_days_since = wd
        if wd >= first_after:
            return 1, ""
        return 0, f"Atlandı (henüz {wd} iş günü; {first_after} bekleniyor)"

    # prev_stage == 1 -> 2. hatırlatma zamanı mı?
    last_sent = state.last_reminder_sent_at(inc.number)
    if last_sent is None:
        # state tutarsız; güvenli tarafta kal.
        return 0, "Atlandı (önceki gönderim zamanı bilinmiyor)"
    wd = working_days_between(last_sent, now, holidays)
    inc.working_days_since = wd
    if wd >= second_after:
        return 2, ""
    return 0, f"Atlandı (1. hatırlatmadan {wd} iş günü; {second_after} bekleniyor)"


def recommend_action(
    inc: Incident,
    state: ReminderState,
    conf: cfg.Config,
    now: Optional[datetime] = None,
) -> str:
    """Salt-okunur aksiyon listesi için: incident'ın önerilen sonraki adımı.

    Gönderim kararını, sürecin manuel adımlarıyla (gün 6 kapatma, 'müşteri yanıt
    verdi') birleştirip insan-okur bir öneri döndürür. Hiçbir yazma yapmaz;
    state yalnızca okunur.
    """
    now = now or datetime.now()
    holidays = parse_holidays(conf.get("workdays.holidays"))

    if not status_in_scope(inc, conf):
        return "Kapsam dışı (statü hedef listede değil)"

    side = classify_side(inc, conf)
    inc.side = side
    if side == "Customer":
        return "Müşteri yanıt verdi — incele ve işlem yap"
    if side != "Us":
        return "Son yorum sahibi belirsiz — kontrol et"

    if inc.last_comment_date is None:
        return "Son yorum tarihi okunamadı — kontrol et"

    first = int(conf.get("reminder.first_after_workdays", 2))
    second = int(conf.get("reminder.second_after_workdays", 2))
    closure = int(conf.get("reminder.closure_after_workdays", 2))
    prev = state.get_stage(inc.number)

    if prev == 0:
        wd = working_days_between(inc.last_comment_date, now, holidays)
        inc.working_days_since = wd
        if wd >= first:
            return f"1. hatırlatma gönder (son yorumdan {wd} iş günü geçti)"
        return f"Bekle — 1. hatırlatma için {first} iş günü ({wd}/{first})"

    last_sent = state.last_reminder_sent_at(inc.number)
    wd = working_days_between(last_sent, now, holidays) if last_sent else None
    inc.working_days_since = wd

    if prev == 1:
        if wd is not None and wd >= second:
            return "2. hatırlatma gönder (kapanış uyarılı)"
        return f"Bekle — 2. hatırlatma için {second} iş günü ({wd}/{second})"

    # prev >= 2 : ikinci hatırlatma gönderilmiş
    if wd is not None and wd >= closure:
        return f"KAPATILABİLİR (gün 6) — müşteri yanıtı yok, manuel kapat ({wd} iş günü)"
    return f"2. hatırlatma gönderildi — kapanış için bekle ({wd}/{closure} iş günü)"


def reminder_text(stage: int, conf: cfg.Config, inc: Optional[Incident] = None) -> str:
    """İlgili kademe metni + idempotensi imzası.

    Metindeki yer tutucular incident bilgisiyle doldurulur:
      {number}            -> incident numarası (ör. INC0010001)
      {assignment_group}  -> atanan grup
      {priority}          -> öncelik
      {status}            -> statü
    """
    key = "reminder.reminder_1_text" if stage == 1 else "reminder.reminder_2_text"
    body = (conf.get(key) or "").rstrip()

    if inc is not None:
        replacements = {
            "{number}": inc.number or "",
            "{assignment_group}": inc.assignment_group or "",
            "{priority}": inc.priority or "",
            "{status}": inc.status or "",
        }
        for placeholder, value in replacements.items():
            body = body.replace(placeholder, value)

    marker = (conf.get("reminder.signature_marker") or "").strip()
    if marker and marker not in body:
        body = f"{body}\n\n{marker}"
    return body


def post_reminder(page: Page, conf: cfg.Config, inc: Incident, text: str) -> None:
    """SADECE 'Additional comments' alanına yorumu yazıp Post butonuna basar.

    Tam form Save/Submit KULLANILMAZ. Kayıt zaten _read_last_comment ile açılmış
    olabilir; güvence için record URL'ine tekrar gidilir.
    """
    base = conf.require("base_url").rstrip("/")
    record_url = inc.url or f"{base}/incident.do?sysparm_query=number={inc.number}"
    page.goto(record_url, wait_until="domcontentloaded")

    root = _content_root(page, conf)
    sel = conf.get("selectors", {})
    input_sel = sel.get("comment_input")
    button_sel = sel.get("comment_post_button")
    if not input_sel or not button_sel:
        raise ValueError("config.yaml: selectors.comment_input / comment_post_button tanımlı değil")

    try:
        box = root.wait_for_selector(input_sel, timeout=conf.get("timeouts.selector", 15000))
    except PWTimeoutError as exc:
        raise RuntimeError(f"Yorum alanı bulunamadı ({inc.number})") from exc

    box.click()
    box.fill(text)
    root.locator(button_sel).first.click()
    # Postun işlenmesi için kısa bekleme.
    page.wait_for_timeout(1500)
    logger.info("Hatırlatma gönderildi: %s (kademe bilgisi audit log'da)", inc.number)


def append_audit_log(inc: Incident, stage: int, dry_run: bool) -> None:
    """reminders_log.csv'ye bir satır ekler."""
    is_new = not cfg.AUDIT_LOG.exists()
    with cfg.AUDIT_LOG.open("a", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        if is_new:
            writer.writerow(
                ["timestamp", "incident", "stage", "dry_run", "status", "assignment_group", "last_comment_author"]
            )
        writer.writerow(
            [
                datetime.now(timezone.utc).isoformat(),
                inc.number,
                STAGE_LABELS.get(stage, str(stage)),
                "yes" if dry_run else "no",
                inc.status,
                inc.assignment_group,
                inc.last_comment_author,
            ]
        )
