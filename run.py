#!/usr/bin/env python3
"""ITSP-Automation CLI.

Komutlar:
  python run.py login              Manuel SSO/MFA login (kalıcı profil oluşturur)
  python run.py report             Salt-okunur: incident_report.xlsx üretir
  python run.py remind [--dry-run] Hatırlatıcı akışı (tam otomatik gönderir)
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime

from playwright.sync_api import Page

from itsp import auth, browser, reminder
from itsp import config as cfg
from itsp import scraper
from itsp.excel_writer import write_report
from itsp.reminder import STAGE_LABELS
from itsp.state import ReminderState

logger = logging.getLogger("itsp")


def _setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def _save_screenshot(page: Page, prefix: str) -> str:
    cfg.SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = cfg.SCREENSHOTS_DIR / f"{prefix}_{ts}.png"
    try:
        page.screenshot(path=str(path), full_page=True)
        logger.info("Ekran görüntüsü kaydedildi: %s", path)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Ekran görüntüsü alınamadı: %s", exc)
    return str(path)


# --------------------------------------------------------------------------
# Komutlar
# --------------------------------------------------------------------------

def cmd_login(conf: cfg.Config) -> int:
    """Manuel login: tarayıcı açılır, kullanıcı SSO/MFA ile giriş yapar."""
    with browser.persistent_context(conf) as context:
        page = context.pages[0] if context.pages else context.new_page()
        auth.open_dashboard(page, conf)
        try:
            auth.wait_for_manual_login(page, conf)
        except auth.ManualLoginRequired as exc:
            logger.error(str(exc))
            return 2
    print(">>> Login tamamlandı. Artık `python run.py report` veya `remind` çalıştırabilirsiniz.")
    return 0


def cmd_report(conf: cfg.Config) -> int:
    """Salt-okunur rapor."""
    with browser.persistent_context(conf) as context:
        page = context.pages[0] if context.pages else context.new_page()
        auth.open_dashboard(page, conf)
        try:
            auth.ensure_authenticated(page, conf)
        except auth.ManualLoginRequired as exc:
            logger.error(str(exc))
            _save_screenshot(page, "auth_required")
            print("\n>>> MANUEL LOGIN GEREKİYOR. `python run.py login` çalıştırın.\n")
            return 2

        # Post-auth: salt-okunur koruma (tüm yazma kapalı).
        browser.enable_readonly_guard(context, conf, allow_comment_post=False)

        try:
            incidents = scraper.scrape_incidents(page, conf)
            out = write_report(incidents)
        except Exception:
            _save_screenshot(page, "error")
            raise
        print(f"\n>>> Rapor hazır: {out} ({len(incidents)} incident)\n")
    return 0


def cmd_remind(conf: cfg.Config, dry_run: bool) -> int:
    """Hatırlatıcı akışı (tam otomatik). --dry-run ile sadece simülasyon."""
    state = ReminderState.load()
    max_per_run = int(conf.get("reminder.max_per_run", 25))

    with browser.persistent_context(conf) as context:
        page = context.pages[0] if context.pages else context.new_page()
        auth.open_dashboard(page, conf)
        try:
            auth.ensure_authenticated(page, conf)
        except auth.ManualLoginRequired as exc:
            logger.error(str(exc))
            _save_screenshot(page, "auth_required")
            print("\n>>> MANUEL LOGIN GEREKİYOR. `python run.py login` çalıştırın.\n")
            return 2

        # Post-auth: remind modu — yalnızca yorum POST'una izin, state değişimi kapalı.
        browser.enable_readonly_guard(context, conf, allow_comment_post=not dry_run)

        try:
            incidents = scraper.scrape_incidents(page, conf)
            sent_count = _process_reminders(page, conf, incidents, state, max_per_run, dry_run)
        except Exception:
            _save_screenshot(page, "error")
            if not dry_run:
                state.save()
            raise

        if not dry_run:
            state.save()
        out = write_report(incidents)

    mode = "DRY-RUN (hiçbir şey gönderilmedi)" if dry_run else f"{sent_count} hatırlatma gönderildi"
    print(f"\n>>> Hatırlatıcı akışı tamamlandı — {mode}. Rapor: {out}\n")
    return 0


def _process_reminders(page, conf, incidents, state, max_per_run, dry_run) -> int:
    """Incident listesini dolaşıp kademe kararına göre hatırlatma gönderir.

    Gönderilen (dry-run dışı) hatırlatma sayısını döndürür.
    """
    sent_count = 0
    for inc in incidents:
        stage, reason = reminder.decide_stage(inc, state, conf)
        if stage == 0:
            inc.action = reason
            logger.info("%s: %s", inc.number, reason)
            continue

        if sent_count >= max_per_run:
            inc.action = "Atlandı (max_per_run limiti)"
            logger.info("%s: max_per_run limiti aşıldı, atlanıyor.", inc.number)
            continue

        label = STAGE_LABELS.get(stage, str(stage))
        inc.reminder_stage = label

        # İdempotensi: Activity'de imza zaten varsa gönderme.
        page.goto(inc.url, wait_until="domcontentloaded")
        if reminder.activity_contains_marker(page, conf):
            inc.action = f"Atlandı ({label} zaten mevcut görünüyor)"
            state.record_sent(inc.number, stage, inc.last_comment_date)
            logger.info("%s: imza zaten var, atlanıyor.", inc.number)
            continue

        text = reminder.reminder_text(stage, conf, inc)
        if dry_run:
            inc.action = f"[DRY-RUN] {label} gönderilecekti"
            logger.info("%s: [DRY-RUN] %s gönderilecekti.", inc.number, label)
        else:
            reminder.post_reminder(page, conf, inc, text)
            state.record_sent(inc.number, stage, inc.last_comment_date)
            inc.action = f"{label} GÖNDERİLDİ"
            sent_count += 1

        reminder.append_audit_log(inc, stage, dry_run)

    return sent_count


def cmd_dump(conf: cfg.Config) -> int:
    """Selektör çıkarımı için: liste ve ilk incident kaydının HTML'ini dosyaya döker.

    Kalıcı (giriş yapılmış) profil ile çalışır; iframe (gsft_main) içeriğini de
    ayrı dosyaya yazar. Çıkan dosyalar `debug/` altında oluşur; bunları
    paylaşarak seçicilerin senin arayüzüne göre netleştirilmesini sağlayabilirsin.
    """
    debug_dir = cfg.ROOT / "debug"
    debug_dir.mkdir(parents=True, exist_ok=True)

    with browser.persistent_context(conf) as context:
        page = context.pages[0] if context.pages else context.new_page()
        auth.open_dashboard(page, conf)
        try:
            auth.ensure_authenticated(page, conf)
        except auth.ManualLoginRequired as exc:
            logger.error(str(exc))
            _save_screenshot(page, "auth_required")
            print("\n>>> MANUEL LOGIN GEREKİYOR. Önce `python run.py login` çalıştırın.\n")
            return 2

        # 1) Incident liste sayfası
        list_url = conf.require("incident_list_url")
        logger.info("Liste sayfası dökülüyor: %s", list_url)
        page.goto(list_url, wait_until="domcontentloaded")
        page.wait_for_timeout(2500)
        _dump_html(page, conf, debug_dir, "list")
        page.screenshot(path=str(debug_dir / "list.png"), full_page=True)

        # 2) İlk incident kaydı (varsa) — tek bir örnek yeterli
        try:
            root = scraper._content_root(page, conf)
            row_sel = conf.get("selectors.row")
            num_sel = conf.get("selectors.number")
            number = ""
            if row_sel and num_sel:
                first = root.locator(row_sel).first
                if first.count() > 0:
                    number = (first.locator(num_sel).first.inner_text(timeout=3000) or "").strip()
            if number:
                base = conf.require("base_url").rstrip("/")
                rec_url = f"{base}/incident.do?sysparm_query=number={number}"
                logger.info("Örnek kayıt dökülüyor: %s", rec_url)
                page.goto(rec_url, wait_until="domcontentloaded")
                page.wait_for_timeout(2500)
                _dump_html(page, conf, debug_dir, "record")
                page.screenshot(path=str(debug_dir / "record.png"), full_page=True)
            else:
                logger.warning(
                    "Liste satırı/numarası okunamadı; mevcut seçicilerle kayıt açılamadı. "
                    "Yine de debug/list_inner.html'i paylaşmanız seçicileri çıkarmaya yeter."
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Örnek kayıt dökülemedi: %s", exc)

    print(
        "\n>>> HTML dökümleri 'debug/' klasörüne yazıldı:\n"
        "    - debug/list_inner.html  (iframe içeriği — asıl liste burada)\n"
        "    - debug/list_outer.html  (dış sayfa)\n"
        "    - debug/record_inner.html / record_outer.html (varsa)\n"
        "    - debug/*.png ekran görüntüleri\n"
        ">>> Bu dosyaları paylaşırsan seçicileri arayüzüne göre netleştiririm.\n"
        ">>> NOT: Dosyalar gerçek incident verisi içerebilir; gerekirse paylaşmadan\n"
        "    önce hassas alanları temizleyebilirsin (yapı/etiketler yeterli).\n"
    )
    return 0


def _dump_html(page, conf: cfg.Config, debug_dir, prefix: str) -> None:
    """Dış sayfa + (varsa) iframe içeriğini ayrı dosyalara yazar."""
    outer = page.content()
    (debug_dir / f"{prefix}_outer.html").write_text(outer, encoding="utf-8")

    root = scraper._content_root(page, conf)
    try:
        inner = root.content()
    except Exception:  # noqa: BLE001
        inner = outer
    (debug_dir / f"{prefix}_inner.html").write_text(inner, encoding="utf-8")
    logger.info("Yazıldı: %s_outer.html ve %s_inner.html", prefix, prefix)


# --------------------------------------------------------------------------
# Giriş noktası
# --------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    _setup_logging()
    parser = argparse.ArgumentParser(description="ITSP (ServiceNow) otomasyonu")
    parser.add_argument("--config", help="config.yaml yolu (opsiyonel)")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("login", help="Manuel SSO/MFA login (kalıcı profil)")
    sub.add_parser("report", help="Salt-okunur rapor (incident_report.xlsx)")
    p_remind = sub.add_parser("remind", help="Hatırlatıcı akışı (tam otomatik)")
    p_remind.add_argument(
        "--dry-run",
        action="store_true",
        help="Hiçbir şey göndermeden ne yapılacağını loglar (önerilir: ilk koşu)",
    )
    sub.add_parser("dump", help="Seçici çıkarımı için liste/kayıt HTML'ini debug/ altına döker")

    args = parser.parse_args(argv)

    try:
        conf = cfg.load_config(args.config)
    except (FileNotFoundError, ValueError) as exc:
        logger.error("Yapılandırma hatası: %s", exc)
        return 1

    try:
        if args.command == "login":
            return cmd_login(conf)
        if args.command == "report":
            return cmd_report(conf)
        if args.command == "remind":
            return cmd_remind(conf, dry_run=args.dry_run)
        if args.command == "dump":
            return cmd_dump(conf)
    except KeyboardInterrupt:
        logger.warning("Kullanıcı tarafından durduruldu.")
        return 130
    except Exception as exc:  # noqa: BLE001
        logger.exception("Beklenmeyen hata: %s", exc)
        # Mümkünse ekran görüntüsü al.
        cfg.SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
        print("\n>>> HATA oluştu. screenshots/ klasörünü kontrol edin.\n")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
