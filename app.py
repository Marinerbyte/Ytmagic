import os
import logging
from threading import Thread
from flask import Flask
from pytube import YouTube, exceptions as PytubeExceptions
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
from telegram.constants import ParseMode

# === Logging Setup ===
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# === Configuration ===
# Yeh environment variable se token padhega.
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
# 50 MB limit in bytes
MAX_FILE_SIZE = 50 * 1024 * 1024 

# === Flask Web App (For Uptime) ===
app = Flask(__name__)

@app.route('/')
def home():
    """Web page to show bot status."""
    return "<h1>Bot is Alive!</h1><p>The YouTube downloader bot is running.</p>"

@app.route('/ping')
def ping():
    """Endpoint for UptimeRobot."""
    return "pong"

def run_flask():
    """Runs the Flask app in a separate thread."""
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

# === Telegram Bot Logic ===

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for /start command."""
    user = update.effective_user
    welcome_text = (
        f"Salaam, {user.mention_html()}!\n\n"
        "I am a YouTube Downloader Bot. Send me any YouTube video link.\n\n"
        "<b>Note:</b> I can only send video files smaller than 50 MB."
    )
    await update.message.reply_html(welcome_text)

async def link_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Processes YouTube links."""
    message_text = update.message.text
    if "youtube.com/" in message_text or "youtu.be/" in message_text:
        sent_message = await update.message.reply_text("⏳ Processing link, please wait...")
        
        try:
            yt = YouTube(message_text)
            
            streams = yt.streams.filter(progressive=True, file_extension='mp4').order_by('resolution').desc()
            
            keyboard = []
            for stream in streams:
                if stream.filesize and stream.filesize <= MAX_FILE_SIZE:
                    filesize_mb = round(stream.filesize / (1024 * 1024), 1)
                    button_text = f"{stream.resolution} ({filesize_mb} MB)"
                    callback_data = f"download|{yt.video_id}|{stream.itag}"
                    keyboard.append([InlineKeyboardButton(button_text, callback_data=callback_data)])

            if not keyboard:
                await sent_message.edit_text("😕 Sorry, no download options under 50 MB found for this video.")
                return

            reply_markup = InlineKeyboardMarkup(keyboard)
            await sent_message.edit_text(
                f"<b>Video:</b> {yt.title}\n\n"
                f"Select a quality to download:",
                reply_markup=reply_markup,
                parse_mode=ParseMode.HTML
            )

        except PytubeExceptions.RegexMatchError:
             await sent_message.edit_text("❌ Invalid YouTube link. Please send a valid one.")
        except Exception as e:
            logger.error(f"Error processing link: {e}")
            await sent_message.edit_text("❌ An unknown error occurred. The video might be private, age-restricted, or region-locked.")
    else:
        await update.message.reply_text("Please send a standard YouTube video link.")

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles button clicks for quality selection."""
    query = update.callback_query
    await query.answer()

    file_path = None
    try:
        action, video_id, itag = query.data.split('|')
        
        if action == "download":
            await query.edit_message_text(text="⬇️ Downloading video...")
            video_url = f"https://www.youtube.com/watch?v={video_id}"
            yt = YouTube(video_url)
            stream = yt.streams.get_by_itag(int(itag))
            
            # Use /tmp/ directory which is usually writable on hosting platforms
            file_path = stream.download(output_path='/tmp/', filename_prefix=video_id)
            
            await query.edit_message_text(text="⬆️ Uploading video...")

            with open(file_path, 'rb') as video_file:
                await context.bot.send_video(
                    chat_id=query.message.chat_id,
                    video=video_file,
                    caption=f"✅ Done: {yt.title}",
                    supports_streaming=True,
                    read_timeout=180, 
                    write_timeout=180
                )
            
            await query.delete_message()

    except Exception as e:
        logger.error(f"Error in button callback: {e}")
        try:
            await query.edit_message_text("❌ Download failed. There was a server-side issue.")
        except Exception:
            pass
    finally:
        # Clean up the downloaded file
        if file_path and os.path.exists(file_path):
            os.remove(file_path)
            logger.info(f"Cleaned up file: {file_path}")

def main():
    """Starts the bot and the web app."""
    if not TELEGRAM_TOKEN:
        logger.critical("FATAL ERROR: TELEGRAM_BOT_TOKEN environment variable is not set!")
        return

    logger.info("Starting application...")

    # Run Flask app in a background thread
    flask_thread = Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()
    logger.info("Flask server started in a background thread.")

    # Set up Telegram Bot
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    application.add_handler(CommandHandler(["start", "help"], start_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, link_handler))
    application.add_handler(CallbackQueryHandler(button_handler))
    
    logger.info("Starting Telegram Bot polling...")
    application.run_polling()

# This is the standard way to run a Python script.
if __name__ == '__main__':
    main()
