from flask import Flask, render_template, request, redirect, url_for, flash
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import plotly.express as px
import pandas as pd
from datetime import datetime, timedelta

from models import db, Admin, User, Download

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-here'  # Change this to a secure secret key
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///bot.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(user_id):
    return Admin.query.get(int(user_id))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        user = Admin.query.filter_by(username=username).first()
        if user and check_password_hash(user.password, password):
            login_user(user)
            return redirect(url_for('dashboard'))
        
        flash('Invalid username or password')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/')
@login_required
def dashboard():
    total_users = User.query.count()
    total_downloads = Download.query.count()
    
    # Get downloads for the last 7 days
    seven_days_ago = datetime.utcnow() - timedelta(days=7)
    downloads = Download.query.filter(Download.created_at >= seven_days_ago).all()
    
    # Create downloads chart
    df = pd.DataFrame([{
        'date': d.created_at.date(),
        'platform': d.platform,
        'media_type': d.media_type
    } for d in downloads])
    
    if not df.empty:
        daily_downloads = px.line(
            df.groupby('date').size().reset_index(name='count'),
            x='date',
            y='count',
            title='Downloads Over Time'
        )
        
        platform_distribution = px.pie(
            df.groupby('platform').size().reset_index(name='count'),
            values='count',
            names='platform',
            title='Downloads by Platform'
        )
    else:
        daily_downloads = None
        platform_distribution = None
    
    return render_template('dashboard.html',
                         total_users=total_users,
                         total_downloads=total_downloads,
                         daily_downloads=daily_downloads.to_html() if daily_downloads else None,
                         platform_distribution=platform_distribution.to_html() if platform_distribution else None)

@app.route('/users')
@login_required
def users():
    users = User.query.all()
    return render_template('users.html', users=users)

@app.route('/downloads')
@login_required
def downloads():
    downloads = Download.query.order_by(Download.created_at.desc()).all()
    return render_template('downloads.html', downloads=downloads)

if __name__ == '__main__':
    app.run(debug=True) 