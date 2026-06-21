"""Login/auth ekranı tespiti ve manuel login akışı."""

from __future__ import annotations

import fnmatch
import logging
import time

from playwright.sync_api import Page, TimeoutError as PWTimeoutError

from . import config as cfg

logger = logging.getLogger(__name__)


class ManualLoginRequired(Exception):
    """report/remind modunda auth ekranına düşülünce fırlatılır."""


def is_auth_screen(page: Page, conf: cfg.Config) -> bool:
    """Mevcut sayfa bir login/SSO/auth ekranı mı?"""
    url = page.url or ""
    for pattern in conf.get("auth.url_patterns", []) or []:
        if fnmatch.fnmatch(url, pattern):
            logger.debug("Auth URL deseni eşleşti: %s ~ %s", url, pattern)
            return True

    for selector in conf.get("auth.dom_selectors", []) or []:
        try:
            if page.locator(selector).first.is_visible(timeout=1500):
                logger.debug("Auth DOM seçicisi görünür: %s", selector)
                return True
        except PWTimeoutError:
            continue
        except Exception:  # noqa: BLE001
            continue
    return False


def open_dashboard(page: Page, conf: cfg.Config) -> None:
    """Dashboard'a gider (yoksa base_url)."""
    target = conf.get("dashboard_url") or conf.require("base_url")
    logger.info("Dashboard açılıyor: %s", target)
    page.goto(target, wait_until="domcontentloaded")


def ensure_authenticated(page: Page, conf: cfg.Config) -> None:
    """report/remind modu için: auth ekranındaysak dur ve istisna fırlat."""
    if is_auth_screen(page, conf):
        raise ManualLoginRequired(
            "Login/auth ekranı tespit edildi — manuel login gerekiyor. "
            "Önce `python run.py login` çalıştırıp SSO/MFA ile giriş yapın."
        )
    logger.info("Oturum geçerli; dashboard erişilebilir.")


def wait_for_manual_login(page: Page, conf: cfg.Config) -> None:
    """login modu: kullanıcı manuel login olana (auth ekranı kaybolana) kadar bekler."""
    timeout_ms = conf.get("timeouts.manual_login", 300000)
    deadline = time.monotonic() + timeout_ms / 1000.0

    if not is_auth_screen(page, conf):
        logger.info("Zaten giriş yapılmış görünüyor; profil hazır.")
        return

    print(
        "\n>>> Lütfen açılan tarayıcı penceresinde SSO/MFA ile MANUEL login olun.\n"
        f">>> Giriş tamamlanana kadar beklenecek (en fazla {int(timeout_ms/1000)} sn)...\n"
    )

    while time.monotonic() < deadline:
        if not is_auth_screen(page, conf):
            print(">>> Giriş algılandı. Oturum ./browser_profile içine kaydedildi.\n")
            logger.info("Manuel login tamamlandı.")
            return
        time.sleep(2)

    raise ManualLoginRequired(
        "Manuel login için verilen süre doldu. Tekrar `python run.py login` deneyin."
    )
