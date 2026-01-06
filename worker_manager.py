"""
Worker Yonetim Araci
====================
Spam yiyen veya devre disi kalan worker'lari yonetmek icin.

Kullanim:
    python worker_manager.py
"""

import asyncio
import sys
import os

# Windows icin
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import sqlite3
from datetime import datetime

DB_PATH = "data/member_adder.db"


def get_connection():
    """Veritabani baglantisi"""
    if not os.path.exists(DB_PATH):
        print(f"[HATA] Veritabani bulunamadi: {DB_PATH}")
        sys.exit(1)
    return sqlite3.connect(DB_PATH)


def list_sessions():
    """Tum session'lari listele"""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT id, user_id, username, status, added_count_today, 
               total_added, flood_until, created_at
        FROM sessions
    """)
    
    rows = cursor.fetchall()
    conn.close()
    
    if not rows:
        print("\n[!] Kayitli session yok.\n")
        return
    
    print("\n" + "=" * 70)
    print("KAYITLI SESSION'LAR")
    print("=" * 70)
    
    for row in rows:
        id, user_id, username, status, today, total, flood, created = row
        
        status_icon = {
            "active": "[AKTIF]",
            "paused": "[BEKLEMEDE]",
            "banned": "[YASAKLI]",
            "deactivated": "[DEVRE DISI]",
            "error": "[HATA]"
        }.get(status, f"[{status}]")
        
        print(f"\nID: {id}")
        print(f"  Kullanici: @{username or user_id}")
        print(f"  Durum: {status_icon}")
        print(f"  Bugun/Toplam: {today}/{total}")
        if flood:
            print(f"  Flood Suresi: {flood}")
        print(f"  Olusturulma: {created}")
    
    print("\n" + "=" * 70)


def reset_session(session_id: int):
    """Session'i aktif yap ve sayaclari sifirla"""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        UPDATE sessions 
        SET status = 'active', 
            flood_until = NULL,
            added_count_today = 0
        WHERE id = ?
    """, (session_id,))
    
    if cursor.rowcount > 0:
        conn.commit()
        print(f"\n[OK] Session {session_id} sifirlandi ve aktif yapildi.\n")
    else:
        print(f"\n[HATA] Session {session_id} bulunamadi.\n")
    
    conn.close()


def reset_all_sessions():
    """Tum session'lari sifirla"""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        UPDATE sessions 
        SET status = 'active', 
            flood_until = NULL,
            added_count_today = 0
    """)
    
    count = cursor.rowcount
    conn.commit()
    conn.close()
    
    print(f"\n[OK] {count} session sifirlandi.\n")


def delete_session(session_id: int):
    """Session'i sil"""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
    
    if cursor.rowcount > 0:
        conn.commit()
        print(f"\n[OK] Session {session_id} silindi.\n")
    else:
        print(f"\n[HATA] Session {session_id} bulunamadi.\n")
    
    conn.close()


def show_stats():
    """Istatistikleri goster"""
    conn = get_connection()
    cursor = conn.cursor()
    
    # Session sayilari
    cursor.execute("SELECT COUNT(*) FROM sessions")
    total = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM sessions WHERE status = 'active'")
    active = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM sessions WHERE status = 'paused'")
    paused = cursor.fetchone()[0]
    
    # Valid users
    cursor.execute("SELECT COUNT(*) FROM valid_users")
    valid = cursor.fetchone()[0]
    
    # Blacklist
    cursor.execute("SELECT COUNT(*) FROM blacklist")
    blacklist = cursor.fetchone()[0]
    
    # Toplam eklenen
    cursor.execute("SELECT SUM(total_added) FROM sessions")
    total_added = cursor.fetchone()[0] or 0
    
    conn.close()
    
    print("\n" + "=" * 40)
    print("ISTATISTIKLER")
    print("=" * 40)
    print(f"Toplam Session: {total}")
    print(f"  - Aktif: {active}")
    print(f"  - Beklemede: {paused}")
    print(f"  - Diger: {total - active - paused}")
    print(f"\nValid Users: {valid}")
    print(f"Blacklist: {blacklist}")
    print(f"Toplam Eklenen: {total_added}")
    print("=" * 40 + "\n")


def clear_blacklist():
    """Kara listeyi temizle"""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("DELETE FROM blacklist")
    count = cursor.rowcount
    conn.commit()
    conn.close()
    
    print(f"\n[OK] {count} kullanici kara listeden silindi.\n")


def main_menu():
    """Ana menu"""
    while True:
        print("\n" + "=" * 40)
        print("WORKER YONETIM ARACI")
        print("=" * 40)
        print("1. Session'lari listele")
        print("2. Bir session'i sifirla (aktif yap)")
        print("3. Tum session'lari sifirla")
        print("4. Bir session'i sil")
        print("5. Istatistikleri goster")
        print("6. Kara listeyi temizle")
        print("0. Cikis")
        print("=" * 40)
        
        choice = input("\nSeciminiz: ").strip()
        
        if choice == "1":
            list_sessions()
        
        elif choice == "2":
            list_sessions()
            try:
                sid = int(input("Sifirlanacak Session ID: "))
                reset_session(sid)
            except ValueError:
                print("[HATA] Gecersiz ID")
        
        elif choice == "3":
            confirm = input("Tum session'lar sifirlanacak. Emin misiniz? (e/h): ")
            if confirm.lower() == 'e':
                reset_all_sessions()
        
        elif choice == "4":
            list_sessions()
            try:
                sid = int(input("Silinecek Session ID: "))
                confirm = input(f"Session {sid} silinecek. Emin misiniz? (e/h): ")
                if confirm.lower() == 'e':
                    delete_session(sid)
            except ValueError:
                print("[HATA] Gecersiz ID")
        
        elif choice == "5":
            show_stats()
        
        elif choice == "6":
            confirm = input("Kara liste temizlenecek. Emin misiniz? (e/h): ")
            if confirm.lower() == 'e':
                clear_blacklist()
        
        elif choice == "0":
            print("\nCikis yapiliyor...\n")
            break
        
        else:
            print("[HATA] Gecersiz secim")


if __name__ == "__main__":
    main_menu()
