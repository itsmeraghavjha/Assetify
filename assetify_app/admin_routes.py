from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app
from flask_login import login_required, current_user
from functools import wraps
from models import db, User, Distributor, AssetRequest
from forms import UserForm, DistributorForm
from sqlalchemy.exc import IntegrityError
from wtforms.validators import DataRequired, Length, EqualTo, Optional 

# --- Create Blueprint ---
admin_bp = Blueprint('admin', __name__)

# --- Helper Functions (Moved from app.py) ---
def role_required(*roles):
    """Decorator to require specific roles"""
    def wrapper(fn):
        @wraps(fn)
        def decorated_view(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for('auth.login')) 
            if current_user.role not in roles:
                flash("You do not have permission to access this page.", "danger")
                return redirect(url_for('core.dashboard'))
            return fn(*args, **kwargs)
        return decorated_view
    return wrapper

def _populate_admin_dropdowns(form):
    """Helper to populate all dropdowns for User and Distributor forms."""
    if hasattr(form, 'distributor_id'):
        distributors = Distributor.query.order_by(Distributor.name).all()
        form.distributor_id.choices = [(d.id, f"{d.name} ({d.code})") for d in distributors]
        form.distributor_id.choices.insert(0, (0, '--- Not a Distributor User ---'))
    if hasattr(form, 'se_id'):
        sales_executives = User.query.filter_by(role='SE').order_by(User.name).all()
        form.se_id.choices = [(se.id, se.name) for se in sales_executives]
        form.se_id.choices.insert(0, (0, '--- Unassigned ---'))
    if hasattr(form, 'bm_id'):
        branch_managers = User.query.filter_by(role='BM').order_by(User.name).all()
        form.bm_id.choices = [(bm.id, f"{bm.name} ({bm.email or 'No Email'})") for bm in branch_managers]
        form.bm_id.choices.insert(0, (0, '--- Select a BM ---'))
    if hasattr(form, 'rh_id'):
        regional_heads = User.query.filter_by(role='RH').order_by(User.name).all()
        form.rh_id.choices = [(rh.id, f"{rh.name} ({rh.email or 'No Email'})") for rh in regional_heads]
        form.rh_id.choices.insert(0, (0, '--- Unassigned ---'))


# --- ADMIN SECTION ---

@admin_bp.route('/')
@login_required
@role_required('Admin')
def dashboard():
    """Admin dashboard redirect"""
    return redirect(url_for('admin.manage_users'))

@admin_bp.route('/users')
@login_required
@role_required('Admin')
def manage_users():
    """Manage users page with sorting and searching"""
    try:
        page = request.args.get('page', 1, type=int)
        sort_by = request.args.get('sort_by', 'name')
        order_by = request.args.get('order_by', 'asc')
        search = request.args.get('search', '').strip()
        query = User.query
        if search:
            search_term = f'%{search}%'
            query = query.filter(
                db.or_(
                    User.name.ilike(search_term),
                    User.employee_code.ilike(search_term),
                    User.email.ilike(search_term),
                    User.role.ilike(search_term)
                )
            )
        sort_column_map = {
            'name': User.name,
            'code': User.employee_code,
            'email': User.email,
            'role': User.role,
            'so': User.so
        }
        sort_field = sort_column_map.get(sort_by, User.name)
        if order_by == 'desc':
            query = query.order_by(sort_field.desc())
        else:
            query = query.order_by(sort_field.asc())
        
        pagination = query.paginate(page=page, per_page=current_app.config['ITEMS_PER_PAGE'], error_out=False)
        
        return render_template(
            'admin/manage_users.html', 
            pagination=pagination,
            users=pagination.items,
            current_sort=sort_by,
            current_order=order_by,
            current_search=search
        )
    except Exception as e:
        flash(f"Error loading users: {e}", "danger")
        return redirect(url_for('core.dashboard'))


@admin_bp.route('/users/add', methods=['GET', 'POST'])
@login_required
@role_required('Admin')
def add_user():
    """Add new user"""
    form = UserForm()
    _populate_admin_dropdowns(form)
    
    form.password.validators = [
        DataRequired(message="Password is required."),
        Length(min=6, message="Password must be at least 6 characters."),
        EqualTo('confirm_password', message='Passwords must match.')
    ]
    
    if form.validate_on_submit():
        existing_code = User.query.filter_by(
            employee_code=form.employee_code.data.strip()
        ).first()
        existing_email = None
        if form.email.data:
            existing_email = User.query.filter(
                db.func.lower(User.email) == form.email.data.strip().lower()
            ).first()
        if existing_code:
            flash('An account with this Employee Code already exists.', 'danger')
        elif existing_email:
            flash('An account with this Email already exists.', 'danger')
        else:
            try:
                new_user = User(
                    name=form.name.data.strip(),
                    employee_code=form.employee_code.data.strip(),
                    email=form.email.data.strip().lower() if form.email.data else None,
                    role=form.role.data,
                    so=form.so.data.strip() if form.so.data else None
                )
                new_user.set_password(form.password.data)
                if new_user.role == 'DB' and form.distributor_id.data != 0:
                    new_user.distributor_id = form.distributor_id.data
                else:
                    new_user.distributor_id = None
                db.session.add(new_user)
                db.session.commit()
                flash(f'User "{new_user.name}" created successfully.', 'success')
                return redirect(url_for('admin.manage_users'))
            except Exception as e:
                db.session.rollback()
                flash(f"Error creating user: {e}", "danger")
    return render_template('admin/user_form.html', form=form, title='Add New User')


@admin_bp.route('/users/edit/<int:user_id>', methods=['GET', 'POST'])
@login_required
@role_required('Admin')
def edit_user(user_id):
    """Edit existing user"""
    user = db.session.get(User, user_id)
    if not user:
        flash("User not found.", "danger")
        return redirect(url_for('admin.manage_users'))
        
    form = UserForm(obj=user)
    _populate_admin_dropdowns(form)
    
    form.password.validators = [
        Optional(),
        Length(min=6, message="Password must be at least 6 characters."),
        EqualTo('confirm_password', message='Passwords must match.')
    ]
    
    if form.validate_on_submit():
        new_employee_code = form.employee_code.data.strip()
        new_email_raw = form.email.data.strip() if form.email.data else None
        new_email = new_email_raw.lower() if new_email_raw else None 
        existing_code = User.query.filter(
            User.employee_code == new_employee_code,
            User.id != user_id
        ).first()
        existing_email = None
        if new_email:
            existing_email = User.query.filter(
                db.func.lower(User.email) == new_email,
                User.id != user_id
            ).first()
        if existing_code:
            flash('This Employee Code is already in use.', 'danger')
        elif existing_email:
            flash('This Email is already in use.', 'danger')
        else:
            try:
                user.name = form.name.data.strip()
                user.employee_code = new_employee_code
                user.email = new_email_raw
                user.role = form.role.data
                user.so = form.so.data.strip() if form.so.data else None
                if form.password.data:
                    user.set_password(form.password.data)
                    
                # --- THIS WAS THE BUG ---
                # This logic was correct, but the form wasn't pre-filling
                # the distributor_id, so form.distributor_id.data was
                # always 0 on POST.
                if user.role == 'DB' and form.distributor_id.data != 0:
                    user.distributor_id = form.distributor_id.data
                else:
                    user.distributor_id = None
                
                db.session.commit()
                flash(f'User "{user.name}" updated successfully.', 'success')
                return redirect(url_for('admin.manage_users'))
            except Exception as e:
                db.session.rollback()
                print(f"--- ERROR during user update: {e} ---") 
                import traceback
                traceback.print_exc() 
                flash(f"Error updating user: {e}", "danger")
    
    # --- THIS IS THE FIX ---
    # This block was missing. It runs on a GET request
    # to pre-select the correct distributor in the dropdown.
    if request.method == 'GET' and user.distributor_id:
        form.distributor_id.data = user.distributor_id
    # --- END OF FIX ---
        
    return render_template('admin/user_form.html', form=form, title=f'Edit User: {user.name}', user=user)

@admin_bp.route('/users/delete/<int:user_id>', methods=['POST'])
@login_required
@role_required('Admin')
def delete_user(user_id):
    """Delete user"""
    user_to_delete = db.session.get(User, user_id)
    if not user_to_delete:
        flash("User not found.", "danger")
        return redirect(url_for('admin.manage_users'))
        
    if user_to_delete.id == current_user.id:
        flash("You cannot delete your own account.", "danger")
        return redirect(url_for('admin.manage_users'))
    has_requests = AssetRequest.query.filter(
        (AssetRequest.requester_id == user_id) |
        (AssetRequest.bm_approver_id == user_id) |
        (AssetRequest.rh_approver_id == user_id)
    ).first()
    if has_requests:
        flash(f'Cannot delete "{user_to_delete.name}" - associated with requests.', 'danger')
        return redirect(url_for('admin.manage_users'))
    is_manager = Distributor.query.filter(
        (Distributor.se_id == user_id) |
        (Distributor.bm_id == user_id) |
        (Distributor.rh_id == user_id)
    ).first()
    if is_manager:
        flash(f'Cannot delete "{user_to_delete.name}" - they are assigned as a manager to one or more distributors. Please re-assign those distributors first.', 'danger')
        return redirect(url_for('admin.manage_users'))
    try:
        db.session.delete(user_to_delete)
        db.session.commit()
        flash(f'User "{user_to_delete.name}" deleted successfully.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f"Error deleting user: {e}", "danger")
    return redirect(url_for('admin.manage_users'))


@admin_bp.route('/distributors')
@login_required
@role_required('Admin')
def manage_distributors():
    """Manage distributors page with sorting and searching"""
    try:
        page = request.args.get('page', 1, type=int)
        sort_by = request.args.get('sort_by', 'name')
        order_by = request.args.get('order_by', 'asc')
        search = request.args.get('search', '').strip()
        SE_User = db.aliased(User)
        BM_User = db.aliased(User)
        RH_User = db.aliased(User)
        query = db.session.query(Distributor).outerjoin(
            SE_User, Distributor.se_id == SE_User.id
        ).outerjoin(
            BM_User, Distributor.bm_id == BM_User.id
        ).outerjoin(
            RH_User, Distributor.rh_id == RH_User.id
        )
        if search:
            search_term = f'%{search}%'
            query = query.filter(
                db.or_(
                    Distributor.name.ilike(search_term),
                    Distributor.code.ilike(search_term),
                    SE_User.name.ilike(search_term),
                    BM_User.name.ilike(search_term),
                    RH_User.name.ilike(search_term)
                )
            )
        sort_column_map = {
            'name': Distributor.name,
            'code': Distributor.code,
            'se': SE_User.name,
            'bm': BM_User.name,
            'rh': RH_User.name
        }
        sort_field = sort_column_map.get(sort_by, Distributor.name)
        if order_by == 'desc':
            query = query.order_by(sort_field.desc())
        else:
            query = query.order_by(sort_field.asc())
        
        pagination = query.paginate(page=page, per_page=current_app.config['ITEMS_PER_PAGE'], error_out=False)
        
        return render_template(
            'admin/manage_distributors.html', 
            pagination=pagination,
            distributors=pagination.items,
            current_sort=sort_by,
            current_order=order_by,
            current_search=search
        )
    except Exception as e:
        flash(f"Error loading distributors: {e}", "danger")
        return redirect(url_for('core.dashboard'))


@admin_bp.route('/distributors/add', methods=['GET', 'POST'])
@login_required
@role_required('Admin')
def add_distributor():
    """Add new distributor"""
    form = DistributorForm()
    _populate_admin_dropdowns(form)
    if form.validate_on_submit():
        existing_code = Distributor.query.filter_by(code=form.code.data.strip()).first()
        existing_name = Distributor.query.filter_by(name=form.name.data.strip()).first()
        if existing_code:
            flash('This Distributor Code already exists.', 'danger')
        elif existing_name:
            flash('This Distributor Name already exists.', 'danger')
        else:
            try:
                new_dist = Distributor(
                    code=form.code.data.strip(),
                    name=form.name.data.strip(),
                    city=form.city.data.strip() or None, 
                    state=form.state.data.strip() or None,
                    se_id=form.se_id.data if form.se_id.data != 0 else None,
                    bm_id=form.bm_id.data if form.bm_id.data != 0 else None,
                    rh_id=form.rh_id.data if form.rh_id.data != 0 else None
                )
                db.session.add(new_dist)
                db.session.commit()
                flash(f'Distributor "{new_dist.name}" created successfully.', 'success')
                return redirect(url_for('admin.manage_distributors'))
            except Exception as e:
                db.session.rollback()
                flash(f"Error creating distributor: {e}", "danger")
                print(f"Error creating distributor: {e}") 
    return render_template('admin/distributor_form.html', form=form, title='Add New Distributor')


@admin_bp.route('/distributors/edit/<int:dist_id>', methods=['GET', 'POST'])
@login_required
@role_required('Admin')
def edit_distributor(dist_id):
    """Edit existing distributor"""
    dist = db.session.get(Distributor, dist_id)
    if not dist:
        flash("Distributor not found.", "danger")
        return redirect(url_for('admin.manage_distributors'))
        
    form = DistributorForm(obj=dist)
    _populate_admin_dropdowns(form)
    if form.validate_on_submit():
        existing_code = Distributor.query.filter(Distributor.code == form.code.data.strip(), Distributor.id != dist_id).first()
        existing_name = Distributor.query.filter(Distributor.name == form.name.data.strip(), Distributor.id != dist_id).first()
        if existing_code:
            flash('This Distributor Code is already in use by another distributor.', 'danger')
        elif existing_name:
            flash('This Distributor Name is already in use by another distributor.', 'danger')
        else:
            try:
                dist.code = form.code.data.strip()
                dist.name = form.name.data.strip()
                dist.city = form.city.data.strip() or None
                dist.state = form.state.data.strip() or None
                dist.se_id = form.se_id.data if form.se_id.data != 0 else None
                dist.bm_id = form.bm_id.data if form.bm_id.data != 0 else None
                dist.rh_id = form.rh_id.data if form.rh_id.data != 0 else None
                db.session.commit()
                flash(f'Distributor "{dist.name}" updated successfully.', 'success')
                return redirect(url_for('admin.manage_distributors'))
            except Exception as e:
                db.session.rollback()
                flash(f"Error updating distributor: {e}", "danger")
                print(f"Error updating distributor: {e}") 
                
    # --- THIS IS THE FIX ---
    # This block was also missing from the distributor edit page.
    if request.method == 'GET':
         form.se_id.data = dist.se_id
         form.bm_id.data = dist.bm_id
         form.rh_id.data = dist.rh_id
    # --- END OF FIX ---
         
    return render_template('admin/distributor_form.html', form=form, title=f'Edit Distributor: {dist.name}')


@admin_bp.route('/distributors/delete/<int:dist_id>', methods=['POST'])
@login_required
@role_required('Admin')
def delete_distributor(dist_id):
    """Delete distributor"""
    dist_to_delete = db.session.get(Distributor, dist_id)
    if not dist_to_delete:
        flash("Distributor not found.", "danger")
        return redirect(url_for('admin.manage_distributors'))
        
    has_requests = AssetRequest.query.filter_by(distributor_id=dist_id).first()
    if has_requests:
        flash(f'Cannot delete "{dist_to_delete.name}" - it is associated with existing requests.', 'danger')
        return redirect(url_for('admin.manage_distributors'))
    has_db_users = User.query.filter_by(distributor_id=dist_id).first()
    if has_db_users:
        flash(f'Cannot delete "{dist_to_delete.name}" - it has one or more Distributor users assigned to it. Please re-assign those users first.', 'danger')
        return redirect(url_for('admin.manage_distributors'))
    try:
        db.session.delete(dist_to_delete)
        db.session.commit()
        flash(f'Distributor "{dist_to_delete.name}" deleted successfully.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f"Error deleting distributor: {e}", "danger")
    return redirect(url_for('admin.manage_distributors'))