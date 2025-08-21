import os
import json
import asyncio
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery, ParseMode
from aiogram.dispatcher.webhook import get_new_configured_app
import stripe
from aiohttp import web

# ====== CONFIG ======
API_TOKEN = os.getenv("API_TOKEN")
CHANNEL_ID = int(os.getenv("CHANNEL_ID"))
WEBHOOK_HOST = os.getenv("WEBHOOK_HOST")  # must start with https
WEBHOOK_PATH = f"/webhook"
WEBHOOK_URL = f"{WEBHOOK_HOST}{WEBHOOK_PATH}"
WEBAPP_HOST = "0.0.0.0"
WEBAPP_PORT = int(os.getenv("PORT", 8000))
ADMIN_LINK = "https://t.me/Alex_reng"

STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY")
STRIPE_ENDPOINT_SECRET = os.getenv("STRIPE_ENDPOINT_SECRET")
PRICE_ID = os.getenv("STRIPE_PRICE_ID")
stripe.api_key = STRIPE_SECRET_KEY

DB_FILE = "subscriptions.json"

bot = Bot(token=API_TOKEN, parse_mode=ParseMode.HTML)
dp = Dispatcher(bot)
subscriptions = {}

# ====== DATA FUNCTIONS ======
def load_subscriptions():
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r") as f:
            return json.load(f)
    return {}

def save_subscriptions(data):
    with open(DB_FILE, "w") as f:
        json.dump(data, f)

subscriptions = load_subscriptions()

# ====== STRIPE CHECKOUT ======
def create_checkout_session(user_id):
    session = stripe.checkout.Session.create(
        payment_method_types=['card'],
        line_items=[{'price': PRICE_ID, 'quantity': 1}],
        mode='payment',
        success_url=f"{WEBHOOK_HOST}/success?user_id={user_id}",
        cancel_url=f"{WEBHOOK_HOST}/cancel",
        metadata={"user_id": str(user_id)}
    )
    return session.url

# ====== START HANDLER ======
@dp.message_handler(commands=['start'])
async def start_command(message: types.Message):
    keyboard = InlineKeyboardMarkup(row_width=1).add(
        InlineKeyboardButton("💬 Skontaktuj się z administratorem", url=ADMIN_LINK),
        InlineKeyboardButton("💳 VIP na miesiąc – 159 PLN", callback_data="buy_vip")
    )
    await message.answer("Witaj! Wybierz opcję poniżej:", reply_markup=keyboard)

# ====== ОПЛАТА ======
@dp.callback_query_handler(lambda c: c.data == "buy_vip")
async def process_buy_vip(callback: CallbackQuery):
    url = create_checkout_session(callback.from_user.id)
    keyboard = InlineKeyboardMarkup().add(
        InlineKeyboardButton("🔗 Przejdź do płatności", url=url)
    )
    await callback.message.answer("Kliknij poniżej, aby zapłacić:", reply_markup=keyboard)
    await callback.answer()

# ====== STRIPE WEBHOOK ======
async def stripe_webhook(request: web.Request):
    payload = await request.read()
    sig_header = request.headers.get('stripe-signature')

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, STRIPE_ENDPOINT_SECRET)
    except stripe.error.SignatureVerificationError:
        return web.Response(status=400)

    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        user_id = session['metadata']['user_id']
        if user_id not in subscriptions:
            invite = await bot.create_chat_invite_link(
                chat_id=CHANNEL_ID,
                expire_date=int((datetime.now() + timedelta(days=1)).timestamp()),
                member_limit=1
            )
            subscriptions[user_id] = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")
            save_subscriptions(subscriptions)
            await bot.send_message(
                int(user_id),
                "✅ Opłata przyjęta! Kliknij, aby dołączyć do kanału:",
                reply_markup=InlineKeyboardMarkup().add(
                    InlineKeyboardButton("🔗 Dołącz do kanału", url=invite.invite_link)
                )
            )

    return web.Response(status=200)

# ====== ПРОВЕРКА ПОДПИСКИ ======
async def check_expired():
    notified = set()
    while True:
        now = datetime.now().date()
        to_remove = []
        for user_id, end_str in subscriptions.items():
            end_date = datetime.strptime(end_str, "%Y-%m-%d").date()
            if end_date == now + timedelta(days=1) and user_id not in notified:
                await bot.send_message(int(user_id), "⏳ Twoja subskrypcja kończy się jutro!")
                notified.add(user_id)
            elif end_date <= now:
                await bot.send_message(int(user_id), "❌ Subskrypcja wygasła. Zostałeś usunięty z kanału.")
                await bot.kick_chat_member(chat_id=CHANNEL_ID, user_id=int(user_id))
                await asyncio.sleep(1)
                await bot.unban_chat_member(chat_id=CHANNEL_ID, user_id=int(user_id))
                to_remove.append(user_id)
        for uid in to_remove:
            subscriptions.pop(uid, None)
        save_subscriptions(subscriptions)
        await asyncio.sleep(86400)
        notified.clear()

from aiogram.utils.executor import start_webhook

# ====== STARTUP & WEBHOOK ======
async def on_startup(dp):
    await bot.set_webhook(WEBHOOK_URL)
    asyncio.create_task(check_expired())

async def on_shutdown(dp):
    await bot.delete_webhook()

if __name__ == '__main__':
    app = web.Application()
    app.router.add_post("/stripe", stripe_webhook)

    start_webhook(
        dispatcher=dp,
        webhook_path=WEBHOOK_PATH,
        on_startup=on_startup,
        on_shutdown=on_shutdown,
        skip_updates=True,
        host=WEBAPP_HOST,
        port=WEBAPP_PORT,
        web_app=app
    )