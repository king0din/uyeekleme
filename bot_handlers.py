"""
Telegram Multi-Client Member Adder - Bot Handlers
==================================================
Bot komutları, inline panel ve interaktif yönetim.
"""

import asyncio
import logging
import functools
from typing import Optional
from datetime import datetime

from pyrogram import Client, filters
from pyrogram.types import (
    Message, 
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton
)
from pyrogram.handlers import MessageHandler, CallbackQueryHandler

import config
from database import DatabaseInterface
from userbot_manager import UserbotManager
from adding_engine import MemberAddingEngine, AddingProgress, TaskStatus

logger = logging.getLogger(__name__)


def owner_only(func):
    """Sadece owner kullanabilir decorator"""
    @functools.wraps(func)
    async def wrapper(self, client: Client, message: Message):
        if message.from_user.id != config.OWNER_ID:
            return
        return await func(self, client, message)
    return wrapper


def owner_only_callback(func):
    """Callback icin owner only"""
    @functools.wraps(func)
    async def wrapper(self, client: Client, callback: CallbackQuery):
        if callback.from_user.id != config.OWNER_ID:
            await callback.answer("Bu paneli sadece bot sahibi kullanabilir!", show_alert=True)
            return
        return await func(self, client, callback)
    return wrapper


class BotHandlers:
    """Bot komut ve callback handler'lari"""
    
    def __init__(self, bot: Client, db: DatabaseInterface, 
                 manager: UserbotManager, engine: MemberAddingEngine):
        self.bot = bot
        self.db = db
        self.manager = manager
        self.engine = engine
        self.panel_message_id: Optional[int] = None
        self.panel_chat_id: Optional[int] = None
        
        self.engine.set_progress_callback(self._on_progress_update)
    
    def register_handlers(self):
        """Handler'lari kaydet"""
        # /start
        @self.bot.on_message(filters.command("start") & filters.private)
        async def start_handler(client, message):
            await self._cmd_start(client, message)
        
        # /panel veya /durum
        @self.bot.on_message(filters.command(["panel", "durum"]) & filters.private)
        async def panel_handler(client, message):
            await self._cmd_panel(client, message)
        
        # /session
        @self.bot.on_message(filters.command("session") & filters.private)
        async def session_handler(client, message):
            await self._cmd_session(client, message)
        
        # /ekle veya /add
        @self.bot.on_message(filters.command(["ekle", "add"]) & filters.private)
        async def add_handler(client, message):
            await self._cmd_add(client, message)
        
        # /durdur veya /stop
        @self.bot.on_message(filters.command(["durdur", "stop"]) & filters.private)
        async def stop_handler(client, message):
            await self._cmd_stop(client, message)
        
        # /yardim veya /help
        @self.bot.on_message(filters.command(["yardim", "help"]) & filters.private)
        async def help_handler(client, message):
            await self._cmd_help(client, message)
        
        # Callback handler
        @self.bot.on_callback_query(filters.regex(r"^(panel|refresh|sessions|stats|pause|resume|stop|close).*"))
        async def callback_handler(client, callback):
            await self._callback_handler(client, callback)
    
    def _progress_bar(self, current: int, total: int, length: int = 20) -> str:
        """Progress bar olustur"""
        if total == 0:
            return "=" * length
        filled = int(length * current / total)
        empty = length - filled
        bar = "#" * filled + "-" * empty
        percent = (current / total) * 100
        return f"[{bar}] {percent:.1f}%"
    
    def _format_time(self, seconds: int) -> str:
        """Saniyeyi okunabilir formata cevir"""
        if seconds < 60:
            return f"{seconds}s"
        elif seconds < 3600:
            return f"{seconds // 60}dk {seconds % 60}s"
        else:
            return f"{seconds // 3600}sa {(seconds % 3600) // 60}dk"
    
    async def _build_panel_text(self) -> str:
        """Panel metnini olustur"""
        stats = await self.db.get_stats()
        
        text = "** Multi-Client Member Adder Panel **\n"
        text += "=" * 35 + "\n\n"
        
        text += "[BOT] Worker Durumu:\n"
        text += f"  - Toplam: {stats['total_sessions']}\n"
        text += f"  - Aktif: {stats['active_sessions']}\n"
        text += f"  - Beklemede: {stats['paused_sessions']}\n"
        text += f"  - Pasif: {stats['inactive_sessions']}\n\n"
        
        text += "[USER] Kullanici Havuzu:\n"
        text += f"  - Valid: {stats['valid_users']}\n"
        text += f"  - Kara Liste: {stats['blacklisted_users']}\n\n"
        
        text += "[STATS] Istatistikler:\n"
        text += f"  - Bugun: {stats['added_today']}\n"
        text += f"  - Toplam: {stats['total_added']}\n\n"
        
        progress = self.engine.get_progress()
        if progress and self.engine.is_running:
            status_text = {
                TaskStatus.RUNNING: "[CALISIYOR]",
                TaskStatus.PAUSED: "[DURAKLATILDI]",
                TaskStatus.COMPLETED: "[TAMAMLANDI]",
                TaskStatus.FAILED: "[BASARISIZ]",
            }.get(progress.status, "[?]")
            
            text += f"{status_text} Aktif Gorev:\n"
            text += f"  Kaynak: {progress.source_title}\n"
            text += f"  Hedef: {progress.target_title}\n"
            text += f"  {self._progress_bar(progress.processed, progress.total_users)}\n"
            text += f"  [+] Eklenen: {progress.added}\n"
            text += f"  [-] Basarisiz: {progress.failed}\n"
            text += f"  [>] Atlanan: {progress.skipped}\n"
            text += f"  Worker: {progress.available_workers}/{progress.active_workers}\n"
            
            if progress.current_user:
                text += f"  Su an: {progress.current_user}\n"
            if progress.estimated_remaining:
                text += f"  Kalan: {self._format_time(progress.estimated_remaining)}\n"
        else:
            text += "[BOSTA] Aktif gorev yok\n"
        
        text += "\n" + "=" * 35
        text += f"\nGuncelleme: {datetime.now().strftime('%H:%M:%S')}"
        
        return text
    
    def _build_panel_keyboard(self) -> InlineKeyboardMarkup:
        """Panel butonlarini olustur"""
        buttons = [
            [
                InlineKeyboardButton("Yenile", callback_data="refresh"),
                InlineKeyboardButton("Istatistik", callback_data="stats")
            ],
            [InlineKeyboardButton("Worker'lar", callback_data="sessions")]
        ]
        
        if self.engine.is_running:
            if self.engine.is_paused:
                buttons.append([
                    InlineKeyboardButton("Devam", callback_data="resume"),
                    InlineKeyboardButton("Durdur", callback_data="stop")
                ])
            else:
                buttons.append([
                    InlineKeyboardButton("Duraklat", callback_data="pause"),
                    InlineKeyboardButton("Durdur", callback_data="stop")
                ])
        
        buttons.append([InlineKeyboardButton("Kapat", callback_data="close")])
        
        return InlineKeyboardMarkup(buttons)
    
    async def _on_progress_update(self, progress: AddingProgress):
        """Progress guncellendiginde panel'i guncelle"""
        if self.panel_message_id and self.panel_chat_id:
            try:
                text = await self._build_panel_text()
                keyboard = self._build_panel_keyboard()
                await self.bot.edit_message_text(
                    chat_id=self.panel_chat_id,
                    message_id=self.panel_message_id,
                    text=text,
                    reply_markup=keyboard
                )
            except Exception as e:
                if "not modified" not in str(e).lower():
                    logger.warning(f"Panel guncelleme hatasi: {e}")
    
    async def _cmd_start(self, client: Client, message: Message):
        """Start komutu"""
        if message.from_user.id != config.OWNER_ID:
            await message.reply("Bu bot ozeldir.")
            return
        
        text = (
            "** Telegram Multi-Client Member Adder **\n\n"
            "Komutlar:\n"
            "- /panel - Kontrol paneli\n"
            "- /session <string> - Userbot ekle\n"
            "- /ekle @kaynak @hedef - Uye ekle\n"
            "- /durdur - Gorevi durdur\n"
            "- /yardim - Detayli yardim"
        )
        await message.reply(text)
    
    async def _cmd_panel(self, client: Client, message: Message):
        """Panel komutu"""
        if message.from_user.id != config.OWNER_ID:
            return
        
        text = await self._build_panel_text()
        keyboard = self._build_panel_keyboard()
        msg = await message.reply(text, reply_markup=keyboard)
        self.panel_message_id = msg.id
        self.panel_chat_id = msg.chat.id
    
    async def _cmd_session(self, client: Client, message: Message):
        """Session ekleme komutu"""
        if message.from_user.id != config.OWNER_ID:
            return
        
        args = message.text.split(maxsplit=1)
        
        if len(args) < 2:
            await message.reply(
                "Kullanim: /session <StringSession>\n\n"
                "StringSession almak icin @StringSessionBot kullanin."
            )
            return
        
        string_session = args[1].strip()
        status_msg = await message.reply("Session kontrol ediliyor...")
        
        result = await self.manager.add_session(string_session)
        
        if result["success"]:
            await status_msg.edit_text(
                f"[OK] Session eklendi!\n\n"
                f"ID: {result['session_id']}\n"
                f"User: {result['user_id']}\n"
                f"Username: @{result['username'] or 'Yok'}"
            )
        else:
            await status_msg.edit_text(f"[HATA] {result['error']}")
    
    async def _cmd_add(self, client: Client, message: Message):
        """Uye ekleme komutu"""
        if message.from_user.id != config.OWNER_ID:
            return
        
        args = message.text.split()
        
        if len(args) < 3:
            await message.reply("Kullanim: /ekle @kaynak @hedef")
            return
        
        source, target = args[1], args[2]
        status_msg = await message.reply("Hazirlaniyor...")
        
        result = await self.engine.start_adding(client, source, target)
        
        if result["success"]:
            await status_msg.edit_text(
                f"[OK] Baslatildi!\n\n"
                f"Kaynak: {result['source_title']}\n"
                f"Hedef: {result['target_title']}\n"
                f"Toplam: {result['total_users']} uye"
            )
            
            text = await self._build_panel_text()
            keyboard = self._build_panel_keyboard()
            panel_msg = await message.reply(text, reply_markup=keyboard)
            self.panel_message_id = panel_msg.id
            self.panel_chat_id = panel_msg.chat.id
        else:
            await status_msg.edit_text(f"[HATA] {result['error']}")
    
    async def _cmd_stop(self, client: Client, message: Message):
        """Durdurma komutu"""
        if message.from_user.id != config.OWNER_ID:
            return
        
        if not self.engine.is_running:
            await message.reply("Aktif gorev yok.")
            return
        await self.engine.stop()
        await message.reply("[OK] Gorev durduruldu.")
    
    async def _cmd_help(self, client: Client, message: Message):
        """Yardim komutu"""
        if message.from_user.id != config.OWNER_ID:
            return
        
        text = (
            "** Kullanim Kilavuzu **\n\n"
            "1. Session Ekleme:\n"
            "   /session AQB...StringSession...\n\n"
            "2. Uye Ekleme:\n"
            "   /ekle @kaynakgrup @hedefgrup\n\n"
            "3. Panel:\n"
            "   /panel\n\n"
            "Ozellikler:\n"
            "- Valid user onceligi\n"
            "- Akilli FloodWait yonetimi\n"
            "- Coklu worker rotasyonu\n"
            "- Kara liste sistemi"
        )
        await message.reply(text)
    
    async def _callback_handler(self, client: Client, callback: CallbackQuery):
        """Callback handler"""
        if callback.from_user.id != config.OWNER_ID:
            await callback.answer("Bu paneli sadece bot sahibi kullanabilir!", show_alert=True)
            return
        
        data = callback.data
        
        if data == "refresh":
            text = await self._build_panel_text()
            keyboard = self._build_panel_keyboard()
            await callback.message.edit_text(text, reply_markup=keyboard)
            await callback.answer("Guncellendi!")
        
        elif data == "stats":
            stats = await self.db.get_stats()
            text = (
                f"** Istatistikler **\n\n"
                f"Worker: {stats['active_sessions']}/{stats['total_sessions']}\n"
                f"Valid: {stats['valid_users']}\n"
                f"Blacklist: {stats['blacklisted_users']}\n"
                f"Bugun: {stats['added_today']}\n"
                f"Toplam: {stats['total_added']}"
            )
            await callback.answer()
            await callback.message.reply(text)
        
        elif data == "sessions":
            statuses = self.manager.get_all_statuses()
            if not statuses:
                await callback.answer("Worker yok!", show_alert=True)
                return
            
            text = "** Worker'lar **\n\n"
            for s in statuses:
                icon = "[+]" if s.is_connected and s.is_available else "[-]"
                if s.flood_until:
                    icon = "[~]"
                text += f"{icon} #{s.session_id} @{s.username or s.user_id} ({s.added_today})\n"
            
            await callback.answer()
            await callback.message.reply(text)
        
        elif data == "pause":
            if self.engine.is_running:
                await self.engine.pause()
                await callback.answer("Duraklatildi!")
                text = await self._build_panel_text()
                keyboard = self._build_panel_keyboard()
                await callback.message.edit_text(text, reply_markup=keyboard)
            else:
                await callback.answer("Aktif gorev yok!", show_alert=True)
        
        elif data == "resume":
            if self.engine.is_running and self.engine.is_paused:
                await self.engine.resume()
                await callback.answer("Devam!")
                text = await self._build_panel_text()
                keyboard = self._build_panel_keyboard()
                await callback.message.edit_text(text, reply_markup=keyboard)
            else:
                await callback.answer("Duraklatilmis gorev yok!", show_alert=True)
        
        elif data == "stop":
            if self.engine.is_running:
                await self.engine.stop()
                await callback.answer("Durduruldu!")
                text = await self._build_panel_text()
                keyboard = self._build_panel_keyboard()
                await callback.message.edit_text(text, reply_markup=keyboard)
            else:
                await callback.answer("Aktif gorev yok!", show_alert=True)
        
        elif data == "close":
            await callback.message.delete()
            self.panel_message_id = None
            self.panel_chat_id = None
