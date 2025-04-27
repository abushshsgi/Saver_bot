from flask import Flask, render_template_string, request, redirect, url_for, session, render_template
from models import init_db, User, Download, db
from config import SQLALCHEMY_DATABASE_URI
import pandas as pd
from datetime import datetime, timedelta
from sqlalchemy import text, func
import plotly.express as px
import plotly.graph_objects as go
import json
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user
import hashlib
from collections import defaultdict
import requests

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = SQLALCHEMY_DATABASE_URI
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'your-secret-key-here'  # O'zgartiring
init_db(app)

# Login Manager
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# Admin credentials
ADMIN_USERNAME = "abdu"
ADMIN_PASSWORD = hashlib.sha256("ab".encode()).hexdigest()

class Admin(UserMixin):
    def __init__(self, id):
        self.id = id

@login_manager.user_loader
def load_user(user_id):
    if user_id == "admin":
        return Admin(user_id)
    return None

def get_user_ip_location(ip):
    try:
        response = requests.get(f"http://ip-api.com/json/{ip}")
        data = response.json()
        if data["status"] == "success":
            return data["country"]
    except:
        pass
    return "Noma'lum"

def get_stats():
    """Get detailed statistics from database"""
    with app.app_context():
        # Asosiy statistika
        today = datetime.now().date()
        yesterday = today - timedelta(days=1)
        
        # Bugungi statistika
        today_stats = db.session.query(
            func.count(User.id).label('new_users'),
            func.count(Download.id).label('downloads')
        ).select_from(User).outerjoin(Download).filter(
            func.date(User.created_at) == today
        ).first()
        
        # Platformalar bo'yicha statistika
        platform_stats = db.session.query(
            Download.platform,
            func.count(Download.id)
        ).filter(Download.platform != 'unknown').group_by(Download.platform).all()
        
        # So'nggi foydalanuvchilar
        recent_users = db.session.query(User).order_by(User.created_at.desc()).limit(10).all()
        
        # So'nggi yuklanishlar
        recent_downloads = db.session.query(
            Download, User
        ).join(User).order_by(Download.created_at.desc()).limit(20).all()
        
        # Active users in last 24h
        active_users = db.session.query(func.count(User.id)).filter(
            User.created_at >= datetime.now() - timedelta(hours=24)
        ).scalar() or 0
        
        # Umumiy statistika
        total_users = User.query.count()
        total_downloads = Download.query.count()
        successful_downloads = Download.query.filter_by(status='success').count()
        
        return {
            'today_new_users': today_stats[0] or 0,
            'today_downloads': today_stats[1] or 0,
            'platform_stats': dict(platform_stats),
            'recent_users': recent_users,
            'recent_downloads': recent_downloads,
            'active_users': active_users,
            'total_users': total_users,
            'total_downloads': total_downloads,
            'successful_downloads': successful_downloads
        }

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = hashlib.sha256(request.form['password'].encode()).hexdigest()
        
        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            user = Admin("admin")
            login_user(user)
            return redirect(url_for('home'))
        return render_template('login.html', error="Noto'g'ri login yoki parol")
    
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/')
@login_required
def home():
    """Admin panel"""
    stats = get_stats()
    return render_template('dashboard.html', stats=stats, platform_data=stats['platform_stats'])

@app.route('/update_stats')
@login_required
def update_stats():
    """Real-time statistics update"""
    stats = get_stats()
    return {
        'today_new_users': stats['today_new_users'],
        'today_downloads': stats['today_downloads'],
        'platform_stats': stats['platform_stats'],
        'active_users': stats['active_users']
    }

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True) 