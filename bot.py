import logging
import os
import time
from collections import defaultdict

from dotenv import load_dotenv
from telegram import Update, ChatPermissions
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# ─── CONFIG ───────────────────────────────────────────────────────────────────
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN not set in .env file")

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

# ─── STATE ────────────────────────────────────────────────────────────────────
link_lock = defaultdict(lambda: True)
warns = defaultdict(int)
user_messages = defaultdict(list)

BAD_WORDS = ["spam", "scam", "fraud"]

MAX_MSG = 5
TIME_WINDOW = 10  # seconds

# ─── HELPERS ──────────────────────────────────────────────────────────────────
async def is_admin(update: Update, user_id: int) -> bool:
    member = await update.effective_chat.get_member(user_id)
    return member.status in ("administrator", "creator")

# ─── COMMANDS ─────────────────────────────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 Group Moderation Bot Active!\n"
        "Use /lock_links or /unlock_links"
    )

async def lock_links(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, update.effective_user.id):
        return
    link_lock[update.effective_chat.id] = True
    await update.message.reply_text("🔒 Links are now blocked.")

async def unlock_links(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, update.effective_user.id):
        return
    link_lock[update.effective_chat.id] = False
    await update.message.reply_text("🔓 Links are now allowed.")

async def settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, update.effective_user.id):
        return

    chat_id = update.effective_chat.id
    link_status = "ON 🔒" if link_lock[chat_id] else "OFF 🔓"

    text = (
        "⚙️ *Bot Settings*\n\n"
        f"🔗 Link Filter: {link_status}\n"
        "🗯 Bad Words Filter: ON\n"
        "🚫 Anti-Flood: ON\n\n"
        "Use commands below:\n"
        "/lock_links\n"
        "/unlock_links\n"
        "/help"
    )

    await update.message.reply_text(text, parse_mode="Markdown")

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📖 *Admin Commands*\n\n"
        "/lock_links – Block all links\n"
        "/unlock_links – Allow links\n"
        "/settings – View bot status\n"
        "/help – Show this message",
        parse_mode="Markdown"
    )
# ─── EVENTS ───────────────────────────────────────────────────────────────────
async def welcome(update: Update, context: ContextTypes.DEFAULT_TYPE):
    for user in update.message.new_chat_members:
        await update.message.reply_text(
            f"👋 Welcome {user.first_name}!\nPlease follow group rules."
        )

async def moderation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    chat_id = msg.chat.id
    user_id = msg.from_user.id
    text = msg.text.lower() if msg.text else ""

    # Ignore admins
    if await is_admin(update, user_id):
        return

    # ─── LINK FILTER ───
    if link_lock[chat_id] and ("http://" in text or "https://" in text or "t.me/" in text):
        await msg.delete()
        warns[user_id] += 1
        await msg.reply_text(f"⚠️ Warning {warns[user_id]}/3: Links not allowed.")
    
    # ─── BAD WORD FILTER ───
    for word in BAD_WORDS:
        if word in text:
            await msg.delete()
            warns[user_id] += 1
            await msg.reply_text(f"⚠️ Warning {warns[user_id]}/3: Inappropriate language.")
            break

    # ─── ANTI-FLOOD ───
    now = time.time()
    user_messages[user_id] = [
        t for t in user_messages[user_id] if now - t < TIME_WINDOW
    ]
    user_messages[user_id].append(now)

    if len(user_messages[user_id]) > MAX_MSG:
        await msg.chat.restrict_member(
            user_id,
            ChatPermissions(can_send_messages=False),
            until_date=int(now + 60),
        )
        await msg.reply_text("🚫 You are muted for flooding (1 minute).")

    # ─── AUTO MUTE ───
    if warns[user_id] >= 3:
        await msg.chat.restrict_member(
            user_id,
            ChatPermissions(can_send_messages=False),
            until_date=int(time.time() + 300),
        )
        await msg.reply_text("🚫 Muted for repeated violations (5 minutes).")
        warns[user_id] = 0

# ─── MAIN ─────────────────────────────────────────────────────────────────────
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("lock_links", lock_links))
    app.add_handler(CommandHandler("unlock_links", unlock_links))
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, moderation))
    app.add_handler(CommandHandler("settings", settings))
    app.add_handler(CommandHandler("help", help_cmd))
    print("🤖 Moderation bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
