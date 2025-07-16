from aiogram import Bot, Dispatcher, types
from aiogram.types import ParseMode
from aiogram.utils.executor import start_webhook
from datetime import datetime, timedelta
import asyncio
import json
import os

API_TOKEN = os.getenv("API_TOKEN")
CHANNEL_ID = int(os.getenv("CHANNEL_ID"))  # должен начинаться с -100
WEBHOOK_HOST = os.getenv("WEBHOOK_HOST")
CHANNEL_LINK = os.getenv("CHANNEL_LINK")

WEBHOOK_PATH = f"/webhook/{API_TOKEN}"
WEBHOOK_URL = f"{WEBHOOK_HOST}{WEBHOOK_PATH}"
WEBAPP_HOST = "0.0.0.0"
WEBAPP_PORT = int(os.getenv("PORT", default=8000))

bot = Bot(token=API_TOKEN, parse_mode=ParseMode.HTML)
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
async def start_handler(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username or "без username"

    # Установка подписки на 2 дня
    end_date = (datetime.now() + timedelta(days=2)).strftime("%Y-%m-%d")
    subscriptions[str(user_id)] = end_date
    save_subscriptions(subscriptions)

    # Отправка ссылки пользователю
    await message.answer(
        f"✅ Привет, @{username or 'друг'}!\n"
        f"Ты получил доступ на 2 дня.\n\n"
        f"🔗 <b>Вот ссылка на канал:</b>\n{CHANNEL_LINK}",
        parse_mode="HTML"
    )

    # Уведомление админу
    await bot.send_message(
        chat_id=message.from_user.id,
        text=f"🔔 Выдан доступ до <b>{end_date}</b>",
        parse_mode="HTML"
    )

@dp.message_handler(commands=['add'])  # опционально, можно удалить если не нужно вручную
async def add_subscription(message: types.Message):
    try:
        _, id_or_username, days = message.text.split()
        days = int(days)
        user_key = id_or_username.strip("@")
        end_date = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d")
        subscriptions[user_key] = end_date
        save_subscriptions(subscriptions)
        await message.reply(f"{id_or_username} добавлен до {end_date}")
    except:
        await message.reply("❗ Используй: /add <id> <дней>")

async def check_expired():
    while True:
        now = datetime.now().date()
        to_remove = []
        for user_id, end_str in subscriptions.items():
            end_date = datetime.strptime(end_str, "%Y-%m-%d").date()

            if end_date == now + timedelta(days=1):
                try:
                    await bot.send_message(int(user_id), "⏳ Завтра заканчивается твоя подписка!")
                except:
                    pass

            elif end_date <= now:
                try:
                    await bot.send_message(int(user_id), "❌ Подписка истекла. Ты удалён из канала.")
                    await bot.kick_chat_member(chat_id=CHANNEL_ID, user_id=int(user_id))
                    await asyncio.sleep(1)
                    await bot.unban_chat_member(chat_id=CHANNEL_ID, user_id=int(user_id))  # Чтобы мог зайти снова
                    to_remove.append(user_id)
                except:
                    pass

        for user_id in to_remove:
            subscriptions.pop(user_id, None)

        save_subscriptions(subscriptions)
        await asyncio.sleep(86400)

async def on_startup(dp):
    await bot.set_webhook(WEBHOOK_URL)
    asyncio.create_task(check_expired())

async def on_shutdown(dp):
    await bot.delete_webhook()

if __name__ == '__main__':
    start_webhook(
        dispatcher=dp,
        webhook_path=WEBHOOK_PATH,
        on_startup=on_startup,
        on_shutdown=on_shutdown,
        skip_updates=True,
        host=WEBAPP_HOST,
        port=WEBAPP_PORT,
    )
