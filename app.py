import os
import tempfile
import threading
import logging
from typing import Optional, List, Dict, Any
import asyncio

# Third-party imports
from flask import Flask, jsonify
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
from pytube import YouTube

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Flask app for uptime monitoring
app = Flask(__name__)

@app.route('/')
def status():
    """Root endpoint showing bot status."""
    return "Bot is Alive"

@app.route('/ping')
def ping():
    """Ping endpoint for uptime monitoring."""
    return "pong"

class YouTubeDownloader:
    """Handles YouTube video downloading and processing."""
    
    MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB in bytes
    
    @staticmethod
    def get_video_info(url: str) -> Optional[YouTube]:
        """Get YouTube video object from URL."""
        try:
            yt = YouTube(url)
            return yt
        except Exception as e:
            logger.error(f"Error getting video info: {e}")
            return None
    
    @staticmethod
    def get_progressive_streams(yt: YouTube) -> List[Dict[str, Any]]:
        """Get progressive mp4 streams under size limit."""
        try:
            streams = yt.streams.filter(progressive=True, file_extension='mp4')
            valid_streams = []
            
            for stream in streams:
                # Get file size
                file_size = stream.filesize
                if file_size and file_size <= YouTubeDownloader.MAX_FILE_SIZE:
                    valid_streams.append({
                        'itag': stream.itag,
                        'resolution': stream.resolution,
                        'fps': stream.fps,
                        'filesize': file_size,
                        'stream': stream
                    })
            
            # Sort by resolution (descending)
            valid_streams.sort(key=lambda x: int(x['resolution'].replace('p', '')) if x['resolution'] else 0, reverse=True)
            return valid_streams
            
        except Exception as e:
            logger.error(f"Error getting streams: {e}")
            return []
    
    @staticmethod
    def download_stream(stream, temp_dir: str) -> Optional[str]:
        """Download stream to temporary directory."""
        try:
            file_path = stream.download(output_path=temp_dir)
            return file_path
        except Exception as e:
            logger.error(f"Error downloading stream: {e}")
            return None

class TelegramBot:
    """Telegram bot for YouTube video downloads."""
    
    def __init__(self, token: str):
        self.token = token
        self.application = Application.builder().token(token).build()
        self.downloader = YouTubeDownloader()
        self._setup_handlers()
    
    def _setup_handlers(self):
        """Setup bot command and message handlers."""
        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(CommandHandler("help", self.help_command))
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))
        self.application.add_handler(CallbackQueryHandler(self.handle_callback))
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command."""
        welcome_message = (
            "🎥 *YouTube Downloader Bot*\n\n"
            "Send me a YouTube URL and I'll help you download it!\n\n"
            "Features:\n"
            "• Progressive MP4 downloads only\n"
            "• 50 MB file size limit\n"
            "• Quality selection\n\n"
            "Just send me any YouTube link to get started!"
        )
        await update.message.reply_text(welcome_message, parse_mode='Markdown')
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command."""
        help_message = (
            "🔗 *How to use:*\n\n"
            "1. Send me a YouTube URL\n"
            "2. Choose your preferred quality\n"
            "3. Wait for the download to complete\n"
            "4. Receive your video file!\n\n"
            "*Limitations:*\n"
            "• Maximum file size: 50 MB\n"
            "• Progressive MP4 streams only\n"
            "• One video at a time\n\n"
            "If you encounter any issues, make sure the YouTube URL is valid and the video is available."
        )
        await update.message.reply_text(help_message, parse_mode='Markdown')
    
    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle incoming text messages (YouTube URLs)."""
        message_text = update.message.text.strip()
        
        # Check if message contains YouTube URL
        if not self._is_youtube_url(message_text):
            await update.message.reply_text(
                "❌ Please send a valid YouTube URL.\n\n"
                "Supported formats:\n"
                "• https://www.youtube.com/watch?v=VIDEO_ID\n"
                "• https://youtu.be/VIDEO_ID\n"
                "• https://m.youtube.com/watch?v=VIDEO_ID"
            )
            return
        
        # Show processing message
        processing_msg = await update.message.reply_text("🔍 Processing YouTube URL...")
        
        try:
            # Get video info
            yt = self.downloader.get_video_info(message_text)
            if not yt:
                await processing_msg.edit_text("❌ Failed to get video information. Please check the URL and try again.")
                return
            
            # Get available streams
            streams = self.downloader.get_progressive_streams(yt)
            if not streams:
                await processing_msg.edit_text(
                    "❌ No suitable video streams found.\n\n"
                    "This could be because:\n"
                    "• All available qualities exceed 50 MB\n"
                    "• No progressive MP4 streams available\n"
                    "• Video is not accessible"
                )
                return
            
            # Create inline keyboard with quality options
            keyboard = []
            for stream in streams:
                size_mb = stream['filesize'] / (1024 * 1024)
                button_text = f"{stream['resolution']} ({size_mb:.1f} MB)"
                callback_data = f"download_{stream['itag']}_{update.message.chat.id}"
                keyboard.append([InlineKeyboardButton(button_text, callback_data=callback_data)])
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            video_info = (
                f"🎥 *{yt.title}*\n"
                f"👤 {yt.author}\n"
                f"⏱️ {self._format_duration(yt.length)}\n\n"
                f"📱 Choose quality to download:"
            )
            
            # Store video URL in context for callback
            context.user_data[f'video_url_{update.message.chat.id}'] = message_text
            
            await processing_msg.edit_text(video_info, parse_mode='Markdown', reply_markup=reply_markup)
            
        except Exception as e:
            logger.error(f"Error processing YouTube URL: {e}")
            await processing_msg.edit_text("❌ An error occurred while processing the video. Please try again.")
    
    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle callback queries from inline buttons."""
        query = update.callback_query
        await query.answer()
        
        try:
            # Parse callback data
            if not query.data.startswith("download_"):
                return
            
            parts = query.data.split("_")
            if len(parts) != 3:
                return
            
            itag = int(parts[1])
            chat_id = int(parts[2])
            
            # Get stored video URL
            video_url = context.user_data.get(f'video_url_{chat_id}')
            if not video_url:
                await query.edit_message_text("❌ Session expired. Please send the YouTube URL again.")
                return
            
            # Show downloading message
            await query.edit_message_text("⬬ Downloading video... Please wait.")
            
            # Get video and stream
            yt = self.downloader.get_video_info(video_url)
            if not yt:
                await query.edit_message_text("❌ Failed to get video information.")
                return
            
            # Find the selected stream
            stream = None
            for s in yt.streams:
                if s.itag == itag:
                    stream = s
                    break
            
            if not stream:
                await query.edit_message_text("❌ Selected quality is no longer available.")
                return
            
            # Create temporary directory
            with tempfile.TemporaryDirectory() as temp_dir:
                # Download video
                file_path = self.downloader.download_stream(stream, temp_dir)
                if not file_path:
                    await query.edit_message_text("❌ Failed to download video.")
                    return
                
                # Update message
                await query.edit_message_text("📤 Uploading video...")
                
                # Send video file
                with open(file_path, 'rb') as video_file:
                    await context.bot.send_video(
                        chat_id=chat_id,
                        video=video_file,
                        caption=f"🎥 {yt.title}\n👤 {yt.author}",
                        supports_streaming=True
                    )
                
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
            
