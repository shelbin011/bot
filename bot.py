from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, ContextTypes, CallbackQueryHandler, MessageHandler, filters, ConversationHandler
)
import os
from dotenv import load_dotenv
from datetime import datetime
import json
import sqlite3
from PIL import Image
import pytesseract
import anthropic

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
CLAUDE_API_KEY = os.getenv("CLAUDE_API_KEY")

# Database setup
def init_db():
    conn = sqlite3.connect('notes_bot.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS documents (
            doc_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            filename TEXT,
            extracted_text TEXT,
            notes TEXT,
            mcqs TEXT,
            summary TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(user_id)
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# States for conversation
AWAITING_IMAGE, PROCESSING, MENU = range(3)

# Initialize Anthropic client
client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)

# ==================== DATABASE FUNCTIONS ====================
def save_user(user_id, username):
    conn = sqlite3.connect('notes_bot.db')
    cursor = conn.cursor()
    cursor.execute('INSERT OR IGNORE INTO users VALUES (?, ?, ?)', (user_id, username, datetime.now()))
    conn.commit()
    conn.close()

def save_document(user_id, filename, extracted_text, notes, mcqs, summary):
    conn = sqlite3.connect('notes_bot.db')
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO documents (user_id, filename, extracted_text, notes, mcqs, summary)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (user_id, filename, extracted_text, notes, mcqs, summary))
    conn.commit()
    conn.close()

def get_user_documents(user_id):
    conn = sqlite3.connect('notes_bot.db')
    cursor = conn.cursor()
    cursor.execute('SELECT doc_id, filename FROM documents WHERE user_id = ? ORDER BY created_at DESC LIMIT 10', (user_id,))
    docs = cursor.fetchall()
    conn.close()
    return docs

def get_document(doc_id):
    conn = sqlite3.connect('notes_bot.db')
    cursor = conn.cursor()
    cursor.execute('SELECT extracted_text, notes, mcqs, summary FROM documents WHERE doc_id = ?', (doc_id,))
    doc = cursor.fetchone()
    conn.close()
    return doc

# ==================== IMAGE PROCESSING ====================
def extract_text_from_image(image_path):
    """Extract text from image using OCR"""
    try:
        image = Image.open(image_path)
        text = pytesseract.image_to_string(image)
        return text if text.strip() else "No text detected. Please upload a clearer image."
    except Exception as e:
        return f"Error extracting text: {str(e)}"

# ==================== CLAUDE AI FUNCTIONS ====================
async def generate_notes(extracted_text):
    """Generate study notes from extracted text using Claude"""
    try:
        message = client.messages.create(
            model="claude-3-5-haiku-20241022",
            max_tokens=2000,
            messages=[
                {
                    "role": "user",
                    "content": f"""Create concise study notes from this text. Format:
- Use bullet points
- Highlight key concepts
- Keep it organized by topic
- Max 500 words

Text:
{extracted_text[:3000]}"""
                }
            ]
        )
        return message.content[0].text
    except Exception as e:
        return f"Error generating notes: {str(e)}"

async def generate_mcqs(extracted_text):
    """Generate MCQs from extracted text using Claude"""
    try:
        message = client.messages.create(
            model="claude-3-5-haiku-20241022",
            max_tokens=1500,
            messages=[
                {
                    "role": "user",
                    "content": f"""Generate 5 multiple-choice questions from this text. Format each as:

Q1: [Question]
A) [Option A]
B) [Option B]
C) [Option C]
D) [Option D]
Answer: [Correct option]

Text:
{extracted_text[:3000]}"""
                }
            ]
        )
        return message.content[0].text
    except Exception as e:
        return f"Error generating MCQs: {str(e)}"

async def generate_summary(extracted_text):
    """Generate chapter summary using Claude"""
    try:
        message = client.messages.create(
            model="claude-3-5-haiku-20241022",
            max_tokens=1000,
            messages=[
                {
                    "role": "user",
                    "content": f"""Write a brief summary (200-300 words) of this text suitable for exam preparation:

{extracted_text[:3000]}"""
                }
            ]
        )
        return message.content[0].text
    except Exception as e:
        return f"Error generating summary: {str(e)}"

# ==================== COMMAND HANDLERS ====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    save_user(user.id, user.username or user.first_name)
    
    keyboard = [
        [InlineKeyboardButton("📸 Upload Screenshot", callback_data="upload")],
        [InlineKeyboardButton("📚 My Documents", callback_data="my_docs")],
        [InlineKeyboardButton("ℹ️ About", callback_data="about")],
        [InlineKeyboardButton("📖 Help", callback_data="help")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    welcome_text = """
🎓 **Exam Notes Generator Bot**

Convert your textbook screenshots into:
✅ Study Notes
✅ MCQ Questions
✅ Chapter Summaries

**How to use:**
1. Upload a textbook screenshot
2. Select what you want to generate
3. Get instant study materials!

Perfect for exam preparation! 📝
"""
    await update.message.reply_text(welcome_text, reply_markup=reply_markup, parse_mode="Markdown")
    return MENU

async def upload_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("📸 Please upload a screenshot of your textbook page.\n\nSupported formats: JPG, PNG")
    return AWAITING_IMAGE

async def process_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Process uploaded image"""
    message = update.message
    user = update.effective_user
    
    if not message.photo:
        await message.reply_text("❌ Please upload an image!")
        return AWAITING_IMAGE
    
    # Download image
    photo_file = await message.photo[-1].get_file()
    image_path = f"temp_{user.id}.jpg"
    await photo_file.download_to_drive(image_path)
    
    # Extract text
    await message.reply_text("⏳ Extracting text from image...")
    extracted_text = extract_text_from_image(image_path)
    
    if not extracted_text or "Error" in extracted_text or "No text" in extracted_text:
        await message.reply_text(f"❌ {extracted_text}")
        os.remove(image_path)
        return MENU
    
    # Store extracted text in context
    context.user_data['extracted_text'] = extracted_text
    context.user_data['image_path'] = image_path
    
    # Show options
    keyboard = [
        [InlineKeyboardButton("📝 Generate Notes", callback_data="gen_notes")],
        [InlineKeyboardButton("❓ Generate MCQs", callback_data="gen_mcqs")],
        [InlineKeyboardButton("📖 Generate Summary", callback_data="gen_summary")],
        [InlineKeyboardButton("🔄 Generate All", callback_data="gen_all")],
        [InlineKeyboardButton("↩️ Back to Menu", callback_data="back_menu")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    preview = extracted_text[:200] + "..." if len(extracted_text) > 200 else extracted_text
    await message.reply_text(f"✅ **Text Extracted Successfully!**\n\nPreview:\n```\n{preview}\n```\n\nWhat would you like to generate?", 
                           reply_markup=reply_markup, parse_mode="Markdown")
    return PROCESSING

async def handle_generation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle different generation options"""
    query = update.callback_query
    await query.answer()
    
    extracted_text = context.user_data.get('extracted_text', '')
    
    if query.data == "gen_notes":
        await query.edit_message_text("⏳ Generating study notes...")
        notes = await generate_notes(extracted_text)
        await query.message.reply_text(f"📝 **Study Notes:**\n\n{notes}", parse_mode="Markdown")
    
    elif query.data == "gen_mcqs":
        await query.edit_message_text("⏳ Generating MCQ questions...")
        mcqs = await generate_mcqs(extracted_text)
        await query.message.reply_text(f"❓ **MCQ Questions:**\n\n{mcqs}", parse_mode="Markdown")
    
    elif query.data == "gen_summary":
        await query.edit_message_text("⏳ Generating summary...")
        summary = await generate_summary(extracted_text)
        await query.message.reply_text(f"📖 **Chapter Summary:**\n\n{summary}", parse_mode="Markdown")
    
    elif query.data == "gen_all":
        await query.edit_message_text("⏳ Generating all study materials...")
        notes = await generate_notes(extracted_text)
        mcqs = await generate_mcqs(extracted_text)
        summary = await generate_summary(extracted_text)
        
        # Save to database
        save_document(update.effective_user.id, "screenshot", extracted_text, notes, mcqs, summary)
        
        await query.message.reply_text(f"📝 **Study Notes:**\n\n{notes}\n\n❓ **MCQs:**\n\n{mcqs}\n\n📖 **Summary:**\n\n{summary}", 
                                     parse_mode="Markdown")
    
    elif query.data == "back_menu":
        keyboard = [
            [InlineKeyboardButton("📸 Upload Screenshot", callback_data="upload")],
            [InlineKeyboardButton("📚 My Documents", callback_data="my_docs")],
            [InlineKeyboardButton("ℹ️ About", callback_data="about")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("🎓 **Exam Notes Generator Bot**\n\nChoose an option:", reply_markup=reply_markup)
        return MENU
    
    return PROCESSING

async def my_documents(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show user's saved documents"""
    query = update.callback_query
    await query.answer()
    
    user = update.effective_user
    docs = get_user_documents(user.id)
    
    if not docs:
        await query.edit_message_text("📚 No documents saved yet. Upload your first screenshot!")
        return
    
    keyboard = [[InlineKeyboardButton(f"📄 {filename}", callback_data=f"doc_{doc_id}")] for doc_id, filename in docs]
    keyboard.append([InlineKeyboardButton("↩️ Back", callback_data="back_menu")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text("📚 **Your Saved Documents:**", reply_markup=reply_markup)

async def view_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """View saved document"""
    query = update.callback_query
    await query.answer()
    
    doc_id = query.data.split('_')[1]
    doc = get_document(doc_id)
    
    if doc:
        extracted_text, notes, mcqs, summary = doc
        await query.message.reply_text(f"📝 **Notes:**\n{notes}\n\n❓ **MCQs:**\n{mcqs}\n\n📖 **Summary:**\n{summary}", 
                                     parse_mode="Markdown")

async def about(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """About bot"""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "🎓 **Exam Notes Generator Bot v2.0**\n\n"
        "📸 Upload textbook screenshots\n"
        "✅ Get instant study notes\n"
        "✅ Generate MCQ questions\n"
        "✅ Create chapter summaries\n\n"
        "Powered by Claude AI + Tesseract OCR\n"
        "Perfect for exam preparation! 📚"
    )

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Help command"""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "📖 **How to Use:**\n\n"
        "1️⃣ Click 'Upload Screenshot'\n"
        "2️⃣ Send your textbook image\n"
        "3️⃣ Choose what to generate\n"
        "4️⃣ Get study materials!\n\n"
        "💡 Tips:\n"
        "• Use clear, well-lit photos\n"
        "• Ensure text is readable\n"
        "• Try different options\n"
        "• Save your documents"
    )

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    
    # Conversation handler
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            MENU: [CallbackQueryHandler(upload_handler, pattern="^upload$"),
                   CallbackQueryHandler(my_documents, pattern="^my_docs$"),
                   CallbackQueryHandler(about, pattern="^about$"),
                   CallbackQueryHandler(help_cmd, pattern="^help$")],
            AWAITING_IMAGE: [MessageHandler(filters.PHOTO, process_image)],
            PROCESSING: [CallbackQueryHandler(handle_generation)],
        },
        fallbacks=[CommandHandler("start", start)],
    )
    
    app.add_handler(conv_handler)
    app.run_polling()

if __name__ == "__main__":
    main()