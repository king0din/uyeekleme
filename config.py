"""
Telegram Multi-Client Member Adder - Configuration
===================================================
Tum sistem ayarlari bu dosyada tanimlanir.

ONEMLI: Spam yememek icin asagidaki ayarlari dikkatli yapin!
"""

from typing import List

# ==================== TELEGRAM API ====================
# https://my.telegram.org adresinden alin
API_ID: int = 12345678  # Kendi API ID'nizi girin
API_HASH: str = "your_api_hash_here"  # Kendi API Hash'inizi girin

# ==================== BOT TOKEN ====================
# @BotFather'dan alin
BOT_TOKEN: str = "your_bot_token_here"

# ==================== OWNER (SAHIP) ====================
# Sadece bu kullanici botu kontrol edebilir
OWNER_ID: int = 123456789  # Kendi Telegram ID'nizi girin

# ==================== DATABASE ====================
DATABASE_TYPE: str = "sqlite"  # "sqlite" veya "mongodb"
SQLITE_PATH: str = "data/member_adder.db"

# MongoDB ayarlari (DATABASE_TYPE = "mongodb" ise)
MONGODB_URI: str = "mongodb://localhost:27017"
MONGODB_DB_NAME: str = "telegram_member_adder"

# ==================== EKLEME AYARLARI ====================
# !!! SPAM YEMEMEK ICIN BU AYARLARI DIKKATLI YAPIN !!!
class AddingConfig:
    # ========== BEKLEME SURELERI (COKK ONEMLI!) ==========
    # Ne kadar uzun bekleme = o kadar az spam riski
    
    MIN_DELAY: int = 90       # Minimum bekleme (saniye) - 90 saniye
    MAX_DELAY: int = 180      # Maximum bekleme (saniye) - 3 dakika
    
    # ========== BATCH (TOPLU) AYARLARI ==========
    # Her X uyeden sonra uzun mola ver
    
    BATCH_SIZE: int = 3       # Her 3 uyeden sonra uzun mola (5'ten 3'e dusuruldu)
    BATCH_DELAY_MIN: int = 600   # Uzun mola minimum - 10 dakika
    BATCH_DELAY_MAX: int = 900   # Uzun mola maximum - 15 dakika
    
    # ========== GUNLUK LIMITLER ==========
    # Cok dusuk tutun - hesabin guvenligini korur
    
    DAILY_LIMIT_PER_BOT: int = 15  # Gunde maksimum 15 uye (35'ten dusuruldu)
    
    # ========== FLOODWAIT ==========
    MAX_FLOOD_WAIT: int = 1800  # 30 dakikadan fazla bekleme = worker devre disi
    
    # ========== WORKER AYARLARI ==========
    MAX_CONCURRENT_BOTS: int = 1  # Ayni anda 1 worker calistir (guvenli)
    
    # ========== AKILLI OZELLIKLER ==========
    PRIORITIZE_VALID_USERS: bool = True   # Valid user onceligi
    AUTO_JOIN_ENABLED: bool = True        # Otomatik grup katilimi
    
    # ========== GUVENLIK IPUCLARI ==========
    """
    SPAM YEMEMEK ICIN:
    
    1. Yeni hesap kullanmayin - en az 1 aylik hesap kullanin
    2. Hesabin profil fotografi, bio'su olmali
    3. Hesap birkac grupta uye olmali
    4. Ilk gun sadece 5-10 uye ekleyin, yavas yavas artirin
    5. Her gun ayni saatlerde calistirmayin
    6. Bir hesap spam yerse 24-48 saat bekleyin
    7. PeerFlood aldiysaniz 1 hafta bekleyin
    """

# ==================== PANEL AYARLARI ====================
class PanelConfig:
    UPDATE_INTERVAL: int = 5  # Guncelleme araligi (saniye)
    PROGRESS_BAR_LENGTH: int = 20
    
    # Simgeler (emoji yerine ASCII)
    EMOJI_SUCCESS: str = "[+]"
    EMOJI_FAILED: str = "[-]"
    EMOJI_WORKING: str = "[~]"
    EMOJI_PAUSED: str = "[=]"
    EMOJI_BOT: str = "[B]"
    EMOJI_USER: str = "[U]"
    EMOJI_VALID: str = "[V]"
    EMOJI_BLACKLIST: str = "[X]"

# ==================== LOG AYARLARI ====================
class LogConfig:
    LEVEL: str = "INFO"
    FORMAT: str = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
    FILE: str = "data/logs/system.log"
    MAX_SIZE: int = 10 * 1024 * 1024  # 10 MB
    BACKUP_COUNT: int = 5
