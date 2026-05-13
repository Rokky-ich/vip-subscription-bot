# bot.py
# aiogram==2.25.2

import os
import json
import asyncio
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher, types
from aiogram.utils import executor

from aiohttp import web
import threading

# =========================
# CONFIG
# =========================

API_TOKEN = os.getenv("API_TOKEN")
CHANNEL_ID = int(os.getenv("CHANNEL_ID", "0"))
ADMIN_ID = int(os.getenv("ADMIN_ID", "2119400801"))

bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot)

DB_FILE = "db.json"

# =========================
# DATABASE
# =========================

def load_db():
    if not os.path.exists(DB_FILE):
        return {
            "links": {},
            "users": {}
        }

    with open(DB_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_db():
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=2)


db = load_db()

# =========================
# CREATE LINK
# =========================

@dp.message_handler(commands=["create"])
async def create_link(message: types.Message):

    if message.from_user.id != ADMIN_ID:
        return

    args = message.get_args()

    try:
        days = int(args)
    except:
        days = 3

    try:
        invite = await bot.create_chat_invite_link(
            chat_id=CHANNEL_ID,
            member_limit=1
        )

        db["links"][invite.invite_link] = {
            "days": days
        }

        save_db()

        await message.reply(
            f"✅ Одноразовая ссылка создана\n\n"
            f"⏳ Дней: {days}\n"
            f"🔗 {invite.invite_link}"
        )

    except Exception as e:
        await message.reply(f"❌ Error: {e}")

# =========================
# USER JOIN
# =========================

@dp.chat_member_handler()
async def user_join(event: types.ChatMemberUpdated):

    try:

        if event.chat.id != CHANNEL_ID:
            return

        old_status = event.old_chat_member.status
        new_status = event.new_chat_member.status

        joined = (
            old_status in ["left", "kicked"]
            and new_status in ["member", "administrator"]
        )

        if not joined:
            return

        user_id = event.from_user.id

        invite_link = None

        if event.invite_link:
            invite_link = event.invite_link.invite_link

        if not invite_link:
            return

        if invite_link not in db["links"]:
            return

        days = db["links"][invite_link]["days"]

        expire_at = (
            datetime.now() + timedelta(days=days)
        ).timestamp()

        db["users"][str(user_id)] = {
            "expire_at": expire_at
        }

        save_db()

        try:
            await bot.send_message(
                user_id,
                f"✅ Доступ активирован на {days} дней."
            )
        except:
            pass

        try:
            await bot.send_message(
                ADMIN_ID,
                f"✅ Новый пользователь\n\n"
                f"ID: {user_id}\n"
                f"⏳ На {days} дней"
            )
        except:
            pass

    except Exception as e:
        print(e)

# =========================
# AUTO KICK
# =========================

async def auto_kick():

    while True:

        now = datetime.now().timestamp()

        expired_users = []

        for user_id, data in db["users"].items():

            expire_at = data["expire_at"]

            if now >= expire_at:

                try:

                    await bot.ban_chat_member(
                        CHANNEL_ID,
                        int(user_id)
                    )

                    await asyncio.sleep(1)

                    await bot.unban_chat_member(
                        CHANNEL_ID,
                        int(user_id)
                    )

                    try:
                        await bot.send_message(
                            int(user_id),
                            "❌ Ваш доступ закончился."
                        )
                    except:
                        pass

                    try:
                        await bot.send_message(
                            ADMIN_ID,
                            f"❌ Пользователь удалён\n\nID: {user_id}"
                        )
                    except:
                        pass

                    expired_users.append(user_id)

                except Exception as e:
                    print(e)

        for user_id in expired_users:
            del db["users"][user_id]

        if expired_users:
            save_db()

        await asyncio.sleep(60)

# =========================
# START
# =========================

@dp.message_handler(commands=["start"])
async def start(message: types.Message):

    await message.reply(
        "Бот работает."
    )

# =========================
# STARTUP
# =========================

async def on_startup(dp):

    asyncio.create_task(auto_kick())

    print("BOT STARTED")

# =========================
# RENDER PORT
# =========================

async def health(request):
    return web.Response(text="OK")

def run_web():
    app = web.Application()
    app.router.add_get("/", health)

    web.run_app(
        app,
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 10000))
    )

# =========================
# RUN
# =========================

if __name__ == "__main__":

    threading.Thread(target=run_web).start()

    executor.start_polling(
        dp,
        skip_updates=True,
        on_startup=on_startup
    )