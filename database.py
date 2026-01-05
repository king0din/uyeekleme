"""
Telegram Multi-Client Member Adder - Database Module
=====================================================
SQLite ve MongoDB desteği ile veritabanı işlemleri.
"""

import os
import sqlite3
import asyncio
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Tuple
from contextlib import contextmanager
from dataclasses import dataclass, asdict
from enum import Enum

import config


class UserStatus(Enum):
    """Kullanıcı durumları"""
    VALID = "valid"  # Eklenebilir
    BLACKLISTED = "blacklisted"  # Gizlilik engeli
    ADDED = "added"  # Zaten eklendi
    FAILED = "failed"  # Başarısız


class BotStatus(Enum):
    """Userbot durumları"""
    ACTIVE = "active"
    PAUSED = "paused"  # FloodWait
    BANNED = "banned"
    DEACTIVATED = "deactivated"
    ERROR = "error"


@dataclass
class Session:
    """Userbot oturum bilgisi"""
    id: int
    string_session: str
    user_id: int
    username: Optional[str]
    phone: Optional[str]
    status: str
    added_count_today: int
    total_added: int
    last_used: Optional[str]
    flood_until: Optional[str]
    created_at: str


@dataclass
class ValidUser:
    """Eklenebilir kullanıcı"""
    user_id: int
    username: Optional[str]
    first_name: Optional[str]
    source_group_id: int
    times_added: int
    last_added: Optional[str]
    created_at: str


@dataclass
class BlacklistedUser:
    """Kara listedeki kullanıcı"""
    user_id: int
    reason: str
    created_at: str


@dataclass
class AddingTask:
    """Ekleme görevi"""
    id: int
    source_group_id: int
    target_group_id: int
    status: str  # pending, running, completed, failed, cancelled
    total_users: int
    added_count: int
    failed_count: int
    skipped_count: int
    started_at: Optional[str]
    completed_at: Optional[str]
    created_at: str


class DatabaseInterface(ABC):
    """Veritabanı arayüzü"""
    
    @abstractmethod
    async def initialize(self) -> None:
        """Veritabanını başlat"""
        pass
    
    # Session işlemleri
    @abstractmethod
    async def add_session(self, string_session: str, user_id: int, 
                         username: Optional[str], phone: Optional[str]) -> int:
        pass
    
    @abstractmethod
    async def get_session(self, session_id: int) -> Optional[Session]:
        pass
    
    @abstractmethod
    async def get_all_sessions(self, status: Optional[str] = None) -> List[Session]:
        pass
    
    @abstractmethod
    async def get_active_sessions(self) -> List[Session]:
        pass
    
    @abstractmethod
    async def update_session_status(self, session_id: int, status: str, 
                                   flood_until: Optional[datetime] = None) -> bool:
        pass
    
    @abstractmethod
    async def increment_session_count(self, session_id: int) -> bool:
        pass
    
    @abstractmethod
    async def reset_daily_counts(self) -> int:
        pass
    
    @abstractmethod
    async def delete_session(self, session_id: int) -> bool:
        pass
    
    # Valid users işlemleri
    @abstractmethod
    async def add_valid_user(self, user_id: int, username: Optional[str],
                            first_name: Optional[str], source_group_id: int) -> bool:
        pass
    
    @abstractmethod
    async def get_valid_users(self, limit: int = 100) -> List[ValidUser]:
        pass
    
    @abstractmethod
    async def is_valid_user(self, user_id: int) -> bool:
        pass
    
    @abstractmethod
    async def update_valid_user_added(self, user_id: int) -> bool:
        pass
    
    @abstractmethod
    async def get_valid_users_count(self) -> int:
        pass
    
    # Blacklist işlemleri
    @abstractmethod
    async def add_to_blacklist(self, user_id: int, reason: str) -> bool:
        pass
    
    @abstractmethod
    async def is_blacklisted(self, user_id: int) -> bool:
        pass
    
    @abstractmethod
    async def get_blacklist_count(self) -> int:
        pass
    
    # Task işlemleri
    @abstractmethod
    async def create_task(self, source_group_id: int, target_group_id: int,
                         total_users: int) -> int:
        pass
    
    @abstractmethod
    async def get_task(self, task_id: int) -> Optional[AddingTask]:
        pass
    
    @abstractmethod
    async def update_task_progress(self, task_id: int, added: int = 0,
                                  failed: int = 0, skipped: int = 0) -> bool:
        pass
    
    @abstractmethod
    async def complete_task(self, task_id: int, status: str) -> bool:
        pass
    
    # İstatistikler
    @abstractmethod
    async def get_stats(self) -> Dict[str, Any]:
        pass


class SQLiteDatabase(DatabaseInterface):
    """SQLite veritabanı implementasyonu"""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._lock = asyncio.Lock()
    
    @contextmanager
    def _get_connection(self):
        """Thread-safe connection context manager"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
    
    async def initialize(self) -> None:
        """Veritabanını ve tabloları oluştur"""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        
        async with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                # Sessions tablosu
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS sessions (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        string_session TEXT UNIQUE NOT NULL,
                        user_id INTEGER UNIQUE NOT NULL,
                        username TEXT,
                        phone TEXT,
                        status TEXT DEFAULT 'active',
                        added_count_today INTEGER DEFAULT 0,
                        total_added INTEGER DEFAULT 0,
                        last_used TEXT,
                        flood_until TEXT,
                        created_at TEXT DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                # Valid users tablosu
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS valid_users (
                        user_id INTEGER PRIMARY KEY,
                        username TEXT,
                        first_name TEXT,
                        source_group_id INTEGER,
                        times_added INTEGER DEFAULT 0,
                        last_added TEXT,
                        created_at TEXT DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                # Blacklist tablosu
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS blacklist (
                        user_id INTEGER PRIMARY KEY,
                        reason TEXT,
                        created_at TEXT DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                # Tasks tablosu
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS tasks (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        source_group_id INTEGER NOT NULL,
                        target_group_id INTEGER NOT NULL,
                        status TEXT DEFAULT 'pending',
                        total_users INTEGER DEFAULT 0,
                        added_count INTEGER DEFAULT 0,
                        failed_count INTEGER DEFAULT 0,
                        skipped_count INTEGER DEFAULT 0,
                        started_at TEXT,
                        completed_at TEXT,
                        created_at TEXT DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                # Added users tablosu (çakışma önleme)
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS added_users (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER NOT NULL,
                        target_group_id INTEGER NOT NULL,
                        session_id INTEGER NOT NULL,
                        added_at TEXT DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(user_id, target_group_id)
                    )
                """)
                
                # İndeksler
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_sessions_status ON sessions(status)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_valid_users_times ON valid_users(times_added)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_added_users ON added_users(user_id, target_group_id)")
    
    # ==================== SESSION İŞLEMLERİ ====================
    
    async def add_session(self, string_session: str, user_id: int,
                         username: Optional[str], phone: Optional[str]) -> int:
        async with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT OR REPLACE INTO sessions 
                    (string_session, user_id, username, phone, status, created_at)
                    VALUES (?, ?, ?, ?, 'active', ?)
                """, (string_session, user_id, username, phone, datetime.now().isoformat()))
                return cursor.lastrowid
    
    async def get_session(self, session_id: int) -> Optional[Session]:
        async with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM sessions WHERE id = ?", (session_id,))
                row = cursor.fetchone()
                if row:
                    return Session(**dict(row))
                return None
    
    async def get_all_sessions(self, status: Optional[str] = None) -> List[Session]:
        async with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                if status:
                    cursor.execute("SELECT * FROM sessions WHERE status = ?", (status,))
                else:
                    cursor.execute("SELECT * FROM sessions")
                return [Session(**dict(row)) for row in cursor.fetchall()]
    
    async def get_active_sessions(self) -> List[Session]:
        """Aktif ve flood'da olmayan session'ları getir"""
        async with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                now = datetime.now().isoformat()
                cursor.execute("""
                    SELECT * FROM sessions 
                    WHERE status = 'active' 
                    AND (flood_until IS NULL OR flood_until < ?)
                    AND added_count_today < ?
                    ORDER BY added_count_today ASC
                """, (now, config.AddingConfig.DAILY_LIMIT_PER_BOT))
                return [Session(**dict(row)) for row in cursor.fetchall()]
    
    async def update_session_status(self, session_id: int, status: str,
                                   flood_until: Optional[datetime] = None) -> bool:
        async with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                flood_str = flood_until.isoformat() if flood_until else None
                cursor.execute("""
                    UPDATE sessions SET status = ?, flood_until = ?
                    WHERE id = ?
                """, (status, flood_str, session_id))
                return cursor.rowcount > 0
    
    async def increment_session_count(self, session_id: int) -> bool:
        async with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE sessions 
                    SET added_count_today = added_count_today + 1,
                        total_added = total_added + 1,
                        last_used = ?
                    WHERE id = ?
                """, (datetime.now().isoformat(), session_id))
                return cursor.rowcount > 0
    
    async def reset_daily_counts(self) -> int:
        async with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("UPDATE sessions SET added_count_today = 0")
                return cursor.rowcount
    
    async def delete_session(self, session_id: int) -> bool:
        async with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
                return cursor.rowcount > 0
    
    # ==================== VALID USERS İŞLEMLERİ ====================
    
    async def add_valid_user(self, user_id: int, username: Optional[str],
                            first_name: Optional[str], source_group_id: int) -> bool:
        async with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                try:
                    cursor.execute("""
                        INSERT OR IGNORE INTO valid_users 
                        (user_id, username, first_name, source_group_id, created_at)
                        VALUES (?, ?, ?, ?, ?)
                    """, (user_id, username, first_name, source_group_id, 
                          datetime.now().isoformat()))
                    return cursor.rowcount > 0
                except sqlite3.IntegrityError:
                    return False
    
    async def get_valid_users(self, limit: int = 100) -> List[ValidUser]:
        async with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT * FROM valid_users 
                    ORDER BY times_added ASC, created_at DESC
                    LIMIT ?
                """, (limit,))
                return [ValidUser(**dict(row)) for row in cursor.fetchall()]
    
    async def is_valid_user(self, user_id: int) -> bool:
        async with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT 1 FROM valid_users WHERE user_id = ?", (user_id,))
                return cursor.fetchone() is not None
    
    async def update_valid_user_added(self, user_id: int) -> bool:
        async with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE valid_users 
                    SET times_added = times_added + 1, last_added = ?
                    WHERE user_id = ?
                """, (datetime.now().isoformat(), user_id))
                return cursor.rowcount > 0
    
    async def get_valid_users_count(self) -> int:
        async with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM valid_users")
                return cursor.fetchone()[0]
    
    # ==================== BLACKLIST İŞLEMLERİ ====================
    
    async def add_to_blacklist(self, user_id: int, reason: str) -> bool:
        async with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                try:
                    cursor.execute("""
                        INSERT OR IGNORE INTO blacklist (user_id, reason, created_at)
                        VALUES (?, ?, ?)
                    """, (user_id, reason, datetime.now().isoformat()))
                    # Valid users'dan da sil
                    cursor.execute("DELETE FROM valid_users WHERE user_id = ?", (user_id,))
                    return True
                except sqlite3.IntegrityError:
                    return False
    
    async def is_blacklisted(self, user_id: int) -> bool:
        async with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT 1 FROM blacklist WHERE user_id = ?", (user_id,))
                return cursor.fetchone() is not None
    
    async def get_blacklist_count(self) -> int:
        async with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM blacklist")
                return cursor.fetchone()[0]
    
    # ==================== TASK İŞLEMLERİ ====================
    
    async def create_task(self, source_group_id: int, target_group_id: int,
                         total_users: int) -> int:
        async with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO tasks (source_group_id, target_group_id, total_users, 
                                      status, started_at, created_at)
                    VALUES (?, ?, ?, 'running', ?, ?)
                """, (source_group_id, target_group_id, total_users,
                      datetime.now().isoformat(), datetime.now().isoformat()))
                return cursor.lastrowid
    
    async def get_task(self, task_id: int) -> Optional[AddingTask]:
        async with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
                row = cursor.fetchone()
                if row:
                    return AddingTask(**dict(row))
                return None
    
    async def update_task_progress(self, task_id: int, added: int = 0,
                                  failed: int = 0, skipped: int = 0) -> bool:
        async with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE tasks 
                    SET added_count = added_count + ?,
                        failed_count = failed_count + ?,
                        skipped_count = skipped_count + ?
                    WHERE id = ?
                """, (added, failed, skipped, task_id))
                return cursor.rowcount > 0
    
    async def complete_task(self, task_id: int, status: str) -> bool:
        async with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE tasks SET status = ?, completed_at = ?
                    WHERE id = ?
                """, (status, datetime.now().isoformat(), task_id))
                return cursor.rowcount > 0
    
    # ==================== ADDED USERS (ÇAKIŞMA ÖNLEME) ====================
    
    async def mark_user_added(self, user_id: int, target_group_id: int, 
                             session_id: int) -> bool:
        async with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                try:
                    cursor.execute("""
                        INSERT OR IGNORE INTO added_users 
                        (user_id, target_group_id, session_id, added_at)
                        VALUES (?, ?, ?, ?)
                    """, (user_id, target_group_id, session_id, 
                          datetime.now().isoformat()))
                    return cursor.rowcount > 0
                except sqlite3.IntegrityError:
                    return False
    
    async def is_user_added_to_group(self, user_id: int, target_group_id: int) -> bool:
        async with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT 1 FROM added_users 
                    WHERE user_id = ? AND target_group_id = ?
                """, (user_id, target_group_id))
                return cursor.fetchone() is not None
    
    # ==================== İSTATİSTİKLER ====================
    
    async def get_stats(self) -> Dict[str, Any]:
        async with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                # Session istatistikleri
                cursor.execute("SELECT COUNT(*) FROM sessions")
                total_sessions = cursor.fetchone()[0]
                
                cursor.execute("SELECT COUNT(*) FROM sessions WHERE status = 'active'")
                active_sessions = cursor.fetchone()[0]
                
                cursor.execute("""
                    SELECT COUNT(*) FROM sessions 
                    WHERE status = 'active' AND flood_until > ?
                """, (datetime.now().isoformat(),))
                paused_sessions = cursor.fetchone()[0]
                
                cursor.execute("SELECT SUM(total_added) FROM sessions")
                total_added = cursor.fetchone()[0] or 0
                
                cursor.execute("SELECT SUM(added_count_today) FROM sessions")
                added_today = cursor.fetchone()[0] or 0
                
                # User istatistikleri
                cursor.execute("SELECT COUNT(*) FROM valid_users")
                valid_users = cursor.fetchone()[0]
                
                cursor.execute("SELECT COUNT(*) FROM blacklist")
                blacklisted = cursor.fetchone()[0]
                
                return {
                    "total_sessions": total_sessions,
                    "active_sessions": active_sessions,
                    "paused_sessions": paused_sessions,
                    "inactive_sessions": total_sessions - active_sessions,
                    "total_added": total_added,
                    "added_today": added_today,
                    "valid_users": valid_users,
                    "blacklisted_users": blacklisted
                }


# MongoDB implementasyonu (opsiyonel)
class MongoDatabase(DatabaseInterface):
    """MongoDB veritabanı implementasyonu"""
    
    def __init__(self, uri: str, db_name: str):
        self.uri = uri
        self.db_name = db_name
        self.client = None
        self.db = None
    
    async def initialize(self) -> None:
        """MongoDB bağlantısını başlat"""
        try:
            from motor.motor_asyncio import AsyncIOMotorClient
            self.client = AsyncIOMotorClient(self.uri)
            self.db = self.client[self.db_name]
            
            # İndeksler oluştur
            await self.db.sessions.create_index("user_id", unique=True)
            await self.db.sessions.create_index("status")
            await self.db.valid_users.create_index("user_id", unique=True)
            await self.db.blacklist.create_index("user_id", unique=True)
            await self.db.added_users.create_index([("user_id", 1), ("target_group_id", 1)], unique=True)
        except ImportError:
            raise ImportError("MongoDB için 'motor' kütüphanesi gerekli: pip install motor")
    
    # Diğer metodlar SQLite ile benzer şekilde implement edilir
    # Kısaltma amacıyla burada gösterilmedi
    
    async def add_session(self, string_session: str, user_id: int,
                         username: Optional[str], phone: Optional[str]) -> int:
        doc = {
            "string_session": string_session,
            "user_id": user_id,
            "username": username,
            "phone": phone,
            "status": "active",
            "added_count_today": 0,
            "total_added": 0,
            "last_used": None,
            "flood_until": None,
            "created_at": datetime.now()
        }
        result = await self.db.sessions.insert_one(doc)
        return result.inserted_id
    
    async def get_session(self, session_id: int) -> Optional[Session]:
        doc = await self.db.sessions.find_one({"_id": session_id})
        if doc:
            doc["id"] = doc.pop("_id")
            return Session(**doc)
        return None
    
    async def get_all_sessions(self, status: Optional[str] = None) -> List[Session]:
        query = {"status": status} if status else {}
        cursor = self.db.sessions.find(query)
        sessions = []
        async for doc in cursor:
            doc["id"] = doc.pop("_id")
            sessions.append(Session(**doc))
        return sessions
    
    async def get_active_sessions(self) -> List[Session]:
        now = datetime.now()
        query = {
            "status": "active",
            "$or": [
                {"flood_until": None},
                {"flood_until": {"$lt": now}}
            ],
            "added_count_today": {"$lt": config.AddingConfig.DAILY_LIMIT_PER_BOT}
        }
        cursor = self.db.sessions.find(query).sort("added_count_today", 1)
        sessions = []
        async for doc in cursor:
            doc["id"] = doc.pop("_id")
            sessions.append(Session(**doc))
        return sessions
    
    async def update_session_status(self, session_id: int, status: str,
                                   flood_until: Optional[datetime] = None) -> bool:
        result = await self.db.sessions.update_one(
            {"_id": session_id},
            {"$set": {"status": status, "flood_until": flood_until}}
        )
        return result.modified_count > 0
    
    async def increment_session_count(self, session_id: int) -> bool:
        result = await self.db.sessions.update_one(
            {"_id": session_id},
            {
                "$inc": {"added_count_today": 1, "total_added": 1},
                "$set": {"last_used": datetime.now()}
            }
        )
        return result.modified_count > 0
    
    async def reset_daily_counts(self) -> int:
        result = await self.db.sessions.update_many(
            {},
            {"$set": {"added_count_today": 0}}
        )
        return result.modified_count
    
    async def delete_session(self, session_id: int) -> bool:
        result = await self.db.sessions.delete_one({"_id": session_id})
        return result.deleted_count > 0
    
    async def add_valid_user(self, user_id: int, username: Optional[str],
                            first_name: Optional[str], source_group_id: int) -> bool:
        try:
            await self.db.valid_users.insert_one({
                "user_id": user_id,
                "username": username,
                "first_name": first_name,
                "source_group_id": source_group_id,
                "times_added": 0,
                "last_added": None,
                "created_at": datetime.now()
            })
            return True
        except Exception:
            return False
    
    async def get_valid_users(self, limit: int = 100) -> List[ValidUser]:
        cursor = self.db.valid_users.find().sort("times_added", 1).limit(limit)
        users = []
        async for doc in cursor:
            users.append(ValidUser(**doc))
        return users
    
    async def is_valid_user(self, user_id: int) -> bool:
        doc = await self.db.valid_users.find_one({"user_id": user_id})
        return doc is not None
    
    async def update_valid_user_added(self, user_id: int) -> bool:
        result = await self.db.valid_users.update_one(
            {"user_id": user_id},
            {"$inc": {"times_added": 1}, "$set": {"last_added": datetime.now()}}
        )
        return result.modified_count > 0
    
    async def get_valid_users_count(self) -> int:
        return await self.db.valid_users.count_documents({})
    
    async def add_to_blacklist(self, user_id: int, reason: str) -> bool:
        try:
            await self.db.blacklist.insert_one({
                "user_id": user_id,
                "reason": reason,
                "created_at": datetime.now()
            })
            await self.db.valid_users.delete_one({"user_id": user_id})
            return True
        except Exception:
            return False
    
    async def is_blacklisted(self, user_id: int) -> bool:
        doc = await self.db.blacklist.find_one({"user_id": user_id})
        return doc is not None
    
    async def get_blacklist_count(self) -> int:
        return await self.db.blacklist.count_documents({})
    
    async def create_task(self, source_group_id: int, target_group_id: int,
                         total_users: int) -> int:
        doc = {
            "source_group_id": source_group_id,
            "target_group_id": target_group_id,
            "status": "running",
            "total_users": total_users,
            "added_count": 0,
            "failed_count": 0,
            "skipped_count": 0,
            "started_at": datetime.now(),
            "completed_at": None,
            "created_at": datetime.now()
        }
        result = await self.db.tasks.insert_one(doc)
        return result.inserted_id
    
    async def get_task(self, task_id: int) -> Optional[AddingTask]:
        doc = await self.db.tasks.find_one({"_id": task_id})
        if doc:
            doc["id"] = doc.pop("_id")
            return AddingTask(**doc)
        return None
    
    async def update_task_progress(self, task_id: int, added: int = 0,
                                  failed: int = 0, skipped: int = 0) -> bool:
        result = await self.db.tasks.update_one(
            {"_id": task_id},
            {"$inc": {"added_count": added, "failed_count": failed, "skipped_count": skipped}}
        )
        return result.modified_count > 0
    
    async def complete_task(self, task_id: int, status: str) -> bool:
        result = await self.db.tasks.update_one(
            {"_id": task_id},
            {"$set": {"status": status, "completed_at": datetime.now()}}
        )
        return result.modified_count > 0
    
    async def mark_user_added(self, user_id: int, target_group_id: int,
                             session_id: int) -> bool:
        try:
            await self.db.added_users.insert_one({
                "user_id": user_id,
                "target_group_id": target_group_id,
                "session_id": session_id,
                "added_at": datetime.now()
            })
            return True
        except Exception:
            return False
    
    async def is_user_added_to_group(self, user_id: int, target_group_id: int) -> bool:
        doc = await self.db.added_users.find_one({
            "user_id": user_id,
            "target_group_id": target_group_id
        })
        return doc is not None
    
    async def get_stats(self) -> Dict[str, Any]:
        total_sessions = await self.db.sessions.count_documents({})
        active_sessions = await self.db.sessions.count_documents({"status": "active"})
        
        now = datetime.now()
        paused_sessions = await self.db.sessions.count_documents({
            "status": "active",
            "flood_until": {"$gt": now}
        })
        
        pipeline = [{"$group": {"_id": None, "total": {"$sum": "$total_added"}}}]
        result = await self.db.sessions.aggregate(pipeline).to_list(1)
        total_added = result[0]["total"] if result else 0
        
        pipeline = [{"$group": {"_id": None, "total": {"$sum": "$added_count_today"}}}]
        result = await self.db.sessions.aggregate(pipeline).to_list(1)
        added_today = result[0]["total"] if result else 0
        
        valid_users = await self.db.valid_users.count_documents({})
        blacklisted = await self.db.blacklist.count_documents({})
        
        return {
            "total_sessions": total_sessions,
            "active_sessions": active_sessions,
            "paused_sessions": paused_sessions,
            "inactive_sessions": total_sessions - active_sessions,
            "total_added": total_added,
            "added_today": added_today,
            "valid_users": valid_users,
            "blacklisted_users": blacklisted
        }


def get_database() -> DatabaseInterface:
    """Yapılandırmaya göre veritabanı instance'ı döndür"""
    if config.DATABASE_TYPE == "mongodb":
        return MongoDatabase(config.MONGODB_URI, config.MONGODB_DB_NAME)
    else:
        return SQLiteDatabase(config.SQLITE_PATH)
