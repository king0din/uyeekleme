"""
Telegram Multi-Client Member Adder - Userbot Manager
=====================================================
Birden fazla Pyrogram client'i yonetir.
PEER_ID_INVALID hatasi duzeltildi.
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
    UserNotParticipant,
    PeerIdInvalid,
    UsernameNotOccupied,
    UsernameInvalid
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
        self._resolved_peers: Dict[int, Any] = {}  # Cache for resolved peers
    
    async def connect(self) -> bool:
        """Client'a baglan"""
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
            logger.info(f"Worker {self.session.id} baglandi: @{me.username or me.id}")
            
            return True
            
        except UserDeactivated:
            self.last_error = "Hesap devre disi"
            await self.db.update_session_status(self.session.id, BotStatus.DEACTIVATED.value)
            logger.error(f"Worker {self.session.id}: Hesap devre disi")
            return False
            
        except AuthKeyUnregistered:
            self.last_error = "Oturum gecersiz"
            await self.db.update_session_status(self.session.id, BotStatus.ERROR.value)
            logger.error(f"Worker {self.session.id}: Auth key gecersiz")
            return False
            
        except SessionRevoked:
            self.last_error = "Oturum iptal edildi"
            await self.db.update_session_status(self.session.id, BotStatus.ERROR.value)
            logger.error(f"Worker {self.session.id}: Oturum iptal edildi")
            return False
            
        except Exception as e:
            self.last_error = str(e)
            logger.error(f"Worker {self.session.id} baglanti hatasi: {e}")
            return False
    
    async def disconnect(self) -> None:
        """Client baglantisini kes"""
        if self.client and self.is_connected:
            try:
                await self.client.stop()
            except Exception as e:
                logger.warning(f"Worker {self.session.id} disconnect hatasi: {e}")
            finally:
                self.is_connected = False
    
    async def resolve_peer(self, user_id: int, username: Optional[str] = None) -> bool:
        """Kullaniciyi resolve et (peer olarak tani)"""
        if not self.client or not self.is_connected:
            return False
        
        # Cache kontrol
        if user_id in self._resolved_peers:
            return True
        
        try:
            # Oncelikle username ile dene
            if username:
                try:
                    peer = await self.client.resolve_peer(username)
                    self._resolved_peers[user_id] = peer
                    return True
                except (UsernameNotOccupied, UsernameInvalid):
                    pass
            
            # User ID ile dene
            try:
                peer = await self.client.resolve_peer(user_id)
                self._resolved_peers[user_id] = peer
                return True
            except PeerIdInvalid:
                pass
            
            return False
            
        except Exception as e:
            logger.debug(f"Peer resolve hatasi {user_id}: {e}")
            return False
    
    async def get_users_from_chat(self, chat_id: int, limit: int = 200) -> List[User]:
        """Gruptan kullanicilari al ve resolve et"""
        if not self.client or not self.is_connected:
            return []
        
        users = []
        try:
            async for member in self.client.get_chat_members(chat_id, limit=limit):
                user = member.user
                if not user.is_bot and not user.is_deleted:
                    users.append(user)
                    # Peer'i cache'e ekle
                    self._resolved_peers[user.id] = True
        except Exception as e:
            logger.warning(f"Worker {self.session.id} uye listesi alinamadi: {e}")
        
        return users
    
    async def is_member_of(self, chat_id: int) -> bool:
        """Grupta uye mi kontrol et"""
        if not self.client or not self.is_connected:
            return False
        
        try:
            await self.client.get_chat_member(chat_id, "me")
            return True
        except UserNotParticipant:
            return False
        except Exception:
            return False
    
    async def join_chat(self, chat_identifier) -> bool:
        """Gruba katil - username veya invite link ile"""
        if not self.client or not self.is_connected:
            return False
        
        try:
            await self.client.join_chat(chat_identifier)
            logger.info(f"Worker {self.session.id} gruba katildi: {chat_identifier}")
            return True
        except UserAlreadyParticipant:
            return True
        except Exception as e:
            logger.warning(f"Worker {self.session.id} gruba katilamadi: {e}")
            return False
    
    async def add_user_to_chat(self, chat_id: int, user_id: int, username: Optional[str] = None) -> Dict[str, Any]:
        """Kullaniciyi gruba ekle"""
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
                result["error"] = "Worker bagli degil"
                return result
            
            if not self.is_available:
                result["error"] = "Worker musait degil"
                return result
            
            # FloodWait kontrolu
            if self.current_flood_wait and datetime.now() < self.current_flood_wait:
                remaining = (self.current_flood_wait - datetime.now()).seconds
                result["error"] = f"FloodWait: {remaining}s kaldi"
                result["flood_wait"] = remaining
                return result
            
            try:
                # Once peer'i resolve et
                user_to_add = user_id
                
                # Eger peer cache'de degilse, username ile dene
                if user_id not in self._resolved_peers:
                    if username:
                        try:
                            # Username ile kullaniciyi bul
                            user_to_add = username
                        except:
                            pass
                
                # Kullaniciyi ekle
                await self.client.add_chat_members(chat_id, user_to_add)
                result["success"] = True
                
                # Basarili - istatistik guncelle
                await self.db.increment_session_count(self.session.id)
                
                # Peer'i cache'e ekle
                self._resolved_peers[user_id] = True
                
                return result
                
            except UserAlreadyParticipant:
                result["error"] = "Zaten uye"
                result["error_type"] = "already_member"
                return result
                
            except UserPrivacyRestricted:
                result["error"] = "Gizlilik kisitlamasi"
                result["error_type"] = "privacy"
                result["should_blacklist"] = True
                return result
                
            except UserNotMutualContact:
                result["error"] = "Karsilikli kisi degil"
                result["error_type"] = "not_contact"
                result["should_blacklist"] = True
                return result
                
            except UserChannelsTooMuch:
                result["error"] = "Cok fazla grupta"
                result["error_type"] = "too_many_channels"
                return result
                
            except UserKicked:
                result["error"] = "Daha once atilmis"
                result["error_type"] = "kicked"
                return result
                
            except UserBannedInChannel:
                result["error"] = "Yasakli kullanici"
                result["error_type"] = "banned"
                return result
                
            except (UserIdInvalid, PeerIdInvalid):
                result["error"] = "Gecersiz kullanici/peer"
                result["error_type"] = "invalid"
                return result
                
            except InputUserDeactivated:
                result["error"] = "Hesap silinmis"
                result["error_type"] = "deactivated"
                result["should_blacklist"] = True
                return result
                
            except FloodWait as e:
                wait_time = e.value
                result["error"] = f"FloodWait: {wait_time}s"
                result["error_type"] = "flood"
                result["flood_wait"] = wait_time
                
                self.current_flood_wait = datetime.now() + timedelta(seconds=wait_time)
                
                if wait_time > config.AddingConfig.MAX_FLOOD_WAIT:
                    self.is_available = False
                    result["worker_disabled"] = True
                    await self.db.update_session_status(
                        self.session.id, 
                        BotStatus.PAUSED.value,
                        self.current_flood_wait
                    )
                    logger.warning(f"Worker {self.session.id} FloodWait nedeniyle devre disi: {wait_time}s")
                
                return result
                
            except PeerFlood:
                result["error"] = "PeerFlood - Spam algilandi"
                result["error_type"] = "peer_flood"
                result["worker_disabled"] = True
                
                self.is_available = False
                await self.db.update_session_status(self.session.id, BotStatus.PAUSED.value)
                logger.error(f"Worker {self.session.id} PeerFlood nedeniyle devre disi")
                
                return result
                
            except ChatAdminRequired:
                result["error"] = "Admin yetkisi gerekli"
                result["error_type"] = "admin_required"
                return result
                
            except ChannelPrivate:
                result["error"] = "Kanal/grup ozel"
                result["error_type"] = "private"
                return result
                
            except ChatWriteForbidden:
                result["error"] = "Yazma yasagi"
                result["error_type"] = "forbidden"
                result["worker_disabled"] = True
                
                self.is_available = False
                logger.warning(f"Worker {self.session.id} hedef grupta yasakli")
                
                return result
                
            except UserDeactivated:
                result["error"] = "Worker hesabi devre disi"
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
        """Worker durumunu dondur"""
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
    """Tum userbotlari yonetir"""
    
    def __init__(self, db: DatabaseInterface):
        self.db = db
        self.workers: Dict[int, UserbotWorker] = {}
        self._lock = asyncio.Lock()
    
    async def load_all_sessions(self) -> int:
        """Tum aktif session'lari yukle ve baglan"""
        sessions = await self.db.get_all_sessions(status=BotStatus.ACTIVE.value)
        connected = 0
        
        for session in sessions:
            worker = UserbotWorker(session, self.db)
            if await worker.connect():
                self.workers[session.id] = worker
                connected += 1
            else:
                logger.warning(f"Session {session.id} baglanamadi")
        
        logger.info(f"{connected}/{len(sessions)} worker baglandi")
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
            # Once test client olustur
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
            
            # Veritabanina kaydet
            session_id = await self.db.add_session(
                string_session=string_session,
                user_id=me.id,
                username=me.username,
                phone=me.phone_number
            )
            
            # Session bilgisini al
            session = await self.db.get_session(session_id)
            
            # Worker olustur ve baglan
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
            result["error"] = "Bu hesap devre disi birakilmis"
            return result
            
        except AuthKeyUnregistered:
            result["error"] = "Gecersiz session string"
            return result
            
        except Exception as e:
            result["error"] = str(e)
            return result
    
    async def remove_session(self, session_id: int) -> bool:
        """Session'i kaldir"""
        async with self._lock:
            if session_id in self.workers:
                await self.workers[session_id].disconnect()
                del self.workers[session_id]
            
            return await self.db.delete_session(session_id)
    
    def get_available_workers(self) -> List[UserbotWorker]:
        """Musait worker'lari dondur"""
        available = []
        for worker in self.workers.values():
            if worker.is_connected and worker.is_available:
                if worker.current_flood_wait:
                    if datetime.now() >= worker.current_flood_wait:
                        worker.current_flood_wait = None
                        worker.is_available = True
                    else:
                        continue
                available.append(worker)
        return available
    
    async def get_next_available_worker(self) -> Optional[UserbotWorker]:
        """Siradaki musait worker'i dondur"""
        available = self.get_available_workers()
        if not available:
            return None
        
        return min(available, key=lambda w: w.session.added_count_today)
    
    async def ensure_workers_in_chat(self, chat_identifier, chat_id: int = None) -> int:
        """Worker'larin grupta oldugunu garantile"""
        joined = 0
        for worker in self.workers.values():
            if worker.is_connected:
                # Oncelikle chat_id ile kontrol et
                is_member = False
                if chat_id:
                    is_member = await worker.is_member_of(chat_id)
                
                if not is_member:
                    # Username veya link ile katil
                    if await worker.join_chat(chat_identifier):
                        joined += 1
                        await asyncio.sleep(3)  # Rate limit icin
        return joined
    
    async def load_users_from_chat(self, chat_id: int) -> Dict[int, User]:
        """Tum worker'lar icin gruptan kullanicilari yukle"""
        all_users = {}
        
        for worker in self.workers.values():
            if worker.is_connected:
                users = await worker.get_users_from_chat(chat_id)
                for user in users:
                    if user.id not in all_users:
                        all_users[user.id] = user
                
                if all_users:
                    break  # Bir worker'dan aldiysan yeterli
        
        return all_users
    
    def get_all_statuses(self) -> List[WorkerStatus]:
        """Tum worker durumlarini dondur"""
        return [worker.get_status() for worker in self.workers.values()]
    
    async def shutdown(self) -> None:
        """Tum worker'lari kapat"""
        for worker in self.workers.values():
            await worker.disconnect()
        self.workers.clear()
        logger.info("Tum worker'lar kapatildi")
