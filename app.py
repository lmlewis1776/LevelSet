import os
import json
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
from functools import wraps

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'levelset-dev-secret-key-change-in-prod')

# Database setup
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'levelsethq.db')

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn

def init_db():
    conn = get_db()
    cursor = conn.cursor()
    
    # Users table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            name TEXT NOT NULL,
            organization TEXT DEFAULT '',
            role TEXT DEFAULT 'user',
            plan TEXT DEFAULT 'free',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Reports table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            report_type TEXT NOT NULL,
            title TEXT NOT NULL,
            data TEXT DEFAULT '{}',
            score REAL DEFAULT 0,
            max_score REAL DEFAULT 0,
            paid INTEGER DEFAULT 0,
            payment_id TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    ''')
    
    # Payments table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            report_id INTEGER,
            amount REAL NOT NULL,
            payment_id TEXT NOT NULL,
            status TEXT DEFAULT 'completed',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (report_id) REFERENCES reports(id)
        )
    ''')
    
    conn.commit()
    conn.close()

# Initialize DB
init_db()

# Flask-Login setup
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

class User(UserMixin):
    def __init__(self, id, email, name, organization, role, plan):
        self.id = id
        self.email = email
        self.name = name
        self.organization = organization
        self.role = role
        self.plan = plan

@login_manager.user_loader
def load_user(user_id):
    conn = get_db()
    user = conn.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
    conn.close()
    if user:
        return User(user['id'], user['email'], user['name'], user['organization'], user['role'], user['plan'])
    return None

# Context processor to inject current year and user info
@app.context_processor
def inject_globals():
    return {
        'current_year': datetime.now().year,
        'now': datetime.now()
    }

# ========== ROUTES ==========

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/pricing')
def pricing():
    return render_template('pricing.html')

@app.route('/privacy')
def privacy():
    return render_template('privacy.html')

@app.route('/terms')
def terms():
    return render_template('terms.html')

@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/contact', methods=['GET', 'POST'])
def contact():
    if request.method == 'POST':
        name = request.form.get('name', '')
        email = request.form.get('email', '')
        subject = request.form.get('subject', '')
        message = request.form.get('message', '')
        conn = get_db()
        conn.execute('CREATE TABLE IF NOT EXISTS contact_messages (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, email TEXT NOT NULL, subject TEXT, message TEXT NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)')
        conn.execute('INSERT INTO contact_messages (name, email, subject, message) VALUES (?, ?, ?, ?)', (name, email, subject, message))
        conn.commit()
        conn.close()
        flash('Thank you for your message! We will get back to you soon.', 'success')
        return redirect(url_for('contact'))
    return render_template('contact.html')

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        password = request.form.get('password')
        organization = request.form.get('organization', '')
        
        if not name or not email or not password:
            flash('All fields are required', 'error')
            return render_template('signup.html')
        
        conn = get_db()
        existing = conn.execute('SELECT id FROM users WHERE email = ?', (email,)).fetchone()
        if existing:
            conn.close()
            flash('Email already registered. Please log in.', 'error')
            return render_template('signup.html')
        
        password_hash = generate_password_hash(password)
        cursor = conn.execute(
            'INSERT INTO users (email, password_hash, name, organization) VALUES (?, ?, ?, ?)',
            (email, password_hash, name, organization)
        )
        conn.commit()
        user_id = cursor.lastrowid
        conn.close()
        
        user = User(user_id, email, name, organization, 'user', 'free')
        login_user(user)
        flash('Welcome to LevelSet!', 'success')
        return redirect(url_for('dashboard'), 303)
    
    return render_template('signup.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        conn = get_db()
        user_data = conn.execute('SELECT * FROM users WHERE email = ?', (email,)).fetchone()
        conn.close()
        
        if user_data and check_password_hash(user_data['password_hash'], password):
            user = User(user_data['id'], user_data['email'], user_data['name'], 
                       user_data['organization'], user_data['role'], user_data['plan'])
            login_user(user)
            flash('Welcome back!', 'success')
            return redirect(url_for('dashboard'), 303)
        
        flash('Invalid email or password', 'error')
    
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/dashboard')
@login_required
def dashboard():
    conn = get_db()
    reports = conn.execute(
        'SELECT * FROM reports WHERE user_id = ? ORDER BY created_at DESC',
        (current_user.id,)
    ).fetchall()
    conn.close()
    return render_template('dashboard.html', reports=reports)

@app.route('/dei-audit', methods=['GET', 'POST'])
@login_required
def dei_audit():
    # Org Health Assessment questions across 5 dimensions
    dimensions = [
        {
            'id': 'hiring_access',
            'name': 'Hiring, Access & Talent Pathways',
            'questions': [
                {'id': 'l1', 'text': 'Does your organization hire for skills and potential over credentials and degrees?', 'options': [('We prioritize degrees', 0), ('We\'re exploring skills-based hiring', 1), ('Skills and potential drive our hiring decisions', 2)]},
                {'id': 'l2', 'text': 'Do you have a clear pathway for recognizing STARs (Skilled Through Alternative Routes) talent?', 'options': [('We don\'t track this', 0), ('We\'re starting to think about it', 1), ('Yes, we actively recruit and advance STARs', 2)]},
                {'id': 'l3', 'text': 'Is your recruitment outreach designed to reach candidates from diverse and underrepresented backgrounds?', 'options': [('We post on the usual job boards', 0), ('We diversify some channels', 1), ('Multi-channel strategy designed for equity', 2)]},
                {'id': 'l4', 'text': 'Do you have pay equity practices and transparent salary bands?', 'options': [('No, salaries are opaque', 0), ('Under review', 1), ('Yes, published bands and regular audits', 2)]},
            ]
        },
        {
            'id': 'belonging',
            'name': 'Culture, Belonging & Psychological Safety',
            'questions': [
                {'id': 'c1', 'text': 'Do your staff and stakeholders feel safe bringing their full selves to work?', 'options': [('We haven\'t measured this', 0), ('We\'ve done a survey or two', 1), ('We regularly measure belonging and act on it', 2)]},
                {'id': 'c2', 'text': 'Are there active employee or community resource groups that shape organizational decisions?', 'options': [('No', 0), ('In planning stages', 1), ('Yes, with budget and leadership access', 2)]},
                {'id': 'c3', 'text': 'Is feedback on inclusion and belonging collected and acted on regularly?', 'options': [('No', 0), ('Annually', 1), ('Quarterly or more, with visible action', 2)]},
                {'id': 'c4', 'text': 'Does your organization have clear, enforced policies that protect against discrimination and harassment?', 'options': [('We rely on basic policies', 0), ('We have policies but enforcement is inconsistent', 1), ('Yes, with training and accountability', 2)]},
            ]
        },
        {
            'id': 'leadership',
            'name': 'Leadership Commitment & Accountability',
            'questions': [
                {'id': 'w1', 'text': 'Is equity work embedded in your strategic plan and budget — not just a statement on your website?', 'options': [('No, it\'s aspirational', 0), ('Partially, with some budget', 1), ('Yes, funded goals with timelines', 2)]},
                {'id': 'w2', 'text': 'Is equity represented at the board and executive leadership level?', 'options': [('No', 0), ('Informal champions only', 1), ('Yes, with role clarity and resources', 2)]},
                {'id': 'w3', 'text': 'Are leaders evaluated on equity outcomes, not just intent?', 'options': [('No', 0), ('Informally discussed', 1), ('Yes, in performance reviews and goals', 2)]},
                {'id': 'w4', 'text': 'Does leadership participate in ongoing equity learning and development?', 'options': [('One-time training only', 0), ('Occasionally', 1), ('Regular, embedded practice', 2)]},
            ]
        },
        {
            'id': 'community',
            'name': 'Community Accountability & Impact',
            'questions': [
                {'id': 'p1', 'text': 'Are the communities you serve at the table when decisions are made?', 'options': [('No, we decide for them', 0), ('We consult them occasionally', 1), ('Community voice is built into our governance', 2)]},
                {'id': 'p2', 'text': 'Do you collect and disaggregate data to understand who you\'re serving and who you\'re missing?', 'options': [('No', 0), ('Sometimes', 1), ('Yes, systematically', 2)]},
                {'id': 'p3', 'text': 'Are your programs and materials accessible across language, ability, and culture?', 'options': [('We haven\'t assessed this', 0), ('Partially accessible', 1), ('Designed for accessibility from the start', 2)]},
                {'id': 'p4', 'text': 'Do you partner with community-based organizations that reflect the communities you serve?', 'options': [('No', 0), ('Occasionally', 1), ('Deep, ongoing partnerships', 2)]},
            ]
        },
        {
            'id': 'tech_mission',
            'name': 'Mission-Driven Technology & Infrastructure',
            'questions': [
                {'id': 'a1', 'text': 'Does your technology infrastructure actively advance your equity goals (not just support operations)?', 'options': [('Tech is just for operations', 0), ('We\'re starting to connect them', 1), ('Tech decisions include equity criteria', 2)]},
                {'id': 'a2', 'text': 'Are the digital tools you use accessible to all stakeholders, including those with disabilities?', 'options': [('We haven\'t checked', 0), ('Partially accessible', 1), ('Yes, regularly tested for accessibility', 2)]},
                {'id': 'a3', 'text': 'Do the communities you serve have a voice in the technology choices that affect them?', 'options': [('No', 0), ('We gather occasional input', 1), ('Community co-design is standard practice', 2)]},
                {'id': 'a4', 'text': 'Is your data collection and storage equitable — protecting communities from harm while giving them agency over their data?', 'options': [('We haven\'t thought about this', 0), ('We have basic data privacy', 1), ('Yes, with community data sovereignty practices', 2)]},
            ]
        }
    ]
    
    
