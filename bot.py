import os
import stripe
import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.utils.executor import start_webhook
from aiohttp import web

# Настройки
BOT_TOKEN = os.getenv("BOT_TOKEN")
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY")
CHANNEL_LINK = os.getenv("CHANNEL_LINK")

stripe.api_key = STRIPE_SECRET_KEY

WEBHOOK_HOST = os.getenv("WEBHOOK_HOST")  # например https://yourapp.onrender.com
WEBHOOK_PATH = f"/webhook/{BOT_TOKEN}"
WEBHOOK_URL = f"{WEBHOOK_HOST}{WEBHOOK_PATH}"

WEBAPP_HOST = '0.0.0.0'
WEBAPP_PORT = int(os.getenv("PORT", 8000))

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)

subscriptions = set()

# --- ОБРАБОТЧИКИ БОТА ---

@dp.message_handler(commands=['start'])
async def send_welcome(message: types.Message):
    user_id = str(message.from_user.id)
    if user_id in subscriptions:
        await message.answer(f"✅ Już masz aktywną subskrypcję!\nLink: {CHANNEL_LINK}")
    else:
        session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{
                'price_data': {
                    'currency': 'pln',
                    'product_data': {
                        'name': 'VIP Subskrypcja',
                    },
                    'unit_amount': 500,  # 5 PLN
                },
                'quantity': 1,
            }],
            mode='payment',
            success_url=f'{WEBHOOK_HOST}/success.html',
            cancel_url=f'{WEBHOOK_HOST}/cancel.html',
            metadata={"user_id": user_id}
        )
        await message.answer("Aby uzyskać dostęp do kanału VIP, dokonaj płatności:")
        await message.answer(session.url)

@dp.message_handler(commands=['verify'])
async def verify_payment(message: types.Message):
    user_id = str(message.from_user.id)
    if user_id in subscriptions:
        await message.answer("✅ Płatność została już potwierdzona. Link: " + CHANNEL_LINK)
    else:
        await message.answer("❌ Brak aktywnej płatności.")

# --- ВЕБХУК ДЛЯ STRIPE ---

async def handle_stripe_webhook(request):
    payload = await request.read()
    sig_header = request.headers.get('stripe-signature')
    endpoint_secret = os.getenv("STRIPE_WEBHOOK_SECRET")

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, endpoint_secret
        )
    except ValueError:
        return web.Response(status=400)
    except stripe.error.SignatureVerificationError:
        return web.Response(status=400)

    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        user_id = session['metadata']['user_id']
        subscriptions.add(user_id)
        try:
            await bot.send_message(user_id, f"✅ Płatność potwierdzona!\nLink do kanału: {CHANNEL_LINK}")
        except:
            pass

    return web.Response(status=200)

# --- ЗАПУСК ---

async def on_startup(dp):
    await bot.set_webhook(WEBHOOK_URL)

async def on_shutdown(dp):
    await bot.delete_webhook()

async def stripe_webhook_runner():
    app = web.Application()
    app.router.add_post('/stripe_webhook', handle_stripe_webhook)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', 8001)
    await site.start()

if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    loop.create_task(stripe_webhook_runner())
    start_webhook(
        dispatcher=dp,
        webhook_path=WEBHOOK_PATH,
        on_startup=on_startup,
        on_shutdown=on_shutdown,
        skip_updates=True,
        host=WEBAPP_HOST,
        port=WEBAPP_PORT
    )
