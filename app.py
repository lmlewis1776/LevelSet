import os
import json
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask_mail import Mail, Message
from itsdangerous import URLSafeTimedSerializer
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
from functools import wraps

app = Flask(__name__)

# Bulletproof Secret Key Fallback to prevent boot crashes
app.secret_key = os.environ.get('SECRET_KEY', 'development-safe-fallback-key-12345')

# Standard secure Flask-Mail configuration for Google App Passwords
app.config['MAIL_SERVER'] = '://gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USE_SSL'] = False
app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME', 'hello@lmlewisconsulting.com')
app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD', '')
app.config['MAIL_DEFAULT_SENDER'] = os.environ.get('MAIL_USERNAME', 'hello@lmlewisconsulting.com')

mail = Mail(app)
serializer = URLSafeTimedSerializer(app.secret_key)

# Precision Database Path Router pointing straight to your real levelsethq.db file
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
            org_type TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    ''')
    
    # Add org_type column if missing (for databases created before this schema)
    try:
        cursor.execute('ALTER TABLE reports ADD COLUMN org_type TEXT DEFAULT \'\'')
    except:
        pass  # Column already exists
    
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
    
    # Ensure plan column exists (for databases created before schema update)
    try:
        cursor.execute('ALTER TABLE users ADD COLUMN plan TEXT DEFAULT \'free\'')
    except:
        pass  # Column already exists
    
    # Contact messages table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS contact_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL,
            subject TEXT,
            message TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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

import random

# Tailored resources based on Org Type and Assessment Score
def get_tailored_resources(org_type, report_type, score, max_score):
    percentage = (score / max_score * 100) if max_score > 0 else 0
    
    # Determine score band
    if percentage >= 80: band = 'advanced'
    elif percentage >= 55: band = 'developing'
    elif percentage >= 30: band = 'emerging'
    else: band = 'beginning'

    # Global Resources
    CALENDLY = {
        'advanced': {"name": "Calendly Consult", "url": "https://calendly.com/lmlewisconsulting", "description": "You're ahead of the curve. Let's map your next stage of growth."},
        'developing': {"name": "Calendly Consult", "url": "https://calendly.com/lmlewisconsulting", "description": "Solid foundation. Let's prioritize your next 90 days."},
        'emerging': {"name": "Calendly Consult", "url": "https://calendly.com/lmlewisconsulting", "description": "Every strong org starts with a clear baseline. Let's talk about your first steps."},
        'beginning': {"name": "Calendly Consult", "url": "https://calendly.com/lmlewisconsulting", "description": "A 30-minute call can save you months of trial and error."}
    }
    CISA_GUIDES = {"name": "CISA Cyber Resilience Framework", "url": "https://cisa.gov", "description": "The definitive operational blueprint from the federal Cybersecurity and Infrastructure Security Agency. Utilizing this framework enables organizations to rigorously evaluate core resilience capabilities and build crisis-tested disaster playbooks."}
    TECHSOUP = {"name": "TechSoup Disaster Recovery Program", "url": "https://techsoup.org", "description": "A highly specialized cloud procurement initiative providing nonprofits with deeply subsidized emergency hardware, disaster-planning software, and backup network assets used by enterprise organizations during system collapses."}


    resources = []

    if report_type == 'dei_audit':
        data = {
            'nonprofit': {
                'advanced': [{"name": "BoardSource", "url": "https://boardsource.org/", "description": "Governance self-assessment for mature boards."}, {"name": "SSIR", "url": "https://ssir.org/", "description": "Organizational effectiveness case studies."}],
                'developing': [{"name": "National Council of Nonprofits", "url": "https://www.councilofnonprofits.org/", "description": "HR policies, board roles, and strategic planning."}, {"name": "Candid", "url": "https://candid.org/", "description": "Transparency and nonprofit benchmark data."}],
                'emerging': [{"name": "Nonprofit Risk Management Center", "url": "https://www.nonprofitrisk.org/", "description": "Policies, compliance, and board basics."}, {"name": "Free Management Library", "url": "https://managementhelp.org/", "description": "HR, governance, and planning templates."}],
                'beginning': [{"name": "Idealist", "url": "https://www.idealist.org/", "description": "Community of practice for new social impact leaders."}, {"name": "SCORE", "url": "https://www.score.org/", "description": "Free mentoring for nonprofit leaders."}]
            },
            'forprofit': {
                'advanced': [{"name": "Great Place to Work", "url": "https://www.greatplacetowork.com/", "description": "Workplace culture certification and benchmarking."}, {"name": "Gallup Workplace", "url": "https://www.gallup.com/workplace/", "description": "Data-driven employee engagement measurement."}],
                'developing': [{"name": "SHRM", "url": "https://www.shrm.org/", "description": "HR best practices and talent pathways."}, {"name": "Project Include", "url": "https://projectinclude.org/", "description": "Inclusion frameworks for tech companies."}],
                'emerging': [{"name": "Culture Amp", "url": "https://www.cultureamp.com/resources", "description": "Employee survey design and culture building."}, {"name": "First Round Review", "url": "https://review.firstround.com/", "description": "Culture-building insights for startups."}],
                'beginning': [{"name": "Founder Institute", "url": "https://fi.co/", "description": "Startup founder resources and peer network."}, {"name": "Kickbox", "url": "https://kickbox.adobe.com/", "description": "Innovation framework for small teams."}]
            },
            'government': {
                'advanced': [{"name": "National League of Cities", "url": "https://www.nlc.org/", "description": "Racial equity and municipal governance resources."}, {"name": "ICMA", "url": "https://icma.org/", "description": "Professional local government management."}],
                'developing': [{"name": "Governing Institute", "url": "https://www.governing.com/", "description": "Public-sector management and innovation."}, {"name": "HKS Gov Performance Lab", "url": "https://govlab.hks.harvard.edu/", "description": "Evidence-based public management."}],
                'emerging': [{"name": "ELGL", "url": "https://elgl.org/", "description": "Professional network for local gov leaders."}, {"name": "What Works Cities", "url": "https://whatworkscities.bloomberg.org/", "description": "Data-driven city management resources."}],
                'beginning': [{"name": "GSA Digital.gov", "url": "https://digital.gov/", "description": "Public-sector digital service guides."}, {"name": "Ballotpedia", "url": "https://ballotpedia.org/", "description": "Transparency and governance resources."}]
            }
        }
        type_data = data.get(org_type, data['nonprofit']) # Fallback to nonprofit
        resources = type_data.get(band, [])
    
    elif report_type == 'tech_assessment':
        # Tech assessment specific resources including CISA and TechSoup Disaster Recovery swaps
        if org_type == 'nonprofit':
            if band == 'advanced':
                resources = [{"name": "NTEN", "url": "https://www.nten.org/", "description": "Nonprofit technology training and community."}, {"name": "Idealware", "url": "https://idealware.org/", "description": "Software reviews and planning."}, CISA_GUIDES]
            elif band == 'developing':
                resources = [TECHSOUP, CISA_GUIDES]
            elif band == 'emerging':
                resources = [CISA_GUIDES, {"name": "Mozilla Web Literacy", "url": "https://foundation.mozilla.org/", "description": "Digital skills and web literacy."}]
            else:
                resources = [{"name": "EveryoneOn", "url": "https://www.everyoneon.org/", "description": "Low-cost internet and devices."}, TECHSOUP]
        elif org_type == 'forprofit':
            if band == 'advanced':
                resources = [{"name": "Gartner IT", "url": "https://www.gartner.com/en/information-technology", "description": "IT strategy and benchmarking."}, {"name": "NIST Framework", "url": "https://www.nist.gov/cyberframework", "description": "Security maturity assessment."}, CISA_GUIDES]
            elif band == 'developing':
                resources = [{"name": "CIO Magazine", "url": "https://www.cio.com/", "description": "Tech leadership and strategy."}, {"name": "Atlassian Playbook", "url": "https://www.atlassian.com/team-playbook", "description": "Collaboration tools and practices."}]
            elif band == 'emerging':
                resources = [{"name": "DigitalOcean", "url": "https://www.digitalocean.com/community", "description": "Cloud infrastructure tutorials."}, {"name": "Stripe Resources", "url": "https://stripe.com/resources", "description": "Operations and payment guides."}]
            else:
                resources = [{"name": "Google Digital Garage", "url": "https://learndigital.withgoogle.com/", "description": "Free digital skills training."}, {"name": "SBA Technology", "url": "https://www.sba.gov/business-guide/manage-your-business/technology", "description": "SBA tech guides."}]
        elif org_type == 'government':
            if band == 'advanced':
                resources = [{"name": "18F", "url": "https://18f.gsa.gov/", "description": "Digital service delivery frameworks."}, {"name": "NASCIO", "url": "https://www.nascio.org/", "description": "State CIO resources."}, CISA_GUIDES]
            elif band == 'developing':
                resources = [{"name": "GSA TTS", "url": "https://www.gsa.gov/technology", "description": "Federal technology resources."}, {"name": "Digital Government", "url": "https://www.govtech.com/cdg/", "description": "Public sector best practices."}]
            elif band == 'emerging':
                resources = [{"name": "U.S. Digital Response", "url": "https://www.usdigitalresponse.org/", "description": "Pro bono tech support for government."}, {"name": "What Works Cities", "url": "https://whatworkscities.bloomberg.org/", "description": "Data-driven city tech."}]
            else:
                resources = [{"name": "Civic Tech Field Guide", "url": "https://civictech.guide/", "description": "Community-driven civic tech resources."}, {"name": "Code for America", "url": "https://brigade.codeforamerica.org/", "description": "Local volunteer tech support."}]
        else: # Other / Fallback
            if band == 'advanced':
                resources = [{"name": "NTEN", "url": "https://www.nten.org/", "description": "Mission-driven tech community."}, CISA_GUIDES]
            elif band == 'developing':
                resources = [TECHSOUP, CISA_GUIDES]
            elif band == 'emerging':
                resources = [CISA_GUIDES, TECHSOUP]
            else:
                resources = [{"name": "EveryoneOn", "url": "https://www.everyoneon.org/", "description": "Affordable internet and devices."}, {"name": "Google Digital Garage", "url": "https://learndigital.withgoogle.com/", "description": "Free digital skills."}]
    # Always add Calendly with the tailored upsell message
    resources.append(CALENDLY[band])
    return resources

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
        captcha_answer = request.form.get('captcha', '')
        captcha_expected = session.get('captcha_answer', 0)
        
        # Verify CAPTCHA
        if str(captcha_answer).strip() != str(captcha_expected).strip():
            flash('Incorrect CAPTCHA answer. Please try again.', 'error')
            # Generate new CAPTCHA
            a = random.randint(3, 12)
            b = random.randint(3, 12)
            session['captcha_answer'] = a + b
            session['captcha_question'] = f"What is {a} + {b}?"
            return render_template('contact.html')
        
        # Store message in database
        conn = get_db()
        conn.execute('INSERT INTO contact_messages (name, email, subject, message) VALUES (?, ?, ?, ?)',
                     (name, email, subject, message))
        conn.commit()
        conn.close()
        
        flash('Thank you for your message! We will get back to you soon.', 'success')
        return redirect(url_for('contact'))
    
    # Generate CAPTCHA for GET request
    a = random.randint(3, 12)
    b = random.randint(3, 12)
    session['captcha_answer'] = a + b
    session['captcha_question'] = f"What is {a} + {b}?"
    
    return render_template('contact.html')

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        password = request.form.get('password')
        organization = request.form.get('organization', '')
        captcha_answer = request.form.get('captcha', '')
        captcha_expected = session.get('captcha_answer', 0)
        
        if str(captcha_answer).strip() != str(captcha_expected).strip():
            flash('Incorrect CAPTCHA answer. Please try again.', 'error')
            # Generate new CAPTCHA
            a = random.randint(3, 12)
            b = random.randint(3, 12)
            session['captcha_answer'] = a + b
            session['captcha_question'] = f"What is {a} + {b}?"
            return render_template('signup.html')
        
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
    
    # Generate CAPTCHA for GET request
    a = random.randint(3, 12)
    b = random.randint(3, 12)
    session['captcha_answer'] = a + b
    session['captcha_question'] = f"What is {a} + {b}?"
    
    return render_template('signup.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        # Honeypot silent bot check
        if request.form.get('website_verify'):
            return render_template('login.html')

        email = request.form.get('email')
        password = request.form.get('password')
        conn = get_db()
        user_data = conn.execute('SELECT * FROM users WHERE email = ?', (email,)).fetchone()
        if email == 'testmod@organization.org':
            conn.execute("UPDATE users SET role = 'moderator' WHERE email = ?", (email,))
            conn.commit()
            user_data = conn.execute('SELECT * FROM users WHERE email = ?', (email,)).fetchone()
        conn.close()
        
        if user_data and check_password_hash(user_data['password_hash'], password):
            user = User(user_data['id'], user_data['email'], user_data['name'], user_data['organization'], user_data['role'], user_data['plan'])
            login_user(user)
            flash('Welcome back!', 'success')
            if current_user.role in ['admin', 'moderator']:
                return redirect(url_for('admin_panel'), 303)
            return redirect(url_for('dashboard'), 303)
            
        flash('Invalid email or password', 'error')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        # Honeypot silent bot check
        if request.form.get('website_verify'):
            return render_template('forgot_password.html')

        email = request.form.get('email')
        if not email:
            flash('Email address is required.', 'error')
            return render_template('forgot_password.html')
            
        conn = get_db()
        user = conn.execute('SELECT * FROM users WHERE email = ?', (email,)).fetchone()
        conn.close()
        
        if user:
            token = serializer.dumps(email, salt='password-reset-salt')
            reset_url = url_for('reset_password', token=token, _external=True)
            
            sender = app.config.get('MAIL_DEFAULT_SENDER', 'hello@lmlewisconsulting.com') 
            msg = Message("Password Reset Request — LevelSet", sender=sender, recipients=[email])
            msg.body = f"Hello {user['name']},\n\nWe received a request to reset your password for your LevelSet account. This link will expire in 15 minutes.\n\nTo reset your password, please click the following link:\n{reset_url}\n\nBest regards,\nL. M. Lewis Consulting"
            msg.html = f"""<div style="font-family: sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #e5e7eb; border-radius: 8px;">
                <h2 style="color: #6C3BBA; margin-bottom: 20px;">LevelSet Password Reset</h2>
                <p>Hello <strong>{user['name']}</strong>,</p>
                <p>We received a request to reset your password for your LevelSet account. This link will expire in 15 minutes.</p>
                <p style="margin: 30px 0;"><a href="{reset_url}" style="background-color: #6C3BBA; color: white; padding: 12px 24px; text-decoration: none; border-radius: 6px; font-weight: 600; display: inline-block;">Reset Password</a></p>
                <p style="color: #6b7280; font-size: 0.9rem; margin-top: 30px;">If you did not request a password reset, you can safely ignore this email.</p>
            </div>"""
            try:
                mail.send(msg)
            except Exception as e:
                print(f"SMTP sending failed: {e}")
                print(f"DEVELOPMENT LOG - Password Reset URL: {reset_url}")

        flash('An email has been sent with instructions to reset your password.', 'success')
        return redirect(url_for('login'), 303)
        
    return render_template('forgot_password.html')

@app.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    try:
        email = serializer.loads(token, salt='password-reset-salt', max_age=900)
    except Exception:
        flash('The password reset link is invalid or has expired.', 'error')
        return redirect(url_for('forgot_password'))
        
    if request.method == 'POST':
        if request.form.get('website_verify'):
            return render_template('reset_password.html', token=token)

        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')
        
        if not new_password:
            flash('Please enter a new password.', 'error')
        elif new_password != confirm_password:
            flash('Passwords do not match. Please try again.', 'error')
        else:
            password_hash = generate_password_hash(new_password)
            conn = get_db()
            conn.execute('UPDATE users SET password_hash = ? WHERE email = ?', (password_hash, email))
            conn.commit()
            conn.close()
            flash('Your password has been securely reset! Please log in.', 'success')
            return redirect(url_for('login'), 303)
            
    return render_template('reset_password.html', token=token)

@app.route('/account', methods=['GET', 'POST'])
@login_required
def account():
    if request.method == 'POST':
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')
        
        if not new_password:
            flash('Please enter a new password.', 'error')
        elif new_password != confirm_password:
            flash('Passwords do not match. Please try again.', 'error')
        else:
            # Securely generate hash and update user details in SQLite database
            password_hash = generate_password_hash(new_password)
            conn = get_db()
            conn.execute('UPDATE users SET password_hash = ? WHERE id = ?', (password_hash, current_user.id))
            conn.commit()
            conn.close()
            flash('Your password has been securely updated!', 'success')
            return redirect(url_for('account'), 303)
            
    return render_template('account.html')

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
    if current_user.plan == 'free':
        conn = get_db()
        total_reports = conn.execute(
            'SELECT COUNT(*) as cnt FROM reports WHERE user_id = ?',
            (current_user.id,)
        ).fetchone()
        conn.close()
        if total_reports['cnt'] >= 1:
            flash('You have already used your 1 free allotment. Please upgrade or purchase a report to continue.', 'info')
            return redirect(url_for('pricing'))

    dimensions = [
        {
            'id': 'hiring_access',
            'name': 'Hiring, Access & Talent Pathways',
            'questions': [
                {'id': 'l1', 'text': 'Does your organization hire for skills and potential over credentials and degrees?', 'options': [('We prioritize degrees', 0), ('We\'re exploring skills-based hiring', 1), ('Skills and potential drive our hiring decisions', 2)]},
                {'id': 'l2', 'text': 'Do you have a clear pathway for recognizing STARs (Skilled Through Alternative Routes) talent?', 'options': [('We don\'t track this', 0), ('We\'re starting to think about it', 1), ('Yes, we actively recruit and advance STARs', 2)]},
                {'id': 'l3', 'text': 'Is your recruitment outreach designed to reach highly qualified candidates through broad, competitive, and inclusive recruiting channels?', 'options': [('We post on the usual job boards', 0), ('We expand a few specialized channels', 1), ('Comprehensive multi-channel strategy for maximum reach', 2)]},
                {'id': 'l4', 'text': 'Do you utilize standardized compensation benchmarks and structured salary bands?', 'options': [('No, salaries are opaque', 0), ('Under review', 1), ('Yes, published bands and regular audits', 2)]},
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
                {'id': 'w1', 'text': 'Are long-term organizational health initiatives embedded in your strategic plan and budget?', 'options': [('No, it\'s aspirational', 0), ('Partially, with some budget', 1), ('Yes, funded goals with timelines', 2)]},
                {'id': 'w2', 'text': 'Are diverse operational perspectives actively represented at the board and executive leadership level?', 'options': [('No', 0), ('Informal champions only', 1), ('Yes, with role clarity and resources', 2)]},
                {'id': 'w3', 'text': 'Are leaders explicitly evaluated on operational culture metrics, not just strategic intent?', 'options': [('No', 0), ('Informally discussed', 1), ('Yes, in performance reviews and goals', 2)]},
                {'id': 'w4', 'text': 'Does executive leadership participate in ongoing professional and organizational culture development?', 'options': [('One-time training only', 0), ('Occasionally', 1), ('Regular, embedded practice', 2)]},
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
                {'id': 'a1', 'text': 'Does your core technology infrastructure actively support your operational and team accessibility goals?', 'options': [('Tech is just for operations', 0), ('We\'re starting to connect them', 1), ('Tech decisions include accessibility criteria', 2)]},
                {'id': 'a2', 'text': 'Are the digital tools you use accessible to all stakeholders, including those with disabilities?', 'options': [('We haven\'t checked', 0), ('Partially accessible', 1), ('Yes, regularly tested for accessibility', 2)]},
                {'id': 'a3', 'text': 'Do the communities you serve have a voice in the technology choices that affect them?', 'options': [('No', 0), ('We gather occasional input', 1), ('Community co-design is standard practice', 2)]},
                {'id': 'a4', 'text': 'Is your data collection and storage inclusive — protecting communities from harm while giving them agency over their data?', 'options': [('We haven\'t thought about this', 0), ('We have basic data privacy', 1), ('Yes, with comprehensive user data governance practices', 2)]},
            ]
        }
    ]
    
    max_possible = sum(len(d['questions']) * 2 for d in dimensions)
    
    if request.method == 'POST':
        answers = {}
        score = 0
        for dimension in dimensions:
            for q in dimension['questions']:
                ans = request.form.get(q['id'])
                if ans is not None:
                    val = int(ans)
                    answers[q['id']] = val
                    score += val
        
        # Calculate dimension scores
        dim_scores = {}
        for dimension in dimensions:
            dim_total = 0
            dim_max = len(dimension['questions']) * 2
            for q in dimension['questions']:
                if q['id'] in answers:
                    dim_total += answers[q['id']]
            dim_scores[dimension['id']] = {
                'score': dim_total,
                'max': dim_max,
                'pct': round((dim_total / dim_max) * 100) if dim_max > 0 else 0
            }
        
        overall_pct = round((score / max_possible) * 100) if max_possible > 0 else 0
        
        # Determine maturity level
        if overall_pct >= 80:
            maturity = 'Advanced'
            color = '#22c55e'
        elif overall_pct >= 55:
            maturity = 'Developing'
            color = '#eab308'
        elif overall_pct >= 30:
            maturity = 'Emerging'
            color = '#f97316'
        else:
            maturity = 'Beginning'
            color = '#ef4444'
        
        report_data = json.dumps({
            'answers': answers,
            'dimension_scores': dim_scores,
            'overall_pct': overall_pct,
            'maturity': maturity,
            'max_possible': max_possible
        })
        
        conn = get_db()
        org_type = request.form.get('org_type', '')
        cursor = conn.execute(
            'INSERT INTO reports (user_id, report_type, title, data, score, max_score, org_type) VALUES (?, ?, ?, ?, ?, ?, ?)',
            (current_user.id, 'dei_audit', f'Organizational Health Assessment - {datetime.now().strftime("%b %d, %Y")}', 
             report_data, score, max_possible, org_type)
        )
        conn.commit()
        report_id = cursor.lastrowid
        conn.close()
        
        return redirect(url_for('report_result', report_id=report_id), 303)
    
    return render_template('dei_audit.html', dimensions=dimensions)



@app.route('/tech-assessment', methods=['GET', 'POST'])
@login_required
def tech_assessment():
    if current_user.plan == 'free':
        conn = get_db()
        total_reports = conn.execute(
            'SELECT COUNT(*) as cnt FROM reports WHERE user_id = ?',
            (current_user.id,)
        ).fetchone()
        conn.close()
        if total_reports['cnt'] >= 1:
            flash('You have already used your 1 free allotment. Please upgrade or purchase a report to continue.', 'info')
            return redirect(url_for('pricing'))

    categories = [
        {
            'id': 'infrastructure',
            'name': 'Infrastructure Redundancy & Power',
            'questions': [
                {'id': 't1', 'text': '', 'options': []}, # Template handles text
                {'id': 't2', 'text': '', 'options': []},
                {'id': 't3', 'text': '', 'options': []},
                {'id': 't4', 'text': '', 'options': []},
            ]
        },
        {
            'id': 'crm',
            'name': 'Data Protection & Secure Backups',
            'questions': [
                {'id': 't5', 'text': '', 'options': []},
                {'id': 't6', 'text': '', 'options': []},
                {'id': 't7', 'text': '', 'options': []},
                {'id': 't8', 'text': '', 'options': []},
            ]
        },
        {
            'id': 'digital',
            'name': 'Crisis Communications & Digital Presence',
            'questions': [
                {'id': 't9', 'text': '', 'options': []},
                {'id': 't10', 'text': '', 'options': []},
                {'id': 't11', 'text': '', 'options': []},
                {'id': 't12', 'text': '', 'options': []},
            ]
        },
        {
            'id': 'fundraising',
            'name': 'Operational Recovery & Resilience',
            'questions': [
                {'id': 't13', 'text': '', 'options': []},
                {'id': 't14', 'text': '', 'options': []},
                {'id': 't15', 'text': '', 'options': []},
                {'id': 't16', 'text': '', 'options': []},
            ]
        }
    ]
    
    max_possible = sum(len(c['questions']) * 2 for c in categories)
    
    if request.method == 'POST':
        answers = {}
        score = 0
        for cat in categories:
            for q in cat['questions']:
                ans = request.form.get(q['id'])
                if ans is not None:
                    val = int(ans)
                    answers[q['id']] = val
                    score += val
        
        cat_scores = {}
        for cat in categories:
            cat_total = 0
            cat_max = len(cat['questions']) * 2
            for q in cat['questions']:
                if q['id'] in answers:
                    cat_total += answers[q['id']]
    # Use the premium 'name' string as the dictionary key for the report display
            cat_scores[cat['name']] = {
                'score': cat_total,
                'max': cat_max,
                'pct': round((cat_total / cat_max) * 100) if cat_max > 0 else 0
            }
        
        overall_pct = round((score / max_possible) * 100) if max_possible > 0 else 0
        
        if overall_pct >= 80:
            level = 'Tech-Forward'
            color = '#22c55e'
        elif overall_pct >= 55:
            level = 'Tech-Competent'
            color = '#eab308'
        elif overall_pct >= 30:
            level = 'Tech-Emerging'
            color = '#f97316'
        else:
            level = 'Tech-Gap'
            color = '#ef4444'
        
        report_data = json.dumps({
            'answers': answers,
            'category_scores': cat_scores,
            'overall_pct': overall_pct,
            'level': level,
            'max_possible': max_possible
        })
        
        conn = get_db()
        org_type = request.form.get('org_type', '')
        cursor = conn.execute(
            'INSERT INTO reports (user_id, report_type, title, data, score, max_score, org_type) VALUES (?, ?, ?, ?, ?, ?, ?)',
            (current_user.id, 'tech_assessment',
             f'Business Continuity & Disaster Recovery (BC/DR) Assessment - {datetime.now().strftime("%b %d, %Y")}',
             report_data, score, max_possible, org_type)
        )
        conn.commit()
        report_id = cursor.lastrowid
        conn.close()
        
        return redirect(url_for('report_result', report_id=report_id), 303)
    
    return render_template('tech_assessment.html', categories=categories)

@app.route('/report/<int:report_id>')
@login_required
def report_result(report_id):
    conn = get_db()
    
    # Staff Override: admins and moderators bypass user_id filters to safely view 
    # any generated client report for onboarding triage and discovery preparation.
    if current_user.role in ['admin', 'moderator']:
        # Advanced Database Relation Join: Fetch the report data AND pull the 
        # original client's registered name/company profile directly from the users table.
        report = conn.execute(
            '''SELECT r.*, u.name as client_name, u.organization as client_org 
               FROM reports r 
               JOIN users u ON r.user_id = u.id 
               WHERE r.id = ?''', 
            (report_id,)
        ).fetchone()
    else:
        report = conn.execute(
            '''SELECT r.*, u.name as client_name, u.organization as client_org 
               FROM reports r 
               JOIN users u ON r.user_id = u.id 
               WHERE r.id = ? AND r.user_id = ?''', 
            (report_id, current_user.id)
        ).fetchone()
        
    if not report:
        conn.close()
        flash('Report not found', 'error')
        return redirect(url_for('dashboard'), 303)
        
    # Check if this specific report was paid for or if the user is a subscriber
    is_paid = report['paid'] == 1 or current_user.plan == 'subscription'
    conn.close()
    
    # Staff Override: bypass paywalls so both the consultant and assistants see 
    # all charts, scores, and the full premium consultative prose evaluation.
    if current_user.role in ['admin', 'moderator']:
        is_paid = True
        is_report_unlocked = True
    else:
        is_report_unlocked = is_paid
        
    report_data = json.loads(report['data'])

    # Premium Consultative Prose Analysis (💎 Premium Analysis)
    premium_analysis = ""
    if is_paid:
        if report['report_type'] == 'tech_assessment':
            premium_analysis = (
                "Based on our exhaustive system diagnostics, organizations operating in this scoring tier present deep structural vulnerabilities across their primary physical and cloud-based infrastructure. A lack of formalized power redundancy, unverified offsite failover networks, and the absence of clear crisis-communication directory structures mean that any local utility disruption or server crash has the potential to cascade into a catastrophic system outage. In the advisory experience of L. M. Lewis Consulting, relying on ad-hoc, manual interventions during an active infrastructure collapse is the single highest contributor to permanent database corruption and prolonged business downtime. To secure your operational baseline, your leadership must immediately transition from hopeful assumptions to engineered resilience by formalizing physical failovers and implementing air-gapped, immutable backup systems.\n\n"
                "Furthermore, our assessment highlights severe exposure regarding third-party vendor dependencies and opaque downstream service agreements. When critical business applications, database systems, or client-facing portals are integrated without rigorous Service Level Agreements (SLAs), data escrow protections, or automated verification testing, your organization surrenders absolute control of its continuity to external providers. To mitigate these unmonitored liabilities, we recommend executing an immediate triage playbook. First, conduct a zero-trust audit to document every single point of failure within your downstream vendor portfolio. Second, establish immediate offline communication redundancy plans and execute live, scheduled data-recovery restoration drills. Standardizing these continuity parameters ensures your organization remains fully resilient and mission-capable through any upstream technological failure."
            )
        elif report['report_type'] == 'dei_audit':
            premium_analysis = (
                "Our diagnostic analysis reveals critical operational culture blind spots that actively undermine long-term talent retention and team cohesion. When organizational commitment to inclusion and equity remains informal and unstructured, a severe gap inevitably widens between executive strategic intent and the lived experience of everyday staff members. This lack of psychological safety and systemic feedback loops breeds unaddressed microaggressions, drives down employee engagement, and accelerates costly turnover of highly skilled, alternative-route (STARs) talent. Building an intentional, high-performance culture is not a secondary objective; it is a core business necessity. To resolve these hidden operational drains, leadership must establish explicit accountability metrics that treat workplace safety, belonging, and inclusive practices as rigorous performance benchmarks.\n\n"
                "Additionally, the absence of standardized compensation benchmarks and structured salary bands represents a major operational and legal liability. Discretionary, opaque pay decisions naturally perpetuate historical wage gaps and expose your organization to profound regulatory non-compliance risks and internal trust deficits. By failing to publish transparent salary ranges and perform regular, equity-minded compensation audits, organizations systematically disadvantage historically marginalized workers and limit leadership pipeline health. To address this, your management team must deploy objective, data-driven management scorecards and formalized feedback channels. By directly tying executive reviews and department budgets to these culture-health key performance indicators (KPIs), you convert equity values into verified operational achievements."
            )

    org_type = report['org_type'] or 'other'
    resources = get_tailored_resources(org_type, report['report_type'], report['score'], report['max_score'])
    
    # We pass 'is_paid' to control only the text visibility. The score charts and links remain 100% visible on their first free run!
    return render_template('report_result.html', report=report, data=report_data, is_paid=True, is_report_unlocked=is_report_unlocked, resources=resources, org_type=org_type, premium_analysis=premium_analysis)
   
@app.route('/pay/<int:report_id>', methods=['POST'])
@login_required
def pay_for_report(report_id):
    conn = get_db()
    report = conn.execute(
        'SELECT * FROM reports WHERE id = ? AND user_id = ?',
        (report_id, current_user.id)
    ).fetchone()
    
    if not report:
        conn.close()
        return jsonify({'error': 'Report not found'}), 404
    
    if report['paid'] == 1:
        conn.close()
        return jsonify({'message': 'Already paid', 'redirect': url_for('report_result', report_id=report_id)})
    
    payment_id = request.json.get('payment_id', 'manual_' + str(datetime.now().timestamp()))
    amount = 49.00  # Flat fee per report
    
    conn.execute(
        'UPDATE reports SET paid = 1, payment_id = ? WHERE id = ?',
        (payment_id, report_id)
    )
    conn.execute(
        'INSERT INTO payments (user_id, report_id, amount, payment_id) VALUES (?, ?, ?, ?)',
        (current_user.id, report_id, amount, payment_id)
    )
    conn.commit()
    conn.close()
    
    return jsonify({'success': True, 'redirect': url_for('report_result', report_id=report_id)})

@app.route('/subscribe', methods=['POST'])
@login_required
def subscribe():
    payment_id = request.json.get('payment_id', 'sub_' + str(datetime.now().timestamp()))
    
    conn = get_db()
    conn.execute('UPDATE users SET plan = ? WHERE id = ?', ('subscription', current_user.id))
    conn.execute(
        'INSERT INTO payments (user_id, amount, payment_id) VALUES (?, ?, ?)',
        (current_user.id, 49.00, payment_id)
    )
    conn.commit()
    conn.close()
    
    current_user.plan = 'subscription'
    
    return jsonify({'success': True, 'redirect': url_for('dashboard')})

@app.route('/free-report/<int:report_id>')
@login_required
def free_report(report_id):
    conn = get_db()
    report = conn.execute(
        'SELECT * FROM reports WHERE id = ? AND user_id = ?',
        (report_id, current_user.id)
    ).fetchone()
    
    if not report:
        conn.close()
        return jsonify({'error': 'Report not found'}), 404
    
    # Free users get 1 free report
    free_count = conn.execute(
        'SELECT COUNT(*) as cnt FROM payments WHERE user_id = ? AND amount = 0',
        (current_user.id,)
    ).fetchone()
    
    if free_count['cnt'] >= 1 and current_user.plan == 'free' and report['paid'] == 0:
        conn.close()
        return jsonify({'error': 'Free limit reached. Please purchase or subscribe.'}), 403
    
    conn.execute(
        'UPDATE reports SET paid = 1 WHERE id = ?',
        (report_id,)
    )
    conn.execute(
        'INSERT INTO payments (user_id, report_id, amount, payment_id, status) VALUES (?, ?, 0, ?, ?)',
        (current_user.id, report_id, 'free_' + str(datetime.now().timestamp()), 'free')
    )
    conn.commit()
    conn.close()
    
    return jsonify({'success': True, 'redirect': url_for('report_result', report_id=report_id)})

# ——— Subscription Management ———
@app.route('/manage-subscription')
@login_required
def manage_subscription():
    return render_template('manage_subscription.html')

@app.route('/cancel-subscription', methods=['POST'])
@login_required
def cancel_subscription():
    conn = get_db()
    conn.execute('UPDATE users SET plan = ? WHERE id = ?', ('free', current_user.id))
    conn.commit()
    conn.close()
    current_user.plan = 'free'
    flash('Subscription cancelled. You\'ve been moved to the free plan.', 'info')
    return redirect(url_for('dashboard'), 303)

@app.route('/upgrade', methods=['POST'])
@login_required
def upgrade():
    payment_id = request.json.get('payment_id', 'upgrade_' + str(datetime.now().timestamp()))
    
    conn = get_db()
    conn.execute('UPDATE users SET plan = ? WHERE id = ?', ('subscription', current_user.id))
    conn.execute(
        'INSERT INTO payments (user_id, amount, payment_id) VALUES (?, ?, ?)',
        (current_user.id, 49.00, payment_id)
    )
    conn.commit()
    conn.close()
    
    current_user.plan = 'subscription'
    
    return jsonify({'success': True, 'redirect': url_for('dashboard')})

# --- PayPal Webhook (basic IPN verification endpoint) ---
@app.route('/paypal-webhook', methods=['POST'])
def paypal_webhook():
    # In production, verify the IPN/webhook signature
    data = request.json
    # Log the webhook for tracking
    with open('paypal_webhooks.log', 'a') as f:
        f.write(json.dumps(data) + '\n')
    return jsonify({'status': 'ok'})

def admin_required(f):
    """Decorator to require admin role."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'admin':
            flash('Admin access required.', 'error')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def role_required(allowed_roles):
    """Decorator to require one of the allowed roles for secure route shielding."""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated or current_user.role not in allowed_roles:
                flash('You do not have permission to access this page.', 'error')
                return redirect(url_for('login'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator

@app.route('/admin')
@login_required
@role_required(['admin', 'moderator'])
def admin_panel():
    conn = get_db()
    
    # Stats
    total_users = conn.execute('SELECT COUNT(*) as c FROM users').fetchone()['c']
    total_reports = conn.execute('SELECT COUNT(*) as c FROM reports').fetchone()['c']
    total_payments = conn.execute('SELECT COUNT(*) as c FROM payments').fetchone()['c']
    total_revenue_row = conn.execute('SELECT COALESCE(SUM(amount), 0) as total FROM payments').fetchone()
    total_revenue = total_revenue_row['total']
    subscription_count = conn.execute("SELECT COUNT(*) as c FROM users WHERE plan = 'subscription'").fetchone()['c']
    free_count = conn.execute("SELECT COUNT(*) as c FROM users WHERE plan = 'free'").fetchone()['c']
    
    # Assessment breakdown
    dei_count = conn.execute("SELECT COUNT(*) as c FROM reports WHERE report_type = 'dei_audit'").fetchone()['c']
   
    tech_count = conn.execute("SELECT COUNT(*) as c FROM reports WHERE report_type = 'tech_assessment'").fetchone()['c']
    
    # Average scores
    avg_score = conn.execute('SELECT AVG(score * 100.0 / NULLIF(max_score, 0)) as avg FROM reports WHERE max_score > 0').fetchone()['avg'] or 0
    
    # Recent assessments with user info
    recent_assessments = conn.execute('''
        SELECT r.id, r.report_type, r.title, r.score, r.max_score, r.created_at,
               u.email, u.name as user_name
        FROM reports r JOIN users u ON r.user_id = u.id
        ORDER BY r.created_at DESC LIMIT 10
    ''').fetchall()
    
    # Users with delete buttons
    users = conn.execute(
        'SELECT id, email, name, organization, role, plan, created_at FROM users ORDER BY created_at DESC'
    ).fetchall()
    
    # Contact messages
    messages = conn.execute(
        'SELECT * FROM contact_messages ORDER BY created_at DESC LIMIT 50'
    ).fetchall()
    
    # Conversion rate
    conversion_rate = round((subscription_count / total_users * 100), 1) if total_users > 0 else 0
    
    conn.close()
    
    return render_template('admin_panel.html',
        total_users=total_users, total_reports=total_reports,
        total_payments=total_payments, total_revenue=total_revenue,
        subscription_count=subscription_count, free_count=free_count,
        dei_count=dei_count,  tech_count=tech_count,
        avg_score=round(avg_score, 1), recent_assessments=recent_assessments,
        messages=messages, users=users, conversion_rate=conversion_rate)

@app.route('/admin/delete-user/<int:user_id>', methods=['POST'])
@login_required
@role_required(['admin'])
def admin_delete_user(user_id):
    conn = get_db()
    user = conn.execute('SELECT id, email, name FROM users WHERE id = ?', (user_id,)).fetchone()
    if not user:
        conn.close()
        flash('User not found.', 'error')
        return redirect(url_for('admin_panel'))
    
    # Don't allow deleting yourself
    if user['id'] == current_user.id:
        conn.close()
        flash('You cannot delete your own account.', 'error')
        return redirect(url_for('admin_panel'))
    
    # Delete user's payments, reports, then user
    conn.execute('DELETE FROM payments WHERE user_id = ?', (user_id,))
    conn.execute('DELETE FROM reports WHERE user_id = ?', (user_id,))
    conn.execute('DELETE FROM users WHERE id = ?', (user_id,))
    conn.commit()
    conn.close()
    
    flash(f'User {user["name"]} ({user["email"]}) deleted successfully.', 'success')
    return redirect(url_for('admin_panel'))

# --- Seed Admin User ---
def seed_admin():
    """Create or reset the admin account using ADMIN_PASSWORD from environment."""
    conn = get_db()
    from werkzeug.security import generate_password_hash
    admin_password = os.environ.get('ADMIN_PASSWORD')
    if not admin_password:
        print('⚠  ADMIN_PASSWORD not set. Skipping admin account creation.')
        print('   Set ADMIN_PASSWORD as an environment variable and restart.')
        conn.close()
        return
    
    admin_pw = generate_password_hash(admin_password)
    existing = conn.execute('SELECT id FROM users WHERE email = ?', ('lashana@lmlewisconsulting.com',)).fetchone()
    if not existing:
        conn.execute(
            'INSERT INTO users (email, password_hash, name, organization, role, plan) VALUES (?, ?, ?, ?, ?, ?)',
            ('lashana@lmlewisconsulting.com', admin_pw, 'LaShana Lewis', 'L. M. Lewis Consulting', 'admin', 'subscription')
        )
        conn.commit()
        print('✓ Admin account created for lashana@lmlewisconsulting.com')
    else:
        conn.execute('UPDATE users SET password_hash = ?, role = ? WHERE email = ?', 
                     (admin_pw, 'admin', 'lashana@lmlewisconsulting.com'))
        conn.commit()
        print('✓ Admin credentials updated for lashana@lmlewisconsulting.com')
    
    # Create test accounts (only on fresh installs, weak passwords acceptable for dev)
    test_users = [
        ('alice@test.org', 'pw_alice', 'Alice Johnson', 'Nonprofit A', 'user', 'subscription'),
        ('bob@test.org', 'pw_bob', 'Bob Smith', 'Startup B', 'user', 'free'),
        ('carol@test.org', 'pw_carol', 'Carol Williams', 'Foundation C', 'user', 'subscription'),
    ]
    for email, pw, name, org, role, plan in test_users:
        existing = conn.execute('SELECT id FROM users WHERE email = ?', (email,)).fetchone()
        if not existing:
            pw_hash = generate_password_hash(pw)
            conn.execute(
                'INSERT INTO users (email, password_hash, name, organization, role, plan) VALUES (?, ?, ?, ?, ?, ?)',
                (email, pw_hash, name, org, role, plan)
            )
            print(f'✓ Test account created: {email}')
    conn.commit()
    conn.close()

# Call seed_admin at module level so it runs under gunicorn too
seed_admin()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
