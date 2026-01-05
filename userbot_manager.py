"""
Telegram Multi-Client Member Adder - Userbot Manager
=====================================================
Birden fazla Pyrogram client'ı yönetir.
"""

import asyncio
import logging
from typing import Optional, List, Dict, Any, Callable
from datetime import datetime, timedelta
from dataclasses import dataclass

from pyrogram import Client
from pyrogram.types import User, Chat
from pyrogram.errors import (
    FloodWait,
    PeerFlood,
    UserPrivacyRestricted,
    UserNotMutualContact,
    UserChannelsTooMuch,
    ChatWriteForbidden,
    UserKicked,
    UserBannedInChannel,
    UserAlreadyParticipant,
    ChatAdminRequired,
    ChannelPrivate,
    UserDeactivated,
    AuthKeyUnregistered,
    SessionRevoked,
    UserIdInvalid,
    InputUserDeactivated,
    InviteHashExpired,
    UserNotParticipant
)

import config
from database import DatabaseInterface, Session, BotStatus

logger = logging.getLogger(__name__)


@dataclass
class WorkerStatus:
    """Worker durumu"""
    session_id: int
    user_id: int
    username: Optional[str]
    is_connected: bool
    is_available: bool
    flood_until: Optional[datetime]
    added_today: int
    error: Optional[str]


class UserbotWorker:
    """Tek bir userbot worker"""
    
    def __init__(self, session: Session, db: DatabaseInterface):
        self.session = session
        self.db = db
        self.client: Optional[Client] = None
        self.is_connected = False
        self.is_available = True
        self.current_flood_wait: Optional[datetime] = None
        self.last_error: Optional[str] = None
        self._lock = asyncio.Lock()
    
    async def connect(self) -> bool:
        """Client'a bağlan"""
        try:
            self.client = Client(
                name=f"worker_{self.session.id}",
                api_id=config.API_ID,
                api_hash=config.API_HASH,
                session_string=self.session.string_session,
                in_memory=True
            )
            
            await self.client.start()
            me = await self.client.get_me()
            
            self.is_connected = True
            self.is_available = True
            logger.info(f"Worker {self.session.id} bağlandı: @{me.username or me.id}")
            
            return True
            
        except UserDeactivated:
            self.last_error = "Hesap devre dışı"
            await self.db.update_session_status(self.session.id, BotStatus.DEACTIVATED.value)
            logger.error(f"Worker {self.session.id}: Hesap devre dışı")
            return False
            
        except AuthKeyUnregistered:
            self.last_error = "Oturum geçersiz"
            await self.db.update_session_status(self.session.id, BotStatus.ERROR.value)
            logger.error(f"Worker {self.session.id}: Auth key geçersiz")
            return False
            
        except SessionRevoked:
            self.last_error = "Oturum iptal edildi"
            await self.db.update_session_status(self.session.id, BotStatus.ERROR.value)
            logger.error(f"Worker {self.session.id}: Oturum iptal edildi")
            return False
            
        except Exception as e:
            self.last_error = str(e)
            logger.error(f"Worker {self.session.id} bağlantı hatası: {e}")
            return False
    
    async def disconnect(self) -> None:
        """Client bağlantısını kes"""
        if self.client and self.is_connected:
            try:
                await self.client.stop()
            except Exception as e:
                logger.warning(f"Worker {self.session.id} disconnect hatası: {e}")
            finally:
                self.is_connected = False
    
    async def is_member_of(self, chat_id: int) -> bool:
        """Grupta üye mi kontrol et"""
        if not self.client or not self.is_connected:
            return False
        
        try:
            await self.client.get_chat_member(chat_id, "me")
            return True
        except UserNotParticipant:
            return False
        except Exception:
            return False
    
    async def join_chat(self, chat_id: int) -> bool:
        """Gruba katıl"""
        if not self.client or not self.is_connected:
            return False
        
        try:
            await self.client.join_chat(chat_id)
            logger.info(f"Worker {self.session.id} gruba katıldı: {chat_id}")
            return True
        except Exception as e:
            logger.warning(f"Worker {self.session.id} gruba katılamadı: {e}")
            return False
    
    async def add_user_to_chat(self, chat_id: int, user_id: int) -> Dict[str, Any]:
        """Kullanıcıyı gruba ekle"""
        async with self._lock:
            result = {
                "success": False,
                "error": None,
                "error_type": None,
                "should_blacklist": False,
                "flood_wait": 0,
                "worker_disabled": False
            }
            
            if not self.client or not self.is_connected:
                result["error"] = "Worker bağlı değil"
                return result
            
            if not self.is_available:
                result["error"] = "Worker müsait değil"
                return result
            
            # FloodWait kontrolü
            if self.current_flood_wait and datetime.now() < self.current_flood_wait:
                remaining = (self.current_flood_wait - datetime.now()).seconds
                result["error"] = f"FloodWait: {remaining}s kaldı"
                result["flood_wait"] = remaining
                return result
            
            try:
                await self.client.add_chat_members(chat_id, user_id)
                result["success"] = True
                
                # Başarılı - istatistik güncelle
                await self.db.increment_session_count(self.session.id)
                
                return result
                
            except UserAlreadyParticipant:
                result["error"] = "Zaten üye"
                result["error_type"] = "already_member"
                return result
                
            except UserPrivacyRestricted:
                result["error"] = "Gizlilik kısıtlaması"
                result["error_type"] = "privacy"
                result["should_blacklist"] = True
                return result
                
            except UserNotMutualContact:
                result["error"] = "Karşılıklı kişi değil"
                result["error_type"] = "not_contact"
                result["should_blacklist"] = True
                return result
                
            except UserChannelsTooMuch:
                result["error"] = "Çok fazla grupta"
                result["error_type"] = "too_many_channels"
                return result
                
            except UserKicked:
                result["error"] = "Daha önce atılmış"
                result["error_type"] = "kicked"
                return result
                
            except UserBannedInChannel:
                result["error"] = "Yasaklı kullanıcı"
                result["error_type"] = "banned"
                return result
                
            except UserIdInvalid:
                result["error"] = "Geçersiz kullanıcı"
                result["error_type"] = "invalid"
                return result
                
            except InputUserDeactivated:
                result["error"] = "Hesap silinmiş"
                result["error_type"] = "deactivated"
                result["should_blacklist"] = True
                return result
                
            except FloodWait as e:
                wait_time = e.value
                result["error"] = f"FloodWait: {wait_time}s"
                result["error_type"] = "flood"
                result["flood_wait"] = wait_time
                
                # FloodWait süresine göre işlem
                self.current_flood_wait = datetime.now() + timedelta(seconds=wait_time)
                
                if wait_time > config.AddingConfig.MAX_FLOOD_WAIT:
                    # Çok uzun süre - worker'ı devre dışı bırak
                    self.is_available = False
                    result["worker_disabled"] = True
                    await self.db.update_session_status(
                        self.session.id, 
                        BotStatus.PAUSED.value,
                        self.current_flood_wait
                    )
                    logger.warning(f"Worker {self.session.id} FloodWait nedeniyle devre dışı: {wait_time}s")
                
                return result
                
            except PeerFlood:
                result["error"] = "PeerFlood - Spam algılandı"
                result["error_type"] = "peer_flood"
                result["worker_disabled"] = True
                
                self.is_available = False
                await self.db.update_session_status(self.session.id, BotStatus.PAUSED.value)
                logger.error(f"Worker {self.session.id} PeerFlood nedeniyle devre dışı")
                
                return result
                
            except ChatAdminRequired:
                result["error"] = "Admin yetkisi gerekli"
                result["error_type"] = "admin_required"
                return result
                
            except ChannelPrivate:
                result["error"] = "Kanal/grup özel"
                result["error_type"] = "private"
                return result
                
            except ChatWriteForbidden:
                result["error"] = "Yazma yasağı"
                result["error_type"] = "forbidden"
                result["worker_disabled"] = True
                
                self.is_available = False
                logger.warning(f"Worker {self.session.id} hedef grupta yasaklı")
                
                return result
                
            except UserDeactivated:
                result["error"] = "Worker hesabı devre dışı"
                result["error_type"] = "worker_deactivated"
                result["worker_disabled"] = True
                
                self.is_connected = False
                self.is_available = False
                await self.db.update_session_status(self.session.id, BotStatus.DEACTIVATED.value)
                
                return result
                
            except Exception as e:
                result["error"] = str(e)
                result["error_type"] = "unknown"
                logger.error(f"Worker {self.session.id} beklenmeyen hata: {e}")
                return result
    
    def get_status(self) -> WorkerStatus:
        """Worker durumunu döndür"""
        return WorkerStatus(
            session_id=self.session.id,
            user_id=self.session.user_id,
            username=self.session.username,
            is_connected=self.is_connected,
            is_available=self.is_available,
            flood_until=self.current_flood_wait,
            added_today=self.session.added_count_today,
            error=self.last_error
        )


class UserbotManager:
    """Tüm userbotları yönetir"""
    
    def __init__(self, db: DatabaseInterface):
        self.db = db
        self.workers: Dict[int, UserbotWorker] = {}
        self._lock = asyncio.Lock()
    
    async def load_all_sessions(self) -> int:
        """Tüm aktif session'ları yükle ve bağlan"""
        sessions = await self.db.get_all_sessions(status=BotStatus.ACTIVE.value)
        connected = 0
        
        for session in sessions:
            worker = UserbotWorker(session, self.db)
            if await worker.connect():
                self.workers[session.id] = worker
                connected += 1
            else:
                logger.warning(f"Session {session.id} bağlanamadı")
        
        logger.info(f"{connected}/{len(sessions)} worker bağlandı")
        return connected
    
    async def add_session(self, string_session: str) -> Dict[str, Any]:
        """Yeni session ekle"""
        result = {
            "success": False,
            "session_id": None,
            "user_id": None,
            "username": None,
            "error": None
        }
        
        try:
            # Önce test client oluştur
            test_client = Client(
                name="test_session",
                api_id=config.API_ID,
                api_hash=config.API_HASH,
                session_string=string_session,
                in_memory=True
            )
            
            await test_client.start()
            me = await test_client.get_me()
            await test_client.stop()
            
            # Veritabanına kaydet
            session_id = await self.db.add_session(
                string_session=string_session,
                user_id=me.id,
                username=me.username,
                phone=me.phone_number
            )
            
            # Session bilgisini al
            session = await self.db.get_session(session_id)
            
            # Worker oluştur ve bağlan
            worker = UserbotWorker(session, self.db)
            if await worker.connect():
                async with self._lock:
                    self.workers[session_id] = worker
                
                result["success"] = True
                result["session_id"] = session_id
                result["user_id"] = me.id
                result["username"] = me.username
            else:
                result["error"] = worker.last_error
            
            return result
            
        except UserDeactivated:
            result["error"] = "Bu hesap devre dışı bırakılmış"
            return result
            
        except AuthKeyUnregistered:
            result["error"] = "Geçersiz session string"
            return result
            
        except Exception as e:
            result["error"] = str(e)
            return result
    
    async def remove_session(self, session_id: int) -> bool:
        """Session'ı kaldır"""
        async with self._lock:
            if session_id in self.workers:
                await self.workers[session_id].disconnect()
                del self.workers[session_id]
            
            return await self.db.delete_session(session_id)
    
    def get_available_workers(self) -> List[UserbotWorker]:
        """Müsait worker'ları döndür"""
        available = []
        for worker in self.workers.values():
            if worker.is_connected and worker.is_available:
                # FloodWait kontrolü
                if worker.current_flood_wait:
                    if datetime.now() >= worker.current_flood_wait:
                        worker.current_flood_wait = None
                        worker.is_available = True
                    else:
                        continue
                available.append(worker)
        return available
    
    async def get_next_available_worker(self) -> Optional[UserbotWorker]:
        """Sıradaki müsait worker'ı döndür (round-robin)"""
        available = self.get_available_workers()
        if not available:
            return None
        
        # En az kullanılmış olanı seç
        return min(available, key=lambda w: w.session.added_count_today)
    
    async def ensure_workers_in_chat(self, chat_id: int) -> int:
        """Worker'ların grupta olduğundan emin ol"""
        joined = 0
        for worker in self.workers.values():
            if worker.is_connected:
                if not await worker.is_member_of(chat_id):
                    if await worker.join_chat(chat_id):
                        joined += 1
                        await asyncio.sleep(2)  # Rate limit için
        return joined
    
    def get_all_statuses(self) -> List[WorkerStatus]:
        """Tüm worker durumlarını döndür"""
        return [worker.get_status() for worker in self.workers.values()]
    
    async def shutdown(self) -> None:
        """Tüm worker'ları kapat"""
        for worker in self.workers.values():
            await worker.disconnect()
        self.workers.clear()
        logger.info("Tüm worker'lar kapatıldı")
