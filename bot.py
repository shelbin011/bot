from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, ContextTypes, CallbackQueryHandler
)
import os
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")  # Load token from .env


# /help command
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Available commands:\n/start\n/help\n/time\n/me\n/info")


# New commands
async def time_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    await update.message.reply_text(f"⏰ Current Server Time:\n{now}")

async def me_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await update.message.reply_text(f"👤 Your Telegram username: @{user.username}")

async def info_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🤖 This bot is created for learning Telegram Bot development!")


# /start command with buttons
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("📄 Help", callback_data="help")],
        [InlineKeyboardButton("ℹ️ About", callback_data="about")],
        [InlineKeyboardButton("✨ New Feature", callback_data="new_feature")],
        [InlineKeyboardButton("🧪 Test Button", callback_data="test_button")],
        [InlineKeyboardButton("⏰ Time", callback_data="time")],
        [InlineKeyboardButton("👤 Who am I?", callback_data="me")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Welcome! Choose an option:", reply_markup=reply_markup)


# Handle button clicks
async def handle_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "help":
        await query.edit_message_text("📄 Help Section:\nUse /help to see commands.")

    elif query.data == "about":
        await query.edit_message_text("ℹ️ This bot demonstrates Telegram Bot features.")

    elif query.data == "new_feature":
        await query.edit_message_text("✨ New features will be added soon!")

    elif query.data == "test_button":
        await query.edit_message_text("🧪 Test Button Clicked Successfully!")

    elif query.data == "time":
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        await query.edit_message_text(f"⏰ Current Time:\n{now}")

    elif query.data == "me":
        user = update.effective_user
        await query.edit_message_text(f"👤 You are @{user.username}")

    else:
        await query.edit_message_text("Unknown option!")


def main():
    app = (
        ApplicationBuilder()
        .token(BOT_TOKEN)
        .job_queue(None)
        .build()
    )

    # Command handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("time", time_command))
    app.add_handler(CommandHandler("me", me_command))
    app.add_handler(CommandHandler("info", info_command))

    # Button handler
    app.add_handler(CallbackQueryHandler(handle_buttons))

    app.run_polling()


if __name__ == "__main__":
    main()
