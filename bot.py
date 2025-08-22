from aiogram import Bot, Dispatcher, types
from aiogram.types import ParseMode, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.utils import executor
from datetime import datetime, timedelta
import stripe
import asyncio
import json
import os

API_TOKEN = os.getenv("API_TOKEN")
CHANNEL_ID = int(os.getenv("CHANNEL_ID"))  # должен начинаться с -100
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY")
ADMIN_ID = int(os.getenv("ADMIN_ID"))

bot = Bot(token=API_TOKEN, parse_mode=ParseMode.HTML)
dp = Dispatcher(bot)
stripe.api_key = STRIPE_SECRET_KEY

DB_FILE = "subscriptions.json"
pending_payments = {}

# Функции для хранения подписок
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
    await message.answer("👋 Witaj! Kliknij przycisk poniżej, aby rozpocząć.", reply_markup=get_start_keyboard())

@dp.message_handler(lambda message: message.text == "🚀 Start")
async def start_handler(message: types.Message):
    user_id = str(message.from_user.id)

    if user_id in subscriptions:
        await message.answer("✅ Masz już aktywny dostęp.")
        return

    session = stripe.checkout.Session.create(
        payment_method_types=['card'],
        line_items=[{
            'price_data': {
                'currency': 'pln',
                'product_data': {
                    'name': 'Dostęp do kanału Telegram',
                },
                'unit_amount': 20000,  # 200.00 PLN
            },
            'quantity': 1,
        }],
        mode='payment',
        success_url='https://t.me/TwojBot?start=paid',
        cancel_url='https://t.me/TwojBot?start=cancel',
        metadata={'user_id': user_id}
    )

    pending_payments[user_id] = session['id']

    keyboard = InlineKeyboardMarkup().add(
        InlineKeyboardButton("💳 Opłać teraz", url=session.url)
    )

    await message.answer("💰 Kliknij poniżej, aby dokonać płatności:", reply_markup=keyboard)

@dp.message_handler(lambda message: message.text == "paid")
async def confirm_payment(message: types.Message):
    user_id = str(message.from_user.id)

    if user_id in subscriptions:
        await message.answer("✅ Masz już aktywny dostęp.")
        return

    # Проверка stripe session
    for session in stripe.checkout.Session.list(limit=10):
        if session.metadata.get('user_id') == user_id and session.payment_status == 'paid':
            end_date = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")
            subscriptions[user_id] = end_date
            save_subscriptions(subscriptions)

            invite = await bot.create_chat_invite_link(
                chat_id=CHANNEL_ID,
                expire_date=int((datetime.now() + timedelta(days=1)).timestamp()),
                member_limit=1
            )
            keyboard = InlineKeyboardMarkup().add(
                InlineKeyboardButton("🔗 Dołącz do kanału", url=invite.invite_link)
            )

            await message.answer("✅ Płatność potwierdzona! Kliknij, aby dołączyć:", reply_markup=keyboard)
            return

    await message.answer("❌ Płatność nie została znaleziona. Spróbuj ponownie lub skontaktuj się z administratorem.")

async def check_expired():
    while True:
        now = datetime.now().date()
        to_remove = []

        for user_id, end_str in subscriptions.items():
            try:
                end_date = datetime.strptime(end_str, "%Y-%m-%d").date()

                if end_date <= now:
                    await bot.send_message(int(user_id), "❌ Subskrypcja wygasła. Zostałeś usunięty z kanału.")
                    await bot.kick_chat_member(chat_id=CHANNEL_ID, user_id=int(user_id))
                    await asyncio.sleep(1)
                    await bot.unban_chat_member(chat_id=CHANNEL_ID, user_id=int(user_id))
                    to_remove.append(user_id)

            except Exception as e:
                print(f"Błąd przy usuwaniu {user_id}: {e}")

        for user_id in to_remove:
            subscriptions.pop(user_id, None)

        save_subscriptions(subscriptions)
        await asyncio.sleep(86400)

if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    loop.create_task(check_expired())
    executor.start_polling(dp, skip_updates=True)