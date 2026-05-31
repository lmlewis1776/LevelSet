import os
import json
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
from functools import wraps

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'equity-engine-dev-secret-key-change-in-prod')

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

# Readiness resources for assessment reports
READINESS_RESOURCES = {
    'high': [
        {
            'name': 'Human Rights Campaign (HRC) Workplace Equality',
            'url': 'https://www.hrc.org/resources/buyers-guide-for-workplace-equality',
            'description': 'HRC provides the Corporate Equality Index (CEI) — a national benchmarking tool for workplace policies and practices related to LGBTQ+ equality.'
        },
        {
            'name': 'NAACP Resources',
            'url': 'https://naacp.org/resources',
            'description': 'NAACP offers resources on racial justice, civic engagement, and organizational equity practices.'
        },
        {
            'name': 'Stanford Social Innovation Review',
            'url': 'https://ssir.org/',
            'description': 'Leading source of ideas and best practices for nonprofits and social enterprises.'
        }
    ],
    'medium': [
        {
            'name': 'National Council of Nonprofits',
            'url': 'https://www.councilofnonprofits.org/',
            'description': 'Resources for nonprofit management best practices, capacity building, and organizational effectiveness.'
        },
        {
            'name': 'Candid / GuideStar',
            'url': 'https://candid.org/',
            'description': 'Nonprofit data, profiles, and resources to help organizations build capacity and find funding.'
        },
        {
            'name': 'TechSoup',
            'url': 'https://www.techsoup.org/',
            'description': 'Technology resources and donations for nonprofits to improve their tech infrastructure.'
        }
    ],
    'basic': [
        {
            'name': 'Idealist',
            'url': 'https://www.idealist.org/',
            'description': 'Community of nonprofits, social enterprises, and changemakers with resources for capacity building.'
        },
        {
            'name': 'NTEN: The Nonprofit Technology Network',
            'url': 'https://www.nten.org/',
            'description': 'Professional development and resources for nonprofit technology and digital strategy.'
        },
        {
            'name': 'L. M. Lewis Consulting',
            'url': 'https://lmlewisconsulting.com',
            'description': 'Ready to go deeper? Book a consultation for personalized guidance on your organizational journey.'
        }
    ]
}

def get_readiness_level(score, max_score):
    pct = round((score / max_score) * 100) if max_score > 0 else 0
    if pct >= 70:
        return 'high'
    elif pct >= 40:
        return 'medium'
    else:
        return 'basic'

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
        email = request.form.get('email')
        password = request.form.get('password')
        captcha_answer = request.form.get('captcha', '')
        captcha_expected = session.get('captcha_answer', 0)
        
        if str(captcha_answer).strip() != str(captcha_expected).strip():
            flash('Incorrect CAPTCHA answer. Please try again.', 'error')
            # Generate new CAPTCHA
            a = random.randint(3, 12)
            b = random.randint(3, 12)
            session['captcha_answer'] = a + b
            session['captcha_question'] = f"What is {a} + {b}?"
            return render_template('login.html')
        
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
    
    # Generate CAPTCHA for GET request
    a = random.randint(3, 12)
    b = random.randint(3, 12)
    session['captcha_answer'] = a + b
    session['captcha_question'] = f"What is {a} + {b}?"
    
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
        cursor = conn.execute(
            'INSERT INTO reports (user_id, report_type, title, data, score, max_score) VALUES (?, ?, ?, ?, ?, ?)',
            (current_user.id, 'dei_audit', f'Equitable Org Audit - {datetime.now().strftime("%b %d, %Y")}', 
             report_data, score, max_possible)
        )
        conn.commit()
        report_id = cursor.lastrowid
        conn.close()
        
        return redirect(url_for('report_result', report_id=report_id), 303)
    
    return render_template('dei_audit.html', dimensions=dimensions)

@app.route('/grant-checklist', methods=['GET', 'POST'])
@login_required
def grant_checklist():
    categories = [
        {
            'id': 'talent_pathways',
            'name': 'Talent Pathways & People Infrastructure',
            'items': [
                {'id': 'od1', 'text': 'Your job descriptions focus on skills and potential rather than credentials and years of experience'},
                {'id': 'od2', 'text': 'You have a process for recognizing and advancing STARs (Skilled Through Alternative Routes) talent'},
                {'id': 'od3', 'text': 'Your interview process is structured and consistent across all candidates'},
                {'id': 'od4', 'text': 'You have clear position descriptions with salary transparency'},
                {'id': 'od5', 'text': 'Staff and leadership reflect the communities you serve'},
                {'id': 'od6', 'text': 'You have a professional development budget that is equitably accessible'},
            ]
        },
        {
            'id': 'equity_infrastructure',
            'name': 'Equity Infrastructure & Accountability',
            'items': [
                {'id': 'fi1', 'text': 'Your mission and vision statements are current and genuinely reflect your equity commitments'},
                {'id': 'fi2', 'text': 'You have a board of directors that reflects community diversity'},
                {'id': 'fi3', 'text': 'You collect data on who you serve and who you\'re missing — and use it'},
                {'id': 'fi4', 'text': 'Community voice is built into your governance or advisory structure'},
                {'id': 'fi5', 'text': 'Your strategic plan includes measurable equity goals with dedicated funding'},
                {'id': 'fi6', 'text': 'You have clear policies on equity, inclusion, and anti-discrimination with accountability mechanisms'},
            ]
        },
        {
            'id': 'mission_ops',
            'name': 'Mission-Aligned Operations & Financial Health',
            'items': [
                {'id': 'pr1', 'text': 'You have a current annual budget tied to programmatic priorities'},
                {'id': 'pr2', 'text': 'Your funding sources are diversified (no single source >50%)'},
                {'id': 'pr3', 'text': 'You have clear accounting systems and internal controls'},
                {'id': 'pr4', 'text': 'Your programs have a documented theory of change or logic model'},
                {'id': 'pr5', 'text': 'You track measurable outcomes and impact data'},
                {'id': 'pr6', 'text': 'Your financial practices are transparent and accessible to stakeholders'},
            ]
        },
        {
            'id': 'community_capacity',
            'name': 'Community Connection & Capacity Building',
            'items': [
                {'id': 'st1', 'text': 'Your programs are designed with community input, not just for community consumption'},
                {'id': 'st2', 'text': 'Your materials and services are accessible across language, ability, and culture'},
                {'id': 'st3', 'text': 'You have community impact stories that center the voices of those you serve'},
                {'id': 'st4', 'text': 'You partner with community-based organizations as equals, not just as referral sources'},
                {'id': 'st5', 'text': 'You have a system for collecting feedback from the communities you serve'},
                {'id': 'st6', 'text': 'Your volunteer and community engagement practices are equitable and reciprocal'},
            ]
        },
        {
            'id': 'readiness_tracking',
            'name': 'Grant Readiness & Funding Strategy',
            'items': [
                {'id': 'gm1', 'text': 'You have a grant tracking system or calendar'},
                {'id': 'gm2', 'text': 'You can produce audited financials or reviewed statements'},
                {'id': 'gm3', 'text': 'Your IRS 501(c)(3) determination and incorporation docs are current'},
                {'id': 'gm4', 'text': 'You have a standard grant proposal boilerplate (mission, approach, impact)'},
                {'id': 'gm5', 'text': 'You have funder relationship management practices beyond just writing checks'},
                {'id': 'gm6', 'text': 'You track which funding opportunities align with your mission vs. chasing every dollar'},
            ]
        }
    ]
    
    if request.method == 'POST':
        results = {}
        total_items = 0
        checked_items = 0
        
        for cat in categories:
            cat_total = len(cat['items'])
            cat_checked = 0
            for item in cat['items']:
                total_items += 1
                if request.form.get(item['id']):
                    cat_checked += 1
                    checked_items += 1
            results[cat['id']] = {
                'checked': cat_checked,
                'total': cat_total,
                'pct': round((cat_checked / cat_total) * 100) if cat_total > 0 else 0
            }
        
        overall_pct = round((checked_items / total_items) * 100) if total_items > 0 else 0
        
        if overall_pct >= 80:
            readiness = 'Highly Ready'
            color = '#22c55e'
        elif overall_pct >= 55:
            readiness = 'Moderately Ready'
            color = '#eab308'
        elif overall_pct >= 30:
            readiness = 'Developing'
            color = '#f97316'
        else:
            readiness = 'Needs Work'
            color = '#ef4444'
        
        report_data = json.dumps({
            'results': results,
            'overall_pct': overall_pct,
            'checked_items': checked_items,
            'total_items': total_items,
            'readiness': readiness
        })
        
        conn = get_db()
        cursor = conn.execute(
            'INSERT INTO reports (user_id, report_type, title, data, score, max_score) VALUES (?, ?, ?, ?, ?, ?)',
            (current_user.id, 'grant_checklist', 
             f'Grant Readiness - {datetime.now().strftime("%b %d, %Y")}',
             report_data, checked_items, total_items)
        )
        conn.commit()
        report_id = cursor.lastrowid
        conn.close()
        
        return redirect(url_for('report_result', report_id=report_id), 303)
    
    return render_template('grant_checklist.html', categories=categories)

@app.route('/tech-assessment', methods=['GET', 'POST'])
@login_required
def tech_assessment():
    categories = [
        {
            'id': 'infrastructure',
            'name': 'Infrastructure & Equity',
            'questions': [
                {'id': 't1', 'text': 'Do you use cloud-based tools that are accessible to all staff regardless of device or location?', 'options': [('No/Limited', 0), ('Partially', 1), ('Yes, fully accessible', 2)]},
                {'id': 't2', 'text': 'Is your data backed up securely and protected from loss?', 'options': [('No/Unsure', 0), ('Occasional backups', 1), ('Automated, tested backups', 2)]},
                {'id': 't3', 'text': 'Do you have an IT security policy that includes protections for community data?', 'options': [('No', 0), ('Basic password policy', 1), ('Yes, comprehensive', 2)]},
                {'id': 't4', 'text': 'Are your digital tools and platforms designed to be accessible to people with disabilities?', 'options': [('Not assessed', 0), ('Partially accessible', 1), ('Yes, WCAG-compliant', 2)]},
            ]
        },
        {
            'id': 'crm',
            'name': 'Data, CRM & Community Insights',
            'questions': [
                {'id': 't5', 'text': 'Do you use a CRM or database that helps you understand who you serve and who you\'re missing?', 'options': [('Spreadsheets only', 0), ('Basic system', 1), ('Purpose-built with equity reporting', 2)]},
                {'id': 't6', 'text': 'Can you generate reports that disaggregate data by race, income, geography, or other equity dimensions?', 'options': [('No', 0), ('With difficulty', 1), ('Easily and regularly', 2)]},
                {'id': 't7', 'text': 'Do your data practices protect community agency — giving people control over their own information?', 'options': [('No/Unsure', 0), ('Basic privacy', 1), ('Yes, community data sovereignty', 2)]},
                {'id': 't8', 'text': 'Do your tools integrate with each other, or do you spend time on manual data entry?', 'options': [('All manual', 0), ('Some integration', 1), ('Automated workflows', 2)]},
            ]
        },
        {
            'id': 'digital',
            'name': 'Digital Presence & Equitable Engagement',
            'questions': [
                {'id': 't9', 'text': 'Is your website modern, mobile-friendly, and accessible to people with disabilities?', 'options': [('Outdated', 0), ('Basic', 1), ('Modern, accessible, tested', 2)]},
                {'id': 't10', 'text': 'Do you use digital tools to engage the communities you serve in ways that work for them?', 'options': [('No/One-size-fits-all', 0), ('Some channels', 1), ('Multi-channel, community-informed', 2)]},
                {'id': 't11', 'text': 'Is your website content available in languages your community speaks?', 'options': [('English only', 0), ('A few pages translated', 1), ('Multi-language by design', 2)]},
                {'id': 't12', 'text': 'Do you track analytics that measure equitable reach — not just total traffic?', 'options': [('Basic page views', 0), ('Some demographic data', 1), ('Yes, equity-focused analytics', 2)]},
            ]
        },
        {
            'id': 'fundraising',
            'name': 'Fundraising Tech & Financial Accessibility',
            'questions': [
                {'id': 't13', 'text': 'Do you accept online payments/donations through an accessible, user-friendly platform?', 'options': [('No/Outdated', 0), ('Basic form', 1), ('Integrated, accessible platform', 2)]},
                {'id': 't14', 'text': 'Do you offer recurring giving or payment options that reduce barriers for supporters?', 'options': [('No', 0), ('Manual only', 1), ('Yes, automated and flexible', 2)]},
                {'id': 't15', 'text': 'Do you use event or program management software that makes participation accessible?', 'options': [('No', 0), ('Basic tools', 1), ('Full-featured and inclusive', 2)]},
                {'id': 't16', 'text': 'Are your payment and donation systems secure and trusted by the communities you serve?', 'options': [('Not sure', 0), ('Basic security', 1), ('Yes, certified and transparent', 2)]},
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
            cat_scores[cat['id']] = {
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
        cursor = conn.execute(
            'INSERT INTO reports (user_id, report_type, title, data, score, max_score) VALUES (?, ?, ?, ?, ?, ?)',
            (current_user.id, 'tech_assessment',
             f'Tech Stack Assessment - {datetime.now().strftime("%b %d, %Y")}',
             report_data, score, max_possible)
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
    report = conn.execute(
        'SELECT * FROM reports WHERE id = ? AND user_id = ?',
        (report_id, current_user.id)
    ).fetchone()
    
    # Check if this is a paid report or user has subscription
    is_paid = report['paid'] == 1 or current_user.plan == 'subscription'
    
    # Free users get a limited version for their first free report
    free_used = False
    if not is_paid and current_user.plan == 'free':
        free_reports = conn.execute(
            'SELECT COUNT(*) as cnt FROM payments WHERE user_id = ? AND amount = 0',
            (current_user.id,)
        ).fetchone()
        if free_reports['cnt'] < 1:
            is_paid = True  # First report is free
    
    conn.close()
    
    if not report:
        flash('Report not found', 'error')
        return redirect(url_for('dashboard'), 303)
    
    report_data = json.loads(report['data'])
    
    # Determine readiness level and get resources
    readiness_level = get_readiness_level(report['score'], report['max_score']) if report['max_score'] > 0 else 'basic'
    resources = READINESS_RESOURCES.get(readiness_level, READINESS_RESOURCES['basic'])
    
    return render_template('report_result.html', report=report, data=report_data, is_paid=is_paid, resources=resources, readiness_level=readiness_level)

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

@app.route('/admin')
@login_required
@admin_required
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
    grant_count = conn.execute("SELECT COUNT(*) as c FROM reports WHERE report_type = 'grant_checklist'").fetchone()['c']
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
        dei_count=dei_count, grant_count=grant_count, tech_count=tech_count,
        avg_score=round(avg_score, 1), recent_assessments=recent_assessments,
        messages=messages, users=users, conversion_rate=conversion_rate)

@app.route('/admin/delete-user/<int:user_id>', methods=['POST'])
@login_required
@admin_required
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
    """Create or reset the admin account."""
    conn = get_db()
    from werkzeug.security import generate_password_hash
    admin_pw = generate_password_hash('LevelSetAdmin2026!')
    existing = conn.execute('SELECT id FROM users WHERE email = ?', ('lashana@lmlewisconsulting.com',)).fetchone()
    if not existing:
        conn.execute(
            'INSERT INTO users (email, password_hash, name, organization, role, plan) VALUES (?, ?, ?, ?, ?, ?)',
            ('lashana@lmlewisconsulting.com', admin_pw, 'LaShana Lewis', 'L. M. Lewis Consulting', 'admin', 'subscription')
        )
        conn.commit()
        print('✓ Admin account created: lashana@lmlewisconsulting.com / LevelSetAdmin2026!')
    else:
        conn.execute('UPDATE users SET password_hash = ?, role = ? WHERE email = ?', 
                     (admin_pw, 'admin', 'lashana@lmlewisconsulting.com'))
        conn.commit()
        print('✓ Admin credentials reset for lashana@lmlewisconsulting.com')
    
    # Create test accounts
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
            print(f'✓ Test account created: {email} / {pw}')
    conn.commit()
    conn.close()

# Call seed_admin at module level so it runs under gunicorn too
seed_admin()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
