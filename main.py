"""
Telegram Multi-Client Member Adder - Main Application
======================================================
Ana uygulama giriş noktası.
"""

import os
import sys
import asyncio
import logging
from datetime import datetime, time, timedelta
from logging.handlers import RotatingFileHandler

from pyrogram import Client

import config
from database import get_database
from userbot_manager import UserbotManager
from adding_engine import MemberAddingEngine
from bot_handlers import BotHandlers

# ==================== LOGGING AYARLARI ====================

def setup_logging():
    """Logging sistemini kur"""
    log_dir = os.path.dirname(config.LogConfig.FILE)
    if log_dir:
        os.makedirs(log_dir, exist_ok=True)
    
    formatter = logging.Formatter(config.LogConfig.FORMAT)
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    
    # File handler
    file_handler = RotatingFileHandler(
        config.LogConfig.FILE,
        maxBytes=config.LogConfig.MAX_SIZE,
        backupCount=config.LogConfig.BACKUP_COUNT
    )
    file_handler.setFormatter(formatter)
    
    # Root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, config.LogConfig.LEVEL))
    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)
    
    # Pyrogram logger'ını sessize al
    logging.getLogger("pyrogram").setLevel(logging.WARNING)


logger = logging.getLogger(__name__)


# ==================== GÜNLÜK SIFIRLAMA ====================

async def daily_reset_task(db):
    """Her gün gece yarısı sayaçları sıfırla"""
    while True:
        now = datetime.now()
        # Bir sonraki gece yarısı
        tomorrow = datetime(now.year, now.month, now.day) + timedelta(days=1)
        wait_seconds = (tomorrow - now).total_seconds()
        
        await asyncio.sleep(wait_seconds)
        
        # Sıfırla
        count = await db.reset_daily_counts()
        logger.info(f"Günlük sayaçlar sıfırlandı: {count} session")


# ==================== ANA UYGULAMA ====================

class MemberAdderApp:
    """Ana uygulama sınıfı"""
    
    def __init__(self):
        self.bot: Client = None
        self.db = None
        self.manager: UserbotManager = None
        self.engine: MemberAddingEngine = None
        self.handlers: BotHandlers = None
    
    async def initialize(self):
        """Uygulamayı başlat"""
        logger.info("=" * 50)
        logger.info("Telegram Multi-Client Member Adder")
        logger.info("=" * 50)
        
        # Yapılandırma kontrolü
        if config.API_ID == 12345678 or config.API_HASH == "your_api_hash_here":
            logger.error("⚠️  API_ID ve API_HASH ayarlanmamış!")
            logger.error("config.py dosyasını düzenleyin.")
            return False
        
        if config.BOT_TOKEN == "your_bot_token_here":
            logger.error("⚠️  BOT_TOKEN ayarlanmamış!")
            logger.error("@BotFather'dan token alın ve config.py'yi düzenleyin.")
            return False
        
        if config.OWNER_ID == 123456789:
            logger.error("⚠️  OWNER_ID ayarlanmamış!")
            logger.error("Telegram ID'nizi config.py'ye girin.")
            return False
        
        # Veritabanı
        logger.info("Veritabanı başlatılıyor...")
        self.db = get_database()
        await self.db.initialize()
        logger.info("✅ Veritabanı hazır")
        
        # Bot client
        logger.info("Bot başlatılıyor...")
        self.bot = Client(
            name="member_adder_bot",
            api_id=config.API_ID,
            api_hash=config.API_HASH,
            bot_token=config.BOT_TOKEN,
            workdir="data"
        )
        
        # Userbot manager
        logger.info("Worker manager başlatılıyor...")
        self.manager = UserbotManager(self.db)
        
        # Adding engine
        self.engine = MemberAddingEngine(self.db, self.manager)
        
        # Bot handlers
        self.handlers = BotHandlers(self.bot, self.db, self.manager, self.engine)
        self.handlers.register_handlers()
        
        return True
    
    async def start(self):
        """Botu başlat ve çalıştır"""
        try:
            # Bot'u başlat
            await self.bot.start()
            me = await self.bot.get_me()
            logger.info(f"✅ Bot başlatıldı: @{me.username}")
            
            # Mevcut session'ları yükle
            logger.info("Userbot'lar yükleniyor...")
            connected = await self.manager.load_all_sessions()
            logger.info(f"✅ {connected} userbot bağlandı")
            
            # İstatistikler
            stats = await self.db.get_stats()
            logger.info(f"📊 Valid users: {stats['valid_users']}")
            logger.info(f"📊 Blacklist: {stats['blacklisted_users']}")
            logger.info(f"📊 Toplam eklenen: {stats['total_added']}")
            
            logger.info("")
            logger.info("🚀 Sistem hazır!")
            logger.info(f"👤 Owner ID: {config.OWNER_ID}")
            logger.info("")
            
            # Çalışmaya devam et
            await asyncio.Event().wait()
            
        except KeyboardInterrupt:
            logger.info("Kapatılıyor...")
        except Exception as e:
            logger.error(f"Hata: {e}")
            raise
        finally:
            await self.shutdown()
    
    async def shutdown(self):
        """Uygulamayı kapat"""
        logger.info("Sistem kapatılıyor...")
        
        if self.engine and self.engine.is_running:
            await self.engine.stop()
        
        if self.manager:
            await self.manager.shutdown()
        
        if self.bot:
            await self.bot.stop()
        
        logger.info("Sistem kapatıldı.")


async def main():
    """Ana fonksiyon"""
    setup_logging()
    
    app = MemberAdderApp()
    
    if await app.initialize():
        await app.start()
    else:
        logger.error("Başlatma başarısız!")
        sys.exit(1)


if __name__ == "__main__":
    # Data klasörünü oluştur
    os.makedirs("data/logs", exist_ok=True)
    
    # Çalıştır
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
