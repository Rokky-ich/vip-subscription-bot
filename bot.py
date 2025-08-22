import os
import json
import stripe
import asyncio
from datetime import datetime, timedelta
from aiohttp import web
from aiogram import Bot, Dispatcher, types, F
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiogram.client.default import DefaultBotProperties
from aiogram import Router
from aiogram.filters import Command

# === Конфигурация окружения ===
BOT_TOKEN = os.getenv("BOT_TOKEN")
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")
WEBHOOK_HOST = os.getenv("WEBHOOK_HOST")
CHANNEL_ID = int(os.getenv("CHANNEL_ID"))
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

WEBHOOK_PATH = f"/webhook/{BOT_TOKEN}"
WEBHOOK_URL = f"{WEBHOOK_HOST}{WEBHOOK_PATH}"
WEBAPP_HOST = "0.0.0.0"
WEBAPP_PORT = int(os.getenv("PORT", 8000))

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
@router.message(Command("start"))
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
@router.message(Command("verify"))
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

# === Stripe Webhook ===
async def stripe_webhook(request):
    payload = await request.read()
    sig_header = request.headers.get("stripe-signature")

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
    except Exception as e:
        print("❌ Stripe webhook error:", e)
        return web.Response(status=400)

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        user_id = session.get("metadata", {}).get("user_id")
        if user_id:
            user_id = str(user_id)
            if user_id not in subscriptions:
                subscriptions[user_id] = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")
                save_subscriptions(subscriptions)

                try:
                    invite = await bot.create_chat_invite_link(
                        chat_id=CHANNEL_ID,
                        expire_date=int((datetime.now() + timedelta(days=1)).timestamp()),
                        member_limit=1
                    )
                    kb = InlineKeyboardMarkup(
                        inline_keyboard=[[InlineKeyboardButton(text="🔗 Dołącz do kanału", url=invite.invite_link)]]
                    )
                    await bot.send_message(user_id, "✅ Płatność potwierdzona! Kliknij, aby dołączyć do kanału:", reply_markup=kb)
                except Exception as e:
                    await bot.send_message(ADMIN_ID, f"❌ Błąd zaproszenia: {e}")

    return web.Response(status=200)

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

# === Webhook startup/shutdown ===
async def on_startup(bot: Bot):
    await bot.set_webhook(WEBHOOK_URL)
    asyncio.create_task(check_expired())

async def on_shutdown(bot: Bot):
    await bot.delete_webhook()

# === Запуск приложения ===
app = web.Application()
app.router.add_post("/stripe_webhook", stripe_webhook)

SimpleRequestHandler(dispatcher=dp, bot=bot).register(app, path=WEBHOOK_PATH)
setup_application(app, dp, bot=bot, on_startup=on_startup, on_shutdown=on_shutdown)

if __name__ == "__main__":
    web.run_app(app, host=WEBAPP_HOST, port=WEBAPP_PORT)