"""
Telegram Multi-Client Member Adder - Adding Engine
===================================================
Akilli uye ekleme motoru - PEER_ID_INVALID duzeltildi.
Userbot'un kendi aldigi uyeleri kullaniyor.
"""

import asyncio
import random
import logging
from typing import Optional, List, Dict, Any, Callable, Set
from datetime import datetime
from dataclasses import dataclass
from enum import Enum

from pyrogram import Client
from pyrogram.types import User, Chat, ChatMember
from pyrogram.enums import ChatMembersFilter, ChatMemberStatus
from pyrogram.errors import (
    FloodWait,
    ChannelPrivate,
    ChatAdminRequired,
    UserNotParticipant
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
    access_hash: Optional[int] = None


class MemberAddingEngine:
    """Akilli uye ekleme motoru"""
    
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
        
        # Kaynak ve hedef bilgileri
        self._source_username: Optional[str] = None
        self._target_username: Optional[str] = None
    
    def set_progress_callback(self, callback: Callable):
        """Ilerleme callback'i ayarla"""
        self._progress_callback = callback
    
    async def _notify_progress(self):
        """Ilerleme bildir"""
        if self._progress_callback and self.progress:
            try:
                await self._progress_callback(self.progress)
            except Exception as e:
                logger.warning(f"Progress callback hatasi: {e}")
    
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
                        first_name=user.first_name
                    ))
        except Exception as e:
            logger.error(f"Kaynak grup uyeleri alinamadi: {e}")
        
        return users
    
    async def _prepare_user_list(self, source_members: List[UserInfo], 
                                 target_members: Set[int],
                                 target_group_id: int) -> List[UserInfo]:
        """Eklenecek kullanici listesini hazirla"""
        users_to_add = []
        valid_users_first = []
        other_users = []
        
        for user in source_members:
            # Zaten hedefte mi?
            if user.user_id in target_members:
                continue
            
            # Daha once bu gorevde islendi mi?
            if user.user_id in self._processed_users:
                continue
            
            # Kara listede mi?
            if await self.db.is_blacklisted(user.user_id):
                continue
            
            # Daha once bu gruba eklendi mi?
            if await self.db.is_user_added_to_group(user.user_id, target_group_id):
                continue
            
            # Valid user mi?
            if config.AddingConfig.PRIORITIZE_VALID_USERS:
                if await self.db.is_valid_user(user.user_id):
                    valid_users_first.append(user)
                else:
                    other_users.append(user)
            else:
                other_users.append(user)
        
        # Karistir
        if len(valid_users_first) > 1:
            random.shuffle(valid_users_first)
        if len(other_users) > 1:
            random.shuffle(other_users)
        
        users_to_add = valid_users_first + other_users
        
        logger.info(f"Eklenecek: {len(users_to_add)} kullanici "
                   f"({len(valid_users_first)} valid, {len(other_users)} yeni)")
        
        return users_to_add
    
    async def _get_delay(self, batch_count: int) -> float:
        """Bekleme suresi hesapla"""
        if batch_count > 0 and batch_count % config.AddingConfig.BATCH_SIZE == 0:
            delay = random.uniform(
                config.AddingConfig.BATCH_DELAY_MIN,
                config.AddingConfig.BATCH_DELAY_MAX
            )
            logger.info(f"Batch molasi: {int(delay)}s")
        else:
            delay = random.uniform(
                config.AddingConfig.MIN_DELAY,
                config.AddingConfig.MAX_DELAY
            )
        return delay
    
    async def start_adding(self, admin_client: Client, 
                          source_chat: int | str,
                          target_chat: int | str) -> Dict[str, Any]:
        """Uye ekleme islemini baslat"""
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
            
            # Username'leri kaydet
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
                
                # Kaynak gruba katil
                source_join_id = self._source_username if self._source_username else source_entity.id
                await self.manager.ensure_workers_in_chat(source_join_id, source_entity.id)
                await asyncio.sleep(2)
                
                # Hedef gruba katil  
                target_join_id = self._target_username if self._target_username else target_entity.id
                await self.manager.ensure_workers_in_chat(target_join_id, target_entity.id)
                await asyncio.sleep(2)
            
            # Ilk worker'i sec
            worker = await self.manager.get_next_available_worker()
            if not worker:
                result["error"] = "Worker gruplara katilamadi"
                return result
            
            # ONEMLI: Uyeleri worker uzerinden al (PEER_ID_INVALID onlemi)
            logger.info("Uyeler worker uzerinden aliniyor...")
            source_members = await self._get_source_members_via_worker(worker, source_entity.id)
            
            if not source_members:
                result["error"] = "Kaynak grupta eklenebilir uye bulunamadi"
                return result
            
            # Hedef grup uyelerini al
            target_members = await self._get_target_members(admin_client, target_entity.id)
            
            # Eklenecek kullanici listesini hazirla
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
            
            # Baslat
            self.is_running = True
            self.should_stop = False
            self._processed_users.clear()
            
            # Progress baslat
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
                worker  # Ayni worker'i kullan
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
        """Ana ekleme dongusu"""
        batch_count = 0
        start_time = datetime.now()
        current_worker = primary_worker
        
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
                
                # Cakisma kontrolu
                if user.user_id in self._processed_users:
                    continue
                
                self._processed_users.add(user.user_id)
                
                # Progress guncelle
                user_name = user.first_name or user.username or str(user.user_id)
                if self.progress:
                    self.progress.current_user = user_name
                    self.progress.processed = i + 1
                    
                    # Tahmini sure hesapla
                    elapsed = (datetime.now() - start_time).total_seconds()
                    if self.progress.added > 0:
                        avg_time = elapsed / self.progress.added
                        remaining = (len(users) - i) * avg_time
                        self.progress.estimated_remaining = int(remaining)
                
                # Worker kontrolu - musait degilse diger worker'i dene
                if not current_worker.is_available or not current_worker.is_connected:
                    new_worker = await self.manager.get_next_available_worker()
                    if new_worker:
                        current_worker = new_worker
                        # Yeni worker icin uyeleri yukle
                        await current_worker.get_users_from_chat(source_group_id)
                    else:
                        logger.warning("Musait worker yok, bekleniyor...")
                        await asyncio.sleep(60)
                        current_worker = await self.manager.get_next_available_worker()
                        if not current_worker:
                            if self.progress:
                                self.progress.errors.append("Musait worker kalmadi")
                            break
                
                # Kullaniciyi ekle - username ile dene
                result = await current_worker.add_user_to_chat(
                    target_group_id, 
                    user.user_id,
                    user.username
                )
                
                if result["success"]:
                    batch_count += 1
                    if self.progress:
                        self.progress.added += 1
                    
                    await self.db.update_task_progress(self.current_task_id, added=1)
                    
                    # Valid user olarak kaydet
                    await self.db.add_valid_user(
                        user_id=user.user_id,
                        username=user.username,
                        first_name=user.first_name,
                        source_group_id=source_group_id
                    )
                    
                    # Eklendi olarak isaretle
                    await self.db.mark_user_added(
                        user_id=user.user_id,
                        target_group_id=target_group_id,
                        session_id=current_worker.session.id
                    )
                    
                    logger.info(f"[+] Eklendi: {user_name} (Worker: {current_worker.session.id})")
                    
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
                    
                    # Kara listeye ekle
                    if result.get("should_blacklist"):
                        await self.db.add_to_blacklist(user.user_id, result["error"])
                    
                    # FloodWait
                    if result.get("flood_wait", 0) > 0:
                        wait_time = result["flood_wait"]
                        if wait_time <= config.AddingConfig.MAX_FLOOD_WAIT:
                            logger.info(f"FloodWait bekleniyor: {wait_time}s")
                            await asyncio.sleep(wait_time + 5)
                        else:
                            # Baska worker dene
                            new_worker = await self.manager.get_next_available_worker()
                            if new_worker and new_worker != current_worker:
                                current_worker = new_worker
                                await current_worker.get_users_from_chat(source_group_id)
                    
                    # Worker devre disi kaldiysa
                    if result.get("worker_disabled"):
                        new_worker = await self.manager.get_next_available_worker()
                        if new_worker:
                            current_worker = new_worker
                            await current_worker.get_users_from_chat(source_group_id)
                    
                    logger.warning(f"[-] Basarisiz: {user_name} - {result['error']}")
                
                # Musait worker sayisini guncelle
                if self.progress:
                    available = self.manager.get_available_workers()
                    self.progress.available_workers = len(available)
                    self.progress.active_workers = len(self.manager.workers)
                
                # Progress bildir
                await self._notify_progress()
                
                # Bekleme
                delay = await self._get_delay(batch_count)
                await asyncio.sleep(delay)
            
            # Tamamlandi
            status = TaskStatus.COMPLETED if not self.should_stop else TaskStatus.CANCELLED
            if self.progress:
                self.progress.status = status
                self.progress.current_user = None
            
            await self.db.complete_task(self.current_task_id, status.value)
            await self._notify_progress()
            
            logger.info(f"Gorev tamamlandi: {status.value}")
            
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
        """Gorevi duraklat"""
        if self.is_running:
            self.is_paused = True
            if self.progress:
                self.progress.status = TaskStatus.PAUSED
            await self._notify_progress()
    
    async def resume(self):
        """Gorevi devam ettir"""
        if self.is_running and self.is_paused:
            self.is_paused = False
            if self.progress:
                self.progress.status = TaskStatus.RUNNING
            await self._notify_progress()
    
    async def stop(self):
        """Gorevi durdur"""
        self.should_stop = True
        self.is_paused = False
        if self.progress:
            self.progress.status = TaskStatus.CANCELLED
        await self._notify_progress()
    
    def get_progress(self) -> Optional[AddingProgress]:
        """Mevcut ilerlemeyi dondur"""
        return self.progress
