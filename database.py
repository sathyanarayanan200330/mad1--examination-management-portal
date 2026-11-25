import os, sqlite3
from flask import current_app, g
from werkzeug.security import generate_password_hash

SCHEMA = '''
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS users (
 id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, email TEXT NOT NULL UNIQUE,
 password_hash TEXT NOT NULL, role TEXT NOT NULL CHECK(role IN ('admin','examiner','student')),
 phone TEXT DEFAULT '', department TEXT DEFAULT '', status TEXT NOT NULL DEFAULT 'active',
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS courses (
 id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT NOT NULL UNIQUE, name TEXT NOT NULL,
 description TEXT DEFAULT '', status TEXT NOT NULL DEFAULT 'active', created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS examinations (
 id INTEGER PRIMARY KEY AUTOINCREMENT, course_id INTEGER NOT NULL REFERENCES courses(id),
 name TEXT NOT NULL, exam_type TEXT NOT NULL, duration INTEGER NOT NULL,
 max_marks REAL NOT NULL, slot_start TEXT NOT NULL, slot_end TEXT NOT NULL,
 booking_start TEXT NOT NULL, booking_end TEXT NOT NULL,
 status TEXT NOT NULL DEFAULT 'draft', description TEXT DEFAULT '',
 created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS rubrics (
 id INTEGER PRIMARY KEY AUTOINCREMENT, examination_id INTEGER NOT NULL REFERENCES examinations(id) ON DELETE CASCADE,
 criterion TEXT NOT NULL, max_marks REAL NOT NULL, weightage REAL NOT NULL DEFAULT 1,
 description TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS slots (
 id INTEGER PRIMARY KEY AUTOINCREMENT, examination_id INTEGER NOT NULL REFERENCES examinations(id),
 examiner_id INTEGER NOT NULL REFERENCES users(id), exam_date TEXT NOT NULL,
 start_time TEXT NOT NULL, end_time TEXT NOT NULL, capacity INTEGER NOT NULL CHECK(capacity > 0),
 status TEXT NOT NULL DEFAULT 'available', created_at TEXT DEFAULT CURRENT_TIMESTAMP,
 UNIQUE(examiner_id, exam_date, start_time)
);
CREATE TABLE IF NOT EXISTS bookings (
 id INTEGER PRIMARY KEY AUTOINCREMENT, student_id INTEGER NOT NULL REFERENCES users(id),
 slot_id INTEGER NOT NULL REFERENCES slots(id), booked_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 status TEXT NOT NULL DEFAULT 'booked', updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS evaluations (
 id INTEGER PRIMARY KEY AUTOINCREMENT, booking_id INTEGER NOT NULL UNIQUE REFERENCES bookings(id),
 examiner_id INTEGER NOT NULL REFERENCES users(id), total_marks REAL NOT NULL,
 remarks TEXT DEFAULT '', published INTEGER NOT NULL DEFAULT 0,
 evaluated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS evaluation_items (
 id INTEGER PRIMARY KEY AUTOINCREMENT, evaluation_id INTEGER NOT NULL REFERENCES evaluations(id) ON DELETE CASCADE,
 rubric_id INTEGER NOT NULL REFERENCES rubrics(id), marks REAL NOT NULL, remarks TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS settings (
 key TEXT PRIMARY KEY, value TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_bookings_student ON bookings(student_id);
CREATE INDEX IF NOT EXISTS idx_slots_examiner ON slots(examiner_id);
'''

def get_db():
    if 'db' not in g:
        os.makedirs(os.path.dirname(current_app.config['DATABASE']), exist_ok=True)
        g.db = sqlite3.connect(current_app.config['DATABASE'])
        g.db.row_factory = sqlite3.Row
        g.db.execute('PRAGMA foreign_keys = ON')
    return g.db

def close_db(_=None):
    db = g.pop('db', None)
    if db is not None: db.close()

def init_db():
    db = get_db()
    db.executescript(SCHEMA)
    admin = db.execute("SELECT id FROM users WHERE role='admin' LIMIT 1").fetchone()
    if not admin:
        db.execute('INSERT INTO users(name,email,password_hash,role,status) VALUES(?,?,?,?,?)',
                   ('System Administrator', current_app.config['ADMIN_EMAIL'],
                    generate_password_hash(current_app.config['ADMIN_PASSWORD']), 'admin', 'active'))
    defaults = {'slot_creation_open':'0', 'booking_open':'0'}
    for k,v in defaults.items(): db.execute('INSERT OR IGNORE INTO settings(key,value) VALUES(?,?)',(k,v))
    db.commit()

def setting(key, default='0'):
    row = get_db().execute('SELECT value FROM settings WHERE key=?',(key,)).fetchone()
    return row['value'] if row else default

def set_setting(key, value):
    db=get_db(); db.execute('INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',(key,str(value))); db.commit()
