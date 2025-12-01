import os
import logging
import random
import sqlite3
from datetime import datetime, date

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

import requests
from urllib.parse import quote_plus

# -------------------- Config --------------------
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


def ensure_column(cur, table: str, column_def: str):
    """
    Ensure a column exists in a table, if not, add it.
    column_def e.g.: "xp INTEGER DEFAULT 0"
    """
    col_name = column_def.split()[0]
    cur.execute(f"PRAGMA table_info({table})")
    cols = [row[1] for row in cur.fetchall()]
    if col_name not in cols:
        cur.execute(f"ALTER TABLE {table} ADD COLUMN {column_def}")
        logger.info("Added column %s to %s", col_name, table)


def init_db():
    conn = get_db_connection()
    cur = conn.cursor()

    # Base users table (original structure)
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

    # New columns (will be added to existing DB if missing)
    new_columns = [
        "xp INTEGER DEFAULT 0",
        "level INTEGER DEFAULT 1",
        "coins INTEGER DEFAULT 0",
        "messages_count INTEGER DEFAULT 0",
        "last_daily TEXT",
        "last_daily_challenge TEXT",
        "birthday TEXT",
        "title TEXT",
        "warnings_count INTEGER DEFAULT 0",
    ]
    for col_def in new_columns:
        ensure_column(cur, "users", col_def)

    # Notes table
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            content TEXT,
            created_at TEXT
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


def add_xp_and_coins(user_id: int, xp_gain: int = 0, coins_gain: int = 0):
    """Add XP and coins, auto-level-up based on XP."""
    # Increase XP and coins
    if xp_gain:
        update_stat(user_id, "xp", xp_gain, "inc")
    if coins_gain:
        update_stat(user_id, "coins", coins_gain, "inc")

    # Recalculate level
    row = get_user(user_id)
    if not row:
        return
    xp = row["xp"] if "xp" in row.keys() else 0
    new_level = 1 + xp // 100  # Simple formula: every 100 XP = +1 level
    if new_level > (row["level"] or 1):
        update_stat(user_id, "level", new_level, mode="set")


def format_badges(row) -> str:
    badges = []
    if row["dice_highscore"] >= 6:
        badges.append("🎲 Dice Master")
    if row["rps_wins"] >= 10:
        badges.append("🥇 RPS Champion")
    if row["games_played"] >= 50:
        badges.append("🔥 Hardcore Gamer")
    if row["coins"] >= 1000:
        badges.append("💰 Rich Player")
    if row["messages_count"] >= 500:
        badges.append("💬 Chatterbox")

    if not badges:
        return "No badges yet. Keep playing! 🎮"
    return ", ".join(badges)


# -------------------- Env / Token --------------------
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
WEATHER_API_KEY = os.getenv("WEATHER_API_KEY")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN not found in .env or env vars!")


# -------------------- Keyboards --------------------
def main_menu_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [
            InlineKeyboardButton("📝 Help", callback_data="help"),
            InlineKeyboardButton("ℹ️ About", callback_data="about"),
        ],
        [
            InlineKeyboardButton("⏰ Time", callback_data="time"),
            InlineKeyboardButton("👤 Profile", callback_data="me"),
        ],
        [
            InlineKeyboardButton("😂 Joke", callback_data="joke"),
            InlineKeyboardButton("🎲 Dice", callback_data="dice"),
        ],
        [
            InlineKeyboardButton("✨ Quote", callback_data="quote"),
        ],
        [
            InlineKeyboardButton("🎮 Games", callback_data="games"),
            InlineKeyboardButton("⚙️ Settings", callback_data="settings"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


def games_menu_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [
            InlineKeyboardButton("🪨📄✂️ RPS", callback_data="game_rps"),
            InlineKeyboardButton("🔢 Guess Number", callback_data="game_guess"),
        ],
        [
            InlineKeyboardButton("🧠 Trivia", callback_data="game_trivia"),
            InlineKeyboardButton("➕ Math", callback_data="game_math"),
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
    status = "🟢 ON" if fun_mode else "🔴 OFF"
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
        "I'm a feature-rich Telegram bot with games, profiles, stats, notes, and more.\n\n"
        "📌 *Quick Commands:*\n"
        "• /help - See all commands\n"
        "• /time - Current time\n"
        "• /me - Your info\n"
        "• /profile - View your profile\n"
        "• /setbio <text> - Set your bio\n"
        "• /setbirthday DD-MM - Set your birthday\n"
        "• /balance - XP, level & coins\n"
        "• /leaderboard - Game rankings\n"
        "• /note <text> - Save a note\n"
        "• /notes - View notes\n"
        "• /weather <city> - Weather info\n"
        "• /shorten <url> - Shorten a link\n"
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
        "/quote - Get an inspirational quote\n\n"
        "👤 *Profile & Economy:*\n"
        "/profile - View your profile & stats\n"
        "/setbio <text> - Set your public bio\n"
        "/setbirthday DD-MM - Set your birthday\n"
        "/balance - View XP, level & coins\n"
        "/leaderboard - View top players\n\n"
        "🧠 *Games:*\n"
        "Use the *Games* menu button, or:\n"
        "/trivia - Start a trivia question\n"
        "/math - Start a math challenge\n\n"
        "📝 *Notes & Tools:*\n"
        "/note <text> - Save a note\n"
        "/notes - List your notes\n"
        "/deletenote <id> - Delete a note\n"
        "/weather <city> - Current weather (requires API key)\n"
        "/shorten <url> - Shorten a long URL\n"
        "/daily - Daily reward & quote\n\n"
        "🛠 *Admin (owner only):*\n"
        "/admin - Admin panel\n"
        "/broadcast <text> - Send message to all users\n"
        "/stats - Global stats\n"
        "/topactive - Top active users\n"
        "/warn - Reply to a user to warn\n"
        "/ban - Reply to ban a user\n"
        "/unban - Reply to unban\n"
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
        "🤖 *TeleBot+ v3.0*\n\n"
        "A learning project with admin tools, profiles, XP, coins, games, leaderboards, notes and more.",
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

    # rewards
    add_xp_and_coins(user.id, xp_gain=10, coins_gain=5)

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


# -------- Profile / XP / Economy --------
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
    xp = row["xp"]
    level = row["level"]
    coins = row["coins"]
    msgs = row["messages_count"]
    birthday = row["birthday"] or "Not set"
    title = row["title"] or "No title"
    badges = format_badges(row)

    # Birthday check
    bday_note = ""
    if row["birthday"]:
        try:
            day, month = map(int, row["birthday"].split("-"))
            today = date.today()
            if today.day == day and today.month == month:
                bday_note = "🎂 Happy Birthday!! 🎉\n\n"
        except Exception:
            pass

    text = (
        f"👤 *Your Profile:*\n\n"
        f"Username: @{username}\n"
        f"ID: `{row['id']}`\n"
        f"Title: {title}\n"
        f"Birthday: {birthday}\n\n"
        f"⭐ *Level:* {level}\n"
        f"✨ *XP:* {xp}\n"
        f"💰 *Coins:* {coins}\n"
        f"💬 Messages sent: {msgs}\n\n"
        f"📝 *Bio:*\n{bio}\n\n"
        f"🎮 *Game Stats:*\n"
        f"• Total games: {games}\n"
        f"• Dice plays: {dice_plays}, High score: {dice_high}\n"
        f"• RPS - Wins: {rps_w}, Losses: {rps_l}, Draws: {rps_d}\n\n"
        f"🏅 *Badges:*\n{badges}\n\n"
        f"{bday_note}"
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


async def setbirthday_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    upsert_user(user)

    if not context.args:
        await update.message.reply_text("Usage: `/setbirthday DD-MM`", parse_mode="Markdown")
        return

    bday = context.args[0]
    try:
        day, month = map(int, bday.split("-"))
        if not (1 <= day <= 31 and 1 <= month <= 12):
            raise ValueError()
    except Exception:
        await update.message.reply_text("❗ Invalid format. Use `DD-MM` (e.g. `05-08`).", parse_mode="Markdown")
        return

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("UPDATE users SET birthday = ? WHERE id = ?", (bday, user.id))
    conn.commit()
    conn.close()

    await update.message.reply_text("🎂 Birthday saved!", parse_mode="Markdown")


async def balance_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    upsert_user(user)
    row = get_user(user.id)

    xp = row["xp"]
    level = row["level"]
    coins = row["coins"]

    await update.message.reply_text(
        f"💰 *Your Balance:*\n\n"
        f"⭐ Level: {level}\n"
        f"✨ XP: {xp}\n"
        f"🪙 Coins: {coins}",
        parse_mode="Markdown",
    )


# -------- Notes & Tools --------
async def note_add_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    upsert_user(user)

    if not context.args:
        await update.message.reply_text("Usage: `/note your note text`", parse_mode="Markdown")
        return

    content = " ".join(context.args)
    now = datetime.utcnow().isoformat()

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO notes (user_id, content, created_at) VALUES (?, ?, ?)",
        (user.id, content, now),
    )
    conn.commit()
    conn.close()

    add_xp_and_coins(user.id, xp_gain=5, coins_gain=2)

    await update.message.reply_text("✅ Note saved!", parse_mode="Markdown")


async def notes_list_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    upsert_user(user)

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, content, created_at FROM notes WHERE user_id = ? ORDER BY id DESC LIMIT 10", (user.id,))
    rows = cur.fetchall()
    conn.close()

    if not rows:
        await update.message.reply_text("📝 You have no notes yet. Use `/note ...` to create one.", parse_mode="Markdown")
        return

    text = "📝 *Your Recent Notes:*\n\n"
    for row in rows:
        text += f"`{row['id']}` — {row['content']}\n"
    await update.message.reply_text(text, parse_mode="Markdown")


async def note_delete_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    upsert_user(user)

    if not context.args:
        await update.message.reply_text("Usage: `/deletenote note_id`", parse_mode="Markdown")
        return

    try:
        note_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❗ Note ID must be a number.")
        return

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM notes WHERE id = ? AND user_id = ?", (note_id, user.id))
    changes = cur.rowcount
    conn.commit()
    conn.close()

    if changes:
        await update.message.reply_text("✅ Note deleted.", parse_mode="Markdown")
    else:
        await update.message.reply_text("❌ Note not found.", parse_mode="Markdown")


async def weather_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    upsert_user(user)

    if not WEATHER_API_KEY:
        await update.message.reply_text(
            "⚠️ Weather API key not configured. Add `WEATHER_API_KEY` to your `.env`.",
            parse_mode="Markdown",
        )
        return

    if not context.args:
        await update.message.reply_text("Usage: `/weather city_name`", parse_mode="Markdown")
        return

    city = " ".join(context.args)
    try:
        url = (
            f"https://api.openweathermap.org/data/2.5/weather?q={quote_plus(city)}"
            f"&appid={WEATHER_API_KEY}&units=metric"
        )
        res = requests.get(url, timeout=10)
        data = res.json()
        if data.get("cod") != 200:
            await update.message.reply_text(f"❌ Couldn't find weather for *{city}*.", parse_mode="Markdown")
            return

        temp = data["main"]["temp"]
        desc = data["weather"][0]["description"].title()
        feels = data["main"]["feels_like"]
        text = (
            f"🌤 *Weather in {city.title()}:*\n\n"
            f"Temperature: *{temp}°C* (feels like {feels}°C)\n"
            f"Condition: *{desc}*"
        )
        await update.message.reply_text(text, parse_mode="Markdown")
    except Exception as e:
        logger.warning("Weather error: %s", e)
        await update.message.reply_text("⚠️ Failed to fetch weather.", parse_mode="Markdown")


async def shorten_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    upsert_user(user)

    if not context.args:
        await update.message.reply_text("Usage: `/shorten https://long-url.com`", parse_mode="Markdown")
        return

    url = context.args[0]
    try:
        res = requests.get("https://tinyurl.com/api-create.php", params={"url": url}, timeout=10)
        short = res.text.strip()
        await update.message.reply_text(
            f"🔗 *Short URL:*\n{short}",
            parse_mode="Markdown",
        )
    except Exception as e:
        logger.warning("Shorten error: %s", e)
        await update.message.reply_text("⚠️ Failed to shorten URL.", parse_mode="Markdown")


async def daily_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    upsert_user(user)
    row = get_user(user.id)

    today_str = date.today().isoformat()
    if row["last_daily"] == today_str:
        await update.message.reply_text("📅 You already claimed today's reward. Come back tomorrow! 🌞")
        return

    quotes = [
        "The future depends on what you do today. - Mahatma Gandhi",
        "Do something today that your future self will thank you for.",
        "Small steps every day lead to big results.",
    ]
    quote = random.choice(quotes)

    # reward
    add_xp_and_coins(user.id, xp_gain=25, coins_gain=20)

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("UPDATE users SET last_daily = ? WHERE id = ?", (today_str, user.id))
    conn.commit()
    conn.close()

    await update.message.reply_text(
        f"🎁 *Daily Reward Claimed!*\n\n"
        f"+25 XP, +20 Coins\n\n"
        f"✨ _{quote}_",
        parse_mode="Markdown",
    )


# -------- Leaderboard --------
async def leaderboard_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    upsert_user(user)

    rps_rows = get_leaderboard("rps_wins")
    dice_rows = get_leaderboard("dice_highscore")
    xp_rows = get_leaderboard("xp")

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

    text += "\n✨ *Top XP:*\n"
    if xp_rows:
        for i, row in enumerate(xp_rows, start=1):
            name = row["username"] or row["first_name"] or "Unknown"
            text += f"{i}. {name} — {row['score']} XP\n"
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
        "/stats - Global stats\n"
        "/topactive - Top active users\n"
        "/warn (reply) - Warn a user\n"
        "/ban (reply) - Ban a user\n"
        "/unban (reply) - Unban a user\n"
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


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_admin(user):
        await update.message.reply_text("⛔ Admins only.")
        return

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM users")
    (user_count,) = cur.fetchone()
    cur.execute("SELECT SUM(messages_count), SUM(games_played) FROM users")
    messages_sum, games_sum = cur.fetchone()
    conn.close()

    messages_sum = messages_sum or 0
    games_sum = games_sum or 0

    await update.message.reply_text(
        f"📊 *Bot Stats:*\n\n"
        f"👥 Users: {user_count}\n"
        f"💬 Total messages tracked: {messages_sum}\n"
        f"🎮 Total games played: {games_sum}\n",
        parse_mode="Markdown",
    )


async def topactive_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_admin(user):
        await update.message.reply_text("⛔ Admins only.")
        return

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT username, first_name, messages_count FROM users "
        "WHERE messages_count > 0 ORDER BY messages_count DESC LIMIT 5"
    )
    rows = cur.fetchall()
    conn.close()

    if not rows:
        await update.message.reply_text("No activity data yet.")
        return

    text = "💬 *Top Active Users:*\n\n"
    for i, row in enumerate(rows, start=1):
        name = row["username"] or row["first_name"] or "Unknown"
        text += f"{i}. {name} — {row['messages_count']} messages\n"

    await update.message.reply_text(text, parse_mode="Markdown")


async def warn_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_admin(user):
        await update.message.reply_text("⛔ Admins only.")
        return

    if not update.message.reply_to_message:
        await update.message.reply_text("Reply to a user's message to warn them.")
        return

    target = update.message.reply_to_message.from_user
    upsert_user(target)

    update_stat(target.id, "warnings_count", 1, mode="inc")
    row = get_user(target.id)
    warns = row["warnings_count"]

    await update.message.reply_text(
        f"⚠️ @{target.username or target.first_name} has been warned. "
        f"Total warnings: {warns}",
        parse_mode="Markdown",
    )


async def ban_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_admin(user):
        await update.message.reply_text("⛔ Admins only.")
        return

    if not update.message.reply_to_message:
        await update.message.reply_text("Reply to a user's message to ban them.")
        return

    target = update.message.reply_to_message.from_user

    try:
        await update.effective_chat.ban_member(target.id)
        await update.message.reply_text(
            f"⛔ User @{target.username or target.first_name} has been banned.",
            parse_mode="Markdown",
        )
    except Exception as e:
        logger.warning("Ban error: %s", e)
        await update.message.reply_text("⚠️ Failed to ban user.", parse_mode="Markdown")


async def unban_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_admin(user):
        await update.message.reply_text("⛔ Admins only.")
        return

    if not update.message.reply_to_message:
        await update.message.reply_text("Reply to a user's message to unban them.")
        return

    target = update.message.reply_to_message.from_user

    try:
        await update.effective_chat.unban_member(target.id)
        await update.message.reply_text(
            f"✅ User @{target.username or target.first_name} has been unbanned.",
            parse_mode="Markdown",
        )
    except Exception as e:
        logger.warning("Unban error: %s", e)
        await update.message.reply_text("⚠️ Failed to unban user.", parse_mode="Markdown")


# -------------------- Callback Query Handler (Games + Menus) --------------------
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
            "ℹ️ *About This Bot*\n\nTeleBot+ v3.0 - Learning project with profiles, XP, coins, stats and games.",
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
        add_xp_and_coins(user.id, xp_gain=10, coins_gain=5)

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
            add_xp_and_coins(user.id, xp_gain=5, coins_gain=2)
        elif (
            (user_move == "Rock" and bot_move == "Scissors")
            or (user_move == "Paper" and bot_move == "Rock")
            or (user_move == "Scissors" and bot_move == "Paper")
        ):
            result = "You win! 🏆"
            update_stat(user.id, "rps_wins", 1, mode="inc")
            add_xp_and_coins(user.id, xp_gain=15, coins_gain=10)
        else:
            result = "I win! 😈"
            update_stat(user.id, "rps_losses", 1, mode="inc")
            add_xp_and_coins(user.id, xp_gain=5, coins_gain=1)

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
        xp_rows = get_leaderboard("xp")
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

        text += "\n✨ *Top XP:*\n"
        if xp_rows:
            for i, row in enumerate(xp_rows, start=1):
                name = row["username"] or row["first_name"] or "Unknown"
                text += f"{i}. {name} — {row['score']} XP\n"
        else:
            text += "No data yet.\n"

        await query.edit_message_text(
            text,
            parse_mode="Markdown",
            reply_markup=games_menu_keyboard(),
        )

    elif data == "game_trivia":
        # small built-in trivia pool
        trivia_qs = [
            ("Which language is this bot written in?", "python"),
            ("What does HTML stand for? (abbr only)", "html"),
            ("Which company created Telegram?", "telegram"),
        ]
        q, ans = random.choice(trivia_qs)
        context.user_data["trivia_answer"] = ans.lower()
        await query.edit_message_text(
            "🧠 *Trivia Quiz!*\n\n"
            f"Q: {q}\n\n"
            "Send your answer as a message.",
            parse_mode="Markdown",
            reply_markup=games_menu_keyboard(),
        )

    elif data == "game_math":
        a = random.randint(1, 20)
        b = random.randint(1, 20)
        op = random.choice(["+", "-"])
        expr = f"{a} {op} {b}"
        answer = eval(expr)
        context.user_data["math_answer"] = answer
        await query.edit_message_text(
            "➕ *Math Challenge!*\n\n"
            f"Solve: `{expr}`\n"
            "Send your answer as a message.",
            parse_mode="Markdown",
            reply_markup=games_menu_keyboard(),
        )

    else:
        await query.edit_message_text(
            "❓ Unknown option!",
            reply_markup=main_menu_keyboard(),
        )


# -------------------- Text Handler (Games + fallback) --------------------
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    upsert_user(user)
    text = update.message.text.strip()

    # Track messages for stats
    update_stat(user.id, "messages_count", 1, mode="inc")

    # Guess-the-number game
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
            # reward depends on efficiency
            reward_xp = max(5, 20 - attempts * 2)
            reward_coins = max(3, 10 - attempts)
            add_xp_and_coins(user.id, xp_gain=reward_xp, coins_gain=reward_coins)

            context.user_data.pop("guess_number", None)
            context.user_data.pop("guess_attempts", None)
        return

    # Trivia answer
    if "trivia_answer" in context.user_data:
        correct = context.user_data["trivia_answer"]
        if text.lower().strip() == correct:
            await update.message.reply_text(
                "✅ Correct! +20 XP, +15 coins.",
                parse_mode="Markdown",
            )
            update_stat(user.id, "games_played", 1, mode="inc")
            add_xp_and_coins(user.id, xp_gain=20, coins_gain=15)
        else:
            await update.message.reply_text(
                f"❌ Incorrect. Correct answer was: *{correct}*.",
                parse_mode="Markdown",
            )
        context.user_data.pop("trivia_answer", None)
        return

    # Math challenge answer
    if "math_answer" in context.user_data:
        try:
            ans = int(text)
        except ValueError:
            await update.message.reply_text("❗ Please send a *number* answer.", parse_mode="Markdown")
            return
        correct = context.user_data["math_answer"]
        if ans == correct:
            await update.message.reply_text(
                "✅ Correct! +15 XP, +10 coins.",
                parse_mode="Markdown",
            )
            update_stat(user.id, "games_played", 1, mode="inc")
            add_xp_and_coins(user.id, xp_gain=15, coins_gain=10)
        else:
            await update.message.reply_text(
                f"❌ Incorrect. Correct answer was: *{correct}*.",
                parse_mode="Markdown",
            )
        context.user_data.pop("math_answer", None)
        return

    # Fallback
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

    # Core
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("time", time_command))
    app.add_handler(CommandHandler("me", me_command))
    app.add_handler(CommandHandler("info", info_command))
    app.add_handler(CommandHandler("joke", joke_command))
    app.add_handler(CommandHandler("dice", dice_command))
    app.add_handler(CommandHandler("quote", quote_command))

    # Profile / economy
    app.add_handler(CommandHandler("profile", profile_command))
    app.add_handler(CommandHandler("setbio", setbio_command))
    app.add_handler(CommandHandler("setbirthday", setbirthday_command))
    app.add_handler(CommandHandler("balance", balance_command))
    app.add_handler(CommandHandler("leaderboard", leaderboard_command))
    app.add_handler(CommandHandler("daily", daily_command))

    # Notes & tools
    app.add_handler(CommandHandler("note", note_add_command))
    app.add_handler(CommandHandler("notes", notes_list_command))
    app.add_handler(CommandHandler("deletenote", note_delete_command))
    app.add_handler(CommandHandler("weather", weather_command))
    app.add_handler(CommandHandler("shorten", shorten_command))

    # Games via commands (optional: /trivia, /math trigger same logic as buttons)
    async def trivia_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
        # Instead of faking callback, just reuse logic directly:
        trivia_qs = [
            ("Which language is this bot written in?", "python"),
            ("What does HTML stand for? (abbr only)", "html"),
            ("Which company created Telegram?", "telegram"),
        ]
        q, ans = random.choice(trivia_qs)
        context.user_data["trivia_answer"] = ans.lower()
        await update.message.reply_text(
            "🧠 *Trivia Quiz!*\n\n"
            f"Q: {q}\n\n"
            "Send your answer as a message.",
            parse_mode="Markdown",
        )

    async def math_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
        a = random.randint(1, 20)
        b = random.randint(1, 20)
        op = random.choice(["+", "-"])
        expr = f"{a} {op} {b}"
        answer = eval(expr)
        context.user_data["math_answer"] = answer
        await update.message.reply_text(
            "➕ *Math Challenge!*\n\n"
            f"Solve: `{expr}`\n"
            "Send your answer as a message.",
            parse_mode="Markdown",
        )

    app.add_handler(CommandHandler("trivia", trivia_cmd))
    app.add_handler(CommandHandler("math", math_cmd))

    # Admin
    app.add_handler(CommandHandler("admin", admin_command))
    app.add_handler(CommandHandler("broadcast", broadcast_command))
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(CommandHandler("topactive", topactive_command))
    app.add_handler(CommandHandler("warn", warn_command))
    app.add_handler(CommandHandler("ban", ban_command))
    app.add_handler(CommandHandler("unban", unban_command))

    # Buttons & text
    app.add_handler(CallbackQueryHandler(handle_buttons))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    # Welcome
    app.add_handler(ChatMemberHandler(chat_member_update, ChatMemberHandler.CHAT_MEMBER))

    logger.info("Bot is starting...")
    app.run_polling()


if __name__ == "__main__":
    main()
