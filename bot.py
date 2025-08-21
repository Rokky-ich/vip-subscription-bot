import os
import stripe
import asyncio
import json
from datetime import datetime, timedelta
from aiohttp import web
from aiogram import Bot, Dispatcher, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.executor import start_webhook

# === Настройки окружения ===
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHANNEL_ID = int(os.getenv("CHANNEL_ID"))
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")
WEBHOOK_HOST = os.getenv("WEBHOOK_HOST")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

WEBHOOK_PATH = f"/webhook/{BOT_TOKEN}"
WEBHOOK_URL = f"{WEBHOOK_HOST}{WEBHOOK_PATH}"
WEBAPP_HOST = "0.0.0.0"
WEBAPP_PORT = int(os.getenv("PORT", 8000))

stripe.api_key = STRIPE_SECRET_KEY

# === Инициализация бота ===
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)

# === Файл базы данных ===
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

# === Команда /start ===
@dp.message_handler(commands=["start"])
async def cmd_start(message: types.Message):
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
        success_url='https://t.me/Twoj_kanal',  # Можно оставить, не используется
        cancel_url='https://t.me/Twoj_kanal',
        metadata={'user_id': user_id}
    )

    await message.answer("💳 Kliknij w link, aby dokonać płatności:")
    await message.answer(session.url)

# === Команда /verify (для ручной проверки) ===
@dp.message_handler(commands=["verify"])
async def cmd_verify(message: types.Message):
    user_id = str(message.from_user.id)

    if user_id in subscriptions:
        try:
            invite = await bot.create_chat_invite_link(
                chat_id=CHANNEL_ID,
                expire_date=int((datetime.now() + timedelta(days=1)).timestamp()),
                member_limit=1
            )
            keyboard = InlineKeyboardMarkup().add(
                InlineKeyboardButton("🔗 Dołącz do kanału", url=invite.invite_link)
            )
            await message.answer("✅ Twoja subskrypcja została potwierdzona!", reply_markup=keyboard)
        except Exception as e:
            await message.answer(f"❌ Błąd: {e}")
    else:
        await message.answer("❌ Nie znaleziono aktywnej subskrypcji.")

# === Stripe Webhook ===
async def stripe_webhook(request):
    payload = await request.read()
    sig_header = request.headers.get("stripe-signature")

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
    except Exception as e:
        print("❌ Webhook error:", str(e))
        return web.Response(status=400)

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        print("✅ Получена сессия Stripe:", session)  # логируем весь объект

        metadata = session.get("metadata", {})
        user_id = metadata.get("user_id")

        if not user_id:
            print("⚠️ user_id отсутствует в metadata!")
            return web.Response(status=200)

        user_id = str(user_id)  # гарантируем строковый формат

        if user_id not in subscriptions:
            subscriptions[user_id] = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")
            save_subscriptions(subscriptions)
            print(f"✅ Подписка добавлена для {user_id}")

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
                    "✅ Płatność potwierdzona! Kliknij poniżej, aby dołączyć do kanału:",
                    reply_markup=keyboard)
            except Exception as e:
                print(f"❌ Ошибка отправки ссылки пользователю {user_id}: {e}")
                await bot.send_message(ADMIN_ID, f"❌ Błąd zaproszenia: {e}")

    return web.Response(status=200)

# === Проверка истекших подписок ===
async def check_expired():
    while True:
        now = datetime.now().date()
        expired = []

        for user_id, end in subscriptions.items():
            try:
                if datetime.strptime(end, "%Y-%m-%d").date() <= now:
                    await bot.kick_chat_member(CHANNEL_ID, int(user_id))
                    await asyncio.sleep(1)
                    await bot.unban_chat_member(CHANNEL_ID, int(user_id))
                    expired.append(user_id)
            except Exception as e:
                await bot.send_message(ADMIN_ID, f"❗Błąd usuwania {user_id}: {e}")

        for user_id in expired:
            subscriptions.pop(user_id)
        save_subscriptions(subscriptions)

        await asyncio.sleep(86400)

# === Стартовые события ===
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

async def on_startup(app):
    await bot.set_webhook(WEBHOOK_URL)
    asyncio.create_task(check_expired())

async def on_shutdown(app):
    await bot.delete_webhook()

if __name__ == "__main__":
    app = web.Application()
    app.on_startup.append(on_startup)
    app.on_shutdown.append(on_shutdown)

    # Stripe Webhook
    app.router.add_post("/stripe_webhook", stripe_webhook)

    # Telegram Webhook
    SimpleRequestHandler(dispatcher=dp, bot=bot).register(app, path=WEBHOOK_PATH)

    # Запуск aiohttp сервера
    web.run_app(app, host=WEBAPP_HOST, port=WEBAPP_PORT)

