# ITSP-Automation

ITSP-Automation icin ornek bir **MCP (Model Context Protocol)** sunucusu.
Claude'a (Claude Desktop veya Claude Code) yeni araclar kazandirmak icin
kullanilir.

## MCP nedir?

MCP, Claude gibi bir asistanin harici araclara/servislere standart bir
sekilde baglanmasini saglayan bir protokoldur. Bir MCP sunucusu yazarsiniz,
Claude ona baglanir ve sizin tanimladiginiz fonksiyonlari (arac / *tool*)
kullanabilir hale gelir.

Bu depodaki `server.py` su araclari sunar:

| Arac | Aciklama |
|------|----------|
| `ping` | Sunucunun ayakta oldugunu dogrular. |
| `echo` | Gonderilen metni geri dondurur. |
| `create_ticket` | Ornek bir IT ticket olusturur. |
| `list_tickets` | Olusturulmus ticket'lari listeler. |

## Kurulum

Python 3.10+ gereklidir.

```bash
# Sanal ortam olustur (onerilir)
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

# Bagimliliklari kur
pip install -r requirements.txt
```

## Yerelde test etme

MCP Inspector ile araclarinizi tarayicidan deneyebilirsiniz:

```bash
mcp dev server.py
```

Sunucuyu dogrudan calistirmak icin:

```bash
python server.py
```

## Claude Desktop'a baglama

Claude Desktop yapilandirma dosyasini acin:

- **macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows:** `%APPDATA%\Claude\claude_desktop_config.json`

Icine su MCP sunucu tanimini ekleyin (`/tam/yol` kismini bu deponun
bulundugu dizinle degistirin):

```json
{
  "mcpServers": {
    "itsp-automation": {
      "command": "python",
      "args": ["/tam/yol/ITSP-Automation/server.py"]
    }
  }
}
```

Sanal ortam kullaniyorsaniz `command` degerini o ortamdaki Python'a
verin, orn. `/tam/yol/ITSP-Automation/.venv/bin/python`.

Claude Desktop'i yeniden baslattiginizda araclar arac (cekic) menusunde
gorunur.

## Claude Code'a baglama

```bash
claude mcp add itsp-automation -- python /tam/yol/ITSP-Automation/server.py
```

## Yeni arac ekleme

`server.py` icinde bir fonksiyon yazip `@mcp.tool()` ile isaretlemeniz
yeterli. Tip ipuclari ve docstring Claude'a otomatik sunulur:

```python
@mcp.tool()
def restart_service(name: str) -> str:
    """Verilen servisi yeniden baslatir."""
    # ... kendi mantiginizi buraya yazin ...
    return f"{name} yeniden baslatildi"
```
