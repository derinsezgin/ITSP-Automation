# ITSP-Automation

ServiceNow (ITSP) için **kalıcı tarayıcı profili** kullanan Playwright + Python
otomasyonu. API olmadığından ve login SSO/MFA gerektirdiğinden, kullanıcı **bir
kez manuel login** olur; oturum `./browser_profile` içinde korunur ve sonraki
çalıştırmalarda yeniden giriş gerekmez.

İki yetenek:

1. **Raporlama (salt-okunur):** Incident listesini dolaşır; her kayıt için
   status, priority, assigned group, **son yorum tarihi/sahibi** toplayıp
   `incident_report.xlsx` üretir.
2. **Hatırlatıcı akışı (yazma):** Son yorum **bizim taraftan** gelmiş ve üzerinden
   **2 iş günü** geçmişse, incident management sürecine göre otomatik hatırlatma
   yorumu gönderir (1. hatırlatma → 2 iş günü sonra kapanış uyarılı 2. hatırlatma).
   Kapatma **otomatik yapılmaz** (manuel).

> **Güvenlik:** `report` modu tamamen salt-okunur. `remind` modu yalnızca Activity
> "Additional comments" alanına yorum **Post** eder; assign/close/resolve/Save
> **yapmaz**. `.env`/koda **parola yazılmaz**.

## Kurulum

```bash
python -m venv .venv && source .venv/bin/activate   # opsiyonel
pip install -r requirements.txt
playwright install chromium
```

## Yapılandırma

`config.yaml` dosyasını kendi ServiceNow instance'ınıza göre düzenleyin:

- `base_url`, `dashboard_url`, `incident_list_url`, `timezone`
- `selectors.*` — DOM seçicileri (varsayılanlar Classic UI / `gsft_main` iframe).
  Next Experience/Workspace kullanıyorsanız bu seçicileri güncelleyin.
- `internal_users` / `internal_groups` — "bizim taraf" tespiti için.
- `reminder.target_statuses`, `reminder.reminder_1_text`, `reminder.reminder_2_text`
  (2. metin **zorunlu kapanış uyarısı** cümlesini içermelidir).
- `workdays.holidays` — resmi tatiller (iş günü hesabı için).

İsteğe bağlı: `.env` içinde yalnızca `ITSP_BASE_URL` (parola **yok**). Örnek:
`.env.example`.

## Kullanım

```bash
# 1) İlk kurulum: tarayıcı açılır, SSO/MFA ile MANUEL login olun
python run.py login

# 2) Salt-okunur rapor → incident_report.xlsx
python run.py report

# 3) Hatırlatıcı akışı — önce DRY-RUN ile doğrulayın (hiçbir şey göndermez)
python run.py remind --dry-run

# 4) Gerçek gönderim (tam otomatik). Önce config.yaml'da max_per_run'ı düşük tutun.
python run.py remind
```

## Davranış

- **Auth ekranına düşülürse** (`report`/`remind`): otomasyon durur,
  `screenshots/auth_required_*.png` alır, **"manuel login gerekiyor"** mesajı
  verir (exit ≠ 0). Çözüm: `python run.py login`.
- **Hata olursa**: `screenshots/error_*.png` kaydedilir.
- **İdempotensi**: Aynı incident'a aynı kademe iki kez gönderilmez
  (`reminder_state.json` + Activity'deki imza `signature_marker` ile). Müşteri
  yanıt verirse döngü sıfırlanır.
- **Audit**: Her hatırlatma `reminders_log.csv` dosyasına işlenir.

## Çıktı / üretilen dosyalar

| Dosya | Açıklama |
|-------|----------|
| `incident_report.xlsx` | Incident raporu (her iki modda da üretilir) |
| `reminders_log.csv` | Gönderilen/planlanan hatırlatmaların audit kaydı |
| `reminder_state.json` | İdempotensi durumu (kademe takibi) |
| `browser_profile/` | Kalıcı oturum (commit edilmez) |
| `screenshots/` | Hata/auth ekran görüntüleri |

## Notlar

- DOM seçicileri ServiceNow sürümüne göre değişebilir; tümü `config.yaml`'da
  düzenlenebilir. Gerçek instance üzerinde önce `report` ve `remind --dry-run`
  ile doğrulayın.
- `limits.max_incidents` ve `reminder.max_per_run` ile kapsam/gönderim sınırlanır.
