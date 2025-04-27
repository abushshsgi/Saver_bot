import os
import logging
import asyncio
import tempfile
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse, urljoin
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from flask import Flask
from models import init_db, User, Download, db
import gc
import telebot
from config import (
    BOT_TOKEN, WELCOME_MESSAGE, DOWNLOAD_SUCCESS_MESSAGE, 
    INVALID_URL_MESSAGE, PROCESSING_MESSAGE, ERROR_MESSAGE,
    DONATION_TEXT, DONATION_URL, SQLALCHEMY_DATABASE_URI
)
from url_validator import get_url_type
from downloaders import (
    download_youtube_video, 
    download_instagram_video, 
    download_twitter_video,
    download_facebook_video,
    DownloadError
)
from keyboards import get_donation_keyboard
from service import get_or_create_user, record_download, record_donation_click, get_user_stats
from datetime import datetime
import re
import yt_dlp
import sys

# Loyihangiz joylashgan papkani sys.path ga qo'shing
project_home = '/home/YOUR_USERNAME/MediaSaverBot'
if project_home not in sys.path:
    sys.path = [project_home] + sys.path

# Initialize Flask for database
bot_app = Flask(__name__)
bot_app.config['SQLALCHEMY_DATABASE_URI'] = SQLALCHEMY_DATABASE_URI
bot_app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
init_db(bot_app)

# Set up logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Active downloads tracking
active_downloads = {}

# Bot obyektini yaratish
bot = telebot.TeleBot(BOT_TOKEN)

def detect_platform(url):
    """URL dan platformani aniqlash"""
    if 'youtube.com' in url or 'youtu.be' in url:
        return 'youtube'
    elif 'instagram.com' in url:
        return 'instagram'
    elif 'tiktok.com' in url:
        return 'tiktok'
    elif 'facebook.com' in url or 'fb.com' in url:
        return 'facebook'
    elif 'twitter.com' in url or 'x.com' in url:
        return 'twitter'
    return 'unknown'

def is_valid_url(url):
    """URL validatsiyasi"""
    url_pattern = re.compile(
        r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+'
    )
    return bool(url_pattern.match(url))

def download_video(url, platform):
    """Video yuklab olish"""
    try:
        # TikTok uchun yuklashni butunlay bloklash
        if platform == 'tiktok':
            raise Exception("TikTok videolarini yuklab bo'lmaydi. Ushbu platforma qo'llab-quvvatlanmaydi.")
        # Vaqtinchalik fayl yaratish
        temp_dir = tempfile.mkdtemp()
        output_template = os.path.join(temp_dir, '%(title)s.%(ext)s')
        # Asosiy sozlamalar
        ydl_opts = {
            'format': 'best[filesize<50M]/mp4',
            'outtmpl': output_template,
            'quiet': False,
            'no_warnings': False,
            'extract_flat': False,
            'ignoreerrors': False,
            'nocheckcertificate': True,
            'no_color': True,
            'noprogress': True,
            'socket_timeout': 30,
            'retries': 10,
            'fragment_retries': 10,
            'concurrent_fragment_downloads': 10
        }
        # Platform-specific sozlamalar
        if platform == 'instagram':
            ydl_opts.update({
                'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
                'extract_flat': False,
                'no_check_formats': True,
                'http_headers': {
                    'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 12_3_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 Instagram 105.0.0.11.118 (iPhone11,8; iOS 12_3_1; en_US; en-US; scale=2.00; 828x1792; 165586599)',
                    'Accept': '*/*',
                    'Accept-Language': 'en-US,en;q=0.5',
                    'Accept-Encoding': 'gzip, deflate',
                    'Origin': 'https://www.instagram.com',
                    'DNT': '1',
                    'Connection': 'keep-alive'
                }
            })
        elif platform == 'youtube':
            ydl_opts.update({
                'format': 'best[filesize<50M]/mp4',
                'merge_output_format': 'mp4'
            })
        # Video yuklab olish
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            try:
                logger.info(f"Video yuklanmoqda: {url}")
                try:
                    video_info = ydl.extract_info(url, download=True)
                    if video_info is None:
                        raise Exception("Video ma'lumotlarini olishda xatolik")
                except Exception as e:
                    logger.error(f"Birinchi urinish xatoligi: {str(e)}")
                    ydl_opts['format'] = 'best'
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl2:
                        video_info = ydl2.extract_info(url, download=True)
                        if video_info is None:
                            raise Exception("Video ma'lumotlarini olishda xatolik")
                video_path = ydl.prepare_filename(video_info)
                if not os.path.exists(video_path):
                    raise Exception("Video yuklab olinmadi")
                file_size = os.path.getsize(video_path)
                if file_size > 50 * 1024 * 1024:
                    raise Exception("Video hajmi juda katta (50MB dan oshib ketdi)")
                return video_path, video_info.get('title', 'Video')
            except Exception as e:
                logger.error(f"yt-dlp xatolik: {str(e)}")
                raise Exception(f"Video yuklab olishda xatolik: {str(e)}")
    except Exception as e:
        logger.error(f"Video yuklab olishda xatolik: {str(e)}")
        raise e

@bot.message_handler(commands=['start'])
def send_welcome(message):
    """Start buyrug'ini qayta ishlash"""
    with bot_app.app_context():
        user_id = str(message.from_user.id)
        username = message.from_user.username
        first_name = message.from_user.first_name
        
        # Foydalanuvchini bazaga qo'shish
        user = User.query.filter_by(user_id=user_id).first()
        if not user:
            user = User(
                user_id=user_id,
                username=username,
                first_name=first_name,
                created_at=datetime.utcnow()
            )
            db.session.add(user)
            db.session.commit()
            logger.info(f"Yangi foydalanuvchi qo'shildi: {user_id}")
        
        bot.reply_to(message, "Assalomu alaykum! Media fayllarni yuklash uchun menga havola yuboring.")

@bot.message_handler(func=lambda message: True)
def handle_message(message):
    """Barcha xabarlarni qayta ishlash"""
    with bot_app.app_context():
        url = message.text.strip()
        if not is_valid_url(url):
            bot.reply_to(message, "Iltimos, to'g'ri URL manzilini yuboring. Masalan: https://youtube.com/...")
            return
        platform = detect_platform(url)
        if platform == 'tiktok':
            bot.reply_to(message, "Bu linkni yuklab bo'lmaydi. TikTok qo'llab-quvvatlanmaydi.")
            return
        # URL ni qayta ishlash
        user = User.query.filter_by(user_id=str(message.from_user.id)).first()
        if user:
            # Yuklanishni bazaga qo'shish
            download = Download(
                user_id=user.id,
                platform=platform,
                url=url,
                created_at=datetime.utcnow(),
                status='processing'  # Boshlang'ich holat
            )
            db.session.add(download)
            db.session.commit()
            logger.info(f"Yangi yuklash qo'shildi: {url} from {platform}")
            
            if platform == 'unknown':
                bot.reply_to(message, "Kechirasiz, bu saytdan yuklay olmayman. Quyidagi saytlardan foydalaning:\n- YouTube\n- Instagram\n- TikTok\n- Facebook\n- Twitter")
                download.status = 'failed'
                db.session.commit()
                return
                
            # Yuklanishni boshlash
            status_message = bot.reply_to(message, f"⏳ Yuklanmoqda... Iltimos kuting.\nPlatforma: {platform}")
            
            try:
                # Video yuklab olish
                video_path, video_title = download_video(url, platform)
                
                # Videoni yuborish
                with open(video_path, 'rb') as video_file:
                    bot.send_video(
                        message.chat.id,
                        video_file,
                        caption=f"✅ {video_title}\n\nYuklab olindi via @{bot.get_me().username}"
                    )
                
                # Muvaffaqiyatli yuklanishni saqlash
                download.status = 'success'
                db.session.commit()
                
                # Status xabarni o'chirish
                bot.delete_message(message.chat.id, status_message.message_id)
                
                # Vaqtinchalik faylni o'chirish
                try:
                    os.remove(video_path)
                    os.rmdir(os.path.dirname(video_path))
                except:
                    pass
                    
            except Exception as e:
                error_msg = str(e)
                logger.error(f"Xatolik yuz berdi: {error_msg}")
                
                # Xatolik xabarini yuborish
                if "File is too large" in error_msg:
                    bot.edit_message_text(
                        "⚠️ Video hajmi juda katta (50MB dan oshib ketdi). Iltimos, kichikroq video tanlang.",
                        message.chat.id,
                        status_message.message_id
                    )
                else:
                    bot.edit_message_text(
                        f"❌ Xatolik yuz berdi: {error_msg}",
                        message.chat.id,
                        status_message.message_id
                    )
                
                # Xatolikni bazaga saqlash
                download.status = 'failed'
                db.session.commit()
        else:
            bot.reply_to(message, "Iltimos, avval /start buyrug'ini yuboring.")

async def cleanup_download(user_id):
    """Cleanup after download is complete"""
    if user_id in active_downloads:
        del active_downloads[user_id]
    gc.collect()  # Force garbage collection

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send a welcome message when the command /start is issued."""
    await update.message.reply_text(WELCOME_MESSAGE)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send a help message when the command /help is issued."""
    await update.message.reply_text(WELCOME_MESSAGE)

async def donate_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send donation information when the command /donate is issued."""
    donation_message = DONATION_TEXT.format(donation_url=DONATION_URL)
    
    # Get donation keyboard with URL validation
    donation_keyboard = get_donation_keyboard(DONATION_URL)
    
    # Send with or without keyboard based on if keyboard creation was successful
    if donation_keyboard:
        await update.message.reply_text(
            donation_message,
            reply_markup=donation_keyboard
        )
    else:
        await update.message.reply_text(donation_message)

async def handle_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Process the URL received from the user."""
    user_id = update.effective_user.id
    url = update.message.text.strip()
    platform = detect_platform(url)
    if platform == 'tiktok':
        await update.message.reply_text("Bu linkni yuklab bo'lmaydi. TikTok qo'llab-quvvatlanmaydi.")
        return
    logger.info(f"Received URL: {url}")
    # Check if user already has an active download
    if user_id in active_downloads:
        await update.message.reply_text("⏳ Iltimos, oldingi yuklanish tugashini kuting...")
        return
    # Check if the URL is valid
    url_type = get_url_type(url)
    if not url_type:
        logger.info(f"Invalid URL rejected: {url}")
        await update.message.reply_text(INVALID_URL_MESSAGE)
        return
    # Mark download as active
    active_downloads[user_id] = True
    # Get or create user in database
    try:
        with bot_app.app_context():
            user_db = get_or_create_user(update)
            if not user_db:
                logger.error("Failed to get or create user in database")
    except Exception as e:
        logger.error(f"Database error when creating user: {str(e)}")
        user_db = None
    # Send processing message
    processing_msg = await update.message.reply_text(PROCESSING_MESSAGE)
    try:
        # Log the download attempt
        logger.info(f"Attempting to download from {url_type}: {url}")
        # Initialize video_path variable
        video_path = None
        # Download the video based on the URL type
        try:
            if url_type == 'youtube':
                video_path = await asyncio.to_thread(download_youtube_video, url)
            elif url_type == 'instagram':
                video_path = await asyncio.to_thread(download_instagram_video, url)
            elif url_type == 'twitter':
                video_path = await asyncio.to_thread(download_twitter_video, url)
            elif url_type == 'facebook':
                video_path = await asyncio.to_thread(download_facebook_video, url)
        except Exception as e:
            raise DownloadError(f"Download failed: {str(e)}")
        # Make sure we have a valid video path
        if video_path is None:
            raise DownloadError(f"Couldn't download video from {url_type}: {url}")
        # Check if the video file exists and is readable
        if not os.path.exists(video_path):
            raise DownloadError("The downloaded file could not be found.")
        file_size = os.path.getsize(video_path)
        file_size_mb = file_size / (1024*1024)
        logger.info(f"Successfully downloaded video, file size: {file_size_mb:.2f} MB")
        # Check if the file isn't too large for Telegram
        max_size_mb = 50
        if file_size > max_size_mb * 1024 * 1024:
            # Record failed download in database
            with bot_app.app_context():
                if user_db:
                    record_download(
                        user_db.user_id, 
                        url, 
                        url_type, 
                        file_size_mb, 
                        'failed', 
                        f"Video too large to send (limit: {max_size_mb}MB)"
                    )
            raise DownloadError(f"The video is too large to send via Telegram (limit: {max_size_mb}MB).")
        # Send the video file
        try:
            with open(video_path, 'rb') as video_file:
                # Get donation keyboard with URL validation
                donation_keyboard = get_donation_keyboard(DONATION_URL)
                # Send video with or without keyboard based on if keyboard creation was successful
                if donation_keyboard:
                    await update.message.reply_video(
                        video=video_file,
                        caption=DOWNLOAD_SUCCESS_MESSAGE,
                        reply_markup=donation_keyboard
                    )
                else:
                    await update.message.reply_video(
                        video=video_file,
                        caption=DOWNLOAD_SUCCESS_MESSAGE
                    )
            logger.info("Video successfully sent to user")
            # Record successful download in database
            try:
                with bot_app.app_context():
                    if user_db:
                        record_download(
                            user_db.user_id, 
                            url, 
                            url_type, 
                            file_size_mb, 
                            'success'
                        )
            except Exception as db_err:
                logger.error(f"Failed to record successful download in database: {str(db_err)}")
        except Exception as e:
            logger.error(f"Error sending video: {str(e)}")
            # Record failed download in database
            try:
                with bot_app.app_context():
                    if user_db:
                        record_download(
                            user_db.user_id, 
                            url, 
                            url_type, 
                            file_size_mb, 
                            'failed', 
                            f"Could not send video: {str(e)}"
                        )
            except Exception as db_err:
                logger.error(f"Failed to record failed download in database: {str(db_err)}")
            raise DownloadError(f"Could not send video: {str(e)}")
        # Delete the processing message
        await processing_msg.delete()
        # Clean up - remove the temporary file
        try:
            os.remove(video_path)
            # If the file is in a temporary directory, try to remove the directory too
            temp_dir = os.path.dirname(video_path)
            if temp_dir.startswith(tempfile.gettempdir()):
                os.rmdir(temp_dir)
            logger.info("Temporary files cleaned up successfully")
        except (OSError, FileNotFoundError) as e:
            logger.warning(f"Failed to clean up temporary files: {str(e)}")
    except DownloadError as e:
        error_message = str(e)
        logger.error(f"Download error: {error_message}")
        # Record failed download in database
        try:
            with bot_app.app_context():
                if user_db:
                    record_download(
                        user_db.user_id, 
                        url, 
                        url_type, 
                        None, 
                        'failed', 
                        error_message
                    )
        except Exception as db_err:
            logger.error(f"Failed to record download in database: {str(db_err)}")
        # Customize error messages for better user experience
        user_friendly_message = ERROR_MESSAGE
        if "is private" in error_message.lower():
            user_friendly_message = "😔 Kechirasiz, men yopiq akkauntlardan video yuklay olmayman. Akkount ochiq bo'lishi kerak."
        elif "is too large" in error_message.lower():
            user_friendly_message = "😔 Kechirasiz, bu video hajmi juda katta. Telegram 50MB gacha ruxsat beradi."
        elif "does not contain a video" in error_message.lower():
            user_friendly_message = "😔 Bu postda video yo'q. Men faqat video kontentni yuklay olaman."
        elif "could not load video information" in error_message.lower():
            user_friendly_message = "😔 Video haqida ma'lumot ololmadim. Video yopiq yoki cheklangan bo'lishi mumkin."
        elif "no suitable video streams" in error_message.lower():
            user_friendly_message = "😔 Video formati topilmadi. Video mavjud emas yoki himoyalangan bo'lishi mumkin."
        # Add the technical details for debugging
        detailed_message = f"{user_friendly_message}\n\nTexnik ma'lumot: {error_message}"
        await processing_msg.edit_text(detailed_message)
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        # Record failed download in database
        try:
            with bot_app.app_context():
                if user_db:
                    record_download(
                        user_db.user_id, 
                        url, 
                        url_type if url_type else 'unknown', 
                        None, 
                        'failed', 
                        f"Unexpected error: {str(e)}"
                    )
        except Exception as db_err:
            logger.error(f"Failed to record download in database: {str(db_err)}")
        await processing_msg.edit_text(f"{ERROR_MESSAGE}\n\nKutilmagan xatolik yuz berdi. Iltimos, keyinroq qayta urinib ko'ring.")
    finally:
        # Always cleanup
        await cleanup_download(user_id)

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle callback queries from inline buttons."""
    query = update.callback_query
    await query.answer()
    
    # Note: We can't track donation clicks via callback_data since 
    # InlineKeyboardButton can't have both url and callback_data.
    # If we want to track clicks, we'd need to create a custom URL shortener/redirect service.

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Log errors caused by updates."""
    logger.error(f"Update {update} caused error {context.error}")

def run_bot():
    """Run the bot."""
    # Check if the bot token is set
    if not BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN environment variable is not set!")
        return
    
    # Create the Application
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Add handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("donate", donate_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_url))
    application.add_handler(CallbackQueryHandler(handle_callback))
    
    # Add error handler
    application.add_error_handler(error_handler)
    
    # Run the bot until the user presses Ctrl-C
    logger.info("Starting bot...")
    application.run_polling(allowed_updates=Update.ALL_TYPES, close_loop=False)
