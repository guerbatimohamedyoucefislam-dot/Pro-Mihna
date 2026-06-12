import os
import json
import psycopg2
import psycopg2.extras
from dotenv import load_dotenv
from flask import Flask, render_template, request, redirect, url_for, session, flash, g, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from datetime import datetime
from translations import translations

load_dotenv()
app = Flask(__name__)
app.config['SECRET_KEY'] = 'pro_mihna_super_secret_key'

UPLOAD_FOLDER = os.path.join('static', 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# ========================= DB HELPERS =========================
class PostgresWrapper:
    def __init__(self, conn):
        self.conn = conn
    
    def execute(self, query, args=()):
        pg_query = query.replace('?', '%s')
        cur = self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(pg_query, args)
        return cur
        
    def commit(self):
        self.conn.commit()
        
    def close(self):
        self.conn.close()

def get_db():
    if 'db' not in g:
        conn = psycopg2.connect(
            os.environ.get('DATABASE_URL'),
            cursor_factory=psycopg2.extras.RealDictCursor
        )
        g.db = PostgresWrapper(conn)
    return g.db

@app.teardown_appcontext
def close_db(e=None):
    db = g.pop('db', None)
    if db is not None:
        db.close()

def query_db(query, args=(), one=False):
    db = get_db()
    pg_query = query.replace('?', '%s')
    cur = db.conn.cursor()
    cur.execute(pg_query, args)
    if pg_query.strip().upper().startswith('SELECT') or 'RETURNING' in pg_query.upper():
        rv = cur.fetchall()
        return (rv[0] if rv else None) if one else rv
    db.commit()
    return None

# ========================= TRANSLATION =========================
@app.context_processor
def inject_globals():
    lang = session.get('lang', 'ar')
    lang_data = translations.get(lang, translations['ar'])
    def t(key):
        return lang_data.get(key, key)
    
    notif_count = 0
    if 'user_id' in session:
        n = query_db('SELECT COUNT(id) as c FROM notifications WHERE user_id = ? AND is_read = FALSE', [session['user_id']], one=True)
        notif_count = n['c'] if n else 0
    
    return dict(t=t, current_lang=lang, notif_count=notif_count)

@app.route('/set_lang/<lang>')
def set_lang(lang):
    if lang in ('ar', 'fr', 'en'):
        session['lang'] = lang
    return redirect(request.referrer or url_for('index'))

# ========================= AUTH =========================
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def create_notification(user_id, title, message, link=''):
    db = get_db()
    db.execute('INSERT INTO notifications (user_id, title, message, link) VALUES (?, ?, ?, ?)',
               [user_id, title, message, link])

def get_profession_name(prof, lang='ar'):
    if lang == 'fr': return prof['name_fr'] or prof['name']
    if lang == 'en': return prof['name_en'] or prof['name']
    return prof['name']

def get_location_name(loc, lang='ar'):
    if lang == 'fr': return loc['name_fr'] or loc['name']
    if lang == 'en': return loc['name_en'] or loc['name']
    return loc['name']

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        password = request.form['password']
        role = request.form['role']
        phone = request.form.get('phone', '')
        location_id = request.form.get('location_id')
        lat = request.form.get('latitude', 32.4912)
        lng = request.form.get('longitude', 3.6744)
        
        db = get_db()
        if query_db('SELECT id FROM users WHERE email = ?', [email], one=True):
            flash('البريد الإلكتروني مسجل مسبقاً / Email already registered', 'error')
            return redirect(url_for('register'))
        
        hashed_pw = generate_password_hash(password)
        cursor = db.execute('INSERT INTO users (name, email, password_hash, role, phone, location_id, latitude, longitude) VALUES (?, ?, ?, ?, ?, ?, ?, ?) RETURNING id',
                            [name, email, hashed_pw, role, phone, location_id, lat, lng])
        user_id = cursor.fetchone()['id']
        
        if role == 'worker':
            profession_id = request.form.get('profession_id')
            bio = request.form.get('bio')
            proof_file = request.files.get('proof_file')
            proof_path = ''
            if proof_file and proof_file.filename != '':
                filename = f"proof_{user_id}_{proof_file.filename}"
                proof_path = os.path.join(UPLOAD_FOLDER, filename)
                proof_file.save(proof_path)
                
            db.execute("INSERT INTO worker_profiles (user_id, profession_id, bio, proof_file_path, status) VALUES (?, ?, ?, ?, 'pending')", 
                       [user_id, profession_id, bio, proof_path])
            # Notify admin
            admin = query_db("SELECT id FROM users WHERE role='admin' LIMIT 1", one=True)
            if admin:
                create_notification(admin['id'], 'عامل جديد', f'{name} سجل حساباً جديداً ويحتاج مراجعة', '/admin')
        
        db.commit()
        flash('تم التسجيل بنجاح / Registration successful', 'success')
        return redirect(url_for('login'))
        
    locations = query_db('SELECT * FROM locations')
    professions = query_db('SELECT * FROM professions')
    return render_template('register.html', locations=locations, professions=professions)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        user = query_db('SELECT * FROM users WHERE email = ?', [email], one=True)
        if user and check_password_hash(user['password_hash'], password):
            session['user_id'] = user['id']
            session['user_name'] = user['name']
            session['user_role'] = user['role']
            if user['role'] == 'customer': return redirect(url_for('customer_dashboard'))
            elif user['role'] == 'worker': return redirect(url_for('worker_dashboard'))
            elif user['role'] == 'admin': return redirect(url_for('admin_dashboard'))
        else:
            flash('بيانات الدخول غير صحيحة / Invalid credentials', 'error')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

# ========================= SEARCH =========================
@app.route('/search')
@login_required
def search_workers():
    lang = session.get('lang', 'ar')
    professions = query_db('SELECT * FROM professions')
    locations = query_db('SELECT * FROM locations')
    
    prof_filter = request.args.get('profession_id')
    loc_filter = request.args.get('location_id')
    text_search = request.args.get('q', '').strip()
    
    query = '''
        SELECT wp.id as worker_profile_id, u.name, u.phone, u.latitude, u.longitude,
               p.name as profession_name, p.name_fr as profession_name_fr, p.name_en as profession_name_en,
               l.name as location_name, l.name_fr as location_name_fr, l.name_en as location_name_en,
               wp.rating, wp.review_count, wp.bio
        FROM worker_profiles wp
        JOIN users u ON wp.user_id = u.id
        JOIN professions p ON wp.profession_id = p.id
        JOIN locations l ON u.location_id = l.id
        WHERE u.role = 'worker' AND wp.status = 'active'
    '''
    params = []
    if prof_filter:
        query += ' AND wp.profession_id = ?'
        params.append(prof_filter)
    if loc_filter:
        query += ' AND u.location_id = ?'
        params.append(loc_filter)
    if text_search:
        query += ' AND (u.name LIKE ? OR wp.bio LIKE ? OR p.name LIKE ? OR p.name_fr LIKE ? OR p.name_en LIKE ?)'
        like = f'%{text_search}%'
        params.extend([like, like, like, like, like])
    query += ' ORDER BY wp.rating DESC, wp.review_count DESC'
    workers = query_db(query, params)
    return render_template('search.html', workers=workers, professions=professions, locations=locations)

# ========================= WORKER PROFILE (PUBLIC) =========================
@app.route('/profile/<int:worker_profile_id>')
@login_required
def worker_public_profile(worker_profile_id):
    lang = session.get('lang', 'ar')
    w = query_db('''
        SELECT wp.*, u.name, u.phone, u.latitude, u.longitude,
               p.name as profession_name, p.name_fr as profession_name_fr, p.name_en as profession_name_en,
               l.name as location_name, l.name_fr as location_name_fr, l.name_en as location_name_en
        FROM worker_profiles wp
        JOIN users u ON wp.user_id = u.id
        JOIN professions p ON wp.profession_id = p.id
        JOIN locations l ON u.location_id = l.id
        WHERE wp.id = ?
    ''', [worker_profile_id], one=True)
    
    reviews = query_db('''
        SELECT r.*, u.name as reviewer_name
        FROM reviews r JOIN users u ON r.reviewer_id = u.id
        WHERE r.worker_profile_id = ?
        ORDER BY r.created_at DESC
    ''', [worker_profile_id])
    
    portfolio = query_db('SELECT * FROM portfolio_items WHERE worker_profile_id = ? ORDER BY created_at DESC', [worker_profile_id])
    availability = query_db('SELECT * FROM worker_availability WHERE worker_profile_id = ? ORDER BY day_of_week, start_time', [worker_profile_id])
    
    return render_template('worker_profile.html', w=w, reviews=reviews, portfolio=portfolio, availability=availability)

# ========================= REQUEST WORKER =========================
@app.route('/request_worker/<int:worker_profile_id>', methods=['POST'])
@login_required
def request_worker(worker_profile_id):
    if session.get('user_role') != 'customer': return "Unauthorized", 401
    description = request.form.get('description')
    db = get_db()
    cursor = db.execute('INSERT INTO standard_requests (customer_id, worker_id, description) VALUES (?, ?, ?) RETURNING id',
               [session['user_id'], worker_profile_id, description])
    req_id = cursor.fetchone()['id']
    # Create conversation
    worker_user = query_db('SELECT user_id FROM worker_profiles WHERE id = ?', [worker_profile_id], one=True)
    if worker_user:
        db.execute('INSERT INTO conversations (customer_id, worker_id, standard_request_id) VALUES (?, ?, ?)',
                   [session['user_id'], worker_user['user_id'], req_id])
        create_notification(worker_user['user_id'], 'طلب جديد', f'{session["user_name"]} أرسل لك طلب عمل', '/worker')
    db.commit()
    flash('تم إرسال الطلب بنجاح / Request sent', 'success')
    return redirect(url_for('customer_dashboard'))

# ========================= CUSTOMER DASHBOARD =========================
@app.route('/customer')
@login_required
def customer_dashboard():
    if session.get('user_role') != 'customer': return redirect(url_for('index'))
    professions = query_db('SELECT * FROM professions')
    locations = query_db('SELECT * FROM locations')
    
    std_requests = query_db('''
        SELECT sr.*, u.name as worker_name, p.name as profession_name, u.phone as worker_phone,
               c.id as conversation_id
        FROM standard_requests sr
        LEFT JOIN worker_profiles wp ON sr.worker_id = wp.id
        LEFT JOIN users u ON wp.user_id = u.id
        LEFT JOIN professions p ON wp.profession_id = p.id
        LEFT JOIN conversations c ON c.standard_request_id = sr.id
        WHERE sr.customer_id = ?
        ORDER BY sr.created_at DESC
    ''', [session['user_id']])
    
    vip_reqs = query_db('''
        SELECT vr.*, p.name as profession_name, l.name as location_name,
               u.name as assigned_worker_name, u.phone as worker_phone,
               c.id as conversation_id
        FROM vip_requests vr
        LEFT JOIN professions p ON vr.profession_id = p.id
        LEFT JOIN locations l ON vr.location_id = l.id
        LEFT JOIN worker_profiles wp ON vr.assigned_worker_id = wp.id
        LEFT JOIN users u ON wp.user_id = u.id
        LEFT JOIN conversations c ON c.vip_request_id = vr.id
        WHERE vr.customer_id = ?
        ORDER BY vr.created_at DESC
    ''', [session['user_id']])
    
    bookings = query_db('''
        SELECT b.*, u.name as worker_name, p.name as profession_name
        FROM bookings b
        JOIN worker_profiles wp ON b.worker_profile_id = wp.id
        JOIN users u ON wp.user_id = u.id
        JOIN professions p ON wp.profession_id = p.id
        WHERE b.customer_id = ?
        ORDER BY b.booking_date DESC, b.time_slot DESC
    ''', [session['user_id']])

    top_manual = query_db('''
        SELECT wp.id as worker_profile_id, u.name, p.name as profession_name, p.name_fr as profession_name_fr, p.name_en as profession_name_en, wp.rating, wp.review_count 
        FROM worker_profiles wp JOIN users u ON wp.user_id = u.id JOIN professions p ON wp.profession_id = p.id
        WHERE p.category = 'manual' AND wp.status = 'active'
        ORDER BY wp.rating DESC, wp.review_count DESC LIMIT 3
    ''')

    top_digital = query_db('''
        SELECT wp.id as worker_profile_id, u.name, p.name as profession_name, p.name_fr as profession_name_fr, p.name_en as profession_name_en, wp.rating, wp.review_count 
        FROM worker_profiles wp JOIN users u ON wp.user_id = u.id JOIN professions p ON wp.profession_id = p.id
        WHERE p.category = 'digital' AND wp.status = 'active'
        ORDER BY wp.rating DESC, wp.review_count DESC LIMIT 3
    ''')

    return render_template('customer_dashboard.html', 
                           std_requests=std_requests, vip_requests=vip_reqs, bookings=bookings,
                           professions=professions, locations=locations, top_manual=top_manual, top_digital=top_digital)

# ========================= WORKER DASHBOARD =========================
@app.route('/worker')
@login_required
def worker_dashboard():
    if session.get('user_role') != 'worker': return redirect(url_for('index'))
    profile = query_db('SELECT * FROM worker_profiles WHERE user_id = ?', [session['user_id']], one=True)
    
    std_requests = query_db('''
        SELECT sr.*, u.name as customer_name, u.phone as customer_phone, c.id as conversation_id
        FROM standard_requests sr
        JOIN users u ON sr.customer_id = u.id
        LEFT JOIN conversations c ON c.standard_request_id = sr.id
        WHERE sr.worker_id = ?
        ORDER BY sr.created_at DESC
    ''', [profile['id']])
    
    vip_reqs = query_db('''
        SELECT vr.*, u.name as customer_name, u.phone as customer_phone,
               p.name as profession_name, l.name as location_name, c.id as conversation_id
        FROM vip_requests vr
        JOIN users u ON vr.customer_id = u.id
        JOIN professions p ON vr.profession_id = p.id
        JOIN locations l ON vr.location_id = l.id
        LEFT JOIN conversations c ON c.vip_request_id = vr.id
        WHERE vr.assigned_worker_id = ?
        ORDER BY vr.created_at DESC
    ''', [profile['id']])
    
    vip_app = query_db('SELECT * FROM worker_vip_applications WHERE worker_id = ? ORDER BY applied_at DESC LIMIT 1', [profile['id']], one=True)
    
    vip_monthly = query_db('''
        SELECT to_char(created_at, 'YYYY-MM') as month, COUNT(id) as count 
        FROM vip_requests WHERE assigned_worker_id = ? 
        GROUP BY month ORDER BY month DESC
    ''', [profile['id']])
    
    std_monthly = query_db('''
        SELECT to_char(created_at, 'YYYY-MM') as month, COUNT(id) as count 
        FROM standard_requests WHERE worker_id = ? 
        GROUP BY month ORDER BY month DESC
    ''', [profile['id']])
    
    portfolio = query_db('SELECT * FROM portfolio_items WHERE worker_profile_id = ? ORDER BY created_at DESC', [profile['id']])
    availability = query_db('SELECT * FROM worker_availability WHERE worker_profile_id = ? ORDER BY day_of_week, start_time', [profile['id']])
    
    my_bookings = query_db('''
        SELECT b.*, u.name as customer_name, u.phone as customer_phone
        FROM bookings b JOIN users u ON b.customer_id = u.id
        WHERE b.worker_profile_id = ?
        ORDER BY b.booking_date DESC
    ''', [profile['id']])
    
    return render_template('worker_dashboard.html', profile=profile, std_requests=std_requests,
                           vip_requests=vip_reqs, vip_app=vip_app, vip_monthly=vip_monthly,
                           std_monthly=std_monthly, portfolio=portfolio, availability=availability, bookings=my_bookings)

@app.route('/worker/update_std_request/<int:req_id>', methods=['POST'])
@login_required
def update_std_request(req_id):
    if session.get('user_role') != 'worker': return "Unauthorized", 401
    status = request.form.get('status')
    db = get_db()
    req = query_db('SELECT * FROM standard_requests WHERE id = ?', [req_id], one=True)
    if not req: return redirect(url_for('worker_dashboard'))
    
    if status == 'accepted':
        db.execute("UPDATE standard_requests SET status = 'accepted' WHERE id = ?", [req_id])
        create_notification(req['customer_id'], 'تم القبول', f'{session["user_name"]} قبل طلبك', '/customer')
    elif status == 'rejected':
        db.execute("UPDATE standard_requests SET status = 'rejected' WHERE id = ?", [req_id])
        create_notification(req['customer_id'], 'تم الرفض', f'{session["user_name"]} رفض طلبك', '/customer')
    elif status == 'worker_done':
        db.execute('UPDATE standard_requests SET worker_confirmed = TRUE WHERE id = ?', [req_id])
        if req['customer_confirmed']:
            db.execute("UPDATE standard_requests SET status = 'completed' WHERE id = ?", [req_id])
            create_notification(req['customer_id'], 'مكتمل ✅', f'تم إتمام الطلب بتأكيد الطرفين', '/customer')
        else:
            create_notification(req['customer_id'], 'تأكيد إنجاز', f'{session["user_name"]} أكد إتمام العمل، أكّد أنت أيضاً', '/customer')
    db.commit()
    return redirect(url_for('worker_dashboard'))

@app.route('/customer/confirm_completion/<int:req_id>', methods=['POST'])
@login_required
def confirm_completion(req_id):
    if session.get('user_role') != 'customer': return "Unauthorized", 401
    db = get_db()
    req = query_db('SELECT * FROM standard_requests WHERE id = ? AND customer_id = ?', [req_id, session['user_id']], one=True)
    if not req: return redirect(url_for('customer_dashboard'))
    
    db.execute('UPDATE standard_requests SET customer_confirmed = TRUE WHERE id = ?', [req_id])
    if req['worker_confirmed']:
        db.execute("UPDATE standard_requests SET status = 'completed' WHERE id = ?", [req_id])
        worker_user = query_db('SELECT user_id FROM worker_profiles WHERE id = ?', [req['worker_id']], one=True)
        if worker_user:
            create_notification(worker_user['user_id'], 'مكتمل ✅', f'الزبون أكد إتمام العمل', '/worker')
    else:
        worker_user = query_db('SELECT user_id FROM worker_profiles WHERE id = ?', [req['worker_id']], one=True)
        if worker_user:
            create_notification(worker_user['user_id'], 'تأكيد إنجاز', f'{session["user_name"]} أكد إتمام العمل، أكّد أنت أيضاً', '/worker')
    db.commit()
    return redirect(url_for('customer_dashboard'))

@app.route('/worker/upload_portfolio', methods=['POST'])
@login_required
def upload_portfolio():
    if session.get('user_role') != 'worker': return "Unauthorized", 401
    profile = query_db('SELECT id FROM worker_profiles WHERE user_id = ?', [session['user_id']], one=True)
    if not profile: return redirect(url_for('worker_dashboard'))
    
    img = request.files.get('portfolio_image')
    caption = request.form.get('caption', '')
    if img and img.filename != '':
        filename = f"portfolio_{profile['id']}_{datetime.now().strftime('%Y%m%d%H%M%S')}_{img.filename}"
        img.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        db = get_db()
        db.execute('INSERT INTO portfolio_items (worker_profile_id, image_path, caption) VALUES (?, ?, ?)',
                   [profile['id'], filename, caption])
        db.commit()
    return redirect(url_for('worker_dashboard'))

@app.route('/worker/delete_portfolio/<int:item_id>', methods=['POST'])
@login_required
def delete_portfolio(item_id):
    profile = query_db('SELECT id FROM worker_profiles WHERE user_id = ?', [session['user_id']], one=True)
    if profile:
        db = get_db()
        db.execute('DELETE FROM portfolio_items WHERE id = ? AND worker_profile_id = ?', [item_id, profile['id']])
        db.commit()
    return redirect(url_for('worker_dashboard'))

@app.route('/worker/set_availability', methods=['POST'])
@login_required
def set_availability():
    if session.get('user_role') != 'worker': return "Unauthorized", 401
    profile = query_db('SELECT id FROM worker_profiles WHERE user_id = ?', [session['user_id']], one=True)
    if not profile: return redirect(url_for('worker_dashboard'))
    
    day = request.form.get('day_of_week')
    start = request.form.get('start_time')
    end = request.form.get('end_time')
    db = get_db()
    db.execute('INSERT INTO worker_availability (worker_profile_id, day_of_week, start_time, end_time) VALUES (?, ?, ?, ?)',
               [profile['id'], day, start, end])
    db.commit()
    return redirect(url_for('worker_dashboard'))

@app.route('/worker/delete_availability/<int:avail_id>', methods=['POST'])
@login_required
def delete_availability(avail_id):
    profile = query_db('SELECT id FROM worker_profiles WHERE user_id = ?', [session['user_id']], one=True)
    if profile:
        db = get_db()
        db.execute('DELETE FROM worker_availability WHERE id = ? AND worker_profile_id = ?', [avail_id, profile['id']])
        db.commit()
    return redirect(url_for('worker_dashboard'))

# ========================= BOOKING =========================
@app.route('/book/<int:worker_profile_id>', methods=['GET', 'POST'])
@login_required
def book_worker(worker_profile_id):
    if session.get('user_role') != 'customer': return redirect(url_for('index'))
    
    w = query_db('''
        SELECT wp.*, u.name, p.name as profession_name
        FROM worker_profiles wp JOIN users u ON wp.user_id = u.id JOIN professions p ON wp.profession_id = p.id
        WHERE wp.id = ?
    ''', [worker_profile_id], one=True)
    
    availability = query_db('SELECT * FROM worker_availability WHERE worker_profile_id = ? ORDER BY day_of_week, start_time', [worker_profile_id])
    
    if request.method == 'POST':
        booking_date = request.form.get('booking_date')
        time_slot = request.form.get('time_slot')
        description = request.form.get('description', '')
        db = get_db()
        db.execute('INSERT INTO bookings (customer_id, worker_profile_id, booking_date, time_slot, description) VALUES (?, ?, ?, ?, ?)',
                   [session['user_id'], worker_profile_id, booking_date, time_slot, description])
        worker_user = query_db('SELECT user_id FROM worker_profiles WHERE id = ?', [worker_profile_id], one=True)
        if worker_user:
            create_notification(worker_user['user_id'], 'حجز جديد', f'{session["user_name"]} حجز موعداً معك', '/worker')
        db.commit()
        flash('تم الحجز بنجاح / Booking confirmed', 'success')
        return redirect(url_for('customer_dashboard'))
    
    return render_template('booking.html', w=w, availability=availability)

# ========================= REVIEW =========================
@app.route('/review/<int:worker_profile_id>', methods=['POST'])
@login_required
def leave_review(worker_profile_id):
    rating = int(request.form.get('rating', 5))
    comment = request.form.get('comment', '')
    db = get_db()
    db.execute('INSERT INTO reviews (reviewer_id, worker_profile_id, rating, comment) VALUES (?, ?, ?, ?)',
               [session['user_id'], worker_profile_id, rating, comment])
    # Update average
    avg = query_db('SELECT AVG(rating) as avg_r, COUNT(id) as cnt FROM reviews WHERE worker_profile_id = ?', [worker_profile_id], one=True)
    db.execute('UPDATE worker_profiles SET rating = ?, review_count = ? WHERE id = ?',
               [round(avg['avg_r'], 1), avg['cnt'], worker_profile_id])
    worker_user = query_db('SELECT user_id FROM worker_profiles WHERE id = ?', [worker_profile_id], one=True)
    if worker_user:
        create_notification(worker_user['user_id'], 'مراجعة جديدة', f'{session["user_name"]} ترك مراجعة لك', '/worker')
    db.commit()
    return redirect(request.referrer or url_for('customer_dashboard'))

# ========================= CHAT =========================
@app.route('/chat/<int:conversation_id>')
@login_required
def chat(conversation_id):
    conv = query_db('SELECT * FROM conversations WHERE id = ?', [conversation_id], one=True)
    if not conv: return redirect(url_for('index'))
    if session['user_id'] not in (conv['customer_id'], conv['worker_id']):
        return "Unauthorized", 401
    
    other_id = conv['worker_id'] if session['user_id'] == conv['customer_id'] else conv['customer_id']
    other = query_db('SELECT name FROM users WHERE id = ?', [other_id], one=True)
    
    messages = query_db('SELECT m.*, u.name as sender_name FROM messages m JOIN users u ON m.sender_id = u.id WHERE m.conversation_id = ? ORDER BY m.created_at ASC', [conversation_id])
    
    # Mark as read
    db = get_db()
    db.execute('UPDATE messages SET is_read = TRUE WHERE conversation_id = ? AND sender_id != ?', [conversation_id, session['user_id']])
    db.commit()
    
    return render_template('chat.html', conv=conv, messages=messages, other=other)

@app.route('/api/chat/send', methods=['POST'])
@login_required
def api_send_message():
    data = request.get_json() if request.is_json else request.form
    conversation_id = data.get('conversation_id')
    content = data.get('content', '').strip()
    if not content: return jsonify({'error': 'empty'}), 400
    
    conv = query_db('SELECT * FROM conversations WHERE id = ?', [conversation_id], one=True)
    if not conv or session['user_id'] not in (conv['customer_id'], conv['worker_id']):
        return jsonify({'error': 'unauthorized'}), 401
    
    db = get_db()
    db.execute('INSERT INTO messages (conversation_id, sender_id, content) VALUES (?, ?, ?)',
               [conversation_id, session['user_id'], content])
    
    other_id = conv['worker_id'] if session['user_id'] == conv['customer_id'] else conv['customer_id']
    create_notification(other_id, 'رسالة جديدة', f'{session["user_name"]}: {content[:50]}', f'/chat/{conversation_id}')
    db.commit()
    return jsonify({'status': 'ok'})

@app.route('/api/chat/messages/<int:conversation_id>')
@login_required
def api_get_messages(conversation_id):
    messages = query_db('''
        SELECT m.id, m.content, m.sender_id, m.created_at, u.name as sender_name
        FROM messages m JOIN users u ON m.sender_id = u.id
        WHERE m.conversation_id = ?
        ORDER BY m.created_at ASC
    ''', [conversation_id])
    
    result = [{'id': m['id'], 'content': m['content'], 'sender_id': m['sender_id'],
               'sender_name': m['sender_name'], 'created_at': m['created_at'],
               'is_mine': m['sender_id'] == session['user_id']} for m in messages]
    return jsonify(result)

# ========================= NOTIFICATIONS =========================
@app.route('/notifications')
@login_required
def view_notifications():
    notifs = query_db('SELECT * FROM notifications WHERE user_id = ? ORDER BY created_at DESC LIMIT 50', [session['user_id']])
    return render_template('notifications.html', notifs=notifs)

@app.route('/notifications/read_all', methods=['POST'])
@login_required
def mark_all_read():
    db = get_db()
    db.execute('UPDATE notifications SET is_read = TRUE WHERE user_id = ?', [session['user_id']])
    db.commit()
    return redirect(url_for('view_notifications'))

# ========================= ADMIN DASHBOARD =========================
@app.route('/admin')
@login_required
def admin_dashboard():
    if session.get('user_role') != 'admin': return redirect(url_for('index'))
    
    stats = {
        'users': query_db('SELECT COUNT(id) as c FROM users', one=True)['c'],
        'workers': query_db("SELECT COUNT(id) as c FROM users WHERE role='worker'", one=True)['c'],
        'vip': query_db('SELECT COUNT(id) as c FROM vip_requests', one=True)['c'],
        'std': query_db('SELECT COUNT(id) as c FROM standard_requests', one=True)['c'],
        'bookings': query_db('SELECT COUNT(id) as c FROM bookings', one=True)['c'],
    }
    
    vip_requests = query_db('''
        SELECT vr.*, u.name as customer_name, p.name as profession_name, l.name as location_name, wu.name as assigned_worker_name
        FROM vip_requests vr
        JOIN users u ON vr.customer_id = u.id
        JOIN professions p ON vr.profession_id = p.id
        JOIN locations l ON vr.location_id = l.id
        LEFT JOIN worker_profiles wp ON vr.assigned_worker_id = wp.id
        LEFT JOIN users wu ON wp.user_id = wu.id
        ORDER BY vr.created_at DESC
    ''')
    
    vip_applications = query_db('''
        SELECT wva.*, u.name as worker_name, p.name as profession_name
        FROM worker_vip_applications wva
        JOIN worker_profiles wp ON wva.worker_id = wp.id
        JOIN users u ON wp.user_id = u.id
        JOIN professions p ON wp.profession_id = p.id
        ORDER BY wva.applied_at DESC
    ''')
    
    vip_workers = query_db('''
        SELECT wp.id, u.name, p.name as profession_name, l.name as location_name
        FROM worker_profiles wp JOIN users u ON wp.user_id = u.id
        JOIN professions p ON wp.profession_id = p.id JOIN locations l ON u.location_id = l.id
        WHERE wp.status = 'active'
    ''')

    pending_workers = query_db('''
        SELECT wp.id as profile_id, u.name, u.email, u.phone, p.name as profession_name, l.name as location_name, wp.bio, wp.proof_file_path
        FROM worker_profiles wp JOIN users u ON wp.user_id = u.id
        JOIN professions p ON wp.profession_id = p.id JOIN locations l ON u.location_id = l.id
        WHERE wp.status = 'pending'
    ''')

    monthly_stats = query_db('''
        SELECT wu.name as worker_name, to_char(vr.created_at, 'YYYY-MM') as month, COUNT(vr.id) as count
        FROM vip_requests vr
        JOIN worker_profiles wp ON vr.assigned_worker_id = wp.id
        JOIN users wu ON wp.user_id = wu.id
        GROUP BY worker_name, month ORDER BY month DESC, count DESC
    ''')
    
    # Chart data
    monthly_trend = query_db('''
        SELECT to_char(created_at, 'YYYY-MM') as month, COUNT(id) as vip_count FROM vip_requests
        GROUP BY month ORDER BY month
    ''')
    std_trend = query_db('''
        SELECT to_char(created_at, 'YYYY-MM') as month, COUNT(id) as std_count FROM standard_requests
        GROUP BY month ORDER BY month
    ''')
    prof_demand = query_db('''
        SELECT p.name, COUNT(vr.id) as demand_count
        FROM vip_requests vr JOIN professions p ON vr.profession_id = p.id
        GROUP BY p.name ORDER BY demand_count DESC LIMIT 6
    ''')
    
    chart_data = {
        'months': [r['month'] for r in monthly_trend],
        'vip_counts': [r['vip_count'] for r in monthly_trend],
        'std_months': [r['month'] for r in std_trend],
        'std_counts': [r['std_count'] for r in std_trend],
        'prof_names': [r['name'] for r in prof_demand],
        'prof_counts': [r['demand_count'] for r in prof_demand],
    }
    
    q = request.args.get('q', '').strip()
    role_filter = request.args.get('role', '')

    cust_query = """
        SELECT u.id, u.name, u.email, u.phone, l.name as location_name
        FROM users u LEFT JOIN locations l ON u.location_id = l.id
        WHERE u.role = 'customer'
    """
    cust_params = []
    if q:
        cust_query += " AND (u.name LIKE ? OR u.phone LIKE ?)"
        cust_params.extend([f"%{q}%", f"%{q}%"])
    cust_query += " ORDER BY u.id DESC"
    
    work_query = """
        SELECT wp.id, u.name, u.email, u.phone, p.name as profession_name, l.name as location_name, 
        wp.status, wp.rating, wp.is_vip_approved
        FROM worker_profiles wp 
        JOIN users u ON wp.user_id = u.id
        LEFT JOIN professions p ON wp.profession_id = p.id
        LEFT JOIN locations l ON u.location_id = l.id
        ORDER BY u.id DESC
    ''')
    
    return render_template('admin_dashboard.html', stats=stats, vip_requests=vip_requests,
                           vip_applications=vip_applications, vip_workers=vip_workers,
                           pending_workers=pending_workers, monthly_stats=monthly_stats,
                           chart_data=json.dumps(chart_data), all_customers=all_customers, all_workers=all_workers)

@app.route('/vip_request', methods=['GET', 'POST'])
@login_required
def create_vip_request():
    if session.get('user_role') != 'customer': return "Unauthorized", 401
    
    if request.method == 'GET':
        professions = query_db('SELECT * FROM professions')
        locations = query_db('SELECT * FROM locations')
        return render_template('vip_request_form.html', professions=professions, locations=locations)
        
    profession_id = request.form.get('profession_id')
    location_id = request.form.get('location_id')
    problem_description = request.form.get('problem_description')
    
    proof_file = request.files.get('proof_file')
    filename = None
    if proof_file and proof_file.filename != '':
        filename = f"req_{session['user_id']}_{proof_file.filename}"
        proof_file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
    
    db = get_db()
    db.execute('INSERT INTO vip_requests (customer_id, profession_id, problem_description, location_id, proof_file_path) VALUES (?, ?, ?, ?, ?)',
               [session['user_id'], profession_id, problem_description, location_id, filename])
    admin = query_db("SELECT id FROM users WHERE role='admin' LIMIT 1", one=True)
    if admin:
        create_notification(admin['id'], 'طلب VIP جديد', f'{session["user_name"]} أرسل طلب VIP', '/admin')
    db.commit()
    flash('تم إرسال طلب VIP بنجاح', 'success')
    return redirect(url_for('customer_dashboard'))

@app.route('/apply_vip', methods=['POST'])
@login_required
def apply_vip():
    if session.get('user_role') != 'worker': return "Unauthorized", 401
    profile = query_db('SELECT * FROM worker_profiles WHERE user_id = ?', [session['user_id']], one=True)
    if profile:
        db = get_db()
        db.execute('INSERT INTO worker_vip_applications (worker_id) VALUES (?)', [profile['id']])
        db.execute('UPDATE worker_profiles SET is_ready_for_vip = TRUE WHERE id = ?', [profile['id']])
        db.commit()
    return redirect(url_for('worker_dashboard'))

@app.route('/admin/process_vip_app/<int:app_id>', methods=['POST'])
@login_required
def process_vip_app(app_id):
    if session.get('user_role') != 'admin': return "Unauthorized", 401
    status = request.form.get('status')
    notes = request.form.get('admin_notes')
    db = get_db()
    db.execute('UPDATE worker_vip_applications SET status = ?, admin_notes = ? WHERE id = ?', [status, notes, app_id])
    wva = query_db('SELECT worker_id FROM worker_vip_applications WHERE id = ?', [app_id], one=True)
    if status == 'approved' and wva:
        db.execute('UPDATE worker_profiles SET is_vip_approved = TRUE WHERE id = ?', [wva['worker_id']])
        wu = query_db('SELECT user_id FROM worker_profiles WHERE id = ?', [wva['worker_id']], one=True)
        if wu: create_notification(wu['user_id'], 'مقبول في VIP', 'تم قبول طلبك للانضمام لنظام VIP', '/worker')
    db.commit()
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/verify_worker/<int:profile_id>', methods=['POST'])
@login_required
def verify_worker(profile_id):
    if session.get('user_role') != 'admin': return "Unauthorized", 401
    action = request.form.get('action')
    db = get_db()
    new_status = 'active' if action == 'approve' else 'rejected'
    db.execute('UPDATE worker_profiles SET status = ? WHERE id = ?', [new_status, profile_id])
    wu = query_db('SELECT user_id FROM worker_profiles WHERE id = ?', [profile_id], one=True)
    if wu and action == 'approve':
        create_notification(wu['user_id'], 'تم تفعيل حسابك', 'تمت الموافقة على حسابك وأصبح ملفك مرئياً للعملاء', '/worker')
    db.commit()
    flash('تمت معالجة التسجيل', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/assign_vip_worker/<int:req_id>', methods=['POST'])
@login_required
def assign_vip_worker(req_id):
    if session.get('user_role') != 'admin': return "Unauthorized", 401
    worker_id = request.form.get('worker_id')
    db = get_db()
    db.execute("UPDATE vip_requests SET assigned_worker_id = ?, status = 'assigned' WHERE id = ?", [worker_id, req_id])
    
    vr = query_db('SELECT customer_id FROM vip_requests WHERE id = ?', [req_id], one=True)
    wu = query_db('SELECT wp.user_id, u.name as worker_name, u.phone as worker_phone FROM worker_profiles wp JOIN users u ON wp.user_id = u.id WHERE wp.id = ?', [worker_id], one=True)
    if vr and wu:
        db.execute('INSERT INTO conversations (customer_id, worker_id, vip_request_id) VALUES (?, ?, ?)',
                   [vr['customer_id'], wu['user_id'], req_id])
        create_notification(vr['customer_id'], '⭐ عامل VIP', f'تم تعيين العامل {wu["worker_name"]} لطلبك VIP. هاتف: {wu["worker_phone"]}', '/customer')
        create_notification(wu['user_id'], '⭐ طلب VIP جديد', 'تم تعيينك لطلب VIP جديد، تواصل مع الزبون', '/worker')
    db.commit()
    flash('تم تعيين العامل بنجاح', 'success')
    return redirect(url_for('admin_dashboard'))

# ========================= ADMIN PDF REPORT =========================
@app.route('/admin/report')
@login_required
def admin_report():
    if session.get('user_role') != 'admin': return redirect(url_for('index'))
    month = request.args.get('month', datetime.now().strftime('%Y-%m'))
    
    stats = {
        'users': query_db('SELECT COUNT(id) as c FROM users', one=True)['c'],
        'workers': query_db("SELECT COUNT(id) as c FROM users WHERE role='worker'", one=True)['c'],
        'active_workers': query_db("SELECT COUNT(id) as c FROM worker_profiles WHERE status='active'", one=True)['c'],
        'pending_workers': query_db("SELECT COUNT(id) as c FROM worker_profiles WHERE status='pending'", one=True)['c'],
        'std_total': query_db('SELECT COUNT(id) as c FROM standard_requests', one=True)['c'],
        'bookings_total': query_db('SELECT COUNT(id) as c FROM bookings', one=True)['c'],
        'vip_month': query_db("SELECT COUNT(id) as c FROM vip_requests WHERE to_char(created_at, 'YYYY-MM') = ?", [month], one=True)['c'],
        'std_month': query_db("SELECT COUNT(id) as c FROM standard_requests WHERE to_char(created_at, 'YYYY-MM') = ?", [month], one=True)['c'],
    }
    
    workers_perf = query_db('''
        SELECT u.name, p.name as profession_name,
               (SELECT COUNT(id) FROM standard_requests WHERE worker_id = wp.id AND to_char(created_at, 'YYYY-MM') = ?) as std_count,
               (SELECT COUNT(id) FROM vip_requests WHERE assigned_worker_id = wp.id AND to_char(created_at, 'YYYY-MM') = ?) as vip_count,
               wp.rating, wp.review_count
        FROM worker_profiles wp
        JOIN users u ON wp.user_id = u.id
        JOIN professions p ON wp.profession_id = p.id
        WHERE wp.status = 'active'
        ORDER BY (std_count + vip_count) DESC
    ''', [month, month])
    
    return render_template('admin_report.html', stats=stats, workers_perf=workers_perf, month=month)

# ========================= REST API (Mobile) =========================
@app.route('/api/v1/')
def api_index():
    return jsonify({'message': 'Welcome to Pro Mihna API v1', 'version': '1.0', 'endpoints': [
        '/api/v1/login', '/api/v1/workers', '/api/v1/worker/<id>', '/api/v1/notifications'
    ]})

@app.route('/api/v1/login', methods=['POST'])
def api_login():
    data = request.get_json()
    if not data: return jsonify({'error': 'JSON body required'}), 400
    user = query_db('SELECT * FROM users WHERE email = ?', [data.get('email')], one=True)
    if user and check_password_hash(user['password_hash'], data.get('password', '')):
        return jsonify({'status': 'ok', 'user': {
            'id': user['id'], 'name': user['name'], 'email': user['email'],
            'role': user['role'], 'phone': user['phone']
        }})
    return jsonify({'error': 'Invalid credentials'}), 401

@app.route('/api/v1/workers')
def api_workers():
    workers = query_db('''
        SELECT wp.id, u.name, u.phone, u.latitude, u.longitude,
               p.name_en as profession, l.name_en as location, wp.rating, wp.review_count, wp.bio
        FROM worker_profiles wp JOIN users u ON wp.user_id = u.id
        JOIN professions p ON wp.profession_id = p.id JOIN locations l ON u.location_id = l.id
        WHERE wp.status = 'active'
        ORDER BY wp.rating DESC
    ''')
    return jsonify([dict(w) for w in workers])

@app.route('/api/v1/worker/<int:worker_id>')
def api_worker_detail(worker_id):
    w = query_db('''
        SELECT wp.*, u.name, u.phone, u.latitude, u.longitude,
               p.name_en as profession, l.name_en as location
        FROM worker_profiles wp JOIN users u ON wp.user_id = u.id
        JOIN professions p ON wp.profession_id = p.id JOIN locations l ON u.location_id = l.id
        WHERE wp.id = ?
    ''', [worker_id], one=True)
    if not w: return jsonify({'error': 'Not found'}), 404
    
    reviews = query_db('SELECT r.rating, r.comment, u.name as reviewer FROM reviews r JOIN users u ON r.reviewer_id = u.id WHERE r.worker_profile_id = ?', [worker_id])
    portfolio = query_db('SELECT image_path, caption FROM portfolio_items WHERE worker_profile_id = ?', [worker_id])
    
    return jsonify({'worker': dict(w), 'reviews': [dict(r) for r in reviews], 'portfolio': [dict(p) for p in portfolio]})

@app.route('/api/v1/notifications')
@login_required
def api_notifications():
    notifs = query_db('SELECT * FROM notifications WHERE user_id = ? ORDER BY created_at DESC LIMIT 20', [session['user_id']])
    return jsonify([dict(n) for n in notifs])

if __name__ == '__main__':
    app.run(debug=True, port=5000)
