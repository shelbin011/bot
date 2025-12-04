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
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    CallbackQueryHandler,
    MessageHandler,
    filters,
)

import requests
from urllib.parse import quote_plus

# -------------------- Config --------------------
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

    # Users table
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            last_name TEXT,
            created_at TEXT,
            bio TEXT,
            xp INTEGER DEFAULT 0,
            level INTEGER DEFAULT 1,
            coins INTEGER DEFAULT 0,
            messages_count INTEGER DEFAULT 0,
            dice_plays INTEGER DEFAULT 0,
            dice_highscore INTEGER DEFAULT 0,
            games_played INTEGER DEFAULT 0,
            rps_wins INTEGER DEFAULT 0,
            rps_losses INTEGER DEFAULT 0,
            rps_draws INTEGER DEFAULT 0,
            birthday TEXT,
            last_daily TEXT
        )
        """
    )

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

    # Indexes for better leaderboard/stat performance
    cur.execute("CREATE INDEX IF NOT EXISTS idx_users_xp ON users (xp)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_users_coins ON users (coins)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_users_games ON users (games_played)")

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
    xp = row["xp"]
    new_level = 1 + xp // 100  # Simple formula: every 100 XP = +1 level
    if new_level > (row["level"] or 1):
        update_stat(user_id, "level", new_level, mode="set")


def get_leaderboard(field: str, limit: int = 5):
    """Generic leaderboard helper."""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        f"SELECT username, first_name, {field} as score FROM users "
        f"WHERE {field} > 0 ORDER BY {field} DESC LIMIT ?",
        (limit,),
    )
    rows = cur.fetchall()
    conn.close()
    return rows


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
            InlineKeyboardButton("🧾 Help", callback_data="help"),
            InlineKeyboardButton("⏰ Time", callback_data="time"),
        ],
        [
            InlineKeyboardButton("👤 Profile", callback_data="me"),
            InlineKeyboardButton("🎮 Games", callback_data="games"),
        ],
        [
            InlineKeyboardButton("🏆 Leaderboard", callback_data="leaderboard_btn"),
            InlineKeyboardButton("🎁 Daily", callback_data="daily_btn"),
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
            InlineKeyboardButton("⚡ Hangman", callback_data="game_hangman"),
            InlineKeyboardButton("⬆️⬇️ Higher/Lower", callback_data="game_hilo"),
        ],
        [
            InlineKeyboardButton("🧩 Anagram", callback_data="game_anagram"),
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
        "🤖 *Welcome to TeleMini!*\n\n"
        "A small multi-feature bot with:\n"
        "• Profiles, XP, level, coins\n"
        "• Games (RPS, Guess, Hangman, etc.)\n"
        "• Notes\n"
        "• Weather & URL shortener\n\n"
        "Use the buttons or commands below to get started.\n\n"
        "📌 *Quick Commands:*\n"
        "/help - Show all commands\n"
        "/profile - Your stats\n"
        "/note - Save a note\n"
        "/weather - Weather info\n"
        "/shorten - Shorten link\n"
        "/daily - Claim daily rewards\n"
        "/leaderboard - Top players\n"
        "/stats - Bot statistics\n"
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
        "🧩 *General:*\n"
        "/start - Show main menu\n"
        "/help - This help\n"
        "/time - Current time\n"
        "/me - Your username & ID\n\n"
        "👤 *Profile & Economy:*\n"
        "/profile - View your profile & stats\n"
        "/setbio <text> - Set your bio\n"
        "/setbirthday DD-MM - Set your birthday\n"
        "/balance - View XP, level & coins\n"
        "/daily - Claim daily rewards\n"
        "/leaderboard - View top players\n"
        "/stats - Bot statistics\n\n"
        "🎮 *Games:*\n"
        "Use the *Games* button or:\n"
        "/dice - Roll a dice\n"
        "/trivia - Trivia question\n"
        "/math - Math challenge\n\n"
        "📝 *Notes & Tools:*\n"
        "/note <text> - Save a note\n"
        "/notes - List your notes\n"
        "/deletenote <id> - Delete note\n"
        "/weather <city> - Weather info\n"
        "/shorten <url> - Shorten a link\n"
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

    add_xp_and_coins(user.id, xp_gain=10, coins_gain=5)

    await update.message.reply_text(f"🎲 You rolled: *{roll}*", parse_mode="Markdown")


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
    cur.execute("SELECT id, content FROM notes WHERE user_id = ? ORDER BY id DESC LIMIT 10", (user.id,))
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


# -------- Trivia & Math Commands (reuse game logic) --------
async def trivia_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    upsert_user(user)

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
    user = update.effective_user
    upsert_user(user)

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


# -------- Daily, Leaderboard, Stats --------
async def daily_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    upsert_user(user)
    row = get_user(user.id)

    today_str = date.today().isoformat()
    if row["last_daily"] == today_str:
        await update.message.reply_text("📅 You already claimed today's reward. Come back tomorrow! 🌞")
        return

    # reward
    add_xp_and_coins(user.id, xp_gain=30, coins_gain=25)

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("UPDATE users SET last_daily = ? WHERE id = ?", (today_str, user.id))
    conn.commit()
    conn.close()

    await update.message.reply_text(
        "🎁 *Daily Reward Claimed!*\n\n"
        "+30 XP\n+25 Coins\nCome back tomorrow!",
        parse_mode="Markdown",
    )


async def leaderboard_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    upsert_user(user)

    xp_rows = get_leaderboard("xp")
    coin_rows = get_leaderboard("coins")
    game_rows = get_leaderboard("games_played")

    def section(title, rows, suffix=""):
        s = title + "\n"
        if rows:
            for i, r in enumerate(rows, start=1):
                name = r["username"] or r["first_name"] or "Unknown"
                s += f"{i}. {name} — {r['score']}{suffix}\n"
        else:
            s += "No data yet.\n"
        s += "\n"
        return s

    text = "🏆 *Leaderboard*\n\n"
    text += section("✨ Top XP:", xp_rows, " XP")
    text += section("💰 Top Coins:", coin_rows, " coins")
    text += section("🎮 Top Gamers:", game_rows, " games")

    await update.message.reply_text(text, parse_mode="Markdown")


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    upsert_user(user)

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM users")
    users = cur.fetchone()[0]

    cur.execute("SELECT SUM(games_played), SUM(messages_count) FROM users")
    games_sum, msgs_sum = cur.fetchone()
    conn.close()

    games_sum = games_sum or 0
    msgs_sum = msgs_sum or 0

    await update.message.reply_text(
        f"📊 *Bot Stats*\n\n"
        f"👥 Total Users: {users}\n"
        f"🎮 Games Played: {games_sum}\n"
        f"💬 Messages Tracked: {msgs_sum}\n",
        parse_mode="Markdown",
    )


# -------------------- Callback Query Handler (Menus + Games) --------------------
async def handle_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    upsert_user(user)
    data = query.data

    if data == "help":
        text = (
            "📄 *Help Section:*\n\n"
            "/start - Main menu\n"
            "/help - Show commands\n"
            "/time - Current time\n"
            "/me - Your info\n"
            "/profile - Your stats\n"
            "/note - Save note\n"
            "/weather - Weather info\n"
            "/shorten - Short link\n"
            "/daily - Claim daily rewards\n"
            "/leaderboard - View top players\n"
            "/stats - Bot statistics\n"
        )
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=main_menu_keyboard())

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

    elif data == "games":
        await query.edit_message_text(
            "🎮 *Games Menu*\n\nChoose a game:",
            parse_mode="Markdown",
            reply_markup=games_menu_keyboard(),
        )

    elif data == "back_main":
        await query.edit_message_text(
            "🏠 *Main Menu*\n\nChoose an option:",
            parse_mode="Markdown",
            reply_markup=main_menu_keyboard(),
        )

    elif data == "leaderboard_btn":
        # Show leaderboard inside the main menu message
        xp_rows = get_leaderboard("xp")
        coin_rows = get_leaderboard("coins")
        game_rows = get_leaderboard("games_played")

        def section(title, rows, suffix=""):
            s = title + "\n"
            if rows:
                for i, r in enumerate(rows, start=1):
                    name = r["username"] or r["first_name"] or "Unknown"
                    s += f"{i}. {name} — {r['score']}{suffix}\n"
            else:
                s += "No data yet.\n"
            s += "\n"
            return s

        text = "🏆 *Leaderboard*\n\n"
        text += section("✨ Top XP:", xp_rows, " XP")
        text += section("💰 Top Coins:", coin_rows, " coins")
        text += section("🎮 Top Gamers:", game_rows, " games")

        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=main_menu_keyboard())

    elif data == "daily_btn":
        row = get_user(user.id)
        today_str = date.today().isoformat()
        if row["last_daily"] == today_str:
            await query.edit_message_text(
                "📅 You already claimed today's reward. Come back tomorrow! 🌞",
                parse_mode="Markdown",
                reply_markup=main_menu_keyboard(),
            )
        else:
            add_xp_and_coins(user.id, xp_gain=30, coins_gain=25)
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("UPDATE users SET last_daily = ? WHERE id = ?", (today_str, user.id))
            conn.commit()
            conn.close()
            await query.edit_message_text(
                "🎁 *Daily Reward Claimed!*\n\n"
                "+30 XP\n+25 Coins\nCome back tomorrow!",
                parse_mode="Markdown",
                reply_markup=main_menu_keyboard(),
            )

    # ----- RPS -----
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

    # ----- Guess Number -----
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

    # ----- Hangman -----
    elif data == "game_hangman":
        words = ["python", "telegram", "database", "crypto", "bot"]
        word = random.choice(words)
        context.user_data["hangman_word"] = word
        context.user_data["hangman_progress"] = ["_"] * len(word)
        context.user_data["hangman_attempts"] = 6

        await query.edit_message_text(
            f"⚡ *Hangman Game*\n\nWord: `{' '.join(context.user_data['hangman_progress'])}`\n"
            f"Attempts left: 6\n\nSend a single letter.",
            parse_mode="Markdown",
            reply_markup=games_menu_keyboard(),
        )

    # ----- Higher/Lower -----
    elif data == "game_hilo":
        number = random.randint(1, 50)
        context.user_data["hilo_current"] = number

        await query.edit_message_text(
            f"⬆️⬇️ *Higher or Lower*\n\nCurrent number: *{number}*\n"
            "Send: `higher` or `lower`",
            parse_mode="Markdown",
            reply_markup=games_menu_keyboard(),
        )

    # ----- Anagram -----
    elif data == "game_anagram":
        words = ["python", "telegram", "coding", "player", "random"]
        word = random.choice(words)
        scrambled = "".join(random.sample(word, len(word)))

        context.user_data["anagram_answer"] = word

        await query.edit_message_text(
            f"🧩 *Anagram Game*\n\nUnscramble this word:\n`{scrambled}`",
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
    text_msg = update.message.text.strip().lower()

    # Track messages for stats
    update_stat(user.id, "messages_count", 1, mode="inc")

    # ----- Guess-the-number -----
    if "guess_number" in context.user_data:
        try:
            guess = int(text_msg)
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

    # ----- Trivia answer -----
    if "trivia_answer" in context.user_data:
        correct = context.user_data["trivia_answer"]
        if text_msg == correct:
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

    # ----- Math challenge answer -----
    if "math_answer" in context.user_data:
        try:
            ans = int(text_msg)
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

    # ----- Hangman -----
    if "hangman_word" in context.user_data:
        letter = text_msg
        if len(letter) != 1 or not letter.isalpha():
            await update.message.reply_text("❗ Send only *one letter*.", parse_mode="Markdown")
            return

        word = context.user_data["hangman_word"]
        progress = context.user_data["hangman_progress"]

        if letter in word:
            for i, char in enumerate(word):
                if char == letter:
                    progress[i] = letter
            if "_" not in progress:
                update_stat(user.id, "games_played", 1, "inc")
                add_xp_and_coins(user.id, xp_gain=25, coins_gain=20)
                context.user_data.pop("hangman_word", None)
                context.user_data.pop("hangman_progress", None)
                context.user_data.pop("hangman_attempts", None)
                await update.message.reply_text(
                    f"🎉 You solved it! Word: *{word}*\n+25 XP, +20 coins!",
                    parse_mode="Markdown",
                )
            else:
                await update.message.reply_text(
                    "✨ Correct!\n" + " ".join(progress)
                )
        else:
            context.user_data["hangman_attempts"] -= 1
            if context.user_data["hangman_attempts"] <= 0:
                word = context.user_data.pop("hangman_word")
                context.user_data.pop("hangman_progress", None)
                context.user_data.pop("hangman_attempts", None)
                await update.message.reply_text(
                    f"💀 You lost! The word was *{word}*.",
                    parse_mode="Markdown",
                )
            else:
                attempts = context.user_data["hangman_attempts"]
                await update.message.reply_text(f"❌ Wrong!\nAttempts left: {attempts}")
        return

    # ----- Higher / Lower -----
    if "hilo_current" in context.user_data:
        guess = text_msg
        number = context.user_data["hilo_current"]
        new = random.randint(1, 50)
        context.user_data["hilo_current"] = new

        result = "higher" if new > number else "lower"
        if guess == result:
            add_xp_and_coins(user.id, xp_gain=10, coins_gain=5)
            msg = f"🎉 Correct! New number: *{new}*\n+10 XP +5 Coins"
        else:
            msg = f"❌ Wrong! It was *{new}*.\nGame over."
            context.user_data.pop("hilo_current", None)

        await update.message.reply_text(msg, parse_mode="Markdown")
        return

    # ----- Anagram -----
    if "anagram_answer" in context.user_data:
        correct = context.user_data["anagram_answer"]
        if text_msg == correct:
            add_xp_and_coins(user.id, xp_gain=20, coins_gain=10)
            context.user_data.pop("anagram_answer", None)
            await update.message.reply_text("🎉 Correct! +20 XP +10 coins")
        else:
            await update.message.reply_text("❌ Wrong! Try again.")
        return

    # Fallback
    await update.message.reply_text(
        "💬 I didn't understand that.\nUse /help or press a button from the menu.",
    )


# -------------------- Main --------------------
def main():
    init_db()

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # Core commands
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("time", time_command))
    app.add_handler(CommandHandler("me", me_command))

    # Profile & economy
    app.add_handler(CommandHandler("profile", profile_command))
    app.add_handler(CommandHandler("setbio", setbio_command))
    app.add_handler(CommandHandler("setbirthday", setbirthday_command))
    app.add_handler(CommandHandler("balance", balance_command))
    app.add_handler(CommandHandler("daily", daily_command))
    app.add_handler(CommandHandler("leaderboard", leaderboard_command))
    app.add_handler(CommandHandler("stats", stats_command))

    # Games commands
    app.add_handler(CommandHandler("dice", dice_command))
    app.add_handler(CommandHandler("trivia", trivia_cmd))
    app.add_handler(CommandHandler("math", math_cmd))

    # Notes & tools
    app.add_handler(CommandHandler("note", note_add_command))
    app.add_handler(CommandHandler("notes", notes_list_command))
    app.add_handler(CommandHandler("deletenote", note_delete_command))
    app.add_handler(CommandHandler("weather", weather_command))
    app.add_handler(CommandHandler("shorten", shorten_command))

    # Buttons & text
    app.add_handler(CallbackQueryHandler(handle_buttons))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    logger.info("Bot is starting...")
    app.run_polling()


if __name__ == "__main__":
    main()
