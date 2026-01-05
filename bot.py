# bot.py
import os
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# Load the bot token from .env
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN not set in .env file")

# --- Command Handlers ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Hello! I am your moderation bot.\n"
        "I will automatically delete messages with links."
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Commands:\n"
        "/start - Start the bot\n"
        "/help - Show this help message\n"
        "/ban - Ban a user (reply to a user's message)"
    )

# --- Message Moderation ---
async def moderate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message:
        return
    # Check for links in the message
    text = message.text or ""
    if "http://" in text.lower() or "https://" in text.lower():
        try:
            await message.delete()
            await message.reply_text(
                f"{message.from_user.mention_html()}, your message was removed because links are not allowed.",
                parse_mode="HTML"
            )
        except Exception as e:
            print(f"Failed to delete message: {e}")

# --- Admin Commands ---
async def ban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.reply_to_message:
        user_to_ban = update.message.reply_to_message.from_user
        try:
            await update.effective_chat.ban_member(user_to_ban.id)
            await update.message.reply_text(f"{user_to_ban.full_name} has been banned.")
        except Exception as e:
            await update.message.reply_text(f"Failed to ban user: {e}")
    else:
        await update.message.reply_text("Reply to a user's message to ban them.")

# --- Main Bot ---
def main():
    # Create the bot application
    app = Application.builder().token(BOT_TOKEN).build()

    # Register handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("ban", ban_user))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, moderate))

    print("Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
