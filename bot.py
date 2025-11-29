import os
import logging
import random
from datetime import datetime

from dotenv import load_dotenv
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    CallbackQueryHandler,
    MessageHandler,
    filters,
)

# -------------------- Logging --------------------
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# -------------------- Env / Token --------------------
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN not found in .env file!")


# -------------------- Helper: Keyboards --------------------
def main_menu_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [
            InlineKeyboardButton("📄 Help", callback_data="help"),
            InlineKeyboardButton("ℹ️ About", callback_data="about"),
        ],
        [
            InlineKeyboardButton("⏰ Time", callback_data="time"),
            InlineKeyboardButton("👤 Who am I?", callback_data="me"),
        ],
        [
            InlineKeyboardButton("😂 Joke", callback_data="joke"),
            InlineKeyboardButton("🎲 Dice", callback_data="dice"),
        ],
        [InlineKeyboardButton("✨ Quote", callback_data="quote")],
        [
            InlineKeyboardButton("🎮 Games", callback_data="games"),
            InlineKeyboardButton("⚙️ Settings", callback_data="settings"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


def games_menu_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [
            InlineKeyboardButton("🪨📄✂️ Rock-Paper-Scissors", callback_data="game_rps"),
        ],
        [
            InlineKeyboardButton("🔢 Guess the Number", callback_data="game_guess"),
        ],
        [
            InlineKeyboardButton("🔙 Back to Main Menu", callback_data="back_main"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


def settings_menu_keyboard(fun_mode: bool) -> InlineKeyboardMarkup:
    status = "ON ✅" if fun_mode else "OFF ❌"
    keyboard = [
        [
            InlineKeyboardButton(f"🎉 Fun Mode: {status}", callback_data="toggle_fun"),
        ],
        [
            InlineKeyboardButton("🔙 Back to Main Menu", callback_data="back_main"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


# -------------------- Commands --------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    logger.info("User %s started the bot.", user.id)

    welcome_text = (
        "🤖 *Welcome to TeleBot!*\n\n"
        "I'm a feature-rich Telegram bot. Choose an option below:\n\n"
        "📌 *Quick Commands:*\n"
        "• /help - See all commands\n"
        "• /time - Current time\n"
        "• /joke - Random jokes\n"
        "• /dice - Roll a dice\n"
        "• /quote - Inspirational quotes\n"
    )

    await update.message.reply_text(
        welcome_text,
        reply_markup=main_menu_keyboard(),
        parse_mode="Markdown",
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info("User %s used /help.", update.effective_user.id)

    help_text = (
        "📄 *Available Commands:*\n\n"
        "/start - Show main menu\n"
        "/help - Show this help\n"
        "/time - Show current time\n"
        "/me - Show your username & ID\n"
        "/info - About this bot\n"
        "/joke - Get a random joke\n"
        "/dice - Roll a dice\n"
        "/quote - Get an inspirational quote\n"
    )
    await update.message.reply_text(help_text, parse_mode="Markdown")


async def time_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    logger.info("Time requested by %s: %s", update.effective_user.id, now)
    await update.message.reply_text(f"⏰ *Current Server Time:*\n`{now}`", parse_mode="Markdown")


async def me_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    username = user.username if user.username else "No username"
    logger.info("User info requested: %s (%s)", username, user.id)

    text = f"👤 *Your Info:*\n\nUsername: @{username}\nID: `{user.id}`"
    await update.message.reply_text(text, parse_mode="Markdown")


async def info_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 *TeleBot v1.0*\n\n"
        "A learning project built using the Telegram Bot API and python-telegram-bot.",
        parse_mode="Markdown",
    )


async def joke_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    jokes = [
        "Why do programmers prefer dark mode? Because light attracts bugs! 🐛",
        "How many programmers does it take to change a light bulb? None, that's hardware!",
        "Why do Java developers wear glasses? Because they don't C#! 👓",
    ]
    joke = random.choice(jokes)
    logger.info("Joke sent to %s", update.effective_user.id)
    await update.message.reply_text(f"😂 {joke}")


async def dice_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    roll = random.randint(1, 6)
    logger.info("Dice rolled for %s: %d", update.effective_user.id, roll)
    await update.message.reply_text(f"🎲 You rolled: *{roll}*", parse_mode="Markdown")


async def quote_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    quotes = [
        "The only way to do great work is to love what you do. - Steve Jobs",
        "Innovation distinguishes between a leader and a follower. - Steve Jobs",
        "Life is what happens when you're busy making other plans. - John Lennon",
    ]
    quote = random.choice(quotes)
    logger.info("Quote sent to %s", update.effective_user.id)
    await update.message.reply_text(f"✨ _{quote}_", parse_mode="Markdown")


# -------------------- Callback Query Handler --------------------
async def handle_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    data = query.data
    logger.info("User %s clicked button: %s", user.id, data)

    # Ensure fun_mode exists in user_data
    fun_mode = context.user_data.get("fun_mode", True)

    # Main menu navigation
    if data == "help":
        text = (
            "📄 *Help Section:*\n\n"
            "/start - Main menu\n"
            "/help - Show commands\n"
            "/time - Current time\n"
            "/me - Your info\n"
            "/joke - Get a joke\n"
            "/dice - Roll dice\n"
            "/quote - Get quote\n"
        )
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=main_menu_keyboard())

    elif data == "about":
        await query.edit_message_text(
            "ℹ️ *About This Bot*\n\nTeleBot v1.0 - Learning project with Telegram Bot API.",
            parse_mode="Markdown",
            reply_markup=main_menu_keyboard(),
        )

    elif data == "time":
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        await query.edit_message_text(
            f"⏰ *Current Time:*\n\n`{now}`",
            parse_mode="Markdown",
            reply_markup=main_menu_keyboard(),
        )

    elif data == "me":
        username = user.username if user.username else "No username"
        await query.edit_message_text(
            f"👤 *You are:* @{username}\nID: `{user.id}`",
            parse_mode="Markdown",
            reply_markup=main_menu_keyboard(),
        )

    elif data == "joke":
        jokes = [
            "Why do programmers prefer dark mode? Because light attracts bugs! 🐛",
            "How many programmers does it take to change a light bulb? None!",
        ]
        await query.edit_message_text(
            f"😂 {random.choice(jokes)}",
            parse_mode="Markdown",
            reply_markup=main_menu_keyboard(),
        )

    elif data == "dice":
        roll = random.randint(1, 6)
        await query.edit_message_text(
            f"🎲 *You rolled:* `{roll}`",
            parse_mode="Markdown",
            reply_markup=main_menu_keyboard(),
        )

    elif data == "quote":
        quotes = [
            "The only way to do great work is to love what you do. - Steve Jobs",
            "Innovation distinguishes between a leader and a follower. - Steve Jobs",
        ]
        await query.edit_message_text(
            f"✨ _{random.choice(quotes)}_",
            parse_mode="Markdown",
            reply_markup=main_menu_keyboard(),
        )

    # Games menu
    elif data == "games":
        await query.edit_message_text(
            "🎮 *Games Menu*\n\nChoose a game:",
            parse_mode="Markdown",
            reply_markup=games_menu_keyboard(),
        )

    # Settings menu
    elif data == "settings":
        await query.edit_message_text(
            "⚙️ *Settings*\n\nToggle your preferences:",
            parse_mode="Markdown",
            reply_markup=settings_menu_keyboard(fun_mode),
        )

    # Toggle fun mode
    elif data == "toggle_fun":
        new_fun_mode = not fun_mode
        context.user_data["fun_mode"] = new_fun_mode
        await query.edit_message_text(
            "⚙️ *Settings*\n\nFun Mode updated!",
            parse_mode="Markdown",
            reply_markup=settings_menu_keyboard(new_fun_mode),
        )

    # Back to main
    elif data == "back_main":
        await query.edit_message_text(
            "🏠 *Main Menu*\n\nChoose an option:",
            parse_mode="Markdown",
            reply_markup=main_menu_keyboard(),
        )

    # Games: Rock-Paper-Scissors
    elif data == "game_rps":
        rps_keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("🪨 Rock", callback_data="rps_rock"),
                    InlineKeyboardButton("📄 Paper", callback_data="rps_paper"),
                    InlineKeyboardButton("✂️ Scissors", callback_data="rps_scissors"),
                ],
                [InlineKeyboardButton("🔙 Back to Games", callback_data="games")],
            ]
        )
        await query.edit_message_text(
            "🪨📄✂️ *Rock-Paper-Scissors*\n\nChoose your move:",
            parse_mode="Markdown",
            reply_markup=rps_keyboard,
        )

    elif data in ("rps_rock", "rps_paper", "rps_scissors"):
        moves = {
            "rps_rock": "Rock",
            "rps_paper": "Paper",
            "rps_scissors": "Scissors",
        }
        user_move = moves[data]
        bot_move = random.choice(list(moves.values()))

        # Decide winner
        if user_move == bot_move:
            result = "It's a draw! 🤝"
        elif (
            (user_move == "Rock" and bot_move == "Scissors")
            or (user_move == "Paper" and bot_move == "Rock")
            or (user_move == "Scissors" and bot_move == "Paper")
        ):
            result = "You win! 🏆"
        else:
            result = "I win! 😈"

        await query.edit_message_text(
            f"🪨📄✂️ *Rock-Paper-Scissors*\n\n"
            f"Your move: *{user_move}*\n"
            f"My move: *{bot_move}*\n\n"
            f"{result}",
            parse_mode="Markdown",
            reply_markup=games_menu_keyboard(),
        )

    # Games: Guess the Number
    elif data == "game_guess":
        number = random.randint(1, 10)
        context.user_data["guess_number"] = number
        context.user_data["guess_attempts"] = 0

        await query.edit_message_text(
            "🔢 *Guess the Number*\n\nI'm thinking of a number between *1 and 10*.\n"
            "Send your guess as a message!",
            parse_mode="Markdown",
            reply_markup=games_menu_keyboard(),
        )

    else:
        await query.edit_message_text(
            "❓ Unknown option!",
            reply_markup=main_menu_keyboard(),
        )


# -------------------- Text Message Handler (for Guess Game) --------------------
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = update.message.text.strip()
    logger.info("User %s sent text: %s", user.id, text)

    # Guess the Number game
    if "guess_number" in context.user_data:
        try:
            guess = int(text)
        except ValueError:
            await update.message.reply_text("❗ Please send a *number* between 1 and 10.", parse_mode="Markdown")
            return

        target = context.user_data["guess_number"]
        context.user_data["guess_attempts"] += 1
        attempts = context.user_data["guess_attempts"]

        if guess < 1 or guess > 10:
            await update.message.reply_text("😅 Only numbers between *1 and 10* please.", parse_mode="Markdown")
        elif guess < target:
            await update.message.reply_text("📉 Too low! Try again.")
        elif guess > target:
            await update.message.reply_text("📈 Too high! Try again.")
        else:
            await update.message.reply_text(
                f"🎉 Correct! The number was *{target}*.\n"
                f"You guessed it in *{attempts}* attempts.",
                parse_mode="Markdown",
            )
            # Clear game state
            context.user_data.pop("guess_number", None)
            context.user_data.pop("guess_attempts", None)
        return

    # If not in a game, generic response
    await update.message.reply_text(
        "💬 I didn't understand that.\nUse /help or press a button from the menu.",
    )


# -------------------- Main --------------------
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # Command handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("time", time_command))
    app.add_handler(CommandHandler("me", me_command))
    app.add_handler(CommandHandler("info", info_command))
    app.add_handler(CommandHandler("joke", joke_command))
    app.add_handler(CommandHandler("dice", dice_command))
    app.add_handler(CommandHandler("quote", quote_command))

    # Callback query handler (for all buttons)
    app.add_handler(CallbackQueryHandler(handle_buttons))

    # Text handler (for number guessing + fallback)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    logger.info("Bot is starting...")
    app.run_polling()


if __name__ == "__main__":
    main()
