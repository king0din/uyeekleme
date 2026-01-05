# 🚀 Telegram Multi-Client Member Adder

Profesyonel, production-ready Telegram üye ekleme sistemi. Birden fazla userbot kullanarak akıllı ve güvenli şekilde grup üyelerini ekler.

## ✨ Özellikler

### 🔐 Güvenlik
- **Owner-Only**: Tüm komutlar sadece belirlenen sahip tarafından kullanılabilir
- **Modüler Yapı**: Veritabanı, bot, userbot yönetimi ayrı modüllerde
- **Kalıcı Veritabanı**: SQLite veya MongoDB desteği

### 🤖 Dinamik Userbot Yönetimi
- **Anlık Session Ekleme**: `.session` komutuyla yeni worker ekleyin
- **Fault Tolerance**: Bir bot banlansa/kapansa sistem çökmez
- **Otomatik Rotasyon**: Worker'lar akıllıca dönüşümlü kullanılır

### 🎯 Akıllı Üye Ekleme
- **Valid User Havuzu**: Başarıyla eklenen kullanıcılar öncelikli
- **Kara Liste**: Gizliliği kapalı kullanıcılar otomatik kaydedilir
- **Çakışma Önleme**: Aynı kullanıcı birden fazla kez eklenmez
- **Hedef Kontrolü**: Zaten grupta olanlar atlanır

### 📊 İnteraktif Panel
- **Canlı Takip**: Progress bar ve anlık istatistikler
- **Inline Butonlar**: Duraklat, devam et, durdur
- **Worker Durumu**: Aktif/pasif/beklemede gösterimi

### 🛡️ Hata Yönetimi
- **FloodWait**: Otomatik bekleme ve worker değişimi
- **PeerFlood**: Spam algılandığında worker devre dışı
- **Privacy Restricted**: Kara listeye otomatik ekleme

## 📁 Proje Yapısı

```
telegram_multi_adder/
├── config.py           # Tüm ayarlar
├── database.py         # SQLite/MongoDB işlemleri
├── userbot_manager.py  # Çoklu client yönetimi
├── adding_engine.py    # Akıllı üye ekleme motoru
├── bot_handlers.py     # Komutlar ve panel
├── main.py             # Ana uygulama
├── requirements.txt    # Bağımlılıklar
└── data/
    ├── member_adder.db # SQLite veritabanı
    └── logs/           # Log dosyaları
```

## 🔧 Kurulum

### 1. Gereksinimleri Yükleyin

```bash
pip install -r requirements.txt
```

### 2. API Bilgilerini Alın

1. **Telegram API**: https://my.telegram.org
   - "API Development Tools"a gidin
   - Yeni uygulama oluşturun
   - `API_ID` ve `API_HASH` alın

2. **Bot Token**: @BotFather
   - `/newbot` komutuyla yeni bot oluşturun
   - Token'ı kopyalayın

3. **Owner ID**: @userinfobot veya @getmyid_bot
   - Telegram ID'nizi öğrenin

### 3. config.py'yi Düzenleyin

```python
API_ID = 12345678  # Gerçek API ID
API_HASH = "abc123..."  # Gerçek API Hash
BOT_TOKEN = "123:ABC..."  # Bot token
OWNER_ID = 987654321  # Sizin Telegram ID'niz
```

### 4. Çalıştırın

```bash
python main.py
```

## 📝 Komutlar

### Bot Komutları (PM'de)

| Komut | Açıklama |
|-------|----------|
| `/start` | Başlangıç mesajı |
| `/panel` | Kontrol panelini aç |
| `/session <string>` | Yeni userbot ekle |
| `/ekle @kaynak @hedef` | Üye eklemeyi başlat |
| `/durdur` | Aktif görevi durdur |
| `/yardim` | Detaylı yardım |

### Userbot Komutları (Herhangi bir yerde)

| Komut | Açıklama |
|-------|----------|
| `.session <string>` | Yeni userbot ekle |
| `.durum` | Panel göster |
| `.ekle @kaynak @hedef` | Üye ekle |

## 🎛️ Panel Özellikleri

Panel şunları gösterir:
- 🤖 Worker sayısı (Aktif/Pasif/Beklemede)
- ✨ Valid user sayısı
- 🚫 Kara liste sayısı
- 📊 Ekleme istatistikleri
- 🔄 Aktif görev ilerlemesi

Panel butonları:
- 🔄 Yenile
- 📊 Detaylı istatistik
- 🤖 Worker listesi
- ⏸️ Duraklat / ▶️ Devam
- ⏹️ Durdur
- ❌ Kapat

## ⚙️ Yapılandırma

### Ekleme Ayarları (config.py)

```python
class AddingConfig:
    MIN_DELAY = 45        # Minimum bekleme (saniye)
    MAX_DELAY = 90        # Maximum bekleme
    BATCH_SIZE = 5        # Kaç üyede bir uzun mola
    BATCH_DELAY_MIN = 180 # Uzun mola min (saniye)
    BATCH_DELAY_MAX = 300 # Uzun mola max
    DAILY_LIMIT_PER_BOT = 35  # Bot başına günlük limit
    MAX_FLOOD_WAIT = 3600     # Max FloodWait (saniye)
    MAX_CONCURRENT_BOTS = 3   # Paralel bot sayısı
    PRIORITIZE_VALID_USERS = True  # Valid user önceliği
    AUTO_JOIN_ENABLED = True       # Otomatik grup katılımı
```

### Veritabanı Seçimi

```python
DATABASE_TYPE = "sqlite"  # veya "mongodb"

# SQLite için
SQLITE_PATH = "data/member_adder.db"

# MongoDB için
MONGODB_URI = "mongodb://localhost:27017"
MONGODB_DB_NAME = "telegram_member_adder"
```

## 🔒 Valid User Sistemi

Sistem şu şekilde çalışır:

1. **İlk Ekleme**: Yeni kullanıcı eklenmeye çalışılır
2. **Başarılı**: `valid_users` tablosuna kaydedilir
3. **Başarısız (Gizlilik)**: `blacklist` tablosuna kaydedilir
4. **Sonraki İşlemler**: Valid user'lar öncelikli denenir

Bu sistem:
- Başarısız deneme sayısını azaltır
- Worker'ların spam yeme riskini minimize eder
- Daha hızlı ve güvenli ekleme sağlar

## ⚠️ Önemli Uyarılar

### Telegram Kuralları
- Bu araç Telegram ToS'u ihlal edebilir
- Hesaplarınız kısıtlanabilir veya yasaklanabilir
- **Riski kendiniz üstlenirsiniz**

### Güvenlik Önerileri
1. Ana hesabınızı kullanmayın
2. Düşük günlük limitler belirleyin
3. Uzun bekleme süreleri kullanın
4. Worker'ları düzenli dinlendirin
5. PeerFlood sonrası 24-48 saat bekleyin

### Hedef Grup Gereksinimleri
- Hedef grupta admin olmalısınız
- Üye ekleme yetkisi olmalı
- Grup gizli değilse worker'lar otomatik katılır

## 🐛 Sorun Giderme

### "Müsait worker yok"
- Tüm worker'lar FloodWait'te olabilir
- Günlük limit dolmuş olabilir
- Yeni session ekleyin

### "Session eklenemedi"
- StringSession geçersiz olabilir
- Hesap devre dışı bırakılmış olabilir
- Yeni session oluşturun

### "Admin yetkisi gerekli"
- Hedef grupta admin olduğunuzdan emin olun
- Üye ekleme yetkisi olduğunu kontrol edin

### FloodWait çok uzun
- Bekleme süresi 1 saatten fazlaysa worker devre dışı kalır
- Diğer worker'lar devam eder
- Sabırlı olun

## 📄 Lisans

Bu proje eğitim amaçlıdır. Kullanımdan doğacak tüm sorumluluk kullanıcıya aittir.

## 🤝 Katkıda Bulunma

Pull request'ler memnuniyetle karşılanır. Büyük değişiklikler için önce issue açın.

---

**⭐ Beğendiyseniz yıldız verin!**
