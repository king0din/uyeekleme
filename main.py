"""
Telegram Multi-Client Member Adder - Main Application
======================================================
Ana uygulama giris noktasi.
Windows uyumlu (emoji yok).
"""

import os
import sys
import asyncio
import logging
from datetime import datetime, timedelta
from logging.handlers import RotatingFileHandler

# Windows icin event loop policy
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

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
    
    # Console handler - UTF-8 encoding
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    
    # Windows icin encoding ayarla
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding='utf-8')
        except:
            pass
    
    # File handler
    file_handler = RotatingFileHandler(
        config.LogConfig.FILE,
        maxBytes=config.LogConfig.MAX_SIZE,
        backupCount=config.LogConfig.BACKUP_COUNT,
        encoding='utf-8'
    )
    file_handler.setFormatter(formatter)
    
    # Root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, config.LogConfig.LEVEL))
    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)
    
    # Pyrogram logger'ini sessize al
    logging.getLogger("pyrogram").setLevel(logging.WARNING)


logger = logging.getLogger(__name__)


# ==================== GUNLUK SIFIRLAMA ====================

async def daily_reset_task(db):
    """Her gun gece yarisi sayaclari sifirla"""
    while True:
        now = datetime.now()
        tomorrow = datetime(now.year, now.month, now.day) + timedelta(days=1)
        wait_seconds = (tomorrow - now).total_seconds()
        
        await asyncio.sleep(wait_seconds)
        
        count = await db.reset_daily_counts()
        logger.info(f"Gunluk sayaclar sifirlandi: {count} session")


# ==================== ANA UYGULAMA ====================

class MemberAdderApp:
    """Ana uygulama sinifi"""
    
    def __init__(self):
        self.bot: Client = None
        self.db = None
        self.manager: UserbotManager = None
        self.engine: MemberAddingEngine = None
        self.handlers: BotHandlers = None
    
    async def initialize(self):
        """Uygulamayi baslat"""
        logger.info("=" * 50)
        logger.info("Telegram Multi-Client Member Adder")
        logger.info("=" * 50)
        
        # Yapilandirma kontrolu
        if config.API_ID == 12345678 or config.API_HASH == "your_api_hash_here":
            logger.error("[!] API_ID ve API_HASH ayarlanmamis!")
            logger.error("    config.py dosyasini duzenleyin.")
            return False
        
        if config.BOT_TOKEN == "your_bot_token_here":
            logger.error("[!] BOT_TOKEN ayarlanmamis!")
            logger.error("    @BotFather'dan token alin ve config.py'yi duzenleyin.")
            return False
        
        if config.OWNER_ID == 123456789:
            logger.error("[!] OWNER_ID ayarlanmamis!")
            logger.error("    Telegram ID'nizi config.py'ye girin.")
            return False
        
        # Veritabani
        logger.info("Veritabani baslatiliyor...")
        self.db = get_database()
        await self.db.initialize()
        logger.info("[OK] Veritabani hazir")
        
        # Bot client
        logger.info("Bot baslatiliyor...")
        self.bot = Client(
            name="member_adder_bot",
            api_id=config.API_ID,
            api_hash=config.API_HASH,
            bot_token=config.BOT_TOKEN,
            workdir="data"
        )
        
        # Userbot manager
        logger.info("Worker manager baslatiliyor...")
        self.manager = UserbotManager(self.db)
        
        # Adding engine
        self.engine = MemberAddingEngine(self.db, self.manager)
        
        # Bot handlers
        self.handlers = BotHandlers(self.bot, self.db, self.manager, self.engine)
        self.handlers.register_handlers()
        
        return True
    
    async def start(self):
        """Botu baslat ve calistir"""
        try:
            # Bot'u baslat
            await self.bot.start()
            me = await self.bot.get_me()
            logger.info(f"[OK] Bot baslatildi: @{me.username}")
            
            # Mevcut session'lari yukle
            logger.info("Userbot'lar yukleniyor...")
            connected = await self.manager.load_all_sessions()
            logger.info(f"[OK] {connected} userbot baglandi")
            
            # Istatistikler
            stats = await self.db.get_stats()
            logger.info(f"[STATS] Valid users: {stats['valid_users']}")
            logger.info(f"[STATS] Blacklist: {stats['blacklisted_users']}")
            logger.info(f"[STATS] Toplam eklenen: {stats['total_added']}")
            
            logger.info("")
            logger.info("[OK] Sistem hazir!")
            logger.info(f"[INFO] Owner ID: {config.OWNER_ID}")
            logger.info("[INFO] Durdurmak icin Ctrl+C")
            logger.info("")
            
            # Botu calisir durumda tut
            from pyrogram import idle
            await idle()
            
        except KeyboardInterrupt:
            logger.info("Kapatiliyor...")
        except Exception as e:
            logger.error(f"Hata: {e}")
            import traceback
            traceback.print_exc()
        finally:
            await self.shutdown()
    
    async def shutdown(self):
        """Uygulamayi kapat"""
        logger.info("Sistem kapatiliyor...")
        
        if self.engine and self.engine.is_running:
            await self.engine.stop()
        
        if self.manager:
            await self.manager.shutdown()
        
        if self.bot:
            try:
                await self.bot.stop()
            except:
                pass
        
        logger.info("Sistem kapatildi.")


async def main():
    """Ana fonksiyon"""
    setup_logging()
    
    app = MemberAdderApp()
    
    if await app.initialize():
        await app.start()
    else:
        logger.error("Baslatma basarisiz!")
        sys.exit(1)


if __name__ == "__main__":
    # Data klasorunu olustur
    os.makedirs("data/logs", exist_ok=True)
    
    # Calistir
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nCikis yapiliyor...")
