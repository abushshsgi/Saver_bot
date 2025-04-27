import threading
from admin_panel import app as admin_app
from bot import bot, bot_app
from config import BOT_TOKEN

def run_admin_panel():
    """Admin panelni ishga tushirish"""
    admin_app.run(host='0.0.0.0', port=5000, debug=True, use_reloader=False)

def run_bot():
    """Botni ishga tushirish"""
    with bot_app.app_context():
        print("Bot ishga tushdi!")
        bot.polling(none_stop=True)

if __name__ == "__main__":
    # Admin panel uchun thread
    admin_thread = threading.Thread(target=run_admin_panel)
    admin_thread.start()
    
    # Botni asosiy threadda ishga tushirish
    print("Bot va Admin Panel ishga tushdi!")
    run_bot() 