import os
import logging
from threading import Thread
from flask import Flask
from pytube import YouTube, exceptions as PytubeExceptions
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters

# Logging setup (optional but recommended for debugging)
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- CONFIGURATION ---
# Apna Telegram Bot Token environment variable se lein.
# Render/Replit par isse 'TELEGRAM_BOT_TOKEN' naam se set karein.
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
# 50 MB limit bytes mein
MAX_FILE_SIZE = 50 * 1024 * 1024 

# --- FLASK WEB APP PART (For Uptime) ---
# Yeh web app bot ko online rakhega
app = Flask(__name__)

@app.route('/')
def home():
    """Web interface jo bot ka status dikhata hai."""
    # Yeh HTML code web page par dikhega
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>TG YT Bot</title>
        <style>
            body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; 
                   display: flex; justify-content: center; align-items: center; height: 100vh; 
                   margin: 0; background-color: #0d1117; color: #c9d1d9; }
            .container { text-align: center; padding: 40px; background-color: #161b22; 
                         border: 1px solid #30363d; border-radius: 10px; }
            h1 { color: #58a6ff; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>Bot is Alive!</h1>
            <p>Aapka Telegram YouTube Downloader Bot chal raha hai.</p>
        </div>
    </body>
    </html>
    """

@app.route('/ping')
def ping():
    """UptimeRobot is endpoint ko ping karega."""
    return "pong"

def run_flask():
    """Flask app ko ek alag thread mein chalata hai."""
    # Hosting platforms jaise Render ke liye port dynamic hota hai.
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

# --- TELEGRAM BOT PART ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/start command ke liye handler."""
    user = update.effective_user
    await update.message.reply_html(
        f"Salaam {user.mention_html()}!\n\n"
        f"Muje koi bhi YouTube video ka link bhejein. Main aapko download karne ke liye options dunga.\n\n"
        f"<b>Note:</b> Sirf 50 MB se choti files hi download ho sakti hain."
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """YouTube links ko process karta hai."""
    message_text = update.message.text
    if "youtube.com/" in message_text or "youtu.be/" in message_text:
        sent_message = await update.message.reply_text("Link process ho raha hai, कृपया प्रतीक्षा करें...")
        
        try:
            yt = YouTube(message_text)
            
            # Progressive streams (video+audio) dhoondein jo 50MB se kam ho
            streams = yt.streams.filter(progressive=True, file_extension='mp4').order_by('resolution').desc()
            
            keyboard = []
            for stream in streams:
                if stream.filesize and stream.filesize <= MAX_FILE_SIZE:
                    filesize_mb = round(stream.filesize / (1024 * 1024), 1)
                    button_text = f"{stream.resolution} ({filesize_mb} MB)"
                    # Callback data mein video ID aur stream ka itag save karein
                    callback_data = f"download|{yt.video_id}|{stream.itag}"
                    keyboard.append([InlineKeyboardButton(button_text, callback_data=callback_data)])

            if not keyboard:
                await sent_message.edit_text("Maaf kijiye, is video ke liye 50 MB se kam ka koi download option uplabdh nahi hai.")
                return

            reply_markup = InlineKeyboardMarkup(keyboard)
            await sent_message.edit_text(
                f"<b>Video Title:</b> {yt.title}\n\n"
                f"Kripya download karne ke liye quality chunein:",
                reply_markup=reply_markup,
                parse_mode='HTML'
            )

        except PytubeExceptions.RegexMatchError:
             await sent_message.edit_text("Galat YouTube link. Kripya sahi link bhejein.")
        except Exception as e:
            logger.error(f"Error processing link: {e}")
            await sent_message.edit_text("Ek error aagaya hai. Ho sakta hai video private ho ya region-locked ho.")
    else:
        await update.message.reply_text("Yeh ek valid YouTube link nahi lag raha hai.")

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Quality selection button ke click ko handle karta hai."""
    query = update.callback_query
    await query.answer()

    try:
        action, video_id, itag = query.data.split('|')
        
        if action == "download":
            await query.edit_message_text(text="⬇️ Video download ho rahi hai...")

            video_url = f"https://www.youtube.com/watch?v={video_id}"
            yt = YouTube(video_url)
            stream = yt.streams.get_by_itag(int(itag))

            # Ek unique naam se file download karein
            file_path = stream.download(output_path='/tmp/', filename_prefix=f"{video_id}_")
            
            await query.edit_message_text(text="⬆️ Video upload ho rahi hai...")

            # User ko video bhejein
            with open(file_path, 'rb') as video_file:
                await context.bot.send_video(
                    chat_id=query.message.chat_id,
                    video=video_file,
                    caption=f"✅ Downloaded: {yt.title}",
                    supports_streaming=True,
                    read_timeout=120, # Lambi uploads ke liye timeout badhayein
                    write_timeout=120
                )
            
            # Original message ko delete kar dein
            await query.delete_message()

    except Exception as e:
        logger.error(f"Error in button callback: {e}")
        try:
            await query.edit_message_text("❌ Download fail ho gaya. Kripya dobara try karein.")
        except Exception as e_inner:
            logger.error(f"Could not edit message after fail: {e_inner}")
    finally:
        # Download ki hui file ko server se hamesha delete kar dein
        if 'file_path' in locals() and os.path.exists(file_path):
            os.remove(file_path)
            logger.info(f"Cleaned up file: {file_path}")

def main() -> None:
    """Telegram bot ko start karta hai aur Flask app ko background mein chalata hai."""
    if not TELEGRAM_TOKEN:
        logger.critical("TELEGRAM_BOT_TOKEN environment variable nahi mila! Bot shuru nahi ho sakta.")
        return
        
    application = Application.builder().token(TELEGRAM_TOKEN).build()

    # Handlers add karein
    application.add_handler(CommandHandler(["start", "help"], start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(CallbackQueryHandler(button_callback))
    
    # Flask app ko background mein chalayein
    flask_thread = Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()
    
    logger.info("Bot shuru ho gaya hai...")
    # Bot ko polling mode mein chalayein
    application.run_polling()

if __name__ == '__main__':
    main()
