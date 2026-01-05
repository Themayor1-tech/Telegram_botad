import os
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)
from better_profanity import profanity

# Load .env locally (optional, Render uses environment variables)
load_dotenv()

# Read BOT_TOKEN from environment
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN not set in environment variables")

# ---------- Handlers ----------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send a welcome message on /start"""
    await update.message.reply_text("Hello! I'm your moderation bot.")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send a help message"""
    await update.message.reply_text("Use me to keep your group safe from spam and profanity!")

async def filter_profanity(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Filter bad words from messages"""
    text = update.message.text
    if profanity.contains_profanity(text):
        await update.message.delete()
        await update.message.reply_text("⚠️ Please avoid using bad language.")

# ---------- Main Function ----------

def main():
    # Build the application
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # Add command handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))

    # Add message handler for profanity filtering
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, filter_profanity))

    # Run the bot
    app.run_polling()

# ---------- Entry Point ----------

if __name__ == "__main__":
    main()
