from aiogram import Bot, Dispatcher, types
from aiogram.types import ParseMode, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.utils.executor import start_webhook
from datetime import datetime, timedelta
import asyncio
import json
import os

API_TOKEN = os.getenv("API_TOKEN")
CHANNEL_ID = int(os.getenv("CHANNEL_ID"))  # Должен начинаться с -100
WEBHOOK_HOST = os.getenv("WEBHOOK_HOST")
ADMIN_ID = 8052545896

WEBHOOK_PATH = f"/webhook/{API_TOKEN}"
WEBHOOK_URL = f"{WEBHOOK_HOST}{WEBHOOK_PATH}"
WEBAPP_HOST = "0.0.0.0"
WEBAPP_PORT = int(os.getenv("PORT", default=8000))

bot = Bot(token=API_TOKEN, parse_mode=ParseMode.HTML)
dp = Dispatcher(bot)

DB_FILE = "/data/subscriptions.json"
pending_requests = {}

def load_subscriptions():
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r") as f:
            return json.load(f)
    return {}

def save_subscriptions(data):
    with open(DB_FILE, "w") as f:
        json.dump(data, f)

subscriptions = load_subscriptions()

def get_start_keyboard():
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add(types.KeyboardButton("🚀 Start"))
    return keyboard

@dp.message_handler(commands=['start'])
async def start_command(message: types.Message):
    await message.answer(
        "👋 Witaj! Kliknij przycisk poniżej, aby rozpocząć.",
        reply_markup=get_start_keyboard()
    )

@dp.message_handler(lambda message: message.text == "🚀 Start")
async def start_handler(message: types.Message):
    user_id = str(message.from_user.id)
    username = message.from_user.username or "bez username"

    if user_id in subscriptions:
        await message.answer("✅ Masz już aktywny dostęp.")
        return

    pending_requests[user_id] = username
    await message.answer("⏳ Twoja prośba została wysłana do administratora. Proszę czekać na zatwierdzenie.")

    keyboard = InlineKeyboardMarkup().add(
        InlineKeyboardButton("✅ Одобрить", callback_data=f"approve:{user_id}"),
        InlineKeyboardButton("❌ Отклонить", callback_data=f"deny:{user_id}")
    )

    await bot.send_message(
        ADMIN_ID,
        f"🔔 Запрос от пользователя:\n👤 @{username}\n🆔 <code>{user_id}</code>",
        parse_mode="HTML",
        reply_markup=keyboard
    )

@dp.callback_query_handler(lambda c: c.data.startswith("approve:") or c.data.startswith("deny:"))
async def handle_admin_action(callback: CallbackQuery):
    action, user_id = callback.data.split(":")
    username = pending_requests.get(user_id, "nieznany")

    if action == "approve":
        end_date = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")
        subscriptions[user_id] = end_date
        save_subscriptions(subscriptions)

        try:
            invite = await bot.create_chat_invite_link(
                chat_id=CHANNEL_ID,
                expire_date=int((datetime.now() + timedelta(days=1)).timestamp()),
                member_limit=1
            )
            keyboard = InlineKeyboardMarkup().add(
                InlineKeyboardButton("🔗 Dołącz do kanału", url=invite.invite_link)
            )

            await bot.send_message(int(user_id),
                                   "✅ Dostęp zatwierdzony! Kliknij przycisk poniżej, aby dołączyć do kanału:",
                                   reply_markup=keyboard)
            await bot.send_message(ADMIN_ID,
                                   f"✅ @{username} (ID: {user_id}) został zatwierdzony do {end_date}.")
        except Exception as e:
            await bot.send_message(ADMIN_ID, f"❗ Błąd przy tworzeniu linku dla {user_id}:\n<code>{e}</code>",
                                   parse_mode="HTML")
    else:
        await bot.send_message(int(user_id), "❌ Dostęp odrzucony.")
        await bot.send_message(ADMIN_ID, f"🚫 @{username} (ID: {user_id}) został odrzucony.")

    pending_requests.pop(user_id, None)
    await callback.answer()

async def check_expired():
    already_notified = set()
    while True:
        now = datetime.now().date()
        to_remove = []

        for user_id, end_str in subscriptions.items():
            try:
                end_date = datetime.strptime(end_str, "%Y-%m-%d").date()

                if end_date == now + timedelta(days=1) and user_id not in already_notified:
                    await bot.send_message(int(user_id), "⏳ Twoja subskrypcja kończy się jutro!")
                    already_notified.add(user_id)

                elif end_date <= now:
                    await bot.send_message(int(user_id), "❌ Subskrypcja wygasła. Zostałeś usunięty z kanału.")
                    await bot.kick_chat_member(chat_id=CHANNEL_ID, user_id=int(user_id))
                    await asyncio.sleep(1)
                    await bot.unban_chat_member(chat_id=CHANNEL_ID, user_id=int(user_id))
                    to_remove.append(user_id)

            except Exception as e:
                print(f"Błąd przy sprawdzaniu {user_id}: {e}")
                await bot.send_message(ADMIN_ID,
                                       f"⚠️ Błąd przy usuwaniu {user_id}:\n<code>{e}</code>",
                                       parse_mode="HTML")

        for user_id in to_remove:
            subscriptions.pop(user_id, None)

        save_subscriptions(subscriptions)
        await asyncio.sleep(86400)
        already_notified.clear()

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