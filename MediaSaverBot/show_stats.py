from flask import Flask
from models import init_db, User, Download, db
from config import SQLALCHEMY_DATABASE_URI
import pandas as pd
from datetime import datetime

# Initialize Flask app
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = SQLALCHEMY_DATABASE_URI
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
init_db(app)

def get_detailed_stats():
    """Barcha yuklanishlar va foydalanuvchilar haqida batafsil ma'lumot olish"""
    with app.app_context():
        # SQL so'rov
        query = """
        SELECT 
            u.user_id,
            u.username,
            u.first_name,
            u.last_name,
            d.url,
            d.source_type as platforma,
            d.file_size as hajmi_mb,
            d.status as holat,
            d.error_message as xatolik,
            d.created_at as yuklangan_vaqt
        FROM users u
        JOIN downloads d ON u.user_id = d.user_id
        ORDER BY d.created_at DESC
        """
        
        # Ma'lumotlarni pandas DataFrame ga o'tkazish
        from sqlalchemy import text
        result = db.session.execute(text(query))
        df = pd.DataFrame(result.fetchall(), columns=result.keys())
        
        if df.empty:
            print("Ma'lumotlar bazasida hech qanday ma'lumot yo'q")
            return None, None
        
        # Vaqtni to'g'ri formatga o'tkazish
        df['yuklangan_vaqt'] = df['yuklangan_vaqt'].apply(lambda x: x.strftime('%Y-%m-%d %H:%M:%S'))
        
        # Hajmni MB ga o'tkazish
        df['hajmi_mb'] = df['hajmi_mb'].apply(lambda x: f"{x:.2f} MB" if x else "N/A")
        
        # CSV faylga saqlash
        filename = f"statistika_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        df.to_csv(filename, index=False, encoding='utf-8-sig')
        
        # Umumiy statistika
        stats = {
            'Jami yuklanishlar': len(df),
            'Muvaffaqiyatli yuklanishlar': len(df[df['holat'] == 'success']),
            'Xatoliklar': len(df[df['holat'] == 'failed']),
            'Faol foydalanuvchilar': len(df['user_id'].unique()),
            'Platformalar bo\'yicha': df['platforma'].value_counts().to_dict()
        }
        
        return filename, stats

if __name__ == "__main__":
    filename, stats = get_detailed_stats()
    if filename and stats:
        print(f"\nStatistika fayli yaratildi: {filename}")
        print("\nUmumiy statistika:")
        for key, value in stats.items():
            print(f"{key}: {value}")
    else:
        print("\nHozircha statistika mavjud emas.") 