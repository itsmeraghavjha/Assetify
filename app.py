import os
import base64
import uuid
from flask import Flask, render_template, redirect, url_for, flash, request, send_from_directory, jsonify
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from flask_mail import Mail, Message
from threading import Thread
from werkzeug.security import generate_password_hash, check_password_hash
from wtforms.validators import DataRequired, Length, Optional, Email, EqualTo
from forms import LoginForm, AssetRequestForm, UserForm, DeploymentForm, DistributorForm
from functools import wraps
from models import db, User, Distributor, AssetRequest
from datetime import datetime
from dotenv import load_dotenv
from sqlalchemy.exc import IntegrityError
from flask_migrate import Migrate
from werkzeug.utils import secure_filename
from datetime import datetime, timedelta
import io
from openpyxl import Workbook
from flask import send_file

# --- LOAD .env file ---
load_dotenv()

# --- App Initialization & Config ---
app = Flask(__name__)
basedir = os.path.abspath(os.path.dirname(__file__))

# --- CONFIG ---
SECRET_KEY = os.environ.get('SECRET_KEY')
if not SECRET_KEY:
    raise ValueError("No SECRET_KEY set. Did you forget to set up your .env file?")
app.config['SECRET_KEY'] = SECRET_KEY
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'app.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['ITEMS_PER_PAGE'] = 20
app.config['UPLOAD_FOLDER'] = os.path.join(basedir, 'uploads')
app.config['ALLOWED_EXTENSIONS'] = {'png', 'jpg', 'jpeg'}
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
app.config['MAIL_SERVER'] = os.environ.get('MAIL_SERVER')
app.config['MAIL_PORT'] = int(os.environ.get('MAIL_PORT', 587))
app.config['MAIL_USE_TLS'] = os.environ.get('MAIL_USE_TLS', 'true').lower() in ['true', '1', 't']
app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD')
app.config['MAIL_DEFAULT_SENDER'] = os.environ.get('MAIL_DEFAULT_SENDER')

if not app.config['MAIL_USERNAME'] or not app.config['MAIL_PASSWORD']:
    print("="*50)
    print("WARNING: Email credentials not set in .env")
    print("Email functionality will be disabled.")
    print("="*50)

# --- Initialize Extensions ---
db.init_app(app)
mail = Mail(app)
migrate = Migrate(app, db)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Please log in to access this page.'
login_manager.login_message_category = 'info'

# --- Helper Functions ---
def send_async_email(app_instance, msg):
    with app_instance.app_context():
        try:
            if app.config['MAIL_USERNAME'] and app.config['MAIL_PASSWORD']:
                mail.send(msg)
                print(f"Email sent to {msg.recipients}")
            else:
                print(f"Email NOT SENT to {msg.recipients} (credentials not configured)")
        except Exception as e:
            print(f"ERROR sending email to {msg.recipients}: {e}")

def send_email(recipient_email, subject, template, **kwargs):
    if not recipient_email:
        print(f"WARN: No recipient email for subject: {subject}")
        return
    if not app.config['MAIL_USERNAME'] or not app.config['MAIL_PASSWORD']:
        print(f"Email skipped (not configured): '{subject}' to {recipient_email}")
        return
    try:
        sender = app.config['MAIL_DEFAULT_SENDER'] or app.config['MAIL_USERNAME']
        msg = Message(subject, sender=sender, recipients=[recipient_email])
        msg.html = render_template(template, **kwargs)
        thread = Thread(target=send_async_email, args=[app, msg])
        thread.daemon = True
        thread.start()
    except Exception as e:
        print(f"ERROR preparing email: {e}")

def _save_photo_from_data_url(data_url, upload_folder, allowed_extensions):
    """Helper function to save a base64 data URL as a file."""
    if not data_url or not data_url.startswith('data:image'):
        return None, "Invalid photo data."
    try:
        header, encoded = data_url.split(",", 1)
        data = base64.b64decode(encoded)
        ext = header.split('/')[1].split(';')[0]
        if ext not in allowed_extensions:
            return None, f"Invalid image type: {ext}"
        filename = f"{uuid.uuid4()}.{ext}"
        filepath = os.path.join(upload_folder, filename)
        with open(filepath, "wb") as f:
            f.write(data)
        return filename, None
    except Exception as e:
        print(f"ERROR processing image: {e}")
        return None, "Error processing image file."

@login_manager.user_loader
def load_user(user_id):
    """Load user by ID for Flask-Login"""
    try:
        # --- THIS IS THE FIX ---
        # Changed from User.query.get() to db.session.get()
        return db.session.get(User, int(user_id))
        # --- END OF FIX ---
    except (ValueError, TypeError):
        return None

def role_required(*roles):
    """Decorator to require specific roles"""
    def wrapper(fn):
        @wraps(fn)
        def decorated_view(*args, **kwargs):
            if not current_user.is_authenticated:
                return login_manager.unauthorized()
            if current_user.role not in roles:
                flash("You do not have permission to access this page.", "danger")
                return redirect(url_for('dashboard'))
            return fn(*args, **kwargs)
        return decorated_view
    return wrapper

# --- Authentication Routes ---
@app.route('/')
@app.route('/login', methods=['GET', 'POST'])
def login():
    """User login"""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(employee_code=form.employee_code.data.strip()).first()
        if user and check_password_hash(user.password_hash, form.password.data):
            login_user(user, remember=form.remember_me.data)
            next_page = request.args.get('next')
            if next_page and next_page.startswith('/'):
                flash(f'Welcome back, {user.name}!', 'success')
                return redirect(next_page)
            flash(f'Welcome back, {user.name}!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid employee code or password.', 'danger')
    return render_template('login.html', form=form)

@app.route('/logout')
@login_required
def logout():
    """User logout"""
    logout_user()
    flash('You have been logged out successfully.', 'success')
    return redirect(url_for('login'))

# --- Core Application Routes ---

@app.route('/dashboard')
@login_required
def dashboard():
    """Main dashboard"""
    page = request.args.get('page', 1, type=int)
    search_distributor = request.args.get('distributor', '').strip()
    filter_status = request.args.get('status', '').strip()
    filter_requester_id = request.args.get('requester', '').strip()
    sort_by = request.args.get('sort_by', 'date')
    order_by = request.args.get('order_by', 'desc')

    base_query = AssetRequest.query
    joined_distributor = False
    joined_requester = False

    if current_user.role == 'SE':
        base_query = base_query.filter_by(requester_id=current_user.id)
    elif current_user.role == 'DB':
        base_query = base_query.filter_by(
            distributor_id=current_user.distributor_id,
            requester_id=current_user.id
        )
    elif current_user.role == 'BM':
        base_query = base_query.join(Distributor).filter(
            db.or_(
                Distributor.bm_id == current_user.id,
                AssetRequest.requester_id == current_user.id
            )
        )
        joined_distributor = True
    elif current_user.role == 'RH':
        base_query = base_query.join(Distributor).filter(
            db.or_(
                Distributor.rh_id == current_user.id,
                AssetRequest.requester_id == current_user.id
            )
        )
        joined_distributor = True
    
    query = base_query

    sort_column_map = {
        'id': AssetRequest.id,
        'date': AssetRequest.request_date,
        'asset': AssetRequest.asset_model,
        'status': AssetRequest.status,
        'requester': User.name,
        'distributor': Distributor.name
    }
    sort_field = sort_column_map.get(sort_by, AssetRequest.request_date)

    if sort_by == 'requester' and not joined_requester:
        query = query.join(User, AssetRequest.requester_id == User.id)
        joined_requester = True
    if sort_by == 'distributor' and not joined_distributor:
        query = query.join(Distributor, AssetRequest.distributor_id == Distributor.id, isouter=True)
        joined_distributor = True

    if order_by == 'asc':
        query = query.order_by(sort_field.asc())
    else:
        query = query.order_by(sort_field.desc())

    if search_distributor:
        if not joined_distributor:
            query = query.join(Distributor, AssetRequest.distributor_id == Distributor.id, isouter=True)
            joined_distributor = True
        query = query.filter(Distributor.name.ilike(f'%{search_distributor}%'))
    if filter_status:
        query = query.filter(AssetRequest.status == filter_status)
    if filter_requester_id and current_user.role in ['Admin', 'BM', 'RH', 'DB']:
        try:
            query = query.filter(AssetRequest.requester_id == int(filter_requester_id))
        except ValueError:
            flash("Invalid requester ID provided in filter.", "warning")
            
    stats = {
        'total_requests': base_query.count(),
        'pending_requests': base_query.filter(AssetRequest.status.like('Pending%')).count(),
        'approved_requests': base_query.filter(AssetRequest.status == 'Approved').count(),
        'deployed_requests': base_query.filter(AssetRequest.status == 'Deployed').count(),
        'rejected_requests': base_query.filter(AssetRequest.status.like('%Rejected%')).count(),
        'pending_bm_count': base_query.filter(AssetRequest.status == 'Pending BM Approval').count(),
        'pending_rh_count': base_query.filter(AssetRequest.status == 'Pending RH Approval').count()
    }
    
    pagination = query.paginate(page=page, per_page=app.config['ITEMS_PER_PAGE'], error_out=False)
    
    requesters = []
    if current_user.role in ['Admin', 'BM', 'RH', 'DB']:
        requesters = User.query.filter_by(role='SE').order_by(User.name).all()
        
    statuses_query = db.session.query(AssetRequest.status).distinct().order_by(AssetRequest.status)
    statuses = [s[0] for s in statuses_query.all()] 

    search_values = {
        'distributor': search_distributor,
        'status': filter_status,
        'requester': filter_requester_id
    }

    return render_template('dashboard.html',
                           stats=stats,
                           pagination=pagination,
                           requests=pagination.items,
                           requesters=requesters,
                           statuses=statuses,
                           search_values=search_values,
                           current_sort=sort_by,
                           current_order=order_by)


@app.route('/new_request', methods=['GET', 'POST'])
@login_required
@role_required('SE', 'Admin', 'DB')
def new_request():
    """Create new asset request"""
    form = AssetRequestForm()

    try:
        if current_user.role == 'SE':
            distributors_db = Distributor.query.filter_by(se_id=current_user.id).order_by(Distributor.name).all()
        elif current_user.role == 'DB':
            distributors_db = Distributor.query.filter_by(id=current_user.distributor_id).all()
        elif current_user.role == 'BM':
            distributors_db = Distributor.query.filter_by(bm_id=current_user.id).order_by(Distributor.name).all()
        elif current_user.role == 'RH':
            distributors_db = Distributor.query.filter_by(rh_id=current_user.id).order_by(Distributor.name).all()
        else: # For Admin role
            distributors_db = Distributor.query.order_by(Distributor.name).all()

        form.distributor_name.choices = [(d.name, d.name) for d in distributors_db]
        if len(distributors_db) != 1:
            form.distributor_name.choices.insert(0, ('', 'Select Distributor'))
        elif not distributors_db:
             flash("You have no distributors assigned to you. Cannot create requests.", "warning")

    except Exception as e:
        print(f"ERROR: Could not load distributor choices: {e}")
        flash("Error loading distributor list.", "danger")
        form.distributor_name.choices = [('', 'Error loading choices')]


    if form.validate_on_submit(): 
        photo_filename, photo_error = _save_photo_from_data_url(
            form.captured_photo.data, app.config['UPLOAD_FOLDER'], app.config['ALLOWED_EXTENSIONS']
        )
        if photo_error:
            return jsonify({'success': False, 'message': f"Photo Error: {photo_error}"}), 400

        distributor = Distributor.query.filter_by(name=form.distributor_name.data).first()
        if not distributor:
            return jsonify({'success': False, 'message': "Selected distributor could not be found."}), 400

        try:
            new_req = AssetRequest(
                requester_id=current_user.id,
                distributor_id=distributor.id,
                asset_model=form.asset_model.data,
                category=form.category.data,
                placement_date=form.placement_date.data,
                latitude=form.latitude.data,
                longitude=form.longitude.data,
                retailer_name=form.retailer_name.data.strip(),
                retailer_contact=form.retailer_contact.data.strip(),
                area_town=form.area_town.data.strip(),
                landmark=form.landmark.data.strip() or None,
                retailer_address=form.retailer_address.data.strip() or None,
                retailer_email=form.retailer_email.data.strip().lower() or None,
                selling_ice_cream=form.selling_ice_cream.data,
                willing_for_signage=form.willing_for_signage.data,
                monthly_sales=form.monthly_sales.data if form.selling_ice_cream.data == 'yes' else None,
                ice_cream_brands=form.ice_cream_brands.data.strip() if form.ice_cream_brands.data and form.selling_ice_cream.data == 'yes' else None,
                competitor_assets=form.competitor_assets.data if form.selling_ice_cream.data == 'yes' else None,
                signage_availability=form.signage_availability.data if form.selling_ice_cream.data == 'yes' else None,
                photo_filename=photo_filename,
                status='Pending BM Approval'
            )
            db.session.add(new_req)
            db.session.commit()

            if distributor.branch_manager and distributor.branch_manager.email:
                send_email(
                    distributor.branch_manager.email,
                    f'New Asset Request #{new_req.id} for Approval',
                    'email/new_for_approval.html',
                    request=new_req,
                    recipient_name=distributor.branch_manager.name or 'Branch Manager'
                )
            else:
                print(f"WARN: No BM assigned or BM has no email for Distributor ID {distributor.id}. Cannot send email.")
            
            flash('Request submitted successfully!', 'success')
            return jsonify({'success': True, 'request_id': new_req.id})

        except IntegrityError as e:
             db.session.rollback()
             print(f"Integrity Error: {e}")
             return jsonify({'success': False, 'message': "Database error: A retailer with this contact number may already exist."}), 400
        except Exception as e:
            db.session.rollback()
            print(f"Unexpected Error: {e}")
            return jsonify({'success': False, 'message': f"An unexpected error occurred: {e}"}), 500

    if request.method == 'POST' and form.errors:
        print("--- VALIDATION FAILED ---")
        print("Form errors:", form.errors) 
        return jsonify({'success': False, 'message': 'Validation Failed', 'errors': form.errors}), 400

    return render_template('new_request.html', form=form, user=current_user)


@app.route('/request/<int:request_id>')
@login_required
def view_request(request_id):
    """View single request"""
    asset_request = db.session.get(AssetRequest, request_id)
    if not asset_request:
        flash("Request not found.", "danger")
        return redirect(url_for('dashboard'))
    
    user = current_user
    req = asset_request
    
    if user.role == 'Admin':
        pass # Admin can see all
    elif user.role == 'SE':
        if req.requester_id != user.id:
            flash("You don't have permission to view this request.", "danger")
            return redirect(url_for('dashboard'))
    elif user.role == 'DB':
        if req.requester_id != user.id:
            flash("You don't have permission to view this request.", "danger")
            return redirect(url_for('dashboard'))
    elif user.role == 'BM':
        if req.distributor.bm_id != user.id and req.requester_id != user.id:
            flash("This request is not for your region.", "danger")
            return redirect(url_for('dashboard'))
    elif user.role == 'RH':
        if req.distributor.rh_id != user.id and req.requester_id != user.id:
            flash("This request is not for your region.", "danger")
            return redirect(url_for('dashboard'))

    return render_template('view_request.html', request=asset_request)


@app.route('/approve/<int:request_id>', methods=['POST'])
@login_required
@role_required('BM', 'RH', 'Admin')
def approve_request(request_id):
    """Approve a request"""
    asset_request = db.session.get(AssetRequest, request_id)
    if not asset_request:
        flash("Request not found.", "danger")
        return redirect(url_for('dashboard'))
        
    action_taken = False
    original_status = asset_request.status

    if current_user.role == 'BM' and asset_request.status == 'Pending BM Approval':
        approval_type = request.form.get('approval_type')
        if approval_type == 'security':
            try:
                amount = int(request.form.get('security_amount', 0))
                if amount <= 0:
                    flash('Security amount must be greater than zero.', 'danger')
                    return redirect(url_for('view_request', request_id=request_id))
                asset_request.bm_approval_type = 'With Security'
                asset_request.bm_security_amount = amount
                asset_request.bm_foc_justification = None 
            except (ValueError, TypeError):
                flash('Invalid security amount entered.', 'danger')
                return redirect(url_for('view_request', request_id=request_id))
        elif approval_type == 'foc':
            justification = request.form.get('foc_justification', '').strip()
            if not justification:
                flash('Justification is required for "Free of Cost" approval.', 'danger')
                return redirect(url_for('view_request', request_id=request_id))
            asset_request.bm_approval_type = 'Free of Cost'
            asset_request.bm_foc_justification = justification
            asset_request.bm_security_amount = None
        else:
            flash('You must select an approval type ("With Security" or "Free of Cost").', 'danger')
            return redirect(url_for('view_request', request_id=request_id))

        asset_request.status = 'Pending RH Approval'
        asset_request.bm_approver_id = current_user.id
        asset_request.bm_remarks = None 
        action_taken = True
        flash('Request approved and forwarded to Regional Head.', 'success')

    elif current_user.role == 'RH' and asset_request.status == 'Pending RH Approval':
        remarks = request.form.get('remarks', '').strip() 
        asset_request.status = 'Approved'
        asset_request.rh_approver_id = current_user.id
        if remarks:
            asset_request.rh_remarks = remarks
        action_taken = True
        flash('Request has been fully approved!', 'success')

    elif current_user.role == 'Admin' and 'Pending' in asset_request.status:
        remarks = request.form.get('remarks', '').strip()
        asset_request.status = 'Approved'
        if original_status == 'Pending BM Approval': 
            asset_request.bm_approver_id = current_user.id
            if remarks: asset_request.bm_remarks = f"Approved by Admin: {remarks}"
        asset_request.rh_approver_id = current_user.id
        if remarks: asset_request.rh_remarks = f"Approved by Admin: {remarks}"
        asset_request.bm_approval_type = "Admin Override" 
        action_taken = True
        flash('Request approved by Admin.', 'success')

    if action_taken:
        try:
            db.session.commit()
            db.session.refresh(asset_request) 
            if original_status == 'Pending BM Approval' and asset_request.status == 'Pending RH Approval':
                if asset_request.distributor.regional_head and asset_request.distributor.regional_head.email:
                    send_email(
                        asset_request.distributor.regional_head.email,
                        f'Asset Request #{asset_request.id} Requires Your Approval',
                        'email/new_for_approval.html',
                        request=asset_request,
                        recipient_name=asset_request.distributor.regional_head.name or 'Regional Head'
                    )
                else:
                    print(f"WARN: Could not send RH approval email for Req #{asset_request.id} - RH not assigned or email missing")
            elif asset_request.status == 'Approved':
                if asset_request.requester and asset_request.requester.email:
                     send_email(
                         asset_request.requester.email,
                         f'Your Asset Request #{asset_request.id} has been Approved',
                         'email/request_outcome.html', 
                         request=asset_request,
                         outcome='Approved'
                     )
                else:
                    print(f"WARN: Could not send Requester approval email for Req #{asset_request.id} - Requester email missing")
        except Exception as e:
            db.session.rollback()
            print(f"ERROR during commit or email sending: {e}") 
            flash(f'Error saving approval or sending email: {e}', 'danger')
            return redirect(url_for('view_request', request_id=request_id)) 
    else:
        if 'Pending' not in asset_request.status: 
             flash('Cannot approve this request at its current stage or you lack permission.', 'warning')
    return redirect(url_for('view_request', request_id=request_id))


@app.route('/reject/<int:request_id>', methods=['POST'])
@login_required
@role_required('BM', 'RH', 'Admin')
def reject_request(request_id):
    """Reject a request"""
    asset_request = db.session.get(AssetRequest, request_id)
    if not asset_request:
        flash("Request not found.", "danger")
        return redirect(url_for('dashboard'))
        
    action_taken = False
    outcome = 'Rejected'
    remarks = request.form.get('remarks', '').strip()
    
    if not remarks:
        flash('Reason for Rejection is required.', 'danger')
        return redirect(url_for('view_request', request_id=request_id))

    if current_user.role == 'BM' and asset_request.status == 'Pending BM Approval':
        asset_request.status = 'Rejected by BM'
        asset_request.bm_approver_id = current_user.id
        asset_request.bm_remarks = remarks
        outcome = 'Rejected by BM'
        action_taken = True
    elif current_user.role == 'RH' and asset_request.status == 'Pending RH Approval':
        asset_request.status = 'Rejected by RH'
        asset_request.rh_approver_id = current_user.id
        asset_request.rh_remarks = remarks
        outcome = 'Rejected by RH'
        action_taken = True
    elif current_user.role == 'Admin' and 'Pending' in asset_request.status:
        original_status = asset_request.status
        asset_request.status = 'Rejected by Admin'
        if original_status == 'Pending BM Approval':
            asset_request.bm_approver_id = current_user.id
            asset_request.bm_remarks = f"Rejected by Admin: {remarks}"
        asset_request.rh_approver_id = current_user.id
        asset_request.rh_remarks = f"Rejected by Admin: {remarks}"
        outcome = 'Rejected by Admin'
        action_taken = True

    if action_taken:
        try:
            db.session.commit()
            if asset_request.requester and asset_request.requester.email:
                send_email(
                    asset_request.requester.email,
                    f'Your Asset Request #{asset_request.id} has been Rejected',
                    'email/request_outcome.html',
                    request=asset_request,
                    outcome=outcome
                )
            flash('Request has been rejected.', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'Error saving rejection: {e}', 'danger')
    else:
        flash('Cannot reject this request at its current stage or you lack permission.', 'warning') 
    return redirect(url_for('view_request', request_id=request_id))

# --- API Routes ---
@app.route('/api/distributors')
@login_required
def get_distributors():
    """API: Get all distributors (with role-based filtering)"""
    try:
        if current_user.role == 'SE':
            distributors = Distributor.query.filter_by(se_id=current_user.id).order_by(Distributor.name).all()
        elif current_user.role == 'DB':
            distributors = Distributor.query.filter_by(id=current_user.distributor_id).all()
        elif current_user.role == 'BM':
            distributors = Distributor.query.filter_by(bm_id=current_user.id).order_by(Distributor.name).all()
        elif current_user.role == 'RH':
            distributors = Distributor.query.filter_by(rh_id=current_user.id).order_by(Distributor.name).all()
        else: # Admin
            distributors = Distributor.query.order_by(Distributor.name).all()
        
        dist_list = [{
            'name': d.name,
            'code': d.code or '',
            'town': d.city or '',
            'asmBm': d.branch_manager.name if d.branch_manager else 'N/A',
            'bmEmail': d.branch_manager.email if d.branch_manager and d.branch_manager.email else '',
            'rhEmail': d.regional_head.email if d.regional_head and d.regional_head.email else ''
        } for d in distributors]
        return jsonify({'ok': True, 'distributors': dist_list})
    except Exception as e:
        print(f"ERROR fetching distributors: {e}")
        return jsonify({'ok': False, 'message': 'Failed to load distributors.'}), 500

@app.route('/api/check_phone/<phone>')
@login_required
def check_retailer_phone(phone):
    """API: Check if phone number already exists"""
    if not phone or not phone.isdigit() or len(phone) != 10:
        return jsonify({'ok': False, 'message': 'Invalid phone format.'}), 400
    try:
        existing = AssetRequest.query.filter_by(retailer_contact=phone).all()
        if existing:
            matches = [f"Req #{req.id} ({req.status})" for req in existing]
            return jsonify({'ok': True, 'exists': True, 'matches': matches})
        return jsonify({'ok': True, 'exists': False})
    except Exception as e:
        print(f"ERROR checking phone {phone}: {e}")
        return jsonify({'ok': False, 'message': 'Error checking phone.'}), 500

# --- Static File Route ---
@app.route('/uploads/<path:filename>')
@login_required
def uploaded_file(filename):
    """Serve uploaded files"""
    try:
        safe_filename = secure_filename(filename)
        return send_from_directory(app.config['UPLOAD_FOLDER'], safe_filename)
    except FileNotFoundError:
        return "File not found", 404

# --- ADMIN SECTION ---

@app.route('/admin/users')
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
        pagination = query.paginate(page=page, per_page=app.config['ITEMS_PER_PAGE'], error_out=False)
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
        return redirect(url_for('dashboard'))


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


@app.route('/admin/users/add', methods=['GET', 'POST'])
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
                return redirect(url_for('manage_users'))
            except Exception as e:
                db.session.rollback()
                flash(f"Error creating user: {e}", "danger")
    return render_template('admin/user_form.html', form=form, title='Add New User')


@app.route('/admin/users/edit/<int:user_id>', methods=['GET', 'POST'])
@login_required
@role_required('Admin')
def edit_user(user_id):
    """Edit existing user"""
    user = db.session.get(User, user_id)
    if not user:
        flash("User not found.", "danger")
        return redirect(url_for('manage_users'))
        
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
                if user.role == 'DB' and form.distributor_id.data != 0:
                    user.distributor_id = form.distributor_id.data
                else:
                    user.distributor_id = None
                db.session.commit()
                flash(f'User "{user.name}" updated successfully.', 'success')
                return redirect(url_for('manage_users'))
            except Exception as e:
                db.session.rollback()
                print(f"--- ERROR during user update: {e} ---") 
                import traceback
                traceback.print_exc() 
                flash(f"Error updating user: {e}", "danger")
    if request.method == 'GET' and user.distributor_id:
        form.distributor_id.data = user.distributor_id
    return render_template('admin/user_form.html', form=form, title=f'Edit User: {user.name}', user=user)

@app.route('/admin/users/delete/<int:user_id>', methods=['POST'])
@login_required
@role_required('Admin')
def delete_user(user_id):
    """Delete user"""
    user_to_delete = db.session.get(User, user_id)
    if not user_to_delete:
        flash("User not found.", "danger")
        return redirect(url_for('manage_users'))
        
    if user_to_delete.id == current_user.id:
        flash("You cannot delete your own account.", "danger")
        return redirect(url_for('manage_users'))
    has_requests = AssetRequest.query.filter(
        (AssetRequest.requester_id == user_id) |
        (AssetRequest.bm_approver_id == user_id) |
        (AssetRequest.rh_approver_id == user_id)
    ).first()
    if has_requests:
        flash(f'Cannot delete "{user_to_delete.name}" - associated with requests.', 'danger')
        return redirect(url_for('manage_users'))
    is_manager = Distributor.query.filter(
        (Distributor.se_id == user_id) |
        (Distributor.bm_id == user_id) |
        (Distributor.rh_id == user_id)
    ).first()
    if is_manager:
        flash(f'Cannot delete "{user_to_delete.name}" - they are assigned as a manager to one or more distributors. Please re-assign those distributors first.', 'danger')
        return redirect(url_for('manage_users'))
    try:
        db.session.delete(user_to_delete)
        db.session.commit()
        flash(f'User "{user_to_delete.name}" deleted successfully.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f"Error deleting user: {e}", "danger")
    return redirect(url_for('manage_users'))

@app.context_processor
def inject_global_vars():
    """Make variables available in all templates"""
    return dict(current_user=current_user)

@app.errorhandler(404)
def not_found_error(error):
    """Handle 404 errors"""
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_error(error):
    """Handle 500 errors"""
    db.session.rollback()
    return render_template('500.html'), 500

@app.route('/admin')
@login_required
@role_required('Admin')
def admin_dashboard():
    """Admin dashboard redirect"""
    return redirect(url_for('manage_users'))


@app.route('/admin/distributors')
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
        pagination = query.paginate(page=page, per_page=app.config['ITEMS_PER_PAGE'], error_out=False)
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
        return redirect(url_for('dashboard'))


@app.route('/admin/distributors/add', methods=['GET', 'POST'])
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
                return redirect(url_for('manage_distributors'))
            except Exception as e:
                db.session.rollback()
                flash(f"Error creating distributor: {e}", "danger")
                print(f"Error creating distributor: {e}") 
    return render_template('admin/distributor_form.html', form=form, title='Add New Distributor')


@app.route('/admin/distributors/edit/<int:dist_id>', methods=['GET', 'POST'])
@login_required
@role_required('Admin')
def edit_distributor(dist_id):
    """Edit existing distributor"""
    dist = db.session.get(Distributor, dist_id)
    if not dist:
        flash("Distributor not found.", "danger")
        return redirect(url_for('manage_distributors'))
        
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
                return redirect(url_for('manage_distributors'))
            except Exception as e:
                db.session.rollback()
                flash(f"Error updating distributor: {e}", "danger")
                print(f"Error updating distributor: {e}") 
    if request.method == 'GET':
         form.se_id.data = dist.se_id
         form.bm_id.data = dist.bm_id
         form.rh_id.data = dist.rh_id
    return render_template('admin/distributor_form.html', form=form, title=f'Edit Distributor: {dist.name}')


@app.route('/admin/distributors/delete/<int:dist_id>', methods=['POST'])
@login_required
@role_required('Admin')
def delete_distributor(dist_id):
    """Delete distributor"""
    dist_to_delete = db.session.get(Distributor, dist_id)
    if not dist_to_delete:
        flash("Distributor not found.", "danger")
        return redirect(url_for('manage_distributors'))
        
    has_requests = AssetRequest.query.filter_by(distributor_id=dist_id).first()
    if has_requests:
        flash(f'Cannot delete "{dist_to_delete.name}" - it is associated with existing requests.', 'danger')
        return redirect(url_for('manage_distributors'))
    has_db_users = User.query.filter_by(distributor_id=dist_id).first()
    if has_db_users:
        flash(f'Cannot delete "{dist_to_delete.name}" - it has one or more Distributor users assigned to it. Please re-assign those users first.', 'danger')
        return redirect(url_for('manage_distributors'))
    try:
        db.session.delete(dist_to_delete)
        db.session.commit()
        flash(f'Distributor "{dist_to_delete.name}" deleted successfully.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f"Error deleting distributor: {e}", "danger")
    return redirect(url_for('manage_distributors'))


@app.route('/request/<int:request_id>/deploy', methods=['GET', 'POST'])
@login_required
@role_required('SE', 'Admin')
def confirm_deployment(request_id):
    """Page for SE to confirm deployment of an asset."""
    asset_request = db.session.get(AssetRequest, request_id)
    if not asset_request:
        flash("Request not found.", "danger")
        return redirect(url_for('dashboard'))
        
    form = DeploymentForm()
    is_original_se = (current_user.role == 'SE' and asset_request.requester_id == current_user.id)
    
    if not (current_user.role == 'Admin' or is_original_se):
        flash("You do not have permission to perform this action.", "danger")
        return redirect(url_for('dashboard'))
    if asset_request.status != 'Approved':
        flash("This request is not in the 'Approved' state and cannot be deployed.", "warning")
        return redirect(url_for('view_request', request_id=request_id))

    if form.validate_on_submit():
        serial_no_stripped = form.deployed_serial_no.data.strip()
        existing_serial = AssetRequest.query.filter(
            AssetRequest.deployed_serial_no == serial_no_stripped,
            AssetRequest.id != request_id 
        ).first()
        if existing_serial:
            flash("This asset serial number has already been recorded for another request.", "danger")
        else:
            photo1_filename, p1_error = _save_photo_from_data_url(
                form.deployment_photo1.data, app.config['UPLOAD_FOLDER'], app.config['ALLOWED_EXTENSIONS']
            )
            if p1_error:
                flash(f"Photo 1 Error: {p1_error}", "danger")
            photo2_filename, p2_error = _save_photo_from_data_url(
                form.deployment_photo2.data, app.config['UPLOAD_FOLDER'], app.config['ALLOWED_EXTENSIONS']
            )
            if p2_error:
                flash(f"Photo 2 Error: {p2_error}", "danger")
            if not existing_serial and not p1_error and not p2_error:
                try:
                    asset_request.deployed_make = form.deployed_make.data.strip()
                    asset_request.deployed_serial_no = serial_no_stripped
                    asset_request.deployment_photo1_filename = photo1_filename
                    asset_request.deployment_photo2_filename = photo2_filename
                    asset_request.deployed_by_id = current_user.id
                    asset_request.deployment_date = datetime.utcnow()
                    asset_request.status = 'Deployed' 
                    db.session.commit()
                    flash('Deployment confirmed successfully! The request is now closed.', 'success')
                    return redirect(url_for('view_request', request_id=request_id))
                except Exception as e:
                    db.session.rollback()
                    print(f"ERROR saving deployment: {e}")
                    flash(f"An error occurred while saving the deployment: {e}", "danger")
    return render_template('deployment_form.html', form=form, request=asset_request)

@app.route('/export/excel')
@login_required
def export_excel():
    """Export requests to an Excel file for DMS based on specific filters."""
    
    base_query = AssetRequest.query
    if current_user.role == 'SE':
        base_query = base_query.filter_by(requester_id=current_user.id)
    elif current_user.role == 'DB':
        base_query = base_query.filter_by(distributor_id=current_user.distributor_id)
    elif current_user.role == 'BM':
        base_query = base_query.join(Distributor).filter(
            Distributor.bm_id == current_user.id
        )
    elif current_user.role == 'RH':
        base_query = base_query.join(Distributor).filter(
            Distributor.rh_id == current_user.id
        )
    
    query = base_query.options(
        db.joinedload(AssetRequest.distributor),
        db.joinedload(AssetRequest.requester)
    ).order_by(AssetRequest.request_date.desc())

    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')
    filter_requester_id = request.args.get('requester')
    filter_status = request.args.get('status')

    try:
        if start_date_str:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            query = query.filter(AssetRequest.request_date >= start_date)
        if end_date_str:
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
            end_date_inclusive = end_date + timedelta(days=1)
            query = query.filter(AssetRequest.request_date < end_date_inclusive)
        if filter_requester_id and current_user.role in ['Admin', 'BM', 'RH', 'DB']:
             query = query.filter(AssetRequest.requester_id == int(filter_requester_id))
        if filter_status:
            query = query.filter(AssetRequest.status == filter_status)
    except ValueError:
        flash("Invalid filter value provided.", "danger")
        return redirect(url_for('dashboard'))
            
    requests_to_export = query.all()

    wb = Workbook()
    ws = wb.active
    ws.title = "DMS Export"

    headers = [
        "Customer Category", "Customer Name", "Customer Code", "Customer Type",
        "Customer Address", "Region", "Sales Office", "pincode",
        "Territory/Cluster", "Contact No 1", "Contact No 2", "Contact No 3",
        "Email Id 1", "Email Id 2", "Primary Contact Person", "Secondary Contact Person",
        "Parent Customer Code", "GST No", "GST State Code", "PAN",
        "Rate Code", "Discount Code", "Remarks", "FSSAI", "BEAT Name"
    ]
    ws.append(headers)

    for req in requests_to_export:
        full_address = f"{req.retailer_address or ''} {req.landmark or ''}".strip()
        row = [
            req.category,
            req.retailer_name,
            req.id,
            "GT",
            full_address,
            req.distributor.city if req.distributor else "",
            req.requester.so if req.requester else "",
            "", "", 
            req.retailer_contact,
            "", "", 
            req.retailer_email,
            "", 
            req.retailer_name,
            "", 
            req.distributor.code if req.distributor else "",
            "", "", "", 
            "", "", 
            "", "", "" 
        ]
        ws.append(row)

    file_buffer = io.BytesIO()
    wb.save(file_buffer)
    file_buffer.seek(0)
    filename = f"hfl_dms_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    return send_file(
        file_buffer,
        as_attachment=True,
        download_name=filename,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

# --- Main Execution ---
if __name__ == '__main__':
    with app.app_context():
        pass
    app.run(debug=True)