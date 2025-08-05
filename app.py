# ========================================================================================
# === 1. IMPORTS & SETUP =================================================================
# ========================================================================================
import os
import logging
import asyncio
from flask import Flask, request
from pytube import YouTube, exceptions as PytubeExceptions
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Bot
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
from telegram.constants import ParseMode

# ========================================================================================
# === 2. LOGGING SETUP ===================================================================
# ========================================================================================
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ========================================================================================
# === 3. CONFIGURATION ===================================================================
# ========================================================================================
class Config:
    """Saari application settings ek jagah par."""
    try:
        TELEGRAM_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
        WEBHOOK_URL = os.environ["WEBHOOK_URL"]
    except KeyError as e:
        logger.critical(f"FATAL: Environment variable {e} set nahi hai! App band ho raha hai.")
        exit()
        
    MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB
    DOWNLOAD_PATH = '/tmp/' # Hosting platforms ke liye temporary directory

# ========================================================================================
# === 4. CORE BOT & WEB APP INITIALIZATION ===============================================
# ========================================================================================
bot = Bot(token=Config.TELEGRAM_TOKEN)
application = Application.builder().bot(bot).build()
app = Flask(__name__) # Yeh 'app' gunicorn ke liye zaroori hai

# ========================================================================================
# === 5. TELEGRAM HELPER FUNCTIONS =======================================================
# ========================================================================================
async def download_video_from_yt(video_id: str, itag: int):
    """YouTube se video download karta hai aur file path return karta hai."""
    try:
        video_url = f"https://www.youtube.com/watch?v={video_id}"
        yt = YouTube(video_url)
        stream = yt.streams.get_by_itag(itag)
        logger.info(f"Downloading '{yt.title}' with itag {itag}")
        file_path = stream.download(output_path=Config.DOWNLOAD_PATH, filename_prefix=f"{video_id}_{itag}_")
        return file_path, yt.title
    except Exception as e:
        logger.error(f"Download helper mein error: {e}")
        return None, None

def cleanup_file(file_path: str):
    """Server se file delete karta hai."""
    if file_path and os.path.exists(file_path):
        os.remove(file_path)
        logger.info(f"File saaf kar di gayi: {file_path}")

# ========================================================================================
# === 6. TELEGRAM COMMAND & MESSAGE HANDLERS =============================================
# ========================================================================================
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await update.message.reply_html(
        f"Salaam, {user.mention_html()}!\n\n"
        "Main ek YouTube Downloader Bot hoon. Muje koi bhi YouTube video ka link bhejein."
    )

async def link_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message_text = update.message.text
    if "youtube.com/" not in message_text and "youtu.be/" not in message_text:
        return await update.message.reply_text("Kripya ek aam YouTube video ka link bhejein.")
        
    sent_message = await update.message.reply_text("⏳ Link process ho raha hai...")
    try:
        yt = YouTube(message_text)
        streams = yt.streams.filter(progressive=True, file_extension='mp4').order_by('resolution').desc()
        
        keyboard = []
        for stream in streams:
            if stream.filesize and stream.filesize <= Config.MAX_FILE_SIZE:
                filesize_mb = round(stream.filesize / (1024 * 1024), 1)
                button_text = f"{stream.resolution} ({filesize_mb} MB)"
                callback_data = f"download|{yt.video_id}|{stream.itag}"
                keyboard.append([InlineKeyboardButton(button_text, callback_data=callback_data)])

        if not keyboard:
            return await sent_message.edit_text("😕 Maaf kijiye, 50 MB se kam ka koi option nahi mila.")

        reply_markup = InlineKeyboardMarkup(keyboard)
        await sent_message.edit_text(
            f"<b>Video:</b> {yt.title}\n\nDownload karne ke liye quality chunein:",
            reply_markup=reply_markup, parse_mode=ParseMode.HTML
        )
    except Exception as e:
        logger.error(f"Link process karne mein error: {e}")
        await sent_message.edit_text("❌ Error: Video private ya unavailable ho sakti hai.")

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    file_path = None
    try:
        action, video_id, itag_str = query.data.split('|')
        itag = int(itag_str)

        if action == "download":
            await query.edit_message_text(text="⬇️ Downloading video...")
            file_path, video_title = await download_video_from_yt(video_id, itag)

            if not file_path:
                return await query.edit_message_text("❌ Download fail ho gaya.")

            await query.edit_message_text(text="⬆️ Uploading video...")
            with open(file_path, 'rb') as video_file:
                await context.bot.send_video(
                    chat_id=query.message.chat_id, video=video_file,
                    caption=f"✅ Done: {video_title}", supports_streaming=True
                )
            await query.delete_message()
    except Exception as e:
        logger.error(f"Button callback mein error: {e}")
        try:
            await query.edit_message_text("❌ Ek anjaan samasya hui.")
        except: pass
    finally:
        cleanup_file(file_path)

# ========================================================================================
# === 7. WEB APP (FLASK) ROUTES ==========================================================
# ========================================================================================

# Handlers ko Application mein add karein
application.add_handler(CommandHandler(["start", "help"], start_command))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, link_handler))
application.add_handler(CallbackQueryHandler(button_handler))

# Yeh route Telegram se aane wale updates ko handle karega
@app.route(f"/{Config.TELEGRAM_TOKEN}", methods=["POST"])
async def webhook():
    update = Update.de_json(request.get_json(force=True), bot)
    await application.process_update(update)
    return "ok"

# *** YAHAN PAR GALTI THEEK KI GAYI HAI ***
# Ek route webhook ko set karne ke liye (sirf ek baar run karna hai)
@app.route("/set_webhook", methods=['GET', 'POST'])
def set_webhook():
    # Sahi URL banayein
    webhook_url_to_set = f"{Config.WEBHOOK_URL}/{Config.TELEGRAM_TOKEN}"
    
    # Webhook set karein
    was_set = asyncio.run(bot.set_webhook(url=webhook_url_to_set))
    
    if was_set:
        return f"Webhook set to {webhook_url_to_set}: {was_set}"
    else:
        return f"Webhook setup failed for {webhook_url_to_set}"

@app.route("/")
def index():
    return "<h1>Bot is alive!</h1>"
