import os
import logging
from threading import Thread
from flask import Flask
from pytube import YouTube, exceptions as PytubeExceptions
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
from telegram.constants import ParseMode

# === Logging Setup: Behtar debugging ke liye ===
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# === Configuration ===
try:
    TELEGRAM_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
    # 50 MB limit in bytes
    MAX_FILE_SIZE = 50 * 1024 * 1024 
except KeyError:
    logger.critical("FATAL ERROR: TELEGRAM_BOT_TOKEN environment variable nahi mila!")
    # Agar token nahi mila to program band ho jayega.
    exit()

# === Flask Web App (Bot ko Zinda Rakhne ke liye) ===
app = Flask(__name__)

@app.route('/')
def home():
    """Web page jo bot ka status dikhata hai."""
    return "<h1>Bot is Alive!</h1><p>Aapka YouTube downloader bot chal raha hai.</p>"

@app.route('/ping')
def ping():
    """UptimeRobot is endpoint ko ping karega."""
    return "pong"

def run_flask():
    """Flask app ko ek alag thread mein chalata hai."""
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

# === Telegram Bot Logic ===

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/start command ke liye handler."""
    user = update.effective_user
    welcome_text = (
        f"Salaam, {user.mention_html()}!\n\n"
        "Main ek YouTube Downloader Bot hoon. Muje koi bhi YouTube video ka link bhejein.\n\n"
        "<b>Note:</b> Main sirf 50 MB se choti video files hi bhej sakta hoon."
    )
    await update.message.reply_html(welcome_text)

async def link_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """YouTube links ko process karta hai."""
    message_text = update.message.text
    if "youtube.com/" in message_text or "youtu.be/" in message_text:
        sent_message = await update.message.reply_text("⏳ Link process ho raha hai, कृपया प्रतीक्षा करें...")
        
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
                await sent_message.edit_text("😕 Maaf kijiye, is video ke liye 50 MB se kam ka koi download option uplabdh nahi hai.")
                return

            reply_markup = InlineKeyboardMarkup(keyboard)
            await sent_message.edit_text(
                f"<b>Video:</b> {yt.title}\n\n"
                f"Download karne ke liye quality chunein:",
                reply_markup=reply_markup,
                parse_mode=ParseMode.HTML
            )

        except PytubeExceptions.RegexMatchError:
             await sent_message.edit_text("❌ Galat YouTube link. Kripya sahi link bhejein.")
        except Exception as e:
            logger.error(f"Link process karne mein error: {e}")
            await sent_message.edit_text("❌ Ek anjaan error aagaya. Ho sakta hai video private, age-restricted, ya region-locked ho.")
    else:
        await update.message.reply_text("Kripya ek aam YouTube video ka link bhejein.")

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Quality selection button ke click ko handle karta hai."""
    query = update.callback_query
    await query.answer()

    file_path = None # File path ko pehle se define kar dein
    try:
        action, video_id, itag = query.data.split('|')
        
        if action == "download":
            await query.edit_message_text(text="⬇️ Video download ho rahi hai...")
            video_url = f"https://www.youtube.com/watch?v={video_id}"
            yt = YouTube(video_url)
            stream = yt.streams.get_by_itag(int(itag))

            # /tmp/ folder ka istemal karein jo hosting platforms par aam taur par writable hota hai
            file_path = stream.download(output_path='/tmp/', filename_prefix=video_id)
            
            await query.edit_message_text(text="⬆️ Video upload ho rahi hai...")

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
        logger.error(f"Button callback mein error: {e}")
        try:
            await query.edit_message_text("❌ Download fail ho gaya. Server par koi samasya hui.")
        except Exception:
            pass # Agar message edit na ho sake to ignore karein
    finally:
        if file_path and os.path.exists(file_path):
            os.remove(file_path)
            logger.info(f"File saaf kar di gayi: {file_path}")

def main():
    """Bot aur Web App ko shuru karta hai."""
    logger.info("Application shuru ho rahi hai...")

    # Flask app ko background mein chalayein
    flask_thread = Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()
    logger.info("Flask server background mein shuru ho gaya hai.")

    # Telegram Bot setup
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    application.add_handler(CommandHandler(["start", "help"], start_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, link_handler))
    application.add_handler(CallbackQueryHandler(button_handler))
    
    logger.info("Telegram Bot polling shuru kar raha hai...")
    # Bot ko polling mode mein chalayein
    application.run_polling()

if __name__ == '__main__':
    main()                    )
                
                # Clean up - file will be automatically deleted when temp_dir exits
                
            # Update final message
            await query.edit_message_text("✅ Video sent successfully!")
            
            # Clean up user data
            context.user_data.pop(f'video_url_{chat_id}', None)
            
        except Exception as e:
            logger.error(f"Error in callback handler: {e}")
            await query.edit_message_text("❌ An error occurred during download. Please try again.")
    
    def _is_youtube_url(self, url: str) -> bool:
        """Check if URL is a valid YouTube URL."""
        youtube_domains = [
            'youtube.com',
            'www.youtube.com',
            'm.youtube.com',
            'youtu.be'
        ]
        return any(domain in url.lower() for domain in youtube_domains)
    
    def _format_duration(self, seconds: int) -> str:
        """Format duration in seconds to MM:SS or HH:MM:SS."""
        if seconds < 3600:
            return f"{seconds // 60}:{seconds % 60:02d}"
        else:
            hours = seconds // 3600
            minutes = (seconds % 3600) // 60
            seconds = seconds % 60
            return f"{hours}:{minutes:02d}:{seconds:02d}"
    
    async def start_bot(self):
        """Start the Telegram bot."""
        logger.info("Telegram bot started successfully")
        
        # Start polling for updates
        async with self.application:
            await self.application.start()
            await self.application.updater.start_polling()
            
            # Keep running until interrupted
            try:
                import signal
                import asyncio
                
                # Wait for interrupt signal
                stop_event = asyncio.Event()
                
                def signal_handler():
                    logger.info("Received stop signal, shutting down...")
                    stop_event.set()
                
                # Handle interrupt signals
                loop = asyncio.get_running_loop()
                for sig in (signal.SIGINT, signal.SIGTERM):
                    loop.add_signal_handler(sig, signal_handler)
                
                # Wait for stop signal
                await stop_event.wait()
                
            except Exception as e:
                logger.error(f"Error in bot main loop: {e}")
            finally:
                await self.application.updater.stop()
                await self.application.stop()

def run_flask_server():
    """Run Flask server in a separate thread."""
    logger.info("Starting Flask server on 0.0.0.0:5000")
    app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)

def run_telegram_bot():
    """Run Telegram bot in asyncio event loop."""
    # Get bot token from environment variable
    bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
    if not bot_token:
        logger.error("TELEGRAM_BOT_TOKEN environment variable not found!")
        return
    
    logger.info("Starting Telegram bot...")
    bot = TelegramBot(bot_token)
    
    # Run bot
    asyncio.run(bot.start_bot())

def main():
    """Main function to start both Flask server and Telegram bot."""
    logger.info("Starting YouTube Downloader Bot with Flask server...")
    
    # Start Flask server in a separate thread
    flask_thread = threading.Thread(target=run_flask_server, daemon=True)
    flask_thread.start()
    
    # Start Telegram bot in main thread
    try:
        run_telegram_bot()
    except KeyboardInterrupt:
        logger.info("Shutting down...")
    except Exception as e:
        logger.error(f"Error running bot: {e}")

if __name__ == '__main__':
    main()
            
