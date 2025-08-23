import asyncio
import json
import os
from datetime import datetime, timedelta

import stripe
from aiohttp import web
from aiogram import Bot, Dispatcher, types, F
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

API_TOKEN = os.getenv("API_TOKEN")
CHANNEL_ID = int(os.getenv("CHANNEL_ID"))
WEBHOOK_HOST = os.getenv("WEBHOOK_HOST")
ADMIN_ID = 2119400801

STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")
stripe.api_key = STRIPE_SECRET_KEY

WEBHOOK_PATH = f"/webhook/{API_TOKEN}"
STRIPE_WEBHOOK_PATH = "/webhook/stripe"
WEBHOOK_URL = f"{WEBHOOK_HOST}{WEBHOOK_PATH}"
WEBAPP_HOST = "0.0.0.0"
WEBAPP_PORT = int(os.getenv("PORT", default=8000))

bot = Bot(token=API_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

DB_FILE = "/data/subscriptions.json"

# === Работа с локальной базой ===
def load_subscriptions():
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r") as f:
            return json.load(f)
    return {}

def save_subscriptions(data):
    with open(DB_FILE, "w") as f:
        json.dump(data, f)

subscriptions = load_subscriptions()

# === Stripe — создание индивидуальной сессии ===
async def create_checkout_session(user_id: int):
    try:
        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=[{
                "price_data": {
                    "currency": "pln",
                    "product_data": {"name": "Dostęp do kanału VIP"},
                    "unit_amount": 500,  # 5 PLN
                },
                "quantity": 1,
            }],
            mode="payment",
            success_url="https://t.me/TwojBot?start=success",
            cancel_url="https://t.me/TwojBot?start=cancel",
            metadata={"user_id": str(user_id)}
        )
        return session.url
    except Exception as e:
        print(f"Stripe error: {e}")
        return None

# === Команда /start ===
@dp.message(F.text == "/start")
async def cmd_start(message: types.Message):
    keyboard = InlineKeyboardMarkup(row_width=1).add(
        InlineKeyboardButton("📞 Kontakt z administratorem", url="https://t.me/wawaadmin"),
        InlineKeyboardButton("💳 Link do płatności", callback_data="pay")
    )
    await message.answer(
        "👋 Cześć! Kliknij przycisk poniżej, aby uzyskać dostęp:",
        reply_markup=keyboard
    )

# === Обработка кнопки "Оплатить" ===
@dp.callback_query(F.data == "pay")
async def handle_payment(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    payment_url = await create_checkout_session(user_id)

    if payment_url:
        await callback.message.answer(
            "💳 Kliknij poniżej, aby przejść do płatności:",
            reply_markup=InlineKeyboardMarkup().add(
                InlineKeyboardButton("🔗 Zapłać teraz", url=payment_url)
            )
        )
    else:
        await callback.message.answer("❌ Błąd podczas generowania linku do płatności.")
    await callback.answer()

# === Stripe Webhook — автоматическая проверка оплаты ===
async def stripe_webhook(request):
    payload = await request.read()
    sig_header = request.headers.get("Stripe-Signature")

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, STRIPE_WEBHOOK_SECRET
        )
    except stripe.error.SignatureVerificationError:
        return web.Response(status=400)

    # Оплата прошла успешно
    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        user_id = session.get("metadata", {}).get("user_id")

        if user_id:
            end_date = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")
            subscriptions[user_id] = end_date
            save_subscriptions(subscriptions)

            try:
                invite = await bot.create_chat_invite_link(
                    chat_id=CHANNEL_ID,
                    expire_date=int((datetime.now() + timedelta(days=1)).timestamp()),
                    member_limit=1
                )
                await bot.send_message(
                    int(user_id),
                    "✅ Płatność potwierdzona! Kliknij poniżej, aby dołączyć do kanału:",
                    reply_markup=InlineKeyboardMarkup().add(
                        InlineKeyboardButton("🔗 Dołącz do kanału", url=invite.invite_link)
                    )
                )
            except Exception as e:
                await bot.send_message(
                    ADMIN_ID,
                    f"⚠️ Błąd przy wysyłaniu linku użytkownikowi {user_id}:\n<code>{e}</code>"
                )
    return web.Response(status=200)

# === Проверка окончания подписок ===
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
                    await bot.send_message(int(user_id), "❌ Twoja subskrypcja wygasła. Zostałeś usunięty z kanału.")
                    await bot.ban_chat_member(CHANNEL_ID, int(user_id))
                    await asyncio.sleep(1)
                    await bot.unban_chat_member(CHANNEL_ID, int(user_id))
                    to_remove.append(user_id)

            except Exception as e:
                await bot.send_message(
                    ADMIN_ID,
                    f"⚠️ Błąd przy usuwaniu {user_id}:\n<code>{e}</code>"
                )

        for user_id in to_remove:
            subscriptions.pop(user_id, None)

        save_subscriptions(subscriptions)
        await asyncio.sleep(86400)
        already_notified.clear()

# === Запуск вебхуков ===
def setup_web_app():
    app = web.Application()
    app.router.add_post(STRIPE_WEBHOOK_PATH, stripe_webhook)
    return app

async def on_startup():
    await bot.set_webhook(WEBHOOK_URL)
    asyncio.create_task(check_expired())

async def on_shutdown():
    await bot.delete_webhook()

if __name__ == "__main__":
    async def main():
        await on_startup()
        runner = web.AppRunner(setup_web_app())
        await runner.setup()
        site = web.TCPSite(runner, WEBAPP_HOST, WEBAPP_PORT)
        await site.start()
        await dp.start_polling(bot)

    asyncio.run(main())