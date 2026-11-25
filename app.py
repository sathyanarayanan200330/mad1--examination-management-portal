from flask import Flask, render_template, request, redirect, url_for, flash, session
from werkzeug.security import generate_password_hash, check_password_hash
from config import Config
from database import get_db, close_db, init_db
from auth import current_user, login_required
from routes.admin import admin_bp
from routes.examiner import examiner_bp
from routes.student import student_bp

app=Flask(__name__); app.config.from_object(Config)
app.teardown_appcontext(close_db)
app.register_blueprint(admin_bp, url_prefix='/admin')
app.register_blueprint(examiner_bp, url_prefix='/examiner')
app.register_blueprint(student_bp, url_prefix='/student')
with app.app_context(): init_db()

@app.context_processor
def inject_globals(): return {'current_user': current_user()}

@app.route('/')
def index(): return redirect(url_for('dashboard') if session.get('user_id') else url_for('login'))

@app.route('/register', methods=['GET','POST'])
def register():
    if request.method=='POST':
        name=request.form.get('name','').strip(); email=request.form.get('email','').strip().lower(); password=request.form.get('password',''); role=request.form.get('role','student')
        if not name or not email or len(password)<8 or role not in ('student','examiner'):
            flash('Enter valid details. Password must contain at least 8 characters.','danger')
        else:
            db=get_db()
            try:
                status='pending' if role=='examiner' else 'active'
                db.execute('INSERT INTO users(name,email,password_hash,role,phone,department,status) VALUES(?,?,?,?,?,?,?)',
                           (name,email,generate_password_hash(password),role,request.form.get('phone','').strip(),request.form.get('department','').strip(),status)); db.commit()
                flash('Registration successful. Examiner accounts require admin approval.' if role=='examiner' else 'Registration successful. You can now log in.','success'); return redirect(url_for('login'))
            except Exception: db.rollback(); flash('That email address is already registered.','danger')
    return render_template('register.html')

@app.route('/login', methods=['GET','POST'])
def login():
    if request.method=='POST':
        email=request.form.get('email','').strip().lower(); password=request.form.get('password','')
        user=get_db().execute('SELECT * FROM users WHERE email=?',(email,)).fetchone()
        if user and check_password_hash(user['password_hash'],password):
            if user['status']!='active': flash('Your account is pending approval or inactive. Contact the administrator.','warning')
            else:
                session.clear(); session.update(user_id=user['id'],role=user['role'],name=user['name']); return redirect(url_for('dashboard'))
        else: flash('Invalid email or password.','danger')
    return render_template('login.html')

@app.route('/logout')
def logout(): session.clear(); flash('You have been logged out.','info'); return redirect(url_for('login'))

@app.route('/dashboard')
@login_required
def dashboard():
    role=session['role']
    return redirect(url_for({'admin':'admin.dashboard','examiner':'examiner.dashboard','student':'student.dashboard'}[role]))

@app.errorhandler(404)
def not_found(_): return render_template('message.html',title='Page not found',message='The requested page does not exist.'),404

if __name__=='__main__': app.run(debug=False)
