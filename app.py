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
    # DEI Audit questions across 5 dimensions
    dimensions = [
        {
            'id': 'leadership',
            'name': 'Leadership & Governance',
            'questions': [
                {'id': 'l1', 'text': 'Does your organization have a formal DEI statement or policy?', 'options': [('No', 0), ('In development', 1), ('Yes, adopted', 2)]},
                {'id': 'l2', 'text': 'Is DEI represented at the board/executive level?', 'options': [('No', 0), ('Informal only', 1), ('Yes, formal role', 2)]},
                {'id': 'l3', 'text': 'Does leadership receive regular DEI training?', 'options': [('Never', 0), ('Occasionally', 1), ('Annually or more', 2)]},
                {'id': 'l4', 'text': 'Are DEI goals included in your strategic plan?', 'options': [('No', 0), ('Partially', 1), ('Yes', 2)]},
            ]
        },
        {
            'id': 'workforce',
            'name': 'Workforce & Hiring',
            'questions': [
                {'id': 'w1', 'text': 'Do you track demographic data of your workforce?', 'options': [('No', 0), ('Informally', 1), ('Yes, systematically', 2)]},
                {'id': 'w2', 'text': 'Do you have blind/structured hiring practices?', 'options': [('No', 0), ('Sometimes', 1), ('Always', 2)]},
                {'id': 'w3', 'text': 'Is your recruitment outreach diverse?', 'options': [('No', 0), ('Some channels', 1), ('Yes, multi-channel', 2)]},
                {'id': 'w4', 'text': 'Do you have pay equity policies?', 'options': [('No', 0), ('Under review', 1), ('Yes', 2)]},
            ]
        },
        {
            'id': 'culture',
            'name': 'Culture & Inclusion',
            'questions': [
                {'id': 'c1', 'text': 'Do you conduct employee engagement surveys?', 'options': [('No', 0), ('Sometimes', 1), ('Regularly', 2)]},
                {'id': 'c2', 'text': 'Are there employee resource groups (ERGs)?', 'options': [('No', 0), ('In planning', 1), ('Yes, active', 2)]},
                {'id': 'c3', 'text': 'Do you have a clear anti-discrimination policy?', 'options': [('No', 0), ('Informal', 1), ('Yes, enforced', 2)]},
                {'id': 'c4', 'text': 'Is feedback on inclusion regularly collected?', 'options': [('No', 0), ('Annually', 1), ('Quarterly+', 2)]},
            ]
        },
        {
            'id': 'programs',
            'name': 'Programs & Services',
            'questions': [
                {'id': 'p1', 'text': 'Are your programs accessible to diverse communities?', 'options': [('No', 0), ('Partially', 1), ('Fully', 2)]},
                {'id': 'p2', 'text': 'Do you collect demographic data on program participants?', 'options': [('No', 0), ('Sometimes', 1), ('Always', 2)]},
                {'id': 'p3', 'text': 'Are your materials available in multiple languages?', 'options': [('No', 0), ('A few', 1), ('Yes, where needed', 2)]},
                {'id': 'p4', 'text': 'Do you partner with diverse community organizations?', 'options': [('No', 0), ('Occasionally', 1), ('Regularly', 2)]},
            ]
        },
        {
            'id': 'accountability',
            'name': 'Accountability & Growth',
            'questions': [
                {'id': 'a1', 'text': 'Do you publicly report DEI metrics?', 'options': [('No', 0), ('Internally only', 1), ('Publicly', 2)]},
                {'id': 'a2', 'text': 'Are managers evaluated on DEI outcomes?', 'options': [('No', 0), ('Informally', 1), ('Formally', 2)]},
                {'id': 'a3', 'text': 'Do you have a DEI budget allocation?', 'options': [('No', 0), ('Ad-hoc', 1), ('Dedicated', 2)]},
                {'id': 'a4', 'text': 'Is DEI training mandatory for all staff?', 'options': [('No', 0), ('For some roles', 1), ('Yes, all staff', 2)]},
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
            (current_user.id, 'dei_audit', f'DEI Audit - {datetime.now().strftime("%b %d, %Y")}', 
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
            'id': 'org_docs',
            'name': 'Organizational Documents',
            'items': [
                {'id': 'od1', 'text': 'Mission and vision statements are current and compelling'},
                {'id': 'od2', 'text': 'IRS 501(c)(3) determination letter (or fiscal sponsor letter)'},
                {'id': 'od3', 'text': 'Articles of Incorporation and Bylaws'},
                {'id': 'od4', 'text': 'Board of Directors list with affiliations'},
                {'id': 'od5', 'text': 'Conflict of Interest policy'},
                {'id': 'od6', 'text': 'Current org chart'},
            ]
        },
        {
            'id': 'financial',
            'name': 'Financial Readiness',
            'items': [
                {'id': 'fi1', 'text': 'Most recent audited financial statements'},
                {'id': 'fi2', 'text': 'Current annual budget (income & expenses)'},
                {'id': 'fi3', 'text': 'IRS Form 990 for the past 3 years'},
                {'id': 'fi4', 'text': 'Indirect cost rate agreement or policy'},
                {'id': 'fi5', 'text': 'Clear accounting system and internal controls'},
                {'id': 'fi6', 'text': 'Diversity of funding sources (not >50% from one source)'},
            ]
        },
        {
            'id': 'program',
            'name': 'Program Readiness',
            'items': [
                {'id': 'pr1', 'text': 'Theory of change or logic model documented'},
                {'id': 'pr2', 'text': 'Measurable program outcomes and targets'},
                {'id': 'pr3', 'text': 'Program evaluation methodology in place'},
                {'id': 'pr4', 'text': 'Client/community impact stories and testimonials'},
                {'id': 'pr5', 'text': 'Data collection system for program metrics'},
            ]
        },
        {
            'id': 'staffing',
            'name': 'Staffing & Capacity',
            'items': [
                {'id': 'st1', 'text': 'Key staff bios and qualifications documented'},
                {'id': 'st2', 'text': 'Clear position descriptions for proposed roles'},
                {'id': 'st3', 'text': 'Staff have relevant grant management experience'},
                {'id': 'st4', 'text': 'DEI training completed by key staff'},
                {'id': 'st5', 'text': 'Volunteer management system (if applicable)'},
            ]
        },
        {
            'id': 'tracking',
            'name': 'Grant Management & Tracking',
            'items': [
                {'id': 'gm1', 'text': 'Grant calendar or tracking system in place'},
                {'id': 'gm2', 'text': 'Past grant reports (successful and unsuccessful)'},
                {'id': 'gm3', 'text': 'Funder relationship management process'},
                {'id': 'gm4', 'text': 'Standard grant proposal boilerplate developed'},
                {'id': 'gm5', 'text': 'Post-award reporting templates ready'},
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
            'name': 'Infrastructure & Operations',
            'questions': [
                {'id': 't1', 'text': 'Do you use cloud-based collaboration tools (e.g., Google Workspace, Office 365)?', 'options': [('No', 0), ('Partially', 1), ('Fully cloud-based', 2)]},
                {'id': 't2', 'text': 'Is your data backed up regularly?', 'options': [('No', 0), ('Occasionally', 1), ('Automated daily', 2)]},
                {'id': 't3', 'text': 'Do you have a documented IT security policy?', 'options': [('No', 0), ('Informal', 1), ('Yes, documented', 2)]},
                {'id': 't4', 'text': 'Is your network protected by firewalls and antivirus?', 'options': [('No', 0), ('Basic', 1), ('Enterprise-grade', 2)]},
            ]
        },
        {
            'id': 'crm',
            'name': 'CRM & Data Management',
            'questions': [
                {'id': 't5', 'text': 'Do you use a CRM or donor management system?', 'options': [('No/Spreadsheets', 0), ('Basic system', 1), ('Purpose-built CRM', 2)]},
                {'id': 't6', 'text': 'Can you generate custom reports from your data?', 'options': [('No', 0), ('With difficulty', 1), ('Easily', 2)]},
                {'id': 't7', 'text': 'Is your data clean and deduplicated?', 'options': [('No', 0), ('Partially', 1), ('Regularly maintained', 2)]},
                {'id': 't8', 'text': 'Do you integrate your tools with each other?', 'options': [('No integration', 0), ('Manual sync', 1), ('Automated APIs', 2)]},
            ]
        },
        {
            'id': 'digital',
            'name': 'Digital Presence & Engagement',
            'questions': [
                {'id': 't9', 'text': 'Do you have a modern, mobile-friendly website?', 'options': [('No/Outdated', 0), ('Basic', 1), ('Modern & accessible', 2)]},
                {'id': 't10', 'text': 'Do you use email marketing tools?', 'options': [('No', 0), ('Basic', 1), ('Advanced with analytics', 2)]},
                {'id': 't11', 'text': 'Is your website accessible (ADA/WCAG compliant)?', 'options': [('Not sure', 0), ('Partially', 1), ('Yes, tested', 2)]},
                {'id': 't12', 'text': 'Do you track website/social media analytics?', 'options': [('No', 0), ('Basic', 1), ('Advanced analytics', 2)]},
            ]
        },
        {
            'id': 'fundraising',
            'name': 'Fundraising & Payment Tech',
            'questions': [
                {'id': 't13', 'text': 'Do you accept online donations?', 'options': [('No', 0), ('Basic form', 1), ('Integrated platform', 2)]},
                {'id': 't14', 'text': 'Do you have a donor portal or recurring giving?', 'options': [('No', 0), ('Manual', 1), ('Automated', 2)]},
                {'id': 't15', 'text': 'Do you use event management software?', 'options': [('No', 0), ('Basic', 1), ('Full-featured', 2)]},
                {'id': 't16', 'text': 'Is your payment processing PCI compliant?', 'options': [('Not sure', 0), ('Working on it', 1), ('Yes, certified', 2)]},
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
    
    return render_template('report_result.html', report=report, data=report_data, is_paid=is_paid)

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
    amount = 29.00  # Flat fee per report
    
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
        (current_user.id, 29.00, payment_id)
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
        (current_user.id, 29.00, payment_id)
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

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
