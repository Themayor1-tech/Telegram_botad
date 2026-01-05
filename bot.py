import os
import logging
import re
from dotenv import load_dotenv
from datetime import datetime, timedelta
from collections import defaultdict
from telegram import Update, ChatPermissions
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ChatJoinRequestHandler,
    filters,
    ContextTypes,
)

from better_profanity import profanity

# --- Load environment ---
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID", 0))

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN not set in .env file")

# --- Logging ---
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Initialize profanity filter ---
profanity.load_censor_words()

# --- Anti-spam tracker ---
user_message_history = defaultdict(list)
SPAM_INTERVAL = 5
SPAM_COUNT = 3
MUTE_MINUTES = 5

# --- Helper functions ---
def contains_link(text: str) -> bool:
    return bool(re.search(r"https?://\S+|www\.\S+", text))

async def log_deleted(update: Update, reason: str):
    if ADMIN_CHAT_ID:
        try:
            await update.effective_chat.send_message(
                chat_id=ADMIN_CHAT_ID,
                text=f"🗑️ Deleted message from {update.message.from_user.mention_html()}:\n"
                     f"Text: {update.message.text}\nReason: {reason}",
                parse_mode="HTML"
            )
        except Exception as e:
            logger.warning(f"Failed to log message: {e}")

async def mute_user(chat_id: int, user_id: int, context: ContextTypes.DEFAULT_TYPE, minutes: int = MUTE_MINUTES):
    until_time = datetime.utcnow() + timedelta(minutes=minutes)
    try:
        await context.bot.restrict_chat_member(
            chat_id=chat_id,
            user_id=user_id,
            permissions=ChatPermissions(can_send_messages=False),
            until_date=until_time,
        )
        logger.info(f"User {user_id} muted for {minutes} minutes")
    except Exception as e:
        logger.warning(f"Failed to mute user {user_id}: {e}")

async def unmute_user(chat_id: int, user_id: int, context: ContextTypes.DEFAULT_TYPE):
    try:
        await context.bot.restrict_chat_member(
            chat_id=chat_id,
            user_id=user_id,
            permissions=ChatPermissions(
                can_send_messages=True,
                can_send_media_messages=True,
                can_send_polls=True,
                can_send_other_messages=True,
                can_add_web_page_previews=True,
                can_change_info=True,
                can_invite_users=True,
                can_pin_messages=True
            ),
        )
        logger.info(f"User {user_id} unmuted")
    except Exception as e:
        logger.warning(f"Failed to unmute user {user_id}: {e}")

async def kick_user(chat_id: int, user_id: int, context: ContextTypes.DEFAULT_TYPE):
    try:
        await context.bot.ban_chat_member(chat_id, user_id)
        await context.bot.unban_chat_member(chat_id, user_id)  # kick (ban+unban)
        logger.info(f"User {user_id} kicked")
    except Exception as e:
        logger.warning(f"Failed to kick user {user_id}: {e}")

async def ban_user(chat_id: int, user_id: int, context: ContextTypes.DEFAULT_TYPE):
    try:
        await context.bot.ban_chat_member(chat_id, user_id)
        logger.info(f"User {user_id} banned")
    except Exception as e:
        logger.warning(f"Failed to ban user {user_id}: {e}")

def is_admin(update: Update) -> bool:
    """Check if the user who sent the command is an admin"""
    user = update.effective_user
    chat = update.effective_chat
    member = chat.get_member(user.id)
    return member.status in ["administrator", "creator"]

# --- Handlers ---

# /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Hello! I am your Group Moderation Bot.\n"
        "Commands for admins:\n"
        "/mute @user [minutes]\n"
        "/unmute @user\n"
        "/kick @user\n"
        "/ban @user"
    )

# Message moderation
async def moderate_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg or not msg.text:
        return
    text = msg.text.strip()
    user_id = msg.from_user.id
    chat_id = msg.chat.id
    now = datetime.utcnow()

    # Track messages for spam
    user_message_history[user_id].append((now, text))
    user_message_history[user_id] = [
        (t, m) for t, m in user_message_history[user_id] if (now - t).total_seconds() <= SPAM_INTERVAL
    ]

    # Profanity filter
    if profanity.contains_profanity(text):
        await msg.delete()
        await log_deleted(update, "Profanity")
        await msg.reply_text("⚠️ Bad language is not allowed!")
        return

    # Link filter
    if contains_link(text):
        await msg.delete()
        await log_deleted(update, "Link detected")
        await msg.reply_text("🚫 Links are not allowed!")
        return

    # Spam detection
    if len(user_message_history[user_id]) >= SPAM_COUNT:
        await msg.delete()
        await log_deleted(update, "Spam detected")
        await msg.reply_text(f"⚠️ {msg.from_user.first_name}, please avoid spamming!")
        await mute_user(chat_id, user_id, context)
        user_message_history[user_id] = []

# Welcome new members
async def welcome_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    for member in update.message.new_chat_members:
        await update.message.reply_text(f"🎉 Welcome {member.mention_html()}!", parse_mode="HTML")

# Handle join requests
async def handle_join_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    join_request = update.chat_join_request
    await join_request.approve()
    try:
        await context.bot.send_message(
            chat_id=join_request.chat.id,
            text=f"🎉 Welcome {join_request.from_user.mention_html()}!",
            parse_mode="HTML",
        )
    except Exception as e:
        logger.warning(f"Failed to send welcome message: {e}")

# --- Admin command handlers ---

async def command_mute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        await update.message.reply_text("❌ Only admins can use this command.")
        return
    if len(context.args) < 1:
        await update.message.reply_text("Usage: /mute @username [minutes]")
        return
    username = context.args[0].lstrip("@")
    minutes = int(context.args[1]) if len(context.args) > 1 else MUTE_MINUTES
    chat = update.effective_chat
    member = await chat.get_member_by_username(username)
    if member:
        await mute_user(chat.id, member.user.id, context, minutes)
        await update.message.reply_text(f"✅ {username} muted for {minutes} minutes")
    else:
        await update.message.reply_text("❌ User not found")

async def command_unmute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        await update.message.reply_text("❌ Only admins can use this command.")
        return
    if len(context.args) < 1:
        await update.message.reply_text("Usage: /unmute @username")
        return
    username = context.args[0].lstrip("@")
    chat = update.effective_chat
    member = await chat.get_member_by_username(username)
    if member:
        await unmute_user(chat.id, member.user.id, context)
        await update.message.reply_text(f"✅ {username} unmuted")
    else:
        await update.message.reply_text("❌ User not found")

async def command_kick(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        await update.message.reply_text("❌ Only admins can use this command.")
        return
    if len(context.args) < 1:
        await update.message.reply_text("Usage: /kick @username")
        return
    username = context.args[0].lstrip("@")
    chat = update.effective_chat
    member = await chat.get_member_by_username(username)
    if member:
        await kick_user(chat.id, member.user.id, context)
        await update.message.reply_text(f"✅ {username} kicked")
    else:
        await update.message.reply_text("❌ User not found")

async def command_ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        await update.message.reply_text("❌ Only admins can use this command.")
        return
    if len(context.args) < 1:
        await update.message.reply_text("Usage: /ban @username")
        return
    username = context.args[0].lstrip("@")
    chat = update.effective_chat
    member = await chat.get_member_by_username(username)
    if member:
        await ban_user(chat.id, member.user.id, context)
        await update.message.reply_text(f"✅ {username} banned")
    else:
        await update.message.reply_text("❌ User not found")

# --- Main function ---
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters

# Example command
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Hello! I'm your bot.")

# Example message handler
async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(update.message.text)

def main():
    # Build the application
    app = ApplicationBuilder().token("YOUR_BOT_TOKEN").build()

    # Add handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))

    # Run the bot
    app.run_polling()

if __name__ == "__main__":
    main()
