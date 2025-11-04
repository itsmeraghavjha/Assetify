import os
import base64
import uuid
from flask import Flask, render_template, redirect, url_for, flash, request, send_from_directory, jsonify
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from flask_mail import Mail, Message
from threading import Thread
from werkzeug.security import generate_password_hash, check_password_hash
from wtforms.validators import DataRequired, Length, Optional, Email, EqualTo
from forms import LoginForm, AssetRequestForm, UserForm, DeploymentForm
from functools import wraps
from models import db, User, Distributor, AssetRequest
from datetime import datetime
from dotenv import load_dotenv
from sqlalchemy.exc import IntegrityError
from flask_migrate import Migrate
from werkzeug.utils import secure_filename
from datetime import datetime, timedelta
# In app.py, at the top with other imports

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

# Database
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'app.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Uploads
app.config['UPLOAD_FOLDER'] = os.path.join(basedir, 'uploads')
app.config['ALLOWED_EXTENSIONS'] = {'png', 'jpg', 'jpeg'}
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Email Config
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
    """Send email asynchronously"""
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
    """Send email with error handling"""
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

@login_manager.user_loader
def load_user(user_id):
    """Load user by ID for Flask-Login"""
    try:
        return User.query.get(int(user_id))
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
            # Prevent open redirect
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


# @app.route('/dashboard')
# @login_required
# def dashboard():
#     """Main dashboard"""

#     # --- 1. GET SORTING & FILTER ARGS ---
    
#     # Get filters from URL parameters
#     search_distributor = request.args.get('distributor', '').strip()
#     filter_status = request.args.get('status', '').strip()
#     filter_requester_id = request.args.get('requester', '').strip()

#     # <--- NEW: Get sorting parameters --->
#     # Default sort by date, descending
#     sort_by = request.args.get('sort_by', 'date')
#     order_by = request.args.get('order_by', 'desc')

#     # --- 2. CREATE BASE QUERY ---
#     base_query = AssetRequest.query
    
#     # Keep track of which tables we've joined
#     joined_distributor = False
#     joined_requester = False

#     # Apply Role-based filtering
#     if current_user.role == 'SE':
#         base_query = base_query.filter_by(requester_id=current_user.id)
#     elif current_user.role == 'BM':
#         base_query = base_query.join(Distributor).filter(
#             db.func.lower(Distributor.bm_email) == current_user.email.lower()
#         )
#         joined_distributor = True # Role filter already joined Distributor
#     elif current_user.role == 'RH':
#         base_query = base_query.join(Distributor).filter(
#             db.func.lower(Distributor.rh_email) == current_user.email.lower()
#         )
#         joined_distributor = True # Role filter already joined Distributor
    
#     # Start the main query
#     query = base_query

#     # <--- NEW: VALIDATE SORT_BY and APPLY JOINS ---
#     # Map public sort_by names to the actual database columns
#     sort_column_map = {
#         'id': AssetRequest.id,
#         'date': AssetRequest.request_date,
#         'asset': AssetRequest.asset_model,
#         'status': AssetRequest.status,
#         'requester': User.name,
#         'distributor': Distributor.name
#     }
    
#     # Get the SQLAlchemy column, default to request_date
#     sort_field = sort_column_map.get(sort_by, AssetRequest.request_date)

#     # Add joins *only if* needed for sorting
#     if sort_by == 'requester' and not joined_requester:
#         query = query.join(User, AssetRequest.requester_id == User.id)
#         joined_requester = True
    
#     if sort_by == 'distributor' and not joined_distributor:
#         query = query.join(Distributor, AssetRequest.distributor_id == Distributor.id, isouter=True)
#         joined_distributor = True

#     # <--- NEW: APPLY ORDER_BY ---
#     if order_by == 'asc':
#         query = query.order_by(sort_field.asc())
#     else:
#         # Default to descending
#         query = query.order_by(sort_field.desc())


#     # --- 3. APPLY FILTERS ---
#     if search_distributor:
#         # Add join *only if* not already joined
#         if not joined_distributor:
#             query = query.join(Distributor, AssetRequest.distributor_id == Distributor.id, isouter=True)
#             joined_distributor = True
#         query = query.filter(Distributor.name.ilike(f'%{search_distributor}%'))

#     if filter_status:
#         query = query.filter(AssetRequest.status == filter_status)
    
#     if filter_requester_id and current_user.role in ['Admin', 'BM', 'RH']:
#         try:
#             query = query.filter(AssetRequest.requester_id == int(filter_requester_id))
#         except ValueError:
#             flash("Invalid requester ID provided in filter.", "warning")
            
#     # --- 4. CALCULATE STATS (from the original role-filtered query) ---
#     stats = {
#         'total_requests': base_query.count(),
#         'pending_requests': base_query.filter(AssetRequest.status.like('Pending%')).count(),
#         'approved_requests': base_query.filter(AssetRequest.status == 'Approved').count(),
#         'deployed_requests': base_query.filter(AssetRequest.status == 'Deployed').count(),
#         'rejected_requests': base_query.filter(AssetRequest.status.like('%Rejected%')).count()
#     }
    
#     # --- 5. EXECUTE QUERY & GET DROPDOWN DATA ---
#     requests = query.all()

#     requesters = []
#     if current_user.role in ['Admin', 'BM', 'RH']:
#         requesters = User.query.filter_by(role='SE').order_by(User.name).all()
        
#     statuses_query = db.session.query(AssetRequest.status).distinct().order_by(AssetRequest.status)
#     statuses = [s[0] for s in statuses_query.all()] 

#     search_values = {
#         'distributor': search_distributor,
#         'status': filter_status,
#         'requester': filter_requester_id
#     }

#     # --- 6. RENDER TEMPLATE ---
#     return render_template('dashboard.html',
#                            stats=stats,
#                            requests=requests,
#                            requesters=requesters,
#                            statuses=statuses,
#                            search_values=search_values,
#                            # <--- NEW: Pass sort state to template --->
#                            current_sort=sort_by,
#                            current_order=order_by)


# In app.py

@app.route('/dashboard')
@login_required
def dashboard():
    """Main dashboard"""

    # --- 1. GET SORTING & FILTER ARGS ---
    search_distributor = request.args.get('distributor', '').strip()
    filter_status = request.args.get('status', '').strip()
    filter_requester_id = request.args.get('requester', '').strip()
    sort_by = request.args.get('sort_by', 'date')
    order_by = request.args.get('order_by', 'desc')

    # --- 2. CREATE BASE QUERY (with role filtering) ---
    base_query = AssetRequest.query
    joined_distributor = False
    joined_requester = False

    if current_user.role == 'SE':
        base_query = base_query.filter_by(requester_id=current_user.id)
    elif current_user.role == 'BM':
        base_query = base_query.join(Distributor).filter(
            db.func.lower(Distributor.bm_email) == current_user.email.lower()
        )
        joined_distributor = True
    elif current_user.role == 'RH':
        base_query = base_query.join(Distributor).filter(
            db.func.lower(Distributor.rh_email) == current_user.email.lower()
        )
        joined_distributor = True
    
    # Start the main query for table display
    query = base_query

    # --- 3. APPLY SORTING (Join tables if needed for sort key) ---
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

    # --- 4. APPLY FILTERS (Join tables if needed for filter key) ---
    if search_distributor:
        if not joined_distributor:
            query = query.join(Distributor, AssetRequest.distributor_id == Distributor.id, isouter=True)
            joined_distributor = True
        query = query.filter(Distributor.name.ilike(f'%{search_distributor}%'))

    if filter_status:
        query = query.filter(AssetRequest.status == filter_status)
    
    if filter_requester_id and current_user.role in ['Admin', 'BM', 'RH']:
        try:
            query = query.filter(AssetRequest.requester_id == int(filter_requester_id))
        except ValueError:
            flash("Invalid requester ID provided in filter.", "warning")
            
    # --- 5. CALCULATE STATS (using the role-filtered base_query) ---
    stats = {
        'total_requests': base_query.count(),
        'pending_requests': base_query.filter(AssetRequest.status.like('Pending%')).count(),
        'approved_requests': base_query.filter(AssetRequest.status == 'Approved').count(),
        'deployed_requests': base_query.filter(AssetRequest.status == 'Deployed').count(),
        'rejected_requests': base_query.filter(AssetRequest.status.like('%Rejected%')).count(),
        # ***** NEW: Calculate Pending Breakdown *****
        'pending_bm_count': base_query.filter(AssetRequest.status == 'Pending BM Approval').count(),
        'pending_rh_count': base_query.filter(AssetRequest.status == 'Pending RH Approval').count()
        # ***** END NEW SECTION *****
    }
    
    # --- 6. EXECUTE FILTERED/SORTED QUERY FOR TABLE & GET DROPDOWN DATA ---
    requests_for_table = query.all() # Renamed variable for clarity

    requesters = []
    if current_user.role in ['Admin', 'BM', 'RH']:
        requesters = User.query.filter_by(role='SE').order_by(User.name).all()
        
    statuses_query = db.session.query(AssetRequest.status).distinct().order_by(AssetRequest.status)
    statuses = [s[0] for s in statuses_query.all()] 

    search_values = {
        'distributor': search_distributor,
        'status': filter_status,
        'requester': filter_requester_id
    }

    # --- 7. RENDER TEMPLATE ---
    return render_template('dashboard.html',
                           stats=stats,
                           requests=requests_for_table, # Pass the correct variable
                           requesters=requesters,
                           statuses=statuses,
                           search_values=search_values,
                           current_sort=sort_by,
                           current_order=order_by)


@app.route('/new_request', methods=['GET', 'POST'])
@login_required
@role_required('SE', 'Admin')
def new_request():
    """Create new asset request"""
    form = AssetRequestForm()

    # --- This logic runs for BOTH GET and POST to populate dropdowns ---
    try:
        if current_user.role == 'SE':
            distributors_db = Distributor.query.filter_by(se_id=current_user.id).order_by(Distributor.name).all()
            if not distributors_db:
                 flash("You have no distributors assigned to you. Please contact an admin.", "warning")
        else: # For Admin role
            distributors_db = Distributor.query.order_by(Distributor.name).all()

        # Populate the dropdown choices
        form.distributor_name.choices = [(d.name, d.name) for d in distributors_db]
        form.distributor_name.choices.insert(0, ('', 'Select Distributor'))

    except Exception as e:
        print(f"ERROR: Could not load distributor choices: {e}")
        flash("Error loading distributor list.", "danger")
        form.distributor_name.choices = [('', 'Error loading choices')]


    # --- Form Submission Logic (POST request) ---
    if form.validate_on_submit(): # This implies request.method == 'POST'
        
        # 1. Save the photo
        photo_filename, photo_error = _save_photo_from_data_url(
            form.captured_photo.data, app.config['UPLOAD_FOLDER'], app.config['ALLOWED_EXTENSIONS']
        )
        if photo_error:
            # Send JSON error back to the fetch request
            return jsonify({'success': False, 'message': f"Photo Error: {photo_error}"}), 400

        # 2. Find the distributor
        distributor = Distributor.query.filter_by(name=form.distributor_name.data).first()
        if not distributor:
            # Send JSON error back to the fetch request
            return jsonify({'success': False, 'message': "Selected distributor could not be found."}), 400

        # 3. Try to create and save the new request
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

            # 4. Send email notification (if configured)
            if distributor.bm_email:
                send_email(
                    distributor.bm_email,
                    f'New Asset Request #{new_req.id} for Approval',
                    'email/new_for_approval.html',
                    request=new_req,
                    recipient_name=distributor.asm_bm_name or 'Branch Manager'
                )
            
            # 5. Send SUCCESS response to JavaScript
            flash('Request submitted successfully!', 'success') # This will show on the *next* page
            return jsonify({'success': True, 'request_id': new_req.id})

        except IntegrityError as e:
             db.session.rollback()
             print(f"Integrity Error: {e}")
             return jsonify({'success': False, 'message': "Database error: A retailer with this contact number may already exist."}), 400
        except Exception as e:
            db.session.rollback()
            print(f"Unexpected Error: {e}")
            return jsonify({'success': False, 'message': f"An unexpected error occurred: {e}"}), 500

    # --- Handle POST request that FAILS validation ---
    if request.method == 'POST' and form.errors:
        print("--- VALIDATION FAILED ---")
        print("Form errors:", form.errors) 
        # Send JSON error with WTForms validation messages
        return jsonify({'success': False, 'message': 'Validation Failed', 'errors': form.errors}), 400

    # --- Handle GET request ---
    # If it's a GET request, just render the template normally
    return render_template('new_request.html', form=form, user=current_user)


@app.route('/request/<int:request_id>')
@login_required
def view_request(request_id):
    """View single request"""
    asset_request = AssetRequest.query.get_or_404(request_id)

    if current_user.role == 'SE' and asset_request.requester_id != current_user.id:
        flash("You don't have permission to view this request.", "danger")
        return redirect(url_for('dashboard'))

    return render_template('view_request.html', request=asset_request)

# In app.py

# In app.py

@app.route('/approve/<int:request_id>', methods=['POST'])
@login_required
@role_required('BM', 'RH', 'Admin')
def approve_request(request_id):
    """Approve a request"""
    asset_request = AssetRequest.query.get_or_404(request_id)
    action_taken = False
    original_status = asset_request.status # Store original status for email logic

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
                asset_request.bm_foc_justification = None # Clear other field
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
            asset_request.bm_security_amount = None # Clear other field
        
        else:
            flash('You must select an approval type ("With Security" or "Free of Cost").', 'danger')
            return redirect(url_for('view_request', request_id=request_id))

        # If all checks passed, set approval status
        asset_request.status = 'Pending RH Approval'
        asset_request.bm_approver_id = current_user.id
        asset_request.bm_remarks = None # Clear rejection remarks
        action_taken = True
        
        flash('Request approved and forwarded to Regional Head.', 'success')

    elif current_user.role == 'RH' and asset_request.status == 'Pending RH Approval':
        remarks = request.form.get('remarks', '').strip() # Optional remarks from RH
        
        asset_request.status = 'Approved'
        asset_request.rh_approver_id = current_user.id
        if remarks:
            asset_request.rh_remarks = remarks
        action_taken = True

        flash('Request has been fully approved!', 'success')

    elif current_user.role == 'Admin' and 'Pending' in asset_request.status:
        remarks = request.form.get('remarks', '').strip()
        asset_request.status = 'Approved'
        
        if original_status == 'Pending BM Approval': # Use original_status here
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

            # --- EMAIL SENDING LOGIC ---
            # Reload to get related objects like distributor
            db.session.refresh(asset_request) 

            # 1. BM approves -> Notify RH
            if original_status == 'Pending BM Approval' and asset_request.status == 'Pending RH Approval':
                if asset_request.distributor and asset_request.distributor.rh_email:
                    send_email(
                        asset_request.distributor.rh_email,
                        f'Asset Request #{asset_request.id} Requires Your Approval',
                        'email/new_for_approval.html', # Use the same template
                        request=asset_request,
                        recipient_name=asset_request.distributor.rh_name or 'Regional Head'
                    )
                else:
                    print(f"WARN: Could not send RH approval email for Req #{asset_request.id} - RH email missing for distributor {asset_request.distributor.name}")

            # 2. RH approves OR Admin approves -> Notify SE
            elif asset_request.status == 'Approved':
                if asset_request.requester and asset_request.requester.email:
                     send_email(
                         asset_request.requester.email,
                         f'Your Asset Request #{asset_request.id} has been Approved',
                         'email/request_outcome.html', # Need this template
                         request=asset_request,
                         outcome='Approved'
                     )
                else:
                    print(f"WARN: Could not send SE approval email for Req #{asset_request.id} - SE email missing")

        except Exception as e:
            db.session.rollback()
            print(f"ERROR during commit or email sending: {e}") # Log error
            flash(f'Error saving approval or sending email: {e}', 'danger')
            return redirect(url_for('view_request', request_id=request_id)) # Redirect on error
    else:
        # This flash message is now handled by the specific logic above if needed
        if 'Pending' not in asset_request.status: # Check if status is already final
             flash('Cannot approve this request at its current stage or you lack permission.', 'warning')
        # If it's still pending but not the user's turn, no flash needed as form won't show

    return redirect(url_for('view_request', request_id=request_id))



@app.route('/reject/<int:request_id>', methods=['POST'])
@login_required
@role_required('BM', 'RH', 'Admin')
def reject_request(request_id):
    """Reject a request"""
    asset_request = AssetRequest.query.get_or_404(request_id)
    action_taken = False
    outcome = 'Rejected'

    if current_user.role == 'BM' and asset_request.status == 'Pending BM Approval':
        asset_request.status = 'Rejected by BM'
        asset_request.bm_approver_id = current_user.id
        outcome = 'Rejected by BM'
        action_taken = True

    elif current_user.role == 'RH' and asset_request.status == 'Pending RH Approval':
        asset_request.status = 'Rejected by RH'
        asset_request.rh_approver_id = current_user.id
        outcome = 'Rejected by RH'
        action_taken = True

    elif current_user.role == 'Admin' and 'Pending' in asset_request.status:
        # Determine original status before admin override
        original_status = asset_request.status
        asset_request.status = 'Rejected by Admin'
        # Set approvers based on original status
        if original_status == 'Pending BM Approval':
            asset_request.bm_approver_id = current_user.id
        asset_request.rh_approver_id = current_user.id # RH approver always set on admin rejection too
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
        flash('Cannot reject this request at its current stage or you lack permission.', 'warning') # Added permission check message

    return redirect(url_for('view_request', request_id=request_id))

# --- API Routes ---
# THIS IS THE CORRECTED CODE
@app.route('/api/distributors')
@login_required
def get_distributors():
    """API: Get all distributors (with role-based filtering)"""
    try:
        # --- START: Added Filter Logic ---
        if current_user.role == 'SE':
            distributors = Distributor.query.filter_by(se_id=current_user.id).order_by(Distributor.name).all()
        else: # Admin and other roles (like BM/RH, if they ever use this)
            distributors = Distributor.query.order_by(Distributor.name).all()
        # --- END: Added Filter Logic ---
        
        dist_list = [{
            'name': d.name,
            'code': d.code or '',
            'town': d.city or '',
            'asmBm': d.asm_bm_name or '',
            'bmEmail': d.bm_email or '',
            'rhEmail': d.rh_email or ''
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
        # --- NEW: Get sort and search parameters ---
        sort_by = request.args.get('sort_by', 'name')
        order_by = request.args.get('order_by', 'asc')
        search = request.args.get('search', '').strip()

        query = User.query

        # --- NEW: Apply search filter ---
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

        # --- NEW: Map sort keys to columns ---
        sort_column_map = {
            'name': User.name,
            'code': User.employee_code,
            'email': User.email,
            'role': User.role,
            'so': User.so
        }
        sort_field = sort_column_map.get(sort_by, User.name)

        # --- NEW: Apply sorting ---
        if order_by == 'desc':
            query = query.order_by(sort_field.desc())
        else:
            query = query.order_by(sort_field.asc())

        users = query.all()
        
        # --- NEW: Pass sort/search state to template ---
        return render_template(
            'admin/manage_users.html', 
            users=users,
            current_sort=sort_by,
            current_order=order_by,
            current_search=search
        )
    except Exception as e:
        flash(f"Error loading users: {e}", "danger")
        return redirect(url_for('dashboard'))


@app.route('/admin/users/add', methods=['GET', 'POST'])
@login_required
@role_required('Admin')
def add_user():
    """Add new user"""
    form = UserForm()

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
            existing_email = User.query.filter_by(
                email=form.email.data.strip()
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
                    email=form.email.data.strip() if form.email.data else None,
                    role=form.role.data,
                    so=form.so.data.strip() if form.so.data else None
                )
                new_user.set_password(form.password.data)

                db.session.add(new_user)
                db.session.commit()

                flash(f'User "{new_user.name}" created successfully.', 'success')
                return redirect(url_for('manage_users'))
            except Exception as e:
                db.session.rollback()
                flash(f"Error creating user: {e}", "danger")

    return render_template('admin/user_form.html', form=form, title='Add New User')

# In app.py

# In app.py

@app.route('/admin/users/edit/<int:user_id>', methods=['GET', 'POST'])
@login_required
@role_required('Admin')
def edit_user(user_id):
    """Edit existing user"""
    user = User.query.get_or_404(user_id)
    form = UserForm(obj=user) # Populate form with current user data

    # Password optional for editing
    form.password.validators = [
        Optional(),
        Length(min=6, message="Password must be at least 6 characters."),
        EqualTo('confirm_password', message='Passwords must match.')
    ]

    if form.validate_on_submit():
        print(f"--- Editing User ID: {user_id} ---") # DEBUG
        new_employee_code = form.employee_code.data.strip()
        new_email_raw = form.email.data.strip() if form.email.data else None
        new_email = new_email_raw.lower() if new_email_raw else None # Store lowercase for comparison
        new_name = form.name.data.strip() # Get the new name from the form

        # Check unique constraints (excluding current user)
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
                # --- START: Modified section ---
                
                # Get the OLD email, role, AND NAME BEFORE the update
                old_email_raw = user.email
                old_email = old_email_raw.lower() if old_email_raw else None
                old_role = user.role
                old_name = user.name # Capture the exact old name
                old_name_lower = old_name.lower() if old_name else None # Store lowercase for comparison
                
                print(f"Old Email: {old_email}, Old Role: {old_role}, Old Name: {old_name}") # DEBUG
                print(f"New Name from form: {new_name}") # DEBUG

                # Update user object attributes
                user.name = new_name # <-- Update user name here
                user.employee_code = new_employee_code
                user.email = new_email_raw
                user.role = form.role.data # The user's role might change here
                user.so = form.so.data.strip() if form.so.data else None

                if form.password.data:
                    user.set_password(form.password.data)

                # Check if email or name changed (case-sensitive check for the actual change)
                email_changed = (old_email != new_email)
                name_changed = (old_name != new_name) 
                print(f"Email changed? {email_changed}, Name changed? {name_changed}") # DEBUG

                # --- Update Distributors based on OLD role ---
                
                # Update EMAIL in distributors if it changed (uses case-insensitive compare)
                if email_changed and old_email:
                    print(f"Attempting to update distributor EMAILS for OLD role: {old_role}")
                    if old_role == 'BM':
                        distributors_to_update = Distributor.query.filter(db.func.lower(Distributor.bm_email) == old_email).all()
                        print(f"Found {len(distributors_to_update)} distributors with old BM email '{old_email}'")
                        for dist in distributors_to_update:
                            dist.bm_email = new_email_raw
                            print(f"Updating BM email for Distributor ID {dist.id} ({dist.name}) to '{new_email_raw}'")
                    elif old_role == 'RH':
                        distributors_to_update = Distributor.query.filter(db.func.lower(Distributor.rh_email) == old_email).all()
                        print(f"Found {len(distributors_to_update)} distributors with old RH email '{old_email}'")
                        for dist in distributors_to_update:
                            dist.rh_email = new_email_raw
                            print(f"Updating RH email for Distributor ID {dist.id} ({dist.name}) to '{new_email_raw}'")

                # Update NAME in distributors if it changed (uses case-insensitive compare)
                # Only proceed if old_name existed
                if name_changed and old_name_lower and (old_role == 'BM' or old_role == 'RH'): 
                    print(f"Attempting to update distributor NAMES for OLD role: {old_role} using OLD name (lower): {old_name_lower}")
                    if old_role == 'BM':
                        # Find distributors matching the OLD BM name (CASE-INSENSITIVE)
                        distributors_to_update = Distributor.query.filter(db.func.lower(Distributor.asm_bm_name) == old_name_lower).all()
                        print(f"Found {len(distributors_to_update)} distributors with old BM name '{old_name}' (case-insensitive)")
                        for dist in distributors_to_update:
                            dist.asm_bm_name = new_name # Update with the NEW name (preserving case from form)
                            print(f"Updating BM name for Distributor ID {dist.id} ({dist.name}) to '{new_name}'")
                    elif old_role == 'RH':
                        # Find distributors matching the OLD RH name (CASE-INSENSITIVE)
                        distributors_to_update = Distributor.query.filter(db.func.lower(Distributor.rh_name) == old_name_lower).all()
                        print(f"Found {len(distributors_to_update)} distributors with old RH name '{old_name}' (case-insensitive)")
                        for dist in distributors_to_update:
                            dist.rh_name = new_name # Update with the NEW name (preserving case from form)
                            print(f"Updating RH name for Distributor ID {dist.id} ({dist.name}) to '{new_name}'")
                # --- End FIX ---

                # --- END: Modified section ---

                db.session.commit()
                print("--- Changes committed successfully ---") # DEBUG
                flash(f'User "{user.name}" updated successfully.', 'success')
                return redirect(url_for('manage_users'))
            except Exception as e:
                db.session.rollback()
                print(f"--- ERROR during update: {e} ---") # DEBUG
                import traceback
                traceback.print_exc() # Print full traceback for detailed error
                flash(f"Error updating user: {e}", "danger")

    # If GET request or validation failed, render form
    return render_template('admin/user_form.html', form=form, title=f'Edit User: {user.name}', user=user)

@app.route('/admin/users/delete/<int:user_id>', methods=['POST'])
@login_required
@role_required('Admin')
def delete_user(user_id):
    """Delete user"""
    user_to_delete = User.query.get_or_404(user_id)

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

    try:
        db.session.delete(user_to_delete)
        db.session.commit()
        flash(f'User "{user_to_delete.name}" deleted successfully.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f"Error deleting user: {e}", "danger")

    return redirect(url_for('manage_users'))

# --- Context Processor ---
@app.context_processor
def inject_global_vars():
    """Make variables available in all templates"""
    return dict(current_user=current_user)

# --- Error Handlers ---
@app.errorhandler(404)
def not_found_error(error):
    """Handle 404 errors"""
    flash('The requested page was not found.', 'warning')
    return redirect(url_for('dashboard'))

@app.errorhandler(500)
def internal_error(error):
    """Handle 500 errors"""
    db.session.rollback()
    flash('An internal error occurred. Please try again.', 'danger')
    return redirect(url_for('dashboard'))





# In app.py
# (At the top, add DistributorForm to the forms import)
from forms import LoginForm, AssetRequestForm, UserForm, DistributorForm

# ... (other routes) ...

# --- ADMIN SECTION ---
@app.route('/admin')
@login_required
@role_required('Admin')
def admin_dashboard():
    """Admin dashboard redirect"""
    # Point to manage_users by default, or a new admin dashboard
    return redirect(url_for('manage_users'))

# ... (all your /admin/users/... routes) ...


# --- NEW DISTRIBUTOR MANAGEMENT ROUTES ---

@app.route('/admin/distributors')
@login_required
@role_required('Admin')
def manage_distributors():
    """Manage distributors page with sorting and searching"""
    try:
        # --- NEW: Get sort and search parameters ---
        sort_by = request.args.get('sort_by', 'name')
        order_by = request.args.get('order_by', 'asc')
        search = request.args.get('search', '').strip()

        # --- NEW: Start query and join with User for SE name ---
        query = Distributor.query.outerjoin(User, Distributor.se_id == User.id)

        # --- NEW: Apply search filter ---
        if search:
            search_term = f'%{search}%'
            query = query.filter(
                db.or_(
                    Distributor.name.ilike(search_term),
                    Distributor.code.ilike(search_term),
                    User.name.ilike(search_term), # Search SE name
                    Distributor.asm_bm_name.ilike(search_term),
                    Distributor.rh_name.ilike(search_term)
                )
            )

        # --- NEW: Map sort keys to columns ---
        sort_column_map = {
            'name': Distributor.name,
            'code': Distributor.code,
            'se': User.name, # Sort by the joined User.name
            'bm': Distributor.asm_bm_name,
            'rh': Distributor.rh_name
        }
        sort_field = sort_column_map.get(sort_by, Distributor.name)

        # --- NEW: Apply sorting ---
        if order_by == 'desc':
            query = query.order_by(sort_field.desc())
        else:
            query = query.order_by(sort_field.asc())

        distributors = query.all()
        
        # --- NEW: Pass sort/search state to template ---
        return render_template(
            'admin/manage_distributors.html', 
            distributors=distributors,
            current_sort=sort_by,
            current_order=order_by,
            current_search=search
        )
    except Exception as e:
        flash(f"Error loading distributors: {e}", "danger")
        return redirect(url_for('dashboard'))

# In app.py

# --- Add this helper function somewhere near the admin routes ---
def _populate_se_choices(form):
    """Helper to populate the SE dropdown in the DistributorForm."""
    # Fetch all users with the 'SE' role
    sales_executives = User.query.filter_by(role='SE').order_by(User.name).all()
    # Create choices list: (value_to_save, label_to_display)
    # We use the user's ID as the value
    form.se_id.choices = [(se.id, se.name) for se in sales_executives]
    # Add an option for "Unassigned" at the beginning
    # Using 0 as the value for 'Unassigned'
    form.se_id.choices.insert(0, (0, '--- Unassigned ---'))

# --- Replace the existing add_distributor route ---
@app.route('/admin/distributors/add', methods=['GET', 'POST'])
@login_required
@role_required('Admin')
def add_distributor():
    """Add new distributor"""
    form = DistributorForm()
    _populate_se_choices(form) # Populate the dropdown before handling POST

    if form.validate_on_submit():
        # Check for uniqueness (code and name)
        existing_code = Distributor.query.filter_by(code=form.code.data.strip()).first()
        existing_name = Distributor.query.filter_by(name=form.name.data.strip()).first()
        if existing_code:
            flash('This Distributor Code already exists.', 'danger')
        elif existing_name:
            flash('This Distributor Name already exists.', 'danger')
        else:
            try:
                # Create new distributor object
                new_dist = Distributor(
                    code=form.code.data.strip(),
                    name=form.name.data.strip(),
                    city=form.city.data.strip() or None, # Store None if empty
                    state=form.state.data.strip() or None,
                    asm_bm_name=form.asm_bm_name.data.strip(),
                    bm_email=form.bm_email.data.strip().lower(),
                    rh_name=form.rh_name.data.strip() or None,
                    rh_email=form.rh_email.data.strip().lower() or None,
                    # Save the selected SE ID (store None if 'Unassigned' was chosen)
                    se_id=form.se_id.data if form.se_id.data != 0 else None
                )
                db.session.add(new_dist)
                db.session.commit()
                flash(f'Distributor "{new_dist.name}" created successfully.', 'success')
                return redirect(url_for('manage_distributors'))
            except Exception as e:
                db.session.rollback()
                flash(f"Error creating distributor: {e}", "danger")
                print(f"Error creating distributor: {e}") # Log error

    # If GET or validation failed, render form again
    return render_template('admin/distributor_form.html', form=form, title='Add New Distributor')

# --- Replace the existing edit_distributor route ---
@app.route('/admin/distributors/edit/<int:dist_id>', methods=['GET', 'POST'])
@login_required
@role_required('Admin')
def edit_distributor(dist_id):
    """Edit existing distributor"""
    dist = Distributor.query.get_or_404(dist_id)
    # Populate form with existing data when GET request
    form = DistributorForm(obj=dist)
    _populate_se_choices(form) # Populate the dropdown

    if form.validate_on_submit():
        # Check for uniqueness (excluding self)
        existing_code = Distributor.query.filter(Distributor.code == form.code.data.strip(), Distributor.id != dist_id).first()
        existing_name = Distributor.query.filter(Distributor.name == form.name.data.strip(), Distributor.id != dist_id).first()
        if existing_code:
            flash('This Distributor Code is already in use by another distributor.', 'danger')
        elif existing_name:
            flash('This Distributor Name is already in use by another distributor.', 'danger')
        else:
            try:
                # Update distributor object attributes
                dist.code = form.code.data.strip()
                dist.name = form.name.data.strip()
                dist.city = form.city.data.strip() or None
                dist.state = form.state.data.strip() or None
                dist.asm_bm_name = form.asm_bm_name.data.strip()
                dist.bm_email = form.bm_email.data.strip().lower()
                dist.rh_name = form.rh_name.data.strip() or None
                dist.rh_email = form.rh_email.data.strip().lower() or None
                # Update the selected SE ID
                dist.se_id = form.se_id.data if form.se_id.data != 0 else None
                
                db.session.commit()
                flash(f'Distributor "{dist.name}" updated successfully.', 'success')
                return redirect(url_for('manage_distributors'))
            except Exception as e:
                db.session.rollback()
                flash(f"Error updating distributor: {e}", "danger")
                print(f"Error updating distributor: {e}") # Log error
    
    # If GET request or validation failed, ensure dropdown is populated correctly
    # WTForms might auto-select the current value, but explicitly setting helps
    if request.method == 'GET' and dist.se_id:
         form.se_id.data = dist.se_id # Pre-select the current SE

    return render_template('admin/distributor_form.html', form=form, title=f'Edit Distributor: {dist.name}')


@app.route('/admin/distributors/delete/<int:dist_id>', methods=['POST'])
@login_required
@role_required('Admin')
def delete_distributor(dist_id):
    """Delete distributor"""
    dist_to_delete = Distributor.query.get_or_404(dist_id)

    # Check if any requests are associated with this distributor
    has_requests = AssetRequest.query.filter_by(distributor_id=dist_id).first()

    if has_requests:
        flash(f'Cannot delete "{dist_to_delete.name}" - it is associated with existing requests.', 'danger')
        return redirect(url_for('manage_distributors'))

    try:
        db.session.delete(dist_to_delete)
        db.session.commit()
        flash(f'Distributor "{dist_to_delete.name}" deleted successfully.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f"Error deleting distributor: {e}", "danger")

    return redirect(url_for('manage_distributors'))

# ... (rest of admin routes) ...



# --- Add this new route somewhere after view_request ---

def _save_photo_from_data_url(data_url, upload_folder, allowed_extensions):
    """Helper function to save a base64 data URL as a file."""
    if not data_url or not data_url.startswith('data:image'):
        return None, "Invalid photo data."

    try:
        header, encoded = data_url.split(",", 1)
        data = base64.b64decode(encoded)
        # Basic extension check, adjust if needed (e.g., handle jpeg/jpg)
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


@app.route('/request/<int:request_id>/deploy', methods=['GET', 'POST'])
@login_required
@role_required('SE', 'Admin') # Only SE (requester) or Admin can confirm
def confirm_deployment(request_id):
    """Page for SE to confirm deployment of an asset."""
    asset_request = AssetRequest.query.get_or_404(request_id)
    form = DeploymentForm()

    # --- Security Checks ---
    # Only the original requester or an admin can access this
    if current_user.role != 'Admin' and asset_request.requester_id != current_user.id:
        flash("You do not have permission to access this page.", "danger")
        return redirect(url_for('dashboard'))

    # Can only deploy if the status is 'Approved'
    if asset_request.status != 'Approved':
        flash("This request is not in the 'Approved' state and cannot be deployed.", "warning")
        return redirect(url_for('view_request', request_id=request_id))

    if form.validate_on_submit():
        # Check for unique serial number before saving photos
        serial_no_stripped = form.deployed_serial_no.data.strip()
        existing_serial = AssetRequest.query.filter(
            AssetRequest.deployed_serial_no == serial_no_stripped,
            AssetRequest.id != request_id # Exclude self if somehow re-deploying
        ).first()
        if existing_serial:
            flash("This asset serial number has already been recorded for another request.", "danger")
            # Don't return yet, let the user correct it
        else:
            # Process and save the two photos
            photo1_filename, p1_error = _save_photo_from_data_url(
                form.deployment_photo1.data, app.config['UPLOAD_FOLDER'], app.config['ALLOWED_EXTENSIONS']
            )
            if p1_error:
                flash(f"Photo 1 Error: {p1_error}", "danger")
                # Don't return yet

            photo2_filename, p2_error = _save_photo_from_data_url(
                form.deployment_photo2.data, app.config['UPLOAD_FOLDER'], app.config['ALLOWED_EXTENSIONS']
            )
            if p2_error:
                flash(f"Photo 2 Error: {p2_error}", "danger")
                # Don't return yet

            # Only proceed if serial is unique AND photos saved successfully
            if not existing_serial and not p1_error and not p2_error:
                try:
                    # Update the AssetRequest object with deployment details
                    asset_request.deployed_make = form.deployed_make.data.strip()
                    asset_request.deployed_serial_no = serial_no_stripped
                    asset_request.deployment_photo1_filename = photo1_filename
                    asset_request.deployment_photo2_filename = photo2_filename
                    asset_request.deployed_by_id = current_user.id
                    asset_request.deployment_date = datetime.utcnow()
                    asset_request.status = 'Deployed' # Close the loop!

                    db.session.commit()
                    flash('Deployment confirmed successfully! The request is now closed.', 'success')
                    return redirect(url_for('view_request', request_id=request_id))

                except Exception as e:
                    db.session.rollback()
                    print(f"ERROR saving deployment: {e}")
                    flash(f"An error occurred while saving the deployment: {e}", "danger")

    # If GET or validation failed (or photo/serial errors occurred above)
    return render_template('deployment_form.html', form=form, request=asset_request)

# In app.py, replace the entire export_excel function with this:

@app.route('/export/excel')
@login_required
def export_excel():
    """Export requests to an Excel file for DMS based on specific filters."""
    
    # --- 1. START WITH THE BASE SECURITY QUERY from the dashboard ---
    base_query = AssetRequest.query

    if current_user.role == 'SE':
        base_query = base_query.filter_by(requester_id=current_user.id)
    elif current_user.role in ['BM', 'DB']:
        base_query = base_query.join(Distributor).filter(
            db.func.lower(Distributor.bm_email) == current_user.email.lower()
        )
    elif current_user.role == 'RH':
        base_query = base_query.join(Distributor).filter(
            db.func.lower(Distributor.rh_email) == current_user.email.lower()
        )
    
    # Eager load related objects (Distributor, Requester) to improve performance
    query = base_query.options(
        db.joinedload(AssetRequest.distributor),
        db.joinedload(AssetRequest.requester)
    ).order_by(AssetRequest.request_date.desc())


    # --- 2. GET NEW FILTERS FROM THE MODAL FORM ---
    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')
    filter_requester_id = request.args.get('requester')
    filter_status = request.args.get('status')

    # --- 3. APPLY NEW FILTERS TO THE QUERY ---
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

    # --- 4. CREATE THE EXCEL FILE IN MEMORY ---
    wb = Workbook()
    ws = wb.active
    ws.title = "DMS Export"

    # ========================================================================
    # --- START: MODIFIED HEADERS AND ROW MAPPING ---
    # ========================================================================

    # Define the headers based on your "HFL to DMS Pushing format.xlsx"
    headers = [
        "Customer Category", "Customer Name", "Customer Code", "Customer Type",
        "Customer Address", "Region", "Sales Office", "pincode",
        "Territory/Cluster", "Contact No 1", "Contact No 2", "Contact No 3",
        "Email Id 1", "Email Id 2", "Primary Contact Person", "Secondary Contact Person",
        "Parent Customer Code", "GST No", "GST State Code", "PAN",
        "Rate Code", "Discount Code", "Remarks", "FSSAI", "BEAT Name"
    ]
    ws.append(headers)

    # --- 5. MAP YOUR DATA TO THE NEW EXCEL COLUMNS ---
    for req in requests_to_export:
        # Combine address and landmark into one field
        full_address = f"{req.retailer_address or ''} {req.landmark or ''}".strip()
        
        row = [
            req.category,                           # Customer Category
            req.retailer_name,                      # Customer Name
            req.id,                                 # Customer Code (Using Req ID as unique code)
            "GT",                                   # Customer Type (Hardcoded as per sample)
            full_address,                           # Customer Address (Combined Address + Landmark)
            req.distributor.city if req.distributor else "", # Region (Using Distributor's City)
            req.requester.so if req.requester else "",       # Sales Office (Using SE's SO)
            "",                                     # pincode (Not in your form)
            "",                                     # Territory/Cluster (Not in your form)
            req.retailer_contact,                   # Contact No 1
            "",                                     # Contact No 2 (Optional)
            "",                                     # Contact No 3 (Optional)
            req.retailer_email,                     # Email Id 1
            "",                                     # Email Id 2 (Optional)
            req.retailer_name,                      # Primary Contact Person
            "",                                     # Secondary Contact Person (Optional)
            req.distributor.code if req.distributor else "", # Parent Customer Code
            "",                                     # GST No (Not in your form)
            "",                                     # GST State Code (Not in your form)
            "",                                     # PAN (Not in your form)
            "",                                     # Rate Code (Not in your form)
            "",                                     # Discount Code (Not in your form)
            "",                                     # Remarks (Optional)
            "",                                     # FSSAI (Not in your form)
            ""                                      # BEAT Name (Not in your form)
        ]
        ws.append(row)

    # ========================================================================
    # --- END: MODIFIED SECTION ---
    # ========================================================================

    # --- 6. SAVE TO A MEMORY BUFFER & SEND ---
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