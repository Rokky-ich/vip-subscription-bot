from aiogram import Bot, Dispatcher, types
from aiogram.types import ParseMode
from aiogram.utils.executor import start_webhook
from datetime import datetime, timedelta
import asyncio
import json
import os

API_TOKEN = os.getenv("API_TOKEN")
CHANNEL_ID = int(os.getenv("CHANNEL_ID"))  # Должен начинаться с -100
WEBHOOK_HOST = os.getenv("WEBHOOK_HOST")
CHANNEL_LINK = os.getenv("CHANNEL_LINK")

ADMIN_ID = 1279721354  # Твой Telegram user ID

WEBHOOK_PATH = f"/webhook/{API_TOKEN}"
WEBHOOK_URL = f"{WEBHOOK_HOST}{WEBHOOK_PATH}"
WEBAPP_HOST = "0.0.0.0"
WEBAPP_PORT = int(os.getenv("PORT", default=8000))

bot = Bot(token=API_TOKEN, parse_mode=ParseMode.HTML)
dp = Dispatcher(bot)

DB_FILE = "/data/subscriptions.json"

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

    # Срок подписки — 2 дня
    end_date = (datetime.now() + timedelta(days=2)).strftime("%Y-%m-%d")
    subscriptions[str(user_id)] = end_date
    save_subscriptions(subscriptions)

    # Отправка ссылки пользователю
    await message.answer(
        f"✅ Привет, @{username}!\n"
        f"Ты получил доступ на <b>2 дня</b>.\n\n"
        f"🔗 <b>Ссылка на канал:</b>\n{CHANNEL_LINK}",
        parse_mode="HTML"
    )

    # Уведомление админу
    await bot.send_message(
        chat_id=ADMIN_ID,
        text=f"👤 @{username} (ID: <code>{user_id}</code>) получил доступ до <b>{end_date}</b>",
        parse_mode="HTML"
    )

@dp.message_handler(commands=['add'])  # Опционально
async def add_subscription(message: types.Message):
    try:
        _, id_or_username, days = message.text.split()
        days = int(days)
        user_key = id_or_username.strip("@")
        end_date = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d")
        subscriptions[user_key] = end_date
        save_subscriptions(subscriptions)
        await message.reply(f"{id_or_username} добавлен до {end_date}")
    except Exception as e:
        await message.reply(f"❗ Ошибка: {e}\nИспользуй: /add <id> <дней>")

async def check_expired():
    while True:
        now = datetime.now().date()
        to_remove = []

        for user_id, end_str in subscriptions.items():
            try:
                end_date = datetime.strptime(end_str, "%Y-%m-%d").date()

                if end_date == now + timedelta(days=1):
                    await bot.send_message(int(user_id), "⏳ Завтра заканчивается твоя подписка!")

                elif end_date <= now:
                    await bot.send_message(int(user_id), "❌ Подписка истекла. Ты удалён из канала.")
                    await bot.kick_chat_member(chat_id=CHANNEL_ID, user_id=int(user_id))
                    await asyncio.sleep(1)
                    await bot.unban_chat_member(chat_id=CHANNEL_ID, user_id=int(user_id))  # Чтобы мог вернуться
                    to_remove.append(user_id)

            except Exception as e:
                print(f"[❌] Ошибка при проверке {user_id}: {e}")
                await bot.send_message(ADMIN_ID, f"⚠️ Ошибка удаления {user_id}:\n<code>{e}</code>", parse_mode="HTML")

        for user_id in to_remove:
            subscriptions.pop(user_id, None)

        save_subscriptions(subscriptions)
        await asyncio.sleep(3600)  # Проверка раз в час

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
