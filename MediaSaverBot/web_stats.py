from flask import Flask, render_template_string
from models import init_db, User, Download, db
from config import SQLALCHEMY_DATABASE_URI
import pandas as pd
from datetime import datetime
from sqlalchemy import text

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = SQLALCHEMY_DATABASE_URI
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
init_db(app)

# HTML template
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Bot Statistikasi</title>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        .table-responsive { margin-top: 20px; }
        .stats-card { margin-bottom: 20px; }
    </style>
</head>
<body>
    <div class="container mt-5">
        <h1 class="mb-4">Bot Statistikasi</h1>
        
        <div class="row">
            <div class="col-md-3">
                <div class="card stats-card">
                    <div class="card-body">
                        <h5 class="card-title">Jami yuklanishlar</h5>
                        <p class="card-text display-6">{{ stats['Jami yuklanishlar'] }}</p>
                    </div>
                </div>
            </div>
            <div class="col-md-3">
                <div class="card stats-card">
                    <div class="card-body">
                        <h5 class="card-title">Muvaffaqiyatli</h5>
                        <p class="card-text display-6">{{ stats['Muvaffaqiyatli yuklanishlar'] }}</p>
                    </div>
                </div>
            </div>
            <div class="col-md-3">
                <div class="card stats-card">
                    <div class="card-body">
                        <h5 class="card-title">Xatoliklar</h5>
                        <p class="card-text display-6">{{ stats['Xatoliklar'] }}</p>
                    </div>
                </div>
            </div>
            <div class="col-md-3">
                <div class="card stats-card">
                    <div class="card-body">
                        <h5 class="card-title">Faol foydalanuvchilar</h5>
                        <p class="card-text display-6">{{ stats['Faol foydalanuvchilar'] }}</p>
                    </div>
                </div>
            </div>
        </div>

        <h3 class="mt-4">Platformalar bo'yicha statistika</h3>
        <div class="row">
            {% for platform, count in stats['Platformalar bo\'yicha'].items() %}
            <div class="col-md-2">
                <div class="card stats-card">
                    <div class="card-body">
                        <h5 class="card-title">{{ platform }}</h5>
                        <p class="card-text display-6">{{ count }}</p>
                    </div>
                </div>
            </div>
            {% endfor %}
        </div>

        <h3 class="mt-4">So'nggi yuklanishlar</h3>
        <div class="table-responsive">
            <table class="table table-striped">
                <thead>
                    <tr>
                        <th>Vaqt</th>
                        <th>Foydalanuvchi</th>
                        <th>Platforma</th>
                        <th>Hajmi</th>
                        <th>Holat</th>
                        <th>URL</th>
                    </tr>
                </thead>
                <tbody>
                    {% for _, row in downloads.iterrows() %}
                    <tr>
                        <td>{{ row['yuklangan_vaqt'] }}</td>
                        <td>{{ row['username'] or row['first_name'] or row['user_id'] }}</td>
                        <td>{{ row['platforma'] }}</td>
                        <td>{{ row['hajmi_mb'] }}</td>
                        <td>
                            {% if row['holat'] == 'success' %}
                            <span class="badge bg-success">✓</span>
                            {% else %}
                            <span class="badge bg-danger">✗</span>
                            {% endif %}
                        </td>
                        <td><small>{{ row['url'][:50] }}...</small></td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
    </div>
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>
"""

def get_stats():
    """Get statistics from database"""
    with app.app_context():
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
        
        result = db.session.execute(text(query))
        df = pd.DataFrame(result.fetchall(), columns=result.keys())
        
        if df.empty:
            return None, None
        
        df['yuklangan_vaqt'] = df['yuklangan_vaqt'].apply(lambda x: x.strftime('%Y-%m-%d %H:%M:%S'))
        df['hajmi_mb'] = df['hajmi_mb'].apply(lambda x: f"{x:.2f} MB" if x else "N/A")
        
        stats = {
            'Jami yuklanishlar': len(df),
            'Muvaffaqiyatli yuklanishlar': len(df[df['holat'] == 'success']),
            'Xatoliklar': len(df[df['holat'] == 'failed']),
            'Faol foydalanuvchilar': len(df['user_id'].unique()),
            'Platformalar bo\'yicha': df['platforma'].value_counts().to_dict()
        }
        
        return df, stats

@app.route('/')
def home():
    """Render statistics page"""
    downloads, stats = get_stats()
    if downloads is None:
        return "Hozircha ma'lumotlar yo'q"
    return render_template_string(HTML_TEMPLATE, downloads=downloads, stats=stats)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000) 