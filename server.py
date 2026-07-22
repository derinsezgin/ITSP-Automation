"""ITSP-Automation MCP sunucusu.

Bu dosya, Model Context Protocol (MCP) uzerinden Claude'a arac (tool)
kazandiran minimal bir ornek sunucudur. Asagidaki uc arac tanimli:

  - ping        : Sunucunun ayakta oldugunu dogrular.
  - echo        : Gonderilen metni geri dondurur.
  - create_ticket: Basit, ornek bir IT ticket olusturur (bellekte tutar).

Yeni araclar eklemek icin @mcp.tool() dekoratorunu kullanip bir fonksiyon
yazmaniz yeterli. Fonksiyonun tip ipuclari (type hints) ve docstring'i
Claude'a otomatik olarak sunulur.
"""

from __future__ import annotations

from datetime import datetime, timezone

from mcp.server.fastmcp import FastMCP

# MCP sunucusunu olustur. Buradaki isim Claude tarafinda gorunur.
mcp = FastMCP("itsp-automation")

# Ornek amacli, bellekte tutulan basit bir ticket deposu.
# Gercek bir senaryoda burasi bir veritabani veya harici API olur.
_TICKETS: list[dict] = []


@mcp.tool()
def ping() -> str:
    """Sunucunun ayakta olup olmadigini kontrol eder.

    Returns:
        "pong" ve o anki UTC zaman damgasi.
    """
    now = datetime.now(timezone.utc).isoformat()
    return f"pong ({now})"


@mcp.tool()
def echo(text: str) -> str:
    """Verilen metni oldugu gibi geri dondurur.

    Args:
        text: Geri dondurulecek metin.
    """
    return text


@mcp.tool()
def create_ticket(title: str, description: str = "", priority: str = "normal") -> dict:
    """Basit bir IT destek ticket'i olusturur (ornek/bellek ici).

    Args:
        title: Ticket basligi.
        description: Sorunun ayrintili aciklamasi.
        priority: Oncelik seviyesi ("low", "normal", "high").

    Returns:
        Olusturulan ticket bilgisini iceren sozluk.
    """
    ticket = {
        "id": len(_TICKETS) + 1,
        "title": title,
        "description": description,
        "priority": priority,
        "status": "open",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    _TICKETS.append(ticket)
    return ticket


@mcp.tool()
def list_tickets() -> list[dict]:
    """Olusturulmus tum ticket'lari listeler."""
    return _TICKETS


def main() -> None:
    """Sunucuyu stdio uzerinden calistirir (Claude'un bekledigi bicim)."""
    mcp.run()


if __name__ == "__main__":
    main()
