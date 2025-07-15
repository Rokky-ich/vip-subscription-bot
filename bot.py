
from aiogram import Bot, Dispatcher, types
from aiogram.utils import executor
from datetime import datetime, timedelta
import asyncio
import json
import os

API_TOKEN = os.getenv("API_TOKEN")
CHANNEL_ID = int(os.getenv("CHANNEL_ID"))

bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot)

DB_FILE = "subscriptions.json"

def load_subscriptions():
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r") as f:
            return json.load(f)
    return {}

def save_subscriptions(data):
    with open(DB_FILE, "w") as f:
        json.dump(data, f)

subscriptions = load_subscriptions()

@dp.message_handler(commands=['start'])
async def send_welcome(message: types.Message):
    await message.reply("Привет! Я бот для подписок. Используй /add @username 7")

@dp.message_handler(commands=['add'])
async def add_subscription(message: types.Message):
    try:
        _, username, days = message.text.split()
        days = int(days)
        user_id = username.strip('@')
        end_date = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d")
        subscriptions[user_id] = end_date
        save_subscriptions(subscriptions)
        await message.reply(f"@{user_id} добавлен до {end_date}")
    except:
        await message.reply("❗ Используй команду так: /add @username 7")

async def check_expired():
    while True:
        now = datetime.now().date()
        to_remove = []
        for user, end_str in subscriptions.items():
            end_date = datetime.strptime(end_str, "%Y-%m-%d").date()
            if end_date == now + timedelta(days=1):
                try:
                    await bot.send_message(f"@{user}", "⏳ Завтра заканчивается твоя подписка!")
                except:
                    pass
            elif end_date <= now:
                try:
                    await bot.send_message(f"@{user}", "❌ Твоя подписка закончилась. Ты удалён из канала.")
                    to_remove.append(user)
                except:
                    pass
        for user in to_remove:
            subscriptions.pop(user, None)
        save_subscriptions(subscriptions)
        await asyncio.sleep(86400)  # Проверка раз в сутки

async def on_startup(_):
    asyncio.create_task(check_expired())

if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True, on_startup=on_startup)
