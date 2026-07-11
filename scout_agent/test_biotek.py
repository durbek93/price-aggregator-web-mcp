import asyncio
import os
import sys

sys.path.insert(0, '/home/ubuntu/price-aggregator-web/scout_agent')
import config
from pyrogram import Client

async def main():
    print("Starting client...")
    app = Client(
        "scout_agent",
        api_id=config.TELEGRAM_API_ID,
        api_hash=config.TELEGRAM_API_HASH,
        phone_number=config.TELEGRAM_PHONE,
        password=config.TELEGRAM_PASSWORD,
        workdir="/app"
    )
    await app.start()
    print("Client started.")
    try:
        chat_id = -1003861704035
        chat = await app.get_chat(chat_id)
        print(f"Chat ID: {chat.id} | Title: {chat.title}")
        async for message in app.get_chat_history(chat_id, limit=30):
            if message.document:
                print(f"Msg ID: {message.id} | Date: {message.date} | File: {message.document.file_name} | Size: {message.document.file_size} | Caption: {message.caption}")
    except Exception as e:
        print("Error during fetch:", e)
    await app.stop()
    print("Client stopped.")

if __name__ == "__main__":
    asyncio.run(main())
