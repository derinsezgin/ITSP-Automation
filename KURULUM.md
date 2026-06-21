# Şirket Bilgisayarında Kurulum ve Çalıştırma Kılavuzu

Bu kılavuz, ITSP-Automation'ı **şirket bilgisayarınızda sıfırdan** kurup
çalıştırmanız için adım adım hazırlanmıştır. Teknik bilgi gerektirmez; yazılanları
sırayla uygulamanız yeterlidir.

> 🔒 **Önemli:** Bu araç **şifrenizi hiçbir yere kaydetmez**. ITSP'ye girişi her
> zaman siz, açılan tarayıcıda manuel yaparsınız. Araç login bilgilerinizi
> görmez/saklamaz.

---

## 1. Gerekli programlar (tek seferlik)

### a) Python kurulumu
1. https://www.python.org/downloads/ adresinden **Python 3.10 veya üzeri** indirin.
2. Kurulum ekranında **"Add Python to PATH"** kutusunu mutlaka işaretleyin, sonra
   "Install Now" deyin.
3. Kurulumun bittiğini doğrulamak için:
   - **Windows:** Başlat → "cmd" yazıp Komut İstemi'ni açın.
   - Şunu yazıp Enter'a basın: `python --version`
   - `Python 3.x.x` görüyorsanız tamamdır.

> Şirket bilgisayarında kurulum izniniz yoksa, BT ekibinden Python kurmalarını
> rica edin (yönetici hakkı gerekebilir).

---

## 2. Projeyi bilgisayara alma

Proje dosyalarını şirket bilgisayarınıza kopyalayın (BT'nin verdiği klasör, USB,
veya Git ile). Diyelim ki klasör şurada olsun:

```
C:\ITSP-Automation
```

Komut İstemi'nde bu klasöre girin:

```bat
cd C:\ITSP-Automation
```

---

## 3. Kütüphaneleri kurma (tek seferlik)

Komut İstemi'nde sırayla şu iki komutu çalıştırın:

```bat
pip install -r requirements.txt
playwright install chromium
```

- İlk komut gerekli Python kütüphanelerini kurar.
- İkinci komut otomasyonun kullanacağı tarayıcıyı (Chromium) indirir.

> Şirket ağı bazı indirmeleri engelliyorsa (proxy/güvenlik duvarı), bu adımda hata
> alabilirsiniz. O durumda BT ekibinden `pip` ve `playwright install` için ağ
> erişimi açmalarını isteyin.

---

## 4. Ayar dosyasını düzenleme (`config.yaml`)

`config.yaml` dosyasını bir metin düzenleyici (Not Defteri yeterli) ile açın ve
kendi ITSP/ServiceNow bilgilerinize göre şu alanları doldurun:

| Alan | Ne yazılacak |
|------|--------------|
| `base_url` | ITSP adresiniz, ör. `https://sirketiniz.service-now.com` |
| `dashboard_url` | Giriş sonrası açılan ana sayfa adresi |
| `incident_list_url` | Incident listesi sayfasının adresi |
| `internal_users` | Sizin ve ekip arkadaşlarınızın ITSP'deki **isimleri** |
| `internal_groups` | Ekibinizin atama grubu/grupları |
| `reminder.target_statuses` | Hangi statülerde hatırlatma yapılacağı |
| `reminder.reminder_1_text` | **1. hatırlatma** mesaj metniniz |
| `reminder.reminder_2_text` | **2. hatırlatma** metniniz (kapanış uyarısı dahil) |
| `workdays.holidays` | Resmi tatiller, ör. `["2026-01-01"]` |

> ⚠️ **Seçiciler (selectors):** Aracın sayfadaki incident'ları ve alanları
> bulabilmesi için `selectors` bölümündeki değerlerin sizin ITSP ekranınıza
> uyması gerekir. Varsayılanlar ServiceNow "Classic" arayüzü içindir. İlk
> denemede veri gelmezse bu kısmın güncellenmesi gerekebilir (bkz. Bölüm 8).

Hatırlatma metinlerini siz yazacaksınız; araç bu metni **olduğu gibi** kopyalar.

---

## 5. İlk giriş (tek seferlik, manuel login)

```bat
python run.py login
```

- Bir tarayıcı penceresi açılır.
- ITSP'ye **her zamanki gibi** kullanıcı adı/şifre + SSO/MFA ile **siz** giriş
  yaparsınız.
- Giriş tamamlanınca araç bunu algılar ve oturumu `browser_profile` klasörüne
  kaydeder. Pencereyi kapatabilirsiniz.

Bundan sonra (oturum dolana kadar) tekrar şifre girmeniz gerekmez.

---

## 6. Rapor alma (güvenli — hiçbir şey yazmaz)

```bat
python run.py report
```

- Incident listesini dolaşır, **sadece okur**.
- Bitince `incident_report.xlsx` dosyası oluşur. Excel ile açabilirsiniz.

Bu komut hiçbir ticket'a yazmaz; istediğiniz kadar çalıştırabilirsiniz.

---

## 7. Otomatik hatırlatma gönderme

### Önce mutlaka DENEME (dry-run) yapın — hiçbir şey göndermez:

```bat
python run.py remind --dry-run
```

Bu komut **hiçbir yorum göndermez**; sadece "hangi incident'a hangi hatırlatma
gönderilecekti" bilgisini ekrana ve `reminders_log.csv` dosyasına yazar. Çıktıyı
inceleyip doğru incident'ların seçildiğini kontrol edin.

### Emin olunca gerçek gönderim:

```bat
python run.py remind
```

- Son yorumu **sizin tarafınızdan** olan ve üzerinden **2 iş günü** geçmiş
  incident'lara otomatik hatırlatma yorumu **gönderir**.
- Önce `config.yaml` içindeki `max_per_run` değerini düşük (ör. `1`) tutarak tek
  bir incident üzerinde test etmeniz önerilir.

> ✅ Araç yalnızca **yorum ekler** (Additional comments). Ticket'ı kapatmaz, atamaz,
> statü değiştirmez. Kapatma işini siz manuel yaparsınız.

---

## 8. Dikkat edilmesi gereken hususlar

- **İlk login şart:** `report` veya `remind` çalıştırınca "manuel login gerekiyor"
  mesajı + `screenshots/auth_required_*.png` görürseniz, oturum dolmuştur. Çözüm:
  tekrar `python run.py login`.
- **Çift gönderim olmaz:** Araç aynı incident'a aynı hatırlatmayı iki kez
  göndermez (`reminder_state.json` + mesajdaki gizli imza ile). Müşteri yanıt
  verirse hatırlatma döngüsü sıfırlanır.
- **Önce dry-run:** Gerçek gönderimden önce **her zaman** `--dry-run` ile kontrol
  edin. Gönderilen yorumlar müşteriye gider ve geri alınamaz.
- **Veri gelmiyorsa (seçiciler):** `report` boş Excel veya eksik alan üretiyorsa,
  `config.yaml` içindeki `selectors` değerleri sizin ITSP arayüzünüze uymuyordur.
  BT ekibinizden veya ServiceNow sürümünüze (Classic / Next Experience) göre bu
  seçicilerin güncellenmesini isteyin.
- **`browser_profile` klasörünü paylaşmayın:** Bu klasör giriş oturumunuzu içerir;
  başkasıyla paylaşmayın, e-postayla göndermeyin, repoya yüklemeyin.
- **Şirket politikası:** Otomatik müşteri mesajı göndermenin kurum politikanıza
  uygun olduğundan ve gerekli izinlere sahip olduğunuzdan emin olun.
- **Tarayıcı penceresi açık kalır:** Araç görünür modda çalışır; çalışırken
  açılan pencereye müdahale etmeyin.

---

## 9. Üretilen dosyalar

| Dosya | Ne işe yarar |
|-------|--------------|
| `incident_report.xlsx` | Incident raporu |
| `reminders_log.csv` | Gönderilen/planlanan hatırlatma kaydı (denetim) |
| `reminder_state.json` | Hangi incident'a hangi hatırlatmanın gittiğinin takibi |
| `screenshots/` | Hata veya login gerektiğinde alınan ekran görüntüleri |
| `browser_profile/` | Giriş oturumunuz (gizli tutun) |

---

## 10. Sık karşılaşılan sorunlar

| Sorun | Çözüm |
|-------|-------|
| `python` komutu tanınmıyor | Python kurulumunda "Add to PATH" işaretlenmemiş; yeniden kurun veya BT'ye danışın |
| `pip install` ağ hatası veriyor | Şirket proxy/güvenlik duvarı; BT'den erişim isteyin |
| "manuel login gerekiyor" | `python run.py login` ile yeniden giriş yapın |
| Excel boş geliyor | `config.yaml` → `selectors` ve `incident_list_url` doğru mu kontrol edin |
| Yanlış incident'a hatırlatma | `internal_users`/`internal_groups` ve `target_statuses` ayarlarını gözden geçirin; `--dry-run` ile test edin |
