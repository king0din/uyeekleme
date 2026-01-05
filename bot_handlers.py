"""
Telegram Multi-Client Member Adder - Bot Handlers
==================================================
Bot komutları, inline panel ve interaktif yönetim.
"""

import asyncio
import logging
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
    async def wrapper(client: Client, message: Message):
        if message.from_user.id != config.OWNER_ID:
            return
        return await func(client, message)
    return wrapper


def owner_only_callback(func):
    """Callback için owner only"""
    async def wrapper(client: Client, callback: CallbackQuery):
        if callback.from_user.id != config.OWNER_ID:
            await callback.answer("⛔ Bu paneli sadece bot sahibi kullanabilir!", show_alert=True)
            return
        return await func(client, callback)
    return wrapper


class BotHandlers:
    """Bot komut ve callback handler'ları"""
    
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
        """Handler'ları kaydet"""
        self.bot.add_handler(MessageHandler(
            self._cmd_start, 
            filters.command("start") & filters.private
        ))
        self.bot.add_handler(MessageHandler(
            self._cmd_panel,
            filters.command(["panel", "durum"]) & filters.private
        ))
        self.bot.add_handler(MessageHandler(
            self._cmd_session,
            filters.command("session") & filters.private
        ))
        self.bot.add_handler(MessageHandler(
            self._cmd_add,
            filters.command(["ekle", "add"]) & filters.private
        ))
        self.bot.add_handler(MessageHandler(
            self._cmd_stop,
            filters.command(["durdur", "stop"]) & filters.private
        ))
        self.bot.add_handler(MessageHandler(
            self._cmd_help,
            filters.command(["yardim", "help"]) & filters.private
        ))
        
        self.bot.add_handler(CallbackQueryHandler(
            self._callback_handler,
            filters.regex(r"^(panel|refresh|sessions|stats|pause|resume|stop|close).*")
        ))
    
    def _progress_bar(self, current: int, total: int, length: int = 20) -> str:
        """Progress bar oluştur"""
        if total == 0:
            return "░" * length
        filled = int(length * current / total)
        empty = length - filled
        bar = "█" * filled + "░" * empty
        percent = (current / total) * 100
        return f"[{bar}] {percent:.1f}%"
    
    def _format_time(self, seconds: int) -> str:
        """Saniyeyi okunabilir formata çevir"""
        if seconds < 60:
            return f"{seconds}s"
        elif seconds < 3600:
            return f"{seconds // 60}dk {seconds % 60}s"
        else:
            return f"{seconds // 3600}sa {(seconds % 3600) // 60}dk"
    
    async def _build_panel_text(self) -> str:
        """Panel metnini oluştur"""
        stats = await self.db.get_stats()
        cfg = config.PanelConfig
        
        text = "🎛️ **Multi-Client Member Adder Panel**\n"
        text += "━" * 35 + "\n\n"
        
        text += f"{cfg.EMOJI_BOT} **Worker Durumu:**\n"
        text += f"├ Toplam: `{stats['total_sessions']}`\n"
        text += f"├ Aktif: `{stats['active_sessions']}`\n"
        text += f"├ Beklemede: `{stats['paused_sessions']}`\n"
        text += f"└ Pasif: `{stats['inactive_sessions']}`\n\n"
        
        text += f"{cfg.EMOJI_USER} **Kullanıcı Havuzu:**\n"
        text += f"├ {cfg.EMOJI_VALID} Valid: `{stats['valid_users']}`\n"
        text += f"└ {cfg.EMOJI_BLACKLIST} Kara Liste: `{stats['blacklisted_users']}`\n\n"
        
        text += f"📊 **İstatistikler:**\n"
        text += f"├ Bugün: `{stats['added_today']}`\n"
        text += f"└ Toplam: `{stats['total_added']}`\n\n"
        
        progress = self.engine.get_progress()
        if progress and self.engine.is_running:
            status_emoji = {
                TaskStatus.RUNNING: cfg.EMOJI_WORKING,
                TaskStatus.PAUSED: cfg.EMOJI_PAUSED,
                TaskStatus.COMPLETED: cfg.EMOJI_SUCCESS,
                TaskStatus.FAILED: cfg.EMOJI_FAILED,
            }.get(progress.status, "❓")
            
            text += f"{status_emoji} **Aktif Görev:**\n"
            text += f"├ `{progress.source_title}` → `{progress.target_title}`\n"
            text += f"├ {self._progress_bar(progress.processed, progress.total_users)}\n"
            text += f"├ {cfg.EMOJI_SUCCESS} `{progress.added}` | "
            text += f"{cfg.EMOJI_FAILED} `{progress.failed}` | "
            text += f"⏭️ `{progress.skipped}`\n"
            text += f"├ Worker: `{progress.available_workers}/{progress.active_workers}`\n"
            
            if progress.current_user:
                text += f"├ Şu an: `{progress.current_user}`\n"
            if progress.estimated_remaining:
                text += f"└ Kalan: `{self._format_time(progress.estimated_remaining)}`\n"
            else:
                text += "└ Kalan: `Hesaplanıyor...`\n"
        else:
            text += "💤 **Aktif görev yok**\n"
        
        text += "\n" + "━" * 35
        text += f"\n🕐 `{datetime.now().strftime('%H:%M:%S')}`"
        
        return text
    
    def _build_panel_keyboard(self) -> InlineKeyboardMarkup:
        """Panel butonlarını oluştur"""
        buttons = [
            [
                InlineKeyboardButton("🔄 Yenile", callback_data="refresh"),
                InlineKeyboardButton("📊 İstatistik", callback_data="stats")
            ],
            [InlineKeyboardButton("🤖 Worker'lar", callback_data="sessions")]
        ]
        
        if self.engine.is_running:
            if self.engine.is_paused:
                buttons.append([
                    InlineKeyboardButton("▶️ Devam", callback_data="resume"),
                    InlineKeyboardButton("⏹️ Durdur", callback_data="stop")
                ])
            else:
                buttons.append([
                    InlineKeyboardButton("⏸️ Duraklat", callback_data="pause"),
                    InlineKeyboardButton("⏹️ Durdur", callback_data="stop")
                ])
        
        buttons.append([InlineKeyboardButton("❌ Kapat", callback_data="close")])
        
        return InlineKeyboardMarkup(buttons)
    
    async def _on_progress_update(self, progress: AddingProgress):
        """Progress güncellendiğinde panel'i güncelle"""
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
                    logger.warning(f"Panel güncelleme hatası: {e}")
    
    @owner_only
    async def _cmd_start(self, client: Client, message: Message):
        """Start komutu"""
        text = (
            "🚀 **Telegram Multi-Client Member Adder**\n\n"
            "**Komutlar:**\n"
            "• `/panel` - Kontrol paneli\n"
            "• `/session <string>` - Userbot ekle\n"
            "• `/ekle @kaynak @hedef` - Üye ekle\n"
            "• `/durdur` - Görevi durdur\n"
            "• `/yardim` - Detaylı yardım"
        )
        await message.reply(text)
    
    @owner_only
    async def _cmd_panel(self, client: Client, message: Message):
        """Panel komutu"""
        text = await self._build_panel_text()
        keyboard = self._build_panel_keyboard()
        msg = await message.reply(text, reply_markup=keyboard)
        self.panel_message_id = msg.id
        self.panel_chat_id = msg.chat.id
    
    @owner_only
    async def _cmd_session(self, client: Client, message: Message):
        """Session ekleme komutu"""
        args = message.text.split(maxsplit=1)
        
        if len(args) < 2:
            await message.reply(
                "❌ **Kullanım:** `/session <StringSession>`\n\n"
                "StringSession almak için @StringSessionBot kullanın."
            )
            return
        
        string_session = args[1].strip()
        status_msg = await message.reply("🔄 **Session kontrol ediliyor...**")
        
        result = await self.manager.add_session(string_session)
        
        if result["success"]:
            await status_msg.edit(
                f"✅ **Session eklendi!**\n\n"
                f"📋 ID: `{result['session_id']}`\n"
                f"👤 User: `{result['user_id']}`\n"
                f"📛 @{result['username'] or 'Yok'}"
            )
        else:
            await status_msg.edit(f"❌ **Hata:** `{result['error']}`")
    
    @owner_only
    async def _cmd_add(self, client: Client, message: Message):
        """Üye ekleme komutu"""
        args = message.text.split()
        
        if len(args) < 3:
            await message.reply("❌ **Kullanım:** `/ekle @kaynak @hedef`")
            return
        
        source, target = args[1], args[2]
        status_msg = await message.reply("🔄 **Hazırlanıyor...**")
        
        result = await self.engine.start_adding(client, source, target)
        
        if result["success"]:
            await status_msg.edit(
                f"✅ **Başlatıldı!**\n\n"
                f"📤 `{result['source_title']}`\n"
                f"📥 `{result['target_title']}`\n"
                f"👥 `{result['total_users']}` üye"
            )
            
            text = await self._build_panel_text()
            keyboard = self._build_panel_keyboard()
            panel_msg = await message.reply(text, reply_markup=keyboard)
            self.panel_message_id = panel_msg.id
            self.panel_chat_id = panel_msg.chat.id
        else:
            await status_msg.edit(f"❌ **Hata:** `{result['error']}`")
    
    @owner_only
    async def _cmd_stop(self, client: Client, message: Message):
        """Durdurma komutu"""
        if not self.engine.is_running:
            await message.reply("ℹ️ Aktif görev yok.")
            return
        await self.engine.stop()
        await message.reply("⏹️ **Görev durduruldu.**")
    
    @owner_only
    async def _cmd_help(self, client: Client, message: Message):
        """Yardım komutu"""
        text = (
            "📖 **Kullanım Kılavuzu**\n\n"
            "**1️⃣ Session Ekleme:**\n"
            "`/session AQB...StringSession...`\n\n"
            "**2️⃣ Üye Ekleme:**\n"
            "`/ekle @kaynakgrup @hedefgrup`\n\n"
            "**3️⃣ Panel:**\n"
            "`/panel`\n\n"
            "**🔒 Özellikler:**\n"
            "• Valid user önceliği\n"
            "• Akıllı FloodWait yönetimi\n"
            "• Çoklu worker rotasyonu\n"
            "• Kara liste sistemi"
        )
        await message.reply(text)
    
    @owner_only_callback
    async def _callback_handler(self, client: Client, callback: CallbackQuery):
        """Callback handler"""
        data = callback.data
        
        if data == "refresh":
            text = await self._build_panel_text()
            keyboard = self._build_panel_keyboard()
            await callback.message.edit(text, reply_markup=keyboard)
            await callback.answer("🔄 Güncellendi!")
        
        elif data == "stats":
            stats = await self.db.get_stats()
            text = (
                f"📊 **İstatistikler**\n\n"
                f"Worker: {stats['active_sessions']}/{stats['total_sessions']}\n"
                f"Valid: {stats['valid_users']}\n"
                f"Blacklist: {stats['blacklisted_users']}\n"
                f"Bugün: {stats['added_today']}\n"
                f"Toplam: {stats['total_added']}"
            )
            await callback.answer()
            await callback.message.reply(text)
        
        elif data == "sessions":
            statuses = self.manager.get_all_statuses()
            if not statuses:
                await callback.answer("Worker yok!", show_alert=True)
                return
            
            text = "🤖 **Worker'lar**\n\n"
            for s in statuses:
                icon = "🟢" if s.is_connected and s.is_available else "🔴"
                if s.flood_until:
                    icon = "🟡"
                text += f"{icon} #{s.session_id} @{s.username or s.user_id} ({s.added_today})\n"
            
            await callback.answer()
            await callback.message.reply(text)
        
        elif data == "pause":
            if self.engine.is_running:
                await self.engine.pause()
                await callback.answer("⏸️ Duraklatıldı!")
                text = await self._build_panel_text()
                keyboard = self._build_panel_keyboard()
                await callback.message.edit(text, reply_markup=keyboard)
            else:
                await callback.answer("Aktif görev yok!", show_alert=True)
        
        elif data == "resume":
            if self.engine.is_running and self.engine.is_paused:
                await self.engine.resume()
                await callback.answer("▶️ Devam!")
                text = await self._build_panel_text()
                keyboard = self._build_panel_keyboard()
                await callback.message.edit(text, reply_markup=keyboard)
            else:
                await callback.answer("Duraklatılmış görev yok!", show_alert=True)
        
        elif data == "stop":
            if self.engine.is_running:
                await self.engine.stop()
                await callback.answer("⏹️ Durduruldu!")
                text = await self._build_panel_text()
                keyboard = self._build_panel_keyboard()
                await callback.message.edit(text, reply_markup=keyboard)
            else:
                await callback.answer("Aktif görev yok!", show_alert=True)
        
        elif data == "close":
            await callback.message.delete()
            self.panel_message_id = None
            self.panel_chat_id = None
