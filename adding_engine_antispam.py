"""
Telegram Multi-Client Member Adder - Anti-Spam Adding Engine
=============================================================
Telegram'in resmi yontemi: Kullanicilari once rehbere ekle, sonra gruba ekle.
Bu yontem spam riskini minimuma indirir.

Nasil Calisir:
1. Kullaniciyi telefon rehberine ekle (ImportContacts)
2. Kisa bir sure bekle (dogal gorunsun)
3. Kullaniciyi gruba ekle
4. Opsiyonel: Rehberden sil (DeleteContacts)

Bu yontem Telegram'in resmi uygulamasinin yaptigi ile ayni.
"""

import asyncio
import random
import logging
from typing import Optional, List, Dict, Any, Callable, Set
from datetime import datetime
from dataclasses import dataclass
from enum import Enum

from pyrogram import Client, raw
from pyrogram.types import User, Chat, ChatMember, ChatPrivileges
from pyrogram.raw import functions, types
from pyrogram.errors import (
    FloodWait,
    ChannelPrivate,
    ChatAdminRequired,
    UserNotParticipant,
    UserAdminInvalid,
    ChatAdminInviteRequired,
    RightForbidden,
    PeerFlood,
    UserPrivacyRestricted,
    UserNotMutualContact,
    PhoneNumberInvalid,
    ContactIdInvalid
)

import config
from database import DatabaseInterface
from userbot_manager import UserbotManager, UserbotWorker

logger = logging.getLogger(__name__)


class TaskStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class AddingProgress:
    """Ekleme ilerleme durumu"""
    task_id: int
    status: TaskStatus
    source_title: str
    target_title: str
    total_users: int
    processed: int
    added: int
    failed: int
    skipped: int
    active_workers: int
    available_workers: int
    current_user: Optional[str]
    estimated_remaining: Optional[int]
    errors: List[str]


@dataclass
class UserInfo:
    """Kullanici bilgisi"""
    user_id: int
    username: Optional[str]
    first_name: Optional[str]
    last_name: Optional[str] = None
    phone: Optional[str] = None
    access_hash: Optional[int] = None


class AntiSpamAddingEngine:
    """
    Anti-Spam Uye Ekleme Motoru
    
    Telegram'in resmi yontemini kullanir:
    1. Kullaniciyi rehbere ekle
    2. Gruba ekle
    3. Rehberden sil (opsiyonel)
    """
    
    def __init__(self, db: DatabaseInterface, manager: UserbotManager):
        self.db = db
        self.manager = manager
        self.current_task_id: Optional[int] = None
        self.is_running = False
        self.is_paused = False
        self.should_stop = False
        self.progress: Optional[AddingProgress] = None
        self._progress_callback: Optional[Callable] = None
        self._processed_users: Set[int] = set()
        self._lock = asyncio.Lock()
        
        self._source_username: Optional[str] = None
        self._target_username: Optional[str] = None
    
    def set_progress_callback(self, callback: Callable):
        self._progress_callback = callback
    
    async def _notify_progress(self):
        if self._progress_callback and self.progress:
            try:
                await self._progress_callback(self.progress)
            except Exception as e:
                logger.warning(f"Progress callback hatasi: {e}")
    
    async def _add_to_contacts(self, worker: UserbotWorker, user: UserInfo) -> bool:
        """
        Kullaniciyi rehbere ekle
        Bu islem Telegram'in resmi API'si uzerinden yapilir
        """
        if not worker.client or not worker.is_connected:
            return False
        
        try:
            # Rastgele telefon numarasi olustur (fake)
            # Not: Gercek numara yoksa Telegram bunu kabul etmeyebilir
            # Ama InputUser ile direkt ekleyebiliriz
            
            # Raw API kullanarak contact ekle
            contact = types.InputPhoneContact(
                client_id=random.randint(1, 9999999),
                phone=f"+1{random.randint(1000000000, 9999999999)}",  # Fake numara
                first_name=user.first_name or "User",
                last_name=user.last_name or str(user.user_id)
            )
            
            result = await worker.client.invoke(
                functions.contacts.ImportContacts(
                    contacts=[contact]
                )
            )
            
            logger.debug(f"Rehbere eklendi: {user.first_name}")
            return True
            
        except Exception as e:
            logger.debug(f"Rehbere ekleme hatasi (onemli degil): {e}")
            return False
    
    async def _add_contact_by_username(self, worker: UserbotWorker, user: UserInfo) -> bool:
        """
        Username ile kullaniciyi contact olarak ekle
        Daha guvenilir yontem
        """
        if not worker.client or not worker.is_connected:
            return False
        
        if not user.username:
            return False
        
        try:
            # Kullaniciyi resolve et
            peer = await worker.client.resolve_peer(user.username)
            
            # AddContact API'sini kullan
            result = await worker.client.invoke(
                functions.contacts.AddContact(
                    id=peer,
                    first_name=user.first_name or "User",
                    last_name=user.last_name or "",
                    phone="",
                    add_phone_privacy_exception=False
                )
            )
            
            logger.debug(f"Contact eklendi: @{user.username}")
            return True
            
        except Exception as e:
            logger.debug(f"Contact ekleme hatasi: {e}")
            return False
    
    async def _delete_contact(self, worker: UserbotWorker, user_id: int) -> bool:
        """Kullaniciyi rehberden sil"""
        if not worker.client or not worker.is_connected:
            return False
        
        try:
            # Peer'i al
            peer = await worker.client.resolve_peer(user_id)
            
            # Sil
            await worker.client.invoke(
                functions.contacts.DeleteContacts(
                    id=[peer]
                )
            )
            
            logger.debug(f"Rehberden silindi: {user_id}")
            return True
            
        except Exception as e:
            logger.debug(f"Rehberden silme hatasi: {e}")
            return False
    
    async def _get_user_full_info(self, worker: UserbotWorker, user: User) -> UserInfo:
        """Kullanici bilgilerini al"""
        return UserInfo(
            user_id=user.id,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name,
            phone=getattr(user, 'phone_number', None)
        )
    
    async def _add_user_with_contact_method(self, worker: UserbotWorker, 
                                            chat_id: int, 
                                            user: UserInfo) -> Dict[str, Any]:
        """
        Anti-spam yontemi ile kullanici ekle:
        1. Kullaniciyi contact olarak ekle
        2. Kisa bekle
        3. Gruba ekle
        4. Contact'tan sil
        """
        result = {
            "success": False,
            "error": None,
            "error_type": None,
            "should_blacklist": False,
            "flood_wait": 0,
            "worker_disabled": False
        }
        
        if not worker.client or not worker.is_connected:
            result["error"] = "Worker bagli degil"
            return result
        
        try:
            # ADIM 1: Kullaniciyi contact olarak ekle
            if user.username:
                contact_added = await self._add_contact_by_username(worker, user)
            else:
                contact_added = False
            
            if contact_added:
                # Dogal gorunmesi icin kisa bekle
                await asyncio.sleep(random.uniform(2, 5))
            
            # ADIM 2: Gruba ekle
            try:
                # Username varsa username ile, yoksa ID ile
                user_to_add = user.username if user.username else user.user_id
                await worker.client.add_chat_members(chat_id, user_to_add)
                result["success"] = True
                
                # Istatistik guncelle
                await self.db.increment_session_count(worker.session.id)
                
            except Exception as add_error:
                raise add_error
            
            finally:
                # ADIM 3: Contact'tan sil (temizlik)
                if contact_added:
                    await asyncio.sleep(1)
                    await self._delete_contact(worker, user.user_id)
            
            return result
            
        except FloodWait as e:
            result["error"] = f"FloodWait: {e.value}s"
            result["error_type"] = "flood"
            result["flood_wait"] = e.value
            
            if e.value > config.AddingConfig.MAX_FLOOD_WAIT:
                result["worker_disabled"] = True
                worker.is_available = False
            
            return result
            
        except PeerFlood:
            result["error"] = "PeerFlood - Spam algilandi"
            result["error_type"] = "peer_flood"
            result["worker_disabled"] = True
            worker.is_available = False
            return result
            
        except UserPrivacyRestricted:
            result["error"] = "Gizlilik kisitlamasi"
            result["error_type"] = "privacy"
            result["should_blacklist"] = True
            return result
            
        except UserNotMutualContact:
            result["error"] = "Karsilikli kisi degil"
            result["error_type"] = "not_contact"
            # Contact yontemi ile bu hatayi bypass edebilmeliyiz
            # Tekrar deneyelim
            return result
            
        except ChatAdminRequired:
            result["error"] = "Admin yetkisi gerekli"
            result["error_type"] = "admin_required"
            return result
            
        except Exception as e:
            result["error"] = str(e)
            result["error_type"] = "unknown"
            logger.error(f"Beklenmeyen hata: {e}")
            return result
    
    async def _promote_workers_in_chat(self, admin_client: Client, chat_id: int) -> int:
        """Worker'lara hedef grupta uye ekleme yetkisi ver"""
        promoted = 0
        
        for worker in self.manager.workers.values():
            if not worker.is_connected:
                continue
            
            try:
                worker_user_id = worker.session.user_id
                
                await admin_client.promote_chat_member(
                    chat_id=chat_id,
                    user_id=worker_user_id,
                    privileges=ChatPrivileges(
                        can_invite_users=True,
                        can_manage_chat=False,
                        can_delete_messages=False,
                        can_restrict_members=False,
                        can_promote_members=False,
                        can_change_info=False,
                        can_post_messages=False,
                        can_edit_messages=False,
                        can_pin_messages=False,
                        can_manage_video_chats=False
                    )
                )
                promoted += 1
                logger.info(f"Worker {worker.session.id} admin yapildi")
                await asyncio.sleep(1)
                
            except Exception as e:
                logger.warning(f"Worker {worker.session.id} admin yapilamadi: {e}")
        
        return promoted
    
    async def _get_target_members(self, client: Client, chat_id: int) -> Set[int]:
        """Hedef gruptaki mevcut uyeleri al"""
        members = set()
        try:
            async for member in client.get_chat_members(chat_id):
                members.add(member.user.id)
        except Exception as e:
            logger.warning(f"Hedef grup uyeleri alinamadi: {e}")
        return members
    
    async def _get_source_members_via_worker(self, worker: UserbotWorker, 
                                              chat_id: int) -> List[UserInfo]:
        """Kaynak grup uyelerini worker uzerinden al"""
        users = []
        
        try:
            raw_users = await worker.get_users_from_chat(chat_id)
            for user in raw_users:
                if not user.is_bot and not user.is_deleted:
                    users.append(UserInfo(
                        user_id=user.id,
                        username=user.username,
                        first_name=user.first_name,
                        last_name=user.last_name
                    ))
        except Exception as e:
            logger.error(f"Kaynak grup uyeleri alinamadi: {e}")
        
        return users
    
    async def _prepare_user_list(self, source_members: List[UserInfo], 
                                 target_members: Set[int],
                                 target_group_id: int) -> List[UserInfo]:
        """Eklenecek kullanici listesini hazirla - USERNAME OLANLARI ONCELE"""
        users_with_username = []
        users_without_username = []
        
        for user in source_members:
            if user.user_id in target_members:
                continue
            if user.user_id in self._processed_users:
                continue
            if await self.db.is_blacklisted(user.user_id):
                continue
            if await self.db.is_user_added_to_group(user.user_id, target_group_id):
                continue
            
            # Username olanlar oncelikli (contact olarak eklenebilir)
            if user.username:
                users_with_username.append(user)
            else:
                users_without_username.append(user)
        
        # Karistir
        random.shuffle(users_with_username)
        random.shuffle(users_without_username)
        
        # Username olanlar once
        users_to_add = users_with_username + users_without_username
        
        logger.info(f"Eklenecek: {len(users_to_add)} kullanici "
                   f"({len(users_with_username)} username'li, {len(users_without_username)} username'siz)")
        
        return users_to_add
    
    async def _get_delay(self, batch_count: int) -> float:
        """Bekleme suresi hesapla"""
        if batch_count > 0 and batch_count % config.AddingConfig.BATCH_SIZE == 0:
            delay = random.uniform(
                config.AddingConfig.BATCH_DELAY_MIN,
                config.AddingConfig.BATCH_DELAY_MAX
            )
            logger.info(f"Batch molasi: {int(delay)}s ({int(delay/60)} dakika)")
        else:
            delay = random.uniform(
                config.AddingConfig.MIN_DELAY,
                config.AddingConfig.MAX_DELAY
            )
        return delay
    
    async def start_adding(self, admin_client: Client, 
                          source_chat: int | str,
                          target_chat: int | str) -> Dict[str, Any]:
        """Uye ekleme islemini baslat (Anti-Spam yontemi)"""
        result = {
            "success": False,
            "task_id": None,
            "error": None,
            "source_title": None,
            "target_title": None,
            "total_users": 0
        }
        
        if self.is_running:
            result["error"] = "Zaten aktif bir gorev var"
            return result
        
        try:
            # Gruplari dogrula
            try:
                source_entity = await admin_client.get_chat(source_chat)
                target_entity = await admin_client.get_chat(target_chat)
            except ChannelPrivate:
                result["error"] = "Grup/kanal ozel ve erisiniz yok"
                return result
            except Exception as e:
                result["error"] = f"Grup bulunamadi: {e}"
                return result
            
            result["source_title"] = source_entity.title
            result["target_title"] = target_entity.title
            
            self._source_username = getattr(source_entity, 'username', None) or str(source_chat)
            self._target_username = getattr(target_entity, 'username', None) or str(target_chat)
            
            # Musait worker kontrolu
            available_workers = self.manager.get_available_workers()
            if not available_workers:
                result["error"] = "Musait worker yok. Once /session ile worker ekleyin."
                return result
            
            # Worker'lari gruplara katildir
            if config.AddingConfig.AUTO_JOIN_ENABLED:
                logger.info("Worker'lar gruplara katiliyor...")
                
                source_join_id = self._source_username if self._source_username else source_entity.id
                await self.manager.ensure_workers_in_chat(source_join_id, source_entity.id)
                await asyncio.sleep(2)
                
                target_join_id = self._target_username if self._target_username else target_entity.id
                await self.manager.ensure_workers_in_chat(target_join_id, target_entity.id)
                await asyncio.sleep(2)
            
            # Worker'lara admin yetkisi ver
            logger.info("Worker'lara admin yetkisi veriliyor...")
            promoted = await self._promote_workers_in_chat(admin_client, target_entity.id)
            if promoted > 0:
                logger.info(f"[OK] {promoted} worker'a admin yetkisi verildi")
                await asyncio.sleep(2)
            
            # Worker sec
            worker = await self.manager.get_next_available_worker()
            if not worker:
                result["error"] = "Worker gruplara katilamadi"
                return result
            
            # Uyeleri al
            logger.info("Uyeler worker uzerinden aliniyor...")
            source_members = await self._get_source_members_via_worker(worker, source_entity.id)
            
            if not source_members:
                result["error"] = "Kaynak grupta eklenebilir uye bulunamadi"
                return result
            
            target_members = await self._get_target_members(admin_client, target_entity.id)
            
            users_to_add = await self._prepare_user_list(
                source_members, target_members, target_entity.id
            )
            
            if not users_to_add:
                result["error"] = "Tum uyeler zaten hedefte veya kara listede"
                return result
            
            result["total_users"] = len(users_to_add)
            
            # Task olustur
            task_id = await self.db.create_task(
                source_group_id=source_entity.id,
                target_group_id=target_entity.id,
                total_users=len(users_to_add)
            )
            
            self.current_task_id = task_id
            result["task_id"] = task_id
            result["success"] = True
            
            self.is_running = True
            self.should_stop = False
            self._processed_users.clear()
            
            self.progress = AddingProgress(
                task_id=task_id,
                status=TaskStatus.RUNNING,
                source_title=source_entity.title,
                target_title=target_entity.title,
                total_users=len(users_to_add),
                processed=0,
                added=0,
                failed=0,
                skipped=0,
                active_workers=len(available_workers),
                available_workers=len(available_workers),
                current_user=None,
                estimated_remaining=None,
                errors=[]
            )
            
            # Async olarak ekleme baslat
            asyncio.create_task(self._adding_loop(
                target_entity.id,
                users_to_add,
                source_entity.id,
                worker
            ))
            
            return result
            
        except Exception as e:
            result["error"] = str(e)
            logger.error(f"Ekleme baslatma hatasi: {e}")
            import traceback
            traceback.print_exc()
            return result
    
    async def _adding_loop(self, target_group_id: int, 
                          users: List[UserInfo],
                          source_group_id: int,
                          primary_worker: UserbotWorker):
        """Ana ekleme dongusu - Anti-Spam yontemi"""
        batch_count = 0
        start_time = datetime.now()
        current_worker = primary_worker
        
        logger.info("=" * 50)
        logger.info("ANTI-SPAM MODU AKTIF")
        logger.info("Kullanicilar contact olarak eklenip gruba ekleniyor")
        logger.info("=" * 50)
        
        try:
            for i, user in enumerate(users):
                if self.should_stop:
                    break
                
                while self.is_paused:
                    await asyncio.sleep(1)
                    if self.should_stop:
                        break
                
                if self.should_stop:
                    break
                
                if user.user_id in self._processed_users:
                    continue
                
                self._processed_users.add(user.user_id)
                
                user_name = user.first_name or user.username or str(user.user_id)
                if self.progress:
                    self.progress.current_user = user_name
                    self.progress.processed = i + 1
                    
                    elapsed = (datetime.now() - start_time).total_seconds()
                    if self.progress.added > 0:
                        avg_time = elapsed / self.progress.added
                        remaining = (len(users) - i) * avg_time
                        self.progress.estimated_remaining = int(remaining)
                
                # Worker kontrolu
                if not current_worker.is_available or not current_worker.is_connected:
                    new_worker = await self.manager.get_next_available_worker()
                    if new_worker:
                        current_worker = new_worker
                        await current_worker.get_users_from_chat(source_group_id)
                    else:
                        logger.warning("Musait worker yok, bekleniyor...")
                        await asyncio.sleep(60)
                        current_worker = await self.manager.get_next_available_worker()
                        if not current_worker:
                            if self.progress:
                                self.progress.errors.append("Musait worker kalmadi")
                            break
                
                # ANTI-SPAM YONTEMI ILE EKLE
                result = await self._add_user_with_contact_method(
                    current_worker,
                    target_group_id,
                    user
                )
                
                if result["success"]:
                    batch_count += 1
                    if self.progress:
                        self.progress.added += 1
                    
                    await self.db.update_task_progress(self.current_task_id, added=1)
                    
                    await self.db.add_valid_user(
                        user_id=user.user_id,
                        username=user.username,
                        first_name=user.first_name,
                        source_group_id=source_group_id
                    )
                    
                    await self.db.mark_user_added(
                        user_id=user.user_id,
                        target_group_id=target_group_id,
                        session_id=current_worker.session.id
                    )
                    
                    logger.info(f"[+] Eklendi: {user_name} (Contact yontemi)")
                    
                else:
                    error_type = result.get("error_type")
                    
                    if error_type == "already_member":
                        if self.progress:
                            self.progress.skipped += 1
                        await self.db.update_task_progress(self.current_task_id, skipped=1)
                    else:
                        if self.progress:
                            self.progress.failed += 1
                            if len(self.progress.errors) < 10:
                                self.progress.errors.append(f"{user_name}: {result['error']}")
                        await self.db.update_task_progress(self.current_task_id, failed=1)
                    
                    if result.get("should_blacklist"):
                        await self.db.add_to_blacklist(user.user_id, result["error"])
                    
                    if result.get("flood_wait", 0) > 0:
                        wait_time = result["flood_wait"]
                        if wait_time <= config.AddingConfig.MAX_FLOOD_WAIT:
                            logger.info(f"FloodWait bekleniyor: {wait_time}s")
                            await asyncio.sleep(wait_time + 5)
                    
                    if result.get("worker_disabled"):
                        logger.warning("Worker devre disi, baska worker deneniyor...")
                        new_worker = await self.manager.get_next_available_worker()
                        if new_worker:
                            current_worker = new_worker
                            await current_worker.get_users_from_chat(source_group_id)
                    
                    logger.warning(f"[-] Basarisiz: {user_name} - {result['error']}")
                
                if self.progress:
                    available = self.manager.get_available_workers()
                    self.progress.available_workers = len(available)
                    self.progress.active_workers = len(self.manager.workers)
                
                await self._notify_progress()
                
                # Bekleme
                delay = await self._get_delay(batch_count)
                logger.info(f"Bekleniyor: {int(delay)}s")
                await asyncio.sleep(delay)
            
            status = TaskStatus.COMPLETED if not self.should_stop else TaskStatus.CANCELLED
            if self.progress:
                self.progress.status = status
                self.progress.current_user = None
            
            await self.db.complete_task(self.current_task_id, status.value)
            await self._notify_progress()
            
            logger.info(f"Gorev tamamlandi: {status.value}")
            logger.info(f"Toplam eklenen: {self.progress.added if self.progress else 0}")
            
        except Exception as e:
            logger.error(f"Ekleme dongusu hatasi: {e}")
            import traceback
            traceback.print_exc()
            if self.progress:
                self.progress.status = TaskStatus.FAILED
                self.progress.errors.append(str(e))
            await self.db.complete_task(self.current_task_id, TaskStatus.FAILED.value)
            await self._notify_progress()
            
        finally:
            self.is_running = False
            self.current_task_id = None
    
    async def pause(self):
        if self.is_running:
            self.is_paused = True
            if self.progress:
                self.progress.status = TaskStatus.PAUSED
            await self._notify_progress()
    
    async def resume(self):
        if self.is_running and self.is_paused:
            self.is_paused = False
            if self.progress:
                self.progress.status = TaskStatus.RUNNING
            await self._notify_progress()
    
    async def stop(self):
        self.should_stop = True
        self.is_paused = False
        if self.progress:
            self.progress.status = TaskStatus.CANCELLED
        await self._notify_progress()
    
    def get_progress(self) -> Optional[AddingProgress]:
        return self.progress
