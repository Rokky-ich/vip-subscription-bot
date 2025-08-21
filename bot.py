import os
import stripe
import time
import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.utils.executor import start_webhook
from aiohttp import web

# --- Настройки окружения ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")
WEBHOOK_HOST = os.getenv("WEBHOOK_HOST")  # Пример: https://yourapp.onrender.com
CHANNEL_ID = os.getenv("CHANNEL_ID")  # Пример: -1001234567890 или @your_channel

WEBHOOK_PATH = f"/webhook/{BOT_TOKEN}"
WEBHOOK_URL = f"{WEBHOOK_HOST}{WEBHOOK_PATH}"

WEBAPP_HOST = "0.0.0.0"
WEBAPP_PORT = int(os.getenv("PORT", 8000))

stripe.api_key = STRIPE_SECRET_KEY

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)

# Хранилище активных пользователей (можно заменить на БД)
subscriptions = set()

# Команда /start
@dp.message_handler(commands=["start"])
async def start_cmd(message: types.Message):
    user_id = str(message.from_user.id)
    if user_id in subscriptions:
        await message.answer(f"✅ Już masz aktywną subskrypcję!\nLink: {CHANNEL_LINK}")
        return

    session = stripe.checkout.Session.create(
        payment_method_types=['card'],
        line_items=[{
            'price_data': {
                'currency': 'pln',
                'product_data': {'name': 'VIP Subskrypcja'},
                'unit_amount': 500,  # 5 PLN
            },
            'quantity': 1,
        }],
        mode='payment',
        success_url='https://t.me/TwojBotTutaj',  # ссылка на бота вместо 404 страницы
        cancel_url='https://t.me/TwojBotTutaj',
        metadata={'user_id': user_id}
    )

    await message.answer("💳 Aby uzyskać dostęp do kanału VIP, dokonaj płatności poniżej:")
    await message.answer(session.url)

# Команда /verify
@dp.message_handler(commands=["verify"])
async def verify_cmd(message: types.Message):
    user_id = str(message.from_user.id)
    if user_id in subscriptions:
        await message.answer(f"✅ Płatność potwierdzona!\nOto link do kanału: {CHANNEL_LINK}")
    else:
        await message.answer("❌ Nie znaleziono płatności. Spróbuj ponownie po chwili.")

# Stripe webhook обработчик
async def handle_stripe_webhook(request):
    payload = await request.read()
    sig_header = request.headers.get("stripe-signature")

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
    except Exception as e:
        print("❌ Stripe webhook błąd:", str(e))
        return web.Response(status=400)

    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        user_id = session['metadata']['user_id']
        subscriptions.add(user_id)
        try:
            await bot.send_message(user_id, f"✅ Płatność potwierdzona!\nTwój link do kanału: {CHANNEL_LINK}")
        except Exception as e:
            print(f"❌ Nie udało się wysłać wiadomości do {user_id}: {e}")

    return web.Response(status=200)

# Запуск webhook для Stripe
async def stripe_webhook_runner():
    app = web.Application()
    app.router.add_post("/stripe_webhook", handle_stripe_webhook)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", 8001)
    await site.start()

# Инициализация
async def on_startup(dp):
    await bot.set_webhook(WEBHOOK_URL)
    asyncio.create_task(stripe_webhook_runner())

async def on_shutdown(dp):
    await bot.delete_webhook()

# Запуск
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
