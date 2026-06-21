"""Kalıcı (persistent) Chromium profili yönetimi + salt-okunur ağ koruması."""

from __future__ import annotations

import fnmatch
import logging
from contextlib import contextmanager
from typing import Iterator

from playwright.sync_api import BrowserContext, Route, sync_playwright

from . import config as cfg

logger = logging.getLogger(__name__)

# Her zaman engellenen HTTP metotları (salt-okunur koruma açıkken).
_MUTATING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


@contextmanager
def persistent_context(conf: cfg.Config) -> Iterator[BrowserContext]:
    """./browser_profile altında kalıcı bir Chromium context açar.

    Oturum (cookies/localStorage) user_data_dir içinde otomatik korunur;
    context kapanınca yeniden login gerekmez.
    """
    cfg.BROWSER_PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    nav_timeout = conf.get("timeouts.navigation", 30000)

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(cfg.BROWSER_PROFILE_DIR),
            headless=False,  # headed: ilk login manuel yapılır
            args=["--start-maximized"],
            no_viewport=True,
        )
        context.set_default_navigation_timeout(nav_timeout)
        context.set_default_timeout(conf.get("timeouts.selector", 15000))
        try:
            yield context
        finally:
            context.close()


def enable_readonly_guard(
    context: BrowserContext,
    conf: cfg.Config,
    *,
    allow_comment_post: bool = False,
) -> None:
    """Mutasyon (POST/PUT/PATCH/DELETE) isteklerini engelleyen route kurar.

    - report modu: allow_comment_post=False → tüm mutasyonlar engellenir.
    - remind modu: allow_comment_post=True → yalnızca state değiştiren
      (config'teki blocked_endpoints) istekler engellenir; yorum POST'una
      izin verilir.

    SSO POST'larını bozmamak için bu fonksiyon ancak dashboard'a (post-auth)
    ulaşıldıktan sonra çağrılmalıdır.
    """
    if not conf.get("readonly_guard.enabled", True):
        logger.info("Salt-okunur koruma config'te kapalı.")
        return

    base_url = conf.get("base_url", "")
    blocked = conf.get("readonly_guard.blocked_endpoints", []) or []

    def handler(route: Route) -> None:
        request = route.request
        method = request.method.upper()
        url = request.url

        if method not in _MUTATING_METHODS:
            route.continue_()
            return

        # Sadece ITSP host'una giden mutasyonları kısıtla; diğer host'lar (SSO vb.) serbest.
        if base_url and not _same_host(url, base_url):
            route.continue_()
            return

        if allow_comment_post:
            # remind modu: yalnızca açıkça yasaklı endpoint'leri blokla.
            if any(fnmatch.fnmatch(url, pat) for pat in blocked):
                logger.warning("Engellendi (state değiştiren istek): %s %s", method, url)
                route.abort()
            else:
                route.continue_()
        else:
            # report modu: tüm mutasyonları blokla.
            logger.warning("Engellendi (salt-okunur): %s %s", method, url)
            route.abort()

    context.route("**", handler)
    mode = "remind (yorum POST serbest)" if allow_comment_post else "report (tüm yazma kapalı)"
    logger.info("Salt-okunur ağ koruması etkin — mod: %s", mode)


def _same_host(url: str, base_url: str) -> bool:
    from urllib.parse import urlparse

    try:
        return urlparse(url).netloc == urlparse(base_url).netloc
    except Exception:  # noqa: BLE001
        return False
