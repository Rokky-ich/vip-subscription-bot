import os
import stripe
from aiogram import Bot, Dispatcher, types
from aiogram.utils.executor import start_webhook
from aiohttp import web
import asyncio

# Настройки
BOT_TOKEN = os.getenv("BOT_TOKEN")
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")
CHANNEL_LINK = os.getenv("CHANNEL_LINK")

WEBHOOK_HOST = os.getenv("WEBHOOK_HOST")  # например https://yourapp.onrender.com
WEBHOOK_PATH = f"/webhook/{BOT_TOKEN}"
WEBHOOK_URL = f"{WEBHOOK_HOST}{WEBHOOK_PATH}"

WEBAPP_HOST = "0.0.0.0"
WEBAPP_PORT = int(os.getenv("PORT", 8000))

stripe.api_key = STRIPE_SECRET_KEY

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)

# Хранилище оплат (в реале замени на БД)
subscriptions = set()

@dp.message_handler(commands=['start'])
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
                'unit_amount': 500,
            },
            'quantity': 1
        }],
        mode='payment',
        success_url='https://t.me/your_channel_link',  # желательно поставить свой канал
        cancel_url='https://t.me/your_channel_link',
        metadata={'user_id': user_id}
    )

    await message.answer("Aby uzyskać dostęp do kanału VIP, dokonaj płatności:")
    await message.answer(session.url)

@dp.message_handler(commands=['verify'])
async def verify_cmd(message: types.Message):
    user_id = str(message.from_user.id)
    if user_id in subscriptions:
        await message.answer(f"✅ Płatność potwierdzona!\nLink do kanału: {CHANNEL_LINK}")
    else:
        await message.answer("❌ Nie znaleziono płatności.")

# Stripe webhook (в том же приложении)
async def handle_stripe_webhook(request):
    payload = await request.read()
    sig_header = request.headers.get("stripe-signature")

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
    except Exception as e:
        print("Webhook error:", str(e))
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

# Создаём сервер aiohttp и на него вешаем Stripe webhook
async def on_startup(dp):
    await bot.set_webhook(WEBHOOK_URL)

    app = dp.bot['app']
    app.router.add_post("/stripe_webhook", handle_stripe_webhook)

async def on_shutdown(dp):
    await bot.delete_webhook()

def main():
    app = web.Application()
    app["bot"] = bot
    bot["app"] = app

    dp["app"] = app
    web.run_app(app, host=WEBAPP_HOST, port=WEBAPP_PORT)

if __name__ == '__main__':
    main()
