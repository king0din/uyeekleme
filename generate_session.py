"""
StringSession Oluşturucu
========================
Bu script ile userbot hesaplarınızın StringSession'larını oluşturabilirsiniz.
"""

import asyncio
from pyrogram import Client

# config.py'den API bilgilerini al
try:
    import config
    API_ID = config.API_ID
    API_HASH = config.API_HASH
except ImportError:
    API_ID = int(input("API_ID: "))
    API_HASH = input("API_HASH: ")


async def main():
    print("=" * 50)
    print("StringSession Oluşturucu")
    print("=" * 50)
    print()
    
    # API bilgileri kontrolü
    if API_ID == 12345678 or API_HASH == "your_api_hash_here":
        print("⚠️  Lütfen config.py'de API_ID ve API_HASH ayarlayın")
        print("    veya aşağıya manuel girin:")
        API_ID = int(input("API_ID: "))
        API_HASH = input("API_HASH: ")
    
    print()
    print("Telegram'a giriş yapılacak...")
    print("Telefon numaranızı uluslararası formatta girin (örn: +905551234567)")
    print()
    
    async with Client(
        name="session_generator",
        api_id=API_ID,
        api_hash=API_HASH,
        in_memory=True
    ) as client:
        # Kullanıcı bilgilerini al
        me = await client.get_me()
        
        # StringSession'ı al
        string_session = await client.export_session_string()
        
        print()
        print("=" * 50)
        print("✅ BAŞARILI!")
        print("=" * 50)
        print()
        print(f"👤 Hesap: {me.first_name} (@{me.username or me.id})")
        print(f"📱 Telefon: {me.phone_number}")
        print()
        print("📋 StringSession:")
        print("-" * 50)
        print(string_session)
        print("-" * 50)
        print()
        print("⚠️  Bu session'ı güvenli bir yerde saklayın!")
        print("    Başkalarıyla paylaşmayın!")
        print()
        print("Botu kullanmak için:")
        print(f"  /session {string_session[:20]}...")
        print("  veya")
        print(f"  .session {string_session[:20]}...")


if __name__ == "__main__":
    asyncio.run(main())
