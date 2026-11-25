from functools import wraps
from flask import session, redirect, url_for, flash, request
from database import get_db

def login_required(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        if not session.get('user_id'):
            flash('Please log in to continue.', 'warning'); return redirect(url_for('login', next=request.path))
        return fn(*args, **kwargs)
    return wrapped

def roles_required(*roles):
    def decorator(fn):
        @wraps(fn)
        @login_required
        def wrapped(*args, **kwargs):
            if session.get('role') not in roles:
                flash('You do not have permission to access that page.', 'danger'); return redirect(url_for('dashboard'))
            return fn(*args, **kwargs)
        return wrapped
    return decorator

def current_user():
    if not session.get('user_id'): return None
    return get_db().execute('SELECT * FROM users WHERE id=?',(session['user_id'],)).fetchone()
