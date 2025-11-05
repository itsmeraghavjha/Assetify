from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, current_user
from werkzeug.security import check_password_hash
from forms import LoginForm
from models import User

# --- Create Blueprint ---
# Note: 'auth' is the name we use in url_for('auth.login')
auth_bp = Blueprint('auth', __name__)


# --- Authentication Routes ---
@auth_bp.route('/', methods=['GET', 'POST'])
@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """User login"""
    if current_user.is_authenticated:
        return redirect(url_for('core.dashboard'))  # <-- UPDATED url_for
    
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(employee_code=form.employee_code.data.strip()).first()
        if user and check_password_hash(user.password_hash, form.password.data):
            login_user(user, remember=form.remember_me.data)
            next_page = request.args.get('next')
            
            flash(f'Welcome back, {user.name}!', 'success')
            if next_page and next_page.startswith('/'):
                return redirect(next_page)
            return redirect(url_for('core.dashboard')) # <-- UPDATED url_for
        else:
            flash('Invalid employee code or password.', 'danger')
            
    return render_template('login.html', form=form)

@auth_bp.route('/logout')
def logout():
    """User logout"""
    logout_user()
    flash('You have been logged out successfully.', 'success')
    return redirect(url_for('auth.login')) # <-- UPDATED url_for