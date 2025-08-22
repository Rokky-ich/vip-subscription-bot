import os
import json
import stripe
import asyncio
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types, F
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.client.default import DefaultBotProperties
from aiogram import Router

# === Конфигурация окружения ===
BOT_TOKEN = os.getenv("BOT_TOKEN")
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")
CHANNEL_ID = int(os.getenv("CHANNEL_ID"))
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

DB_FILE = "subscriptions.json"
stripe.api_key = STRIPE_SECRET_KEY

# === База подписок ===
def load_subscriptions():
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r") as f:
            return json.load(f)
    return {}

def save_subscriptions(data):
    with open(DB_FILE, "w") as f:
        json.dump(data, f)

subscriptions = load_subscriptions()

# === Инициализация бота и диспетчера ===
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher(storage=MemoryStorage())
router = Router()
dp.include_router(router)

# === Команда /start ===
@router.message(F.text == "/start")
async def start(message: types.Message):
    user_id = str(message.from_user.id)

    if user_id in subscriptions:
        await message.answer("✅ Masz już aktywną subskrypcję.")
        return

    session = stripe.checkout.Session.create(
        payment_method_types=['card'],
        line_items=[{
            'price_data': {
                'currency': 'pln',
                'product_data': {'name': 'VIP Subskrypcja'},
                'unit_amount': 500,
            },
            'quantity': 1
        }],
        mode='payment',
        success_url='https://t.me/Twoj_kanal',
        cancel_url='https://t.me/Twoj_kanal',
        metadata={'user_id': user_id}
    )

    await message.answer("💳 Kliknij w link, aby dokonać płatności:")
    await message.answer(session.url)

# === Команда /verify ===
@router.message(F.text == "/verify")
async def verify(message: types.Message):
    user_id = str(message.from_user.id)
    if user_id not in subscriptions:
        await message.answer("❌ Nie znaleziono aktywnej subskrypcji.")
        return

    try:
        invite = await bot.create_chat_invite_link(
            chat_id=CHANNEL_ID,
            expire_date=int((datetime.now() + timedelta(days=1)).timestamp()),
            member_limit=1
        )
        kb = InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="🔗 Dołącz do kanału", url=invite.invite_link)]]
        )
        await message.answer("✅ Twoja subskrypcja została potwierdzona!", reply_markup=kb)
    except Exception as e:
        await message.answer(f"❌ Błąd: {e}")

# === Задача: автоудаление по истечению подписки ===
async def check_expired():
    while True:
        now = datetime.now().date()
        expired = []

        for user_id, end in subscriptions.items():
            try:
                if datetime.strptime(end, "%Y-%m-%d").date() <= now:
                    await bot.ban_chat_member(CHANNEL_ID, int(user_id))
                    await bot.unban_chat_member(CHANNEL_ID, int(user_id))
                    expired.append(user_id)
            except Exception as e:
                await bot.send_message(ADMIN_ID, f"❗ Błąd usuwania {user_id}: {e}")

        for user_id in expired:
            subscriptions.pop(user_id)
        save_subscriptions(subscriptions)
        await asyncio.sleep(86400)

# === Запуск через polling ===
async def main():
    asyncio.create_task(check_expired())
    await dp.start_polling(bot)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
