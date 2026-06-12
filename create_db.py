import os
import psycopg2
from dotenv import load_dotenv
from werkzeug.security import generate_password_hash
from datetime import datetime

load_dotenv()

# Connect to PostgreSQL (Supabase)
conn = psycopg2.connect(os.environ.get('DATABASE_URL'))
cursor = conn.cursor()

print("Dropping old tables if they exist...")
cursor.execute('''
DROP TABLE IF EXISTS notifications CASCADE;
DROP TABLE IF EXISTS portfolio_items CASCADE;
DROP TABLE IF EXISTS bookings CASCADE;
DROP TABLE IF EXISTS reviews CASCADE;
DROP TABLE IF EXISTS messages CASCADE;
DROP TABLE IF EXISTS conversations CASCADE;
DROP TABLE IF EXISTS vip_requests CASCADE;
DROP TABLE IF EXISTS standard_requests CASCADE;
DROP TABLE IF EXISTS worker_vip_applications CASCADE;
DROP TABLE IF EXISTS worker_availability CASCADE;
DROP TABLE IF EXISTS worker_profiles CASCADE;
DROP TABLE IF EXISTS users CASCADE;
DROP TABLE IF EXISTS professions CASCADE;
DROP TABLE IF EXISTS locations CASCADE;
''')

print("Creating tables...")
cursor.execute('''
CREATE TABLE locations (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    name_fr TEXT,
    name_en TEXT
);

CREATE TABLE professions (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    name_fr TEXT,
    name_en TEXT,
    category TEXT CHECK(category IN ('manual', 'digital')) NOT NULL
);

CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT UNIQUE,
    password_hash TEXT,
    role TEXT CHECK(role IN ('customer', 'worker', 'admin')) NOT NULL,
    phone TEXT,
    location_id INTEGER,
    latitude REAL DEFAULT 32.4912,
    longitude REAL DEFAULT 3.6744,
    preferred_lang TEXT DEFAULT 'ar',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (location_id) REFERENCES locations(id)
);

CREATE TABLE worker_profiles (
    id SERIAL PRIMARY KEY,
    user_id INTEGER UNIQUE,
    profession_id INTEGER,
    is_ready_for_vip BOOLEAN DEFAULT FALSE,
    is_vip_approved BOOLEAN DEFAULT FALSE,
    rating REAL DEFAULT 0.0,
    review_count INTEGER DEFAULT 0,
    bio TEXT,
    proof_file_path TEXT,
    status TEXT CHECK(status IN ('pending', 'active', 'inactive', 'rejected', 'suspended')) DEFAULT 'pending',
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (profession_id) REFERENCES professions(id)
);

CREATE TABLE worker_availability (
    id SERIAL PRIMARY KEY,
    worker_profile_id INTEGER,
    day_of_week INTEGER CHECK(day_of_week BETWEEN 0 AND 6),
    start_time TEXT,
    end_time TEXT,
    FOREIGN KEY (worker_profile_id) REFERENCES worker_profiles(id)
);

CREATE TABLE worker_vip_applications (
    id SERIAL PRIMARY KEY,
    worker_id INTEGER,
    status TEXT CHECK(status IN ('pending', 'approved', 'rejected')) DEFAULT 'pending',
    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    admin_notes TEXT,
    FOREIGN KEY (worker_id) REFERENCES worker_profiles(id)
);

CREATE TABLE standard_requests (
    id SERIAL PRIMARY KEY,
    customer_id INTEGER,
    worker_id INTEGER,
    description TEXT,
    status TEXT CHECK(status IN ('pending', 'accepted', 'completed', 'cancelled', 'rejected')) DEFAULT 'pending',
    worker_confirmed BOOLEAN DEFAULT FALSE,
    customer_confirmed BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (customer_id) REFERENCES users(id),
    FOREIGN KEY (worker_id) REFERENCES worker_profiles(id)
);

CREATE TABLE vip_requests (
    id SERIAL PRIMARY KEY,
    customer_id INTEGER,
    profession_id INTEGER,
    problem_description TEXT,
    location_id INTEGER,
    proof_file_path TEXT,
    status TEXT CHECK(status IN ('pending', 'processing', 'assigned', 'completed', 'cancelled')) DEFAULT 'pending',
    assigned_worker_id INTEGER,
    admin_notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (customer_id) REFERENCES users(id),
    FOREIGN KEY (profession_id) REFERENCES professions(id),
    FOREIGN KEY (location_id) REFERENCES locations(id),
    FOREIGN KEY (assigned_worker_id) REFERENCES worker_profiles(id)
);

CREATE TABLE conversations (
    id SERIAL PRIMARY KEY,
    customer_id INTEGER,
    worker_id INTEGER,
    standard_request_id INTEGER,
    vip_request_id INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (customer_id) REFERENCES users(id),
    FOREIGN KEY (worker_id) REFERENCES users(id),
    FOREIGN KEY (standard_request_id) REFERENCES standard_requests(id),
    FOREIGN KEY (vip_request_id) REFERENCES vip_requests(id)
);

CREATE TABLE messages (
    id SERIAL PRIMARY KEY,
    conversation_id INTEGER,
    sender_id INTEGER,
    content TEXT NOT NULL,
    is_read BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (conversation_id) REFERENCES conversations(id),
    FOREIGN KEY (sender_id) REFERENCES users(id)
);

CREATE TABLE reviews (
    id SERIAL PRIMARY KEY,
    reviewer_id INTEGER,
    worker_profile_id INTEGER,
    rating INTEGER CHECK(rating BETWEEN 1 AND 5),
    comment TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (reviewer_id) REFERENCES users(id),
    FOREIGN KEY (worker_profile_id) REFERENCES worker_profiles(id)
);

CREATE TABLE bookings (
    id SERIAL PRIMARY KEY,
    customer_id INTEGER,
    worker_profile_id INTEGER,
    booking_date TEXT,
    time_slot TEXT,
    description TEXT,
    status TEXT CHECK(status IN ('pending', 'confirmed', 'completed', 'cancelled')) DEFAULT 'pending',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (customer_id) REFERENCES users(id),
    FOREIGN KEY (worker_profile_id) REFERENCES worker_profiles(id)
);

CREATE TABLE portfolio_items (
    id SERIAL PRIMARY KEY,
    worker_profile_id INTEGER,
    image_path TEXT NOT NULL,
    caption TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (worker_profile_id) REFERENCES worker_profiles(id)
);

CREATE TABLE notifications (
    id SERIAL PRIMARY KEY,
    user_id INTEGER,
    title TEXT,
    message TEXT,
    link TEXT,
    is_read BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id)
);
''')

print("Inserting initial data...")
locations = [
    ('بلدية غرداية', 'Commune de Ghardaïa', 'Ghardaia Municipality'),
    ('ضاية بن ضحوة', 'Daïa Ben Dahoua', 'Daia Ben Dahoua'),
    ('العطف', 'El Atteuf', 'El Atteuf'),
    ('بونورة', 'Bounoura', 'Bounoura'),
]
import psycopg2.extras
psycopg2.extras.execute_values(cursor, 'INSERT INTO locations (name, name_fr, name_en) VALUES %s', locations)

professions = [
    ('سباك', 'Plombier', 'Plumber', 'manual'),
    ('كهربائي', 'Électricien', 'Electrician', 'manual'),
    ('نجار', 'Menuisier', 'Carpenter', 'manual'),
    ('بناء', 'Maçon', 'Mason', 'manual'),
    ('البرمجة: تطوير مواقع وتطبيقات', 'Développement web et applications', 'Web & App Development', 'digital'),
    ('التصميم الجرافيكي', 'Design graphique', 'Graphic Design', 'digital'),
    ('التصوير الفوتوغرافي والفيديو', 'Photographie et vidéo', 'Photography & Video', 'digital'),
    ('المونتاج وإنتاج المحتوى', 'Montage et production de contenu', 'Video Editing & Content', 'digital'),
    ('التسويق الرقمي', 'Marketing digital', 'Digital Marketing', 'digital'),
    ('الترجمة والكتابة الإبداعية', 'Traduction et rédaction', 'Translation & Creative Writing', 'digital'),
]
psycopg2.extras.execute_values(cursor, 'INSERT INTO professions (name, name_fr, name_en, category) VALUES %s', professions)

admin_pw = generate_password_hash('admin123')
cursor.execute('INSERT INTO users (name, email, password_hash, role) VALUES (%s, %s, %s, %s)',
           ('مدير النظام', 'admin@promihna.com', admin_pw, 'admin'))

conn.commit()
cursor.close()
conn.close()

print("Database initialized successfully on Supabase (PostgreSQL)!")
