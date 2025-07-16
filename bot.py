from aiogram import Bot, Dispatcher, types
from aiogram.types import ParseMode
from aiogram.utils.executor import start_webhook
from datetime import datetime, timedelta
import asyncio
import json
import os

API_TOKEN = os.getenv("API_TOKEN")
CHANNEL_ID = int(os.getenv("CHANNEL_ID"))
WEBHOOK_HOST = os.getenv("WEBHOOK_HOST")  # Пример: https://your-app.onrender.com

WEBHOOK_PATH = f"/webhook/{API_TOKEN}"
WEBHOOK_URL = f"{WEBHOOK_HOST}{WEBHOOK_PATH}"

WEBAPP_HOST = "0.0.0.0"
WEBAPP_PORT = int(os.getenv("PORT", default=8000))

bot = Bot(token=API_TOKEN, parse_mode=ParseMode.HTML)
dp = Dispatcher(bot)

# Укажи здесь свой Telegram user ID
ADMIN_ID = 1279721354  # например: 123456789

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
    user_id = message.from_user.id
    username = message.from_user.username or "без username"
    await message.reply("Привет! Я бот для подписок. Используй /add @username 7")

    # Уведомление админу
    await bot.send_message(
        ADMIN_ID,
        f"🔔 Новый пользователь нажал /start:\n👤 Username: @{username}\n🆔 ID: <code>{user_id}</code>",
        parse_mode="HTML"
    )

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
        await asyncio.sleep(86400)

async def on_startup(dp):
    await bot.set_webhook(WEBHOOK_URL)
    asyncio.create_task(check_expired())

async def on_shutdown(dp):
    await bot.delete_webhook()

if __name__ == '__main__':
    from aiogram.dispatcher.webhook import get_new_configured_app
    start_webhook(
        dispatcher=dp,
        webhook_path=WEBHOOK_PATH,
        on_startup=on_startup,
        on_shutdown=on_shutdown,
        skip_updates=True,
        host=WEBAPP_HOST,
        port=WEBAPP_PORT,
    )
