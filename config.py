"""
Telegram Multi-Client Member Adder - Configuration
===================================================
Tüm sistem ayarları bu dosyada tanımlanır.
"""

from typing import List

# ==================== TELEGRAM API ====================
# https://my.telegram.org adresinden alın
API_ID: int = 12345678  # Kendi API ID'nizi girin
API_HASH: str = "your_api_hash_here"  # Kendi API Hash'inizi girin

# ==================== BOT TOKEN ====================
# @BotFather'dan alın
BOT_TOKEN: str = "your_bot_token_here"

# ==================== OWNER (SAHİP) ====================
# Sadece bu kullanıcı botu kontrol edebilir
OWNER_ID: int = 123456789  # Kendi Telegram ID'nizi girin

# ==================== DATABASE ====================
# SQLite veya MongoDB seçin
DATABASE_TYPE: str = "sqlite"  # "sqlite" veya "mongodb"

# SQLite ayarları
SQLITE_PATH: str = "data/member_adder.db"

# MongoDB ayarları (DATABASE_TYPE = "mongodb" ise)
MONGODB_URI: str = "mongodb://localhost:27017"
MONGODB_DB_NAME: str = "telegram_member_adder"

# ==================== EKLEME AYARLARI ====================
class AddingConfig:
    # Her userbot için bekleme süreleri (saniye)
    MIN_DELAY: int = 45
    MAX_DELAY: int = 90
    
    # Batch ayarları
    BATCH_SIZE: int = 5  # Her X üyeden sonra uzun mola
    BATCH_DELAY_MIN: int = 180  # 3 dakika
    BATCH_DELAY_MAX: int = 300  # 5 dakika
    
    # Userbot başına günlük limit
    DAILY_LIMIT_PER_BOT: int = 35
    
    # FloodWait eşiği - bu süreyi aşarsa bot devre dışı
    MAX_FLOOD_WAIT: int = 3600  # 1 saat
    
    # Paralel çalışan maksimum userbot sayısı
    MAX_CONCURRENT_BOTS: int = 3
    
    # Valid user önceliği
    PRIORITIZE_VALID_USERS: bool = True
    
    # Otomatik katılım
    AUTO_JOIN_ENABLED: bool = True

# ==================== PANEL AYARLARI ====================
class PanelConfig:
    # Progress bar güncelleme aralığı (saniye)
    UPDATE_INTERVAL: int = 3
    
    # Progress bar uzunluğu
    PROGRESS_BAR_LENGTH: int = 20
    
    # Emoji'ler
    EMOJI_SUCCESS: str = "✅"
    EMOJI_FAILED: str = "❌"
    EMOJI_WORKING: str = "🔄"
    EMOJI_PAUSED: str = "⏸️"
    EMOJI_BOT: str = "🤖"
    EMOJI_USER: str = "👤"
    EMOJI_VALID: str = "✨"
    EMOJI_BLACKLIST: str = "🚫"

# ==================== LOG AYARLARI ====================
class LogConfig:
    LEVEL: str = "INFO"
    FORMAT: str = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
    FILE: str = "data/logs/system.log"
    MAX_SIZE: int = 10 * 1024 * 1024  # 10 MB
    BACKUP_COUNT: int = 5
