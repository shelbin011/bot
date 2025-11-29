import os
import logging
import random
import sqlite3
from datetime import datetime

from dotenv import load_dotenv
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ChatMemberUpdated,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    CallbackQueryHandler,
    MessageHandler,
    ChatMemberHandler,
    filters,
)

# -------------------- Config --------------------
# you are the admin by username
OWNER_USERNAMES = {"Shelbin34"}

DB_PATH = "bot_data.db"

# -------------------- Logging --------------------
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

stream_handler = logging.StreamHandler()
stream_handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
logger.addHandler(stream_handler)

# -------------------- DB Helpers --------------------
def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            last_name TEXT,
            created_at TEXT,
            bio TEXT,
            fun_mode INTEGER DEFAULT 1,
            games_played INTEGER DEFAULT 0,
            dice_plays INTEGER DEFAULT 0,
            dice_highscore INTEGER DEFAULT 0,
            rps_wins INTEGER DEFAULT 0,
            rps_losses INTEGER DEFAULT 0,
            rps_draws INTEGER DEFAULT 0
        )
        """
    )
    conn.commit()
    conn.close()


def upsert_user(user):
    conn = get_db_connection()
    cur = conn.cursor()
    now = datetime.utcnow().isoformat()
    cur.execute(
        """
        INSERT INTO users (id, username, first_name, last_name, created_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            username = excluded.username,
            first_name = excluded.first_name,
            last_name = excluded.last_name
        """,
        (user.id, user.username, user.first_name, user.last_name, now),
    )
    conn.commit()
    conn.close()


def is_admin(user) -> bool:
    return user.username in OWNER_USERNAMES


def update_stat(user_id: int, field: str, value, mode="inc"):
    conn = get_db_connection()
    cur = conn.cursor()
    if mode == "inc":
        cur.execute(f"UPDATE users SET {field} = {field} + ? WHERE id = ?", (value, user_id))
    elif mode == "set":
        cur.execute(f"UPDATE users SET {field} = ? WHERE id = ?", (value, user_id))
    conn.commit()
    conn.close()


def get_user(user_id: int):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    row = cur.fetchone()
    conn.close()
    return row


def get_leaderboard(field: str, limit: int = 5):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        f"SELECT id, username, first_name, {field} as score FROM users "
        f"WHERE {field} > 0 ORDER BY {field} DESC LIMIT ?",
        (limit,),
    )
    rows = cur.fetchall()
    conn.close()
    return rows


def get_user_count():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM users")
    (count,) = cur.fetchone()
    conn.close()
    return count


# -------------------- Env / Token --------------------
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN not found in .env or env vars!")


# -------------------- Keyboards --------------------
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
            InlineKeyboardButton("🏆 Leaderboard", callback_data="leaderboard"),
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


# -------------------- Command Handlers --------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    upsert_user(user)
    logger.info("User %s (%s) started the bot.", user.id, user.username)

    welcome_text = (
        "🤖 *Welcome to TeleBot+!*\n\n"
        "I'm a feature-rich Telegram bot with games, profiles, stats, and more.\n\n"
        "📌 *Quick Commands:*\n"
        "• /help - See all commands\n"
        "• /time - Current time\n"
        "• /me - Your info\n"
        "• /profile - View your profile\n"
        "• /setbio <text> - Set your bio\n"
        "• /leaderboard - Game rankings\n"
    )

    await update.message.reply_text(
        welcome_text,
        reply_markup=main_menu_keyboard(),
        parse_mode="Markdown",
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    upsert_user(user)

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
        "/profile - View your profile & stats\n"
        "/setbio <text> - Set your public bio\n"
        "/leaderboard - View top players\n"
        "/admin - Admin panel (owner only)\n"
    )
    await update.message.reply_text(help_text, parse_mode="Markdown")


async def time_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    upsert_user(user)

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    await update.message.reply_text(f"⏰ *Current Server Time:*\n`{now}`", parse_mode="Markdown")


async def me_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    upsert_user(user)
    username = user.username if user.username else "No username"

    text = f"👤 *Your Info:*\n\nUsername: @{username}\nID: `{user.id}`"
    await update.message.reply_text(text, parse_mode="Markdown")


async def info_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    upsert_user(user)
    await update.message.reply_text(
        "🤖 *TeleBot+ v2.0*\n\n"
        "A learning project with admin tools, profiles, games, leaderboards and more.",
        parse_mode="Markdown",
    )


async def joke_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    upsert_user(user)
    jokes = [
        "Why do programmers prefer dark mode? Because light attracts bugs! 🐛",
        "How many programmers does it take to change a light bulb? None, that's hardware!",
        "Why do Java developers wear glasses? Because they don't C#! 👓",
    ]
    joke = random.choice(jokes)
    await update.message.reply_text(f"😂 {joke}")


async def dice_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    upsert_user(user)
    roll = random.randint(1, 6)

    row = get_user(user.id)
    prev_high = row["dice_highscore"] if row else 0
    if roll > prev_high:
        update_stat(user.id, "dice_highscore", roll, mode="set")
    update_stat(user.id, "dice_plays", 1, mode="inc")
    update_stat(user.id, "games_played", 1, mode="inc")

    await update.message.reply_text(f"🎲 You rolled: *{roll}*", parse_mode="Markdown")


async def quote_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    upsert_user(user)
    quotes = [
        "The only way to do great work is to love what you do. - Steve Jobs",
        "Innovation distinguishes between a leader and a follower. - Steve Jobs",
        "Life is what happens when you're busy making other plans. - John Lennon",
    ]
    quote = random.choice(quotes)
    await update.message.reply_text(f"✨ _{quote}_", parse_mode="Markdown")


# -------- Profile commands --------
async def profile_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    upsert_user(user)
    row = get_user(user.id)

    if not row:
        await update.message.reply_text("❌ No profile found. Try again.")
        return

    username = row["username"] or "No username"
    bio = row["bio"] or "No bio set."
    games = row["games_played"]
    dice_plays = row["dice_plays"]
    dice_high = row["dice_highscore"]
    rps_w = row["rps_wins"]
    rps_l = row["rps_losses"]
    rps_d = row["rps_draws"]

    text = (
        f"👤 *Your Profile:*\n\n"
        f"Username: @{username}\n"
        f"ID: `{row['id']}`\n\n"
        f"📝 *Bio:*\n{bio}\n\n"
        f"🎮 *Game Stats:*\n"
        f"• Total games: {games}\n"
        f"• Dice plays: {dice_plays}, High score: {dice_high}\n"
        f"• RPS - Wins: {rps_w}, Losses: {rps_l}, Draws: {rps_d}\n"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


async def setbio_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    upsert_user(user)

    if not context.args:
        await update.message.reply_text("Usage: `/setbio your bio here`", parse_mode="Markdown")
        return

    bio_text = " ".join(context.args)
    if len(bio_text) > 200:
        await update.message.reply_text("❗ Bio too long. Keep it under 200 characters.")
        return

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("UPDATE users SET bio = ? WHERE id = ?", (bio_text, user.id))
    conn.commit()
    conn.close()

    await update.message.reply_text("✅ Bio updated!", parse_mode="Markdown")


# -------- Leaderboard --------
async def leaderboard_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    upsert_user(user)

    rps_rows = get_leaderboard("rps_wins")
    dice_rows = get_leaderboard("dice_highscore")

    text = "🏆 *Leaderboard*\n\n"

    text += "🪨📄✂️ *RPS Wins:*\n"
    if rps_rows:
        for i, row in enumerate(rps_rows, start=1):
            name = row["username"] or row["first_name"] or "Unknown"
            text += f"{i}. {name} — {row['score']} wins\n"
    else:
        text += "No data yet.\n"

    text += "\n🎲 *Dice Highscore:*\n"
    if dice_rows:
        for i, row in enumerate(dice_rows, start=1):
            name = row["username"] or row["first_name"] or "Unknown"
            text += f"{i}. {name} — {row['score']}\n"
    else:
        text += "No data yet.\n"

    await update.message.reply_text(text, parse_mode="Markdown")


# -------- Admin --------
async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    upsert_user(user)

    if not is_admin(user):
        await update.message.reply_text("⛔ You are not allowed to access admin panel.")
        return

    user_count = get_user_count()
    text = (
        "🛠 *Admin Panel*\n\n"
        f"👥 Total users: {user_count}\n\n"
        "Commands:\n"
        "/broadcast <text> - Send message to all users\n"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_admin(user):
        await update.message.reply_text("⛔ You are not allowed to broadcast.")
        return

    if not context.args:
        await update.message.reply_text("Usage: `/broadcast your message`", parse_mode="Markdown")
        return

    message = " ".join(context.args)

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id FROM users")
    rows = cur.fetchall()
    conn.close()

    sent = 0
    failed = 0
    for row in rows:
        try:
            await context.bot.send_message(chat_id=row["id"], text=message)
            sent += 1
        except Exception as e:
            logger.warning("Failed to send broadcast to %s: %s", row["id"], e)
            failed += 1

    await update.message.reply_text(
        f"✅ Broadcast finished.\nSent: {sent}\nFailed: {failed}",
        parse_mode="Markdown",
    )


# -------------------- Callback Query Handler --------------------
async def handle_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    upsert_user(user)
    data = query.data

    row = get_user(user.id)
    fun_mode = bool(row["fun_mode"]) if row else True

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
            "/profile - Your stats\n"
            "/leaderboard - Top players\n"
        )
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=main_menu_keyboard())

    elif data == "about":
        await query.edit_message_text(
            "ℹ️ *About This Bot*\n\nTeleBot+ v2.0 - Learning project with profiles, stats and games.",
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
        row = get_user(user.id)
        prev_high = row["dice_highscore"] if row else 0
        if roll > prev_high:
            update_stat(user.id, "dice_highscore", roll, mode="set")
        update_stat(user.id, "dice_plays", 1, mode="inc")
        update_stat(user.id, "games_played", 1, mode="inc")

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

    elif data == "games":
        await query.edit_message_text(
            "🎮 *Games Menu*\n\nChoose a game:",
            parse_mode="Markdown",
            reply_markup=games_menu_keyboard(),
        )

    elif data == "settings":
        await query.edit_message_text(
            "⚙️ *Settings*\n\nToggle your preferences:",
            parse_mode="Markdown",
            reply_markup=settings_menu_keyboard(fun_mode),
        )

    elif data == "toggle_fun":
        new_fun_mode = not fun_mode
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("UPDATE users SET fun_mode = ? WHERE id = ?", (1 if new_fun_mode else 0, user.id))
        conn.commit()
        conn.close()

        await query.edit_message_text(
            "⚙️ *Settings*\n\nFun Mode updated!",
            parse_mode="Markdown",
            reply_markup=settings_menu_keyboard(new_fun_mode),
        )

    elif data == "back_main":
        await query.edit_message_text(
            "🏠 *Main Menu*\n\nChoose an option:",
            parse_mode="Markdown",
            reply_markup=main_menu_keyboard(),
        )

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

        if user_move == bot_move:
            result = "It's a draw! 🤝"
            update_stat(user.id, "rps_draws", 1, mode="inc")
        elif (
            (user_move == "Rock" and bot_move == "Scissors")
            or (user_move == "Paper" and bot_move == "Rock")
            or (user_move == "Scissors" and bot_move == "Paper")
        ):
            result = "You win! 🏆"
            update_stat(user.id, "rps_wins", 1, mode="inc")
        else:
            result = "I win! 😈"
            update_stat(user.id, "rps_losses", 1, mode="inc")

        update_stat(user.id, "games_played", 1, mode="inc")

        await query.edit_message_text(
            f"🪨📄✂️ *Rock-Paper-Scissors*\n\n"
            f"Your move: *{user_move}*\n"
            f"My move: *{bot_move}*\n\n"
            f"{result}",
            parse_mode="Markdown",
            reply_markup=games_menu_keyboard(),
        )

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

    elif data == "leaderboard":
        rps_rows = get_leaderboard("rps_wins")
        dice_rows = get_leaderboard("dice_highscore")
        text = "🏆 *Leaderboard*\n\n"

        text += "🪨📄✂️ *RPS Wins:*\n"
        if rps_rows:
            for i, row in enumerate(rps_rows, start=1):
                name = row["username"] or row["first_name"] or "Unknown"
                text += f"{i}. {name} — {row['score']} wins\n"
        else:
            text += "No data yet.\n"

        text += "\n🎲 *Dice Highscore:*\n"
        if dice_rows:
            for i, row in enumerate(dice_rows, start=1):
                name = row["username"] or row["first_name"] or "Unknown"
                text += f"{i}. {name} — {row['score']}\n"
        else:
            text += "No data yet.\n"

        await query.edit_message_text(
            text,
            parse_mode="Markdown",
            reply_markup=games_menu_keyboard(),
        )

    else:
        await query.edit_message_text(
            "❓ Unknown option!",
            reply_markup=main_menu_keyboard(),
        )


# -------------------- Text Handler (Guess Game + fallback) --------------------
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    upsert_user(user)
    text = update.message.text.strip()

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
            update_stat(user.id, "games_played", 1, mode="inc")
            context.user_data.pop("guess_number", None)
            context.user_data.pop("guess_attempts", None)
        return

    await update.message.reply_text(
        "💬 I didn't understand that.\nUse /help or press a button from the menu.",
    )


# -------------------- Welcome New Members --------------------
async def chat_member_update(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_member: ChatMemberUpdated = update.chat_member
    new = chat_member.new_chat_member
    old = chat_member.old_chat_member

    if (
        old.status in ("left", "kicked")
        and new.status == "member"
    ):
        user = new.user
        upsert_user(user)
        try:
            await context.bot.send_message(
                chat_id=chat_member.chat.id,
                text=f"👋 Welcome @{user.username or user.first_name} to this chat!",
            )
        except Exception as e:
            logger.warning("Failed to send welcome message: %s", e)


# -------------------- Main --------------------
def main():
    init_db()

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("time", time_command))
    app.add_handler(CommandHandler("me", me_command))
    app.add_handler(CommandHandler("info", info_command))
    app.add_handler(CommandHandler("joke", joke_command))
    app.add_handler(CommandHandler("dice", dice_command))
    app.add_handler(CommandHandler("quote", quote_command))
    app.add_handler(CommandHandler("profile", profile_command))
    app.add_handler(CommandHandler("setbio", setbio_command))
    app.add_handler(CommandHandler("leaderboard", leaderboard_command))
    app.add_handler(CommandHandler("admin", admin_command))
    app.add_handler(CommandHandler("broadcast", broadcast_command))

    app.add_handler(CallbackQueryHandler(handle_buttons))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    app.add_handler(ChatMemberHandler(chat_member_update, ChatMemberHandler.CHAT_MEMBER))

    logger.info("Bot is starting...")
    app.run_polling()


if __name__ == "__main__":
    main()
