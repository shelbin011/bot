from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, ContextTypes, CallbackQueryHandler, MessageHandler, filters
)
import os
from dotenv import load_dotenv
from datetime import datetime
import random

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Available commands:\n"
        "/start - Show main menu\n"
        "/help - Show this help\n"
        "/time - Show current time\n"
        "/me - Show your username\n"
        "/info - About this bot\n"
        "/joke - Get a random joke\n"
        "/dice - Roll a dice\n"
        "/quote - Get an inspirational quote"
    )

async def time_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    await update.message.reply_text(f"⏰ Current Server Time:\n{now}")

async def me_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    username = user.username if user.username else "No username"
    await update.message.reply_text(f"👤 Your Telegram username: @{username}\nID: {user.id}")

async def info_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🤖 This bot is created for learning Telegram Bot development!")

async def joke_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    jokes = [
        "Why do programmers prefer dark mode? Because light attracts bugs! 🐛",
        "How many programmers does it take to change a light bulb? None, that's hardware!",
        "Why do Java developers wear glasses? Because they don't C#! 👓",
    ]
    await update.message.reply_text(f"😂 {random.choice(jokes)}")

async def dice_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    roll = random.randint(1, 6)
    await update.message.reply_text(f"🎲 You rolled: {roll}")

async def quote_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    quotes = [
        "The only way to do great work is to love what you do. - Steve Jobs",
        "Innovation distinguishes between a leader and a follower. - Steve Jobs",
        "Life is what happens when you're busy making other plans. - John Lennon",
    ]
    await update.message.reply_text(f"✨ {random.choice(quotes)}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("📄 Help", callback_data="help"), InlineKeyboardButton("ℹ️ About", callback_data="about")],
        [InlineKeyboardButton("⏰ Time", callback_data="time"), InlineKeyboardButton("👤 Who am I?", callback_data="me")],
        [InlineKeyboardButton("😂 Joke", callback_data="joke"), InlineKeyboardButton("🎲 Dice", callback_data="dice")],
        [InlineKeyboardButton("✨ Quote", callback_data="quote")],
        [InlineKeyboardButton("🎮 Games", callback_data="games"), InlineKeyboardButton("⚙️ Settings", callback_data="settings")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    welcome_text = (
        "🤖 **Welcome to TeleBot!**\n\n"
        "I'm a feature-rich Telegram bot. Choose an option below:\n\n"
        "📌 **Quick Links:**\n"
        "• /help - See all commands\n"
        "• /time - Current time\n"
        "• /joke - Random jokes\n"
        "• /dice - Roll a dice\n"
        "• /quote - Inspirational quotes"
    )
    await update.message.reply_text(welcome_text, reply_markup=reply_markup, parse_mode="Markdown")

async def handle_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "help":
        await query.edit_message_text(
            "📄 **Help Section:**\n\n"
            "/start - Main menu\n"
            "/help - Show commands\n"
            "/time - Current time\n"
            "/me - Your info\n"
            "/joke - Get a joke\n"
            "/dice - Roll dice\n"
            "/quote - Get quote",
            parse_mode="Markdown"
        )

    elif query.data == "about":
        await query.edit_message_text("ℹ️ **About This Bot**\n\nTeleBot v1.0 - Learning project with Telegram Bot API", parse_mode="Markdown")

    elif query.data == "time":
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        await query.edit_message_text(f"⏰ **Current Time:**\n\n`{now}`", parse_mode="Markdown")

    elif query.data == "me":
        user = update.effective_user
        username = user.username if user.username else "No username"
        await query.edit_message_text(f"👤 **You are:** @{username}", parse_mode="Markdown")

    elif query.data == "joke":
        jokes = [
            "Why do programmers prefer dark mode? Because light attracts bugs! 🐛",
            "How many programmers does it take to change a light bulb? None!",
        ]
        await query.edit_message_text(f"😂 {random.choice(jokes)}", parse_mode="Markdown")

    elif query.data == "dice":
        roll = random.randint(1, 6)
        await query.edit_message_text(f"🎲 **You rolled:** `{roll}`", parse_mode="Markdown")

    elif query.data == "quote":
        quotes = [
            "The only way to do great work is to love what you do. - Steve Jobs",
            "Innovation distinguishes between a leader and a follower. - Steve Jobs",
        ]
        await query.edit_message_text(f"✨ _{random.choice(quotes)}_", parse_mode="Markdown")

    elif query.data == "games":
        await query.edit_message_text("🎮 **Games Coming Soon!**", parse_mode="Markdown")

    elif query.data == "settings":
        await query.edit_message_text("⚙️ **Settings:**\n\nNo settings available yet.", parse_mode="Markdown")

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("time", time_command))
    app.add_handler(CommandHandler("me", me_command))
    app.add_handler(CommandHandler("info", info_command))
    app.add_handler(CommandHandler("joke", joke_command))
    app.add_handler(CommandHandler("dice", dice_command))
    app.add_handler(CommandHandler("quote", quote_command))

    app.add_handler(CallbackQueryHandler(handle_buttons))

    app.run_polling()

if __name__ == "__main__":
    main()