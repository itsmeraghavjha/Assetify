import os
import base64
import uuid
import io
from flask import (
    Blueprint, render_template, redirect, url_for, flash, request, 
    send_from_directory, jsonify, current_app, send_file
)
from flask_login import login_required, current_user
from flask_mail import Message
from threading import Thread
from functools import wraps
from models import db, User, Distributor, AssetRequest
from forms import AssetRequestForm, DeploymentForm
from sqlalchemy.exc import IntegrityError
from werkzeug.utils import secure_filename
from datetime import datetime, timedelta
from openpyxl import Workbook
# We do not import db or mail here, they are imported from the factory in __init__.py

# --- Create Blueprint ---
core_bp = Blueprint('core', __name__)

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

def send_async_email(app_instance, msg):
    with app_instance.app_context():
        try:
            # --- FIX: Import mail from the app factory ---
            from assetify_app import mail
            if app_instance.config['MAIL_USERNAME'] and app_instance.config['MAIL_PASSWORD']:
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
    if not current_app.config['MAIL_USERNAME'] or not current_app.config['MAIL_PASSWORD']:
        print(f"Email skipped (not configured): '{subject}' to {recipient_email}")
        return
    try:
        sender = current_app.config['MAIL_DEFAULT_SENDER'] or current_app.config['MAIL_USERNAME']
        msg = Message(subject, sender=sender, recipients=[recipient_email])
        msg.html = render_template(template, **kwargs)
        
        thread = Thread(target=send_async_email, args=[current_app._get_current_object(), msg])
        thread.daemon = True
        thread.start()
    except Exception as e:
        print(f"ERROR preparing email: {e}")

# --- THIS IS THE ORIGINAL FUNCTION FOR SAVING TO THE UPLOADS FOLDER ---
def _save_photo_from_data_url(data_url):
    """Helper function to save a base64 data URL as a file."""
    upload_folder = current_app.config['UPLOAD_FOLDER']
    allowed_extensions = current_app.config['ALLOWED_EXTENSIONS']
    
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
        return filename, None # Return the filename
    except Exception as e:
        print(f"ERROR processing image: {e}")
        return None, "Error processing image file."


# --- Core Application Routes ---

@core_bp.route('/dashboard')
@login_required
def dashboard():
    # ... (This function is unchanged from the blueprint version) ...
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
    
    pagination = query.paginate(page=page, per_page=current_app.config['ITEMS_PER_PAGE'], error_out=False)
    
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


@core_bp.route('/new_request', methods=['GET', 'POST'])
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
        # --- Uses the local _save_photo_from_data_url ---
        photo_filename, photo_error = _save_photo_from_data_url(
            form.captured_photo.data
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
                photo_filename=photo_filename, # <-- Saves the filename
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


@core_bp.route('/request/<int:request_id>')
@login_required
def view_request(request_id):
    # ... (This function is unchanged from the blueprint version) ...
    asset_request = db.session.get(AssetRequest, request_id)
    if not asset_request:
        flash("Request not found.", "danger")
        return redirect(url_for('core.dashboard'))
    
    user = current_user
    req = asset_request
    
    if user.role == 'Admin':
        pass 
    elif user.role == 'SE':
        if req.requester_id != user.id:
            flash("You don't have permission to view this request.", "danger")
            return redirect(url_for('core.dashboard'))
    elif user.role == 'DB':
        if req.requester_id != user.id:
            flash("You don't have permission to view this request.", "danger")
            return redirect(url_for('core.dashboard'))
    elif user.role == 'BM':
        if req.distributor.bm_id != user.id and req.requester_id != user.id:
            flash("This request is not for your region.", "danger")
            return redirect(url_for('core.dashboard'))
    elif user.role == 'RH':
        if req.distributor.rh_id != user.id and req.requester_id != user.id:
            flash("This request is not for your region.", "danger")
            return redirect(url_for('core.dashboard'))

    return render_template('view_request.html', request=asset_request)


@core_bp.route('/approve/<int:request_id>', methods=['POST'])
@login_required
@role_required('BM', 'RH', 'Admin')
def approve_request(request_id):
    # ... (This function is unchanged, and already contains the "disabled SE email" logic) ...
    asset_request = db.session.get(AssetRequest, request_id)
    if not asset_request:
        flash("Request not found.", "danger")
        return redirect(url_for('core.dashboard'))
        
    action_taken = False
    original_status = asset_request.status

    if current_user.role == 'BM' and asset_request.status == 'Pending BM Approval':
        approval_type = request.form.get('approval_type')
        if approval_type == 'security':
            try:
                amount = int(request.form.get('security_amount', 0))
                if amount <= 0:
                    flash('Security amount must be greater than zero.', 'danger')
                    return redirect(url_for('core.view_request', request_id=request_id))
                asset_request.bm_approval_type = 'With Security'
                asset_request.bm_security_amount = amount
                asset_request.bm_foc_justification = None 
            except (ValueError, TypeError):
                flash('Invalid security amount entered.', 'danger')
                return redirect(url_for('core.view_request', request_id=request_id))
        elif approval_type == 'foc':
            justification = request.form.get('foc_justification', '').strip()
            if not justification:
                flash('Justification is required for "Free of Cost" approval.', 'danger')
                return redirect(url_for('core.view_request', request_id=request_id))
            asset_request.bm_approval_type = 'Free of Cost'
            asset_request.bm_foc_justification = justification
            asset_request.bm_security_amount = None
        else:
            flash('You must select an approval type ("With Security" or "Free of Cost").', 'danger')
            return redirect(url_for('core.view_request', request_id=request_id))

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
            
            # --- SE Email is Disabled Here ---
            # elif asset_request.status == 'Approved':
            #     if asset_request.requester and asset_request.requester.email:
            #          send_email( ... )

        except Exception as e:
            db.session.rollback()
            print(f"ERROR during commit or email sending: {e}") 
            flash(f'Error saving approval or sending email: {e}', 'danger')
            return redirect(url_for('core.view_request', request_id=request_id)) 
    else:
        if 'Pending' not in asset_request.status: 
             flash('Cannot approve this request at its current stage or you lack permission.', 'warning')
    return redirect(url_for('core.view_request', request_id=request_id))


@core_bp.route('/reject/<int:request_id>', methods=['POST'])
@login_required
@role_required('BM', 'RH', 'Admin')
def reject_request(request_id):
    # ... (This function is unchanged, and already contains the "disabled SE email" logic) ...
    asset_request = db.session.get(AssetRequest, request_id)
    if not asset_request:
        flash("Request not found.", "danger")
        return redirect(url_for('core.dashboard'))
        
    action_taken = False
    outcome = 'Rejected'
    remarks = request.form.get('remarks', '').strip()
    
    if not remarks:
        flash('Reason for Rejection is required.', 'danger')
        return redirect(url_for('core.view_request', request_id=request_id))

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
            
            # --- SE Email is Disabled Here ---
            # if asset_request.requester and asset_request.requester.email:
            #     send_email( ... )
            
            flash('Request has been rejected.', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'Error saving rejection: {e}', 'danger')
    else:
        flash('Cannot reject this request at its current stage or you lack permission.', 'warning') 
    return redirect(url_for('core.view_request', request_id=request_id))

@core_bp.route('/request/<int:request_id>/deploy', methods=['GET', 'POST'])
@login_required
@role_required('SE', 'Admin')
def confirm_deployment(request_id):
    """Page for SE to confirm deployment of an asset."""
    asset_request = db.session.get(AssetRequest, request_id)
    if not asset_request:
        flash("Request not found.", "danger")
        return redirect(url_for('core.dashboard'))
        
    form = DeploymentForm()
    is_original_se = (current_user.role == 'SE' and asset_request.requester_id == current_user.id)
    
    if not (current_user.role == 'Admin' or is_original_se):
        flash("You do not have permission to perform this action.", "danger")
        return redirect(url_for('core.dashboard'))
    if asset_request.status != 'Approved':
        flash("This request is not in the 'Approved' state and cannot be deployed.", "warning")
        return redirect(url_for('core.view_request', request_id=request_id))

    if form.validate_on_submit():
        serial_no_stripped = form.deployed_serial_no.data.strip()
        existing_serial = AssetRequest.query.filter(
            AssetRequest.deployed_serial_no == serial_no_stripped,
            AssetRequest.id != request_id 
        ).first()
        if existing_serial:
            flash("This asset serial number has already been recorded for another request.", "danger")
        else:
            # --- Uses the local _save_photo_from_data_url ---
            photo1_filename, p1_error = _save_photo_from_data_url(
                form.deployment_photo1.data
            )
            if p1_error:
                flash(f"Photo 1 Error: {p1_error}", "danger")
            
            photo2_filename, p2_error = _save_photo_from_data_url(
                form.deployment_photo2.data
            )
            if p2_error:
                flash(f"Photo 2 Error: {p2_error}", "danger")
                
            if not existing_serial and not p1_error and not p2_error:
                try:
                    asset_request.deployed_make = form.deployed_make.data.strip()
                    asset_request.deployed_serial_no = serial_no_stripped
                    asset_request.deployment_photo1_filename = photo1_filename # <-- Saves filename
                    asset_request.deployment_photo2_filename = photo2_filename # <-- Saves filename
                    asset_request.deployed_by_id = current_user.id
                    asset_request.deployment_date = datetime.utcnow()
                    asset_request.status = 'Deployed' 
                    db.session.commit()
                    flash('Deployment confirmed successfully! The request is now closed.', 'success')
                    return redirect(url_for('core.view_request', request_id=request_id))
                except Exception as e:
                    db.session.rollback()
                    print(f"ERROR saving deployment: {e}")
                    flash(f"An error occurred while saving the deployment: {e}", "danger")
    return render_template('deployment_form.html', form=form, request=asset_request)

@core_bp.route('/export/excel')
@login_required
def export_excel():
    # ... (This function is unchanged from the blueprint version) ...
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
        return redirect(url_for('core.dashboard'))
            
    requests_to_export = query.all()

    wb = Workbook()
    ws = wb.active
    ws.title = "DMS Export"

    headers = [
        # --- Original DMS Headers ---
        "Customer Category", "Customer Name", "Customer Code", "Customer Type",
        "Customer Address", "Region", "Sales Office", "pincode",
        "Territory/Cluster", "Contact No 1", "Contact No 2", "Contact No 3",
        "Email Id 1", "Email Id 2", "Primary Contact Person", "Secondary Contact Person",
        "Parent Customer Code", "GST No", "GST State Code", "PAN",
        "Rate Code", "Discount Code", "Remarks", "FSSAI", "BEAT Name",
        
        # --- NEW TRACKING HEADERS ---
        "Request ID",
        "Request Date",
        "Request Status",
        "SE (Requester)",
        "Distributor Name",
        "BM Approver",
        "BM Approval Type",
        "BM Security Amount",
        "BM FOC Justification",
        "RH Approver",
        "Deployed By",
        "Deployment Date"
    ]
    ws.append(headers)

    for req in requests_to_export:
        full_address = f"{req.retailer_address or ''} {req.landmark or ''}".strip()
        row = [
            # --- Original DMS Data ---
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
            "", "", "" ,
            
            # --- NEW TRACKING DATA ---
            f"#{req.id}",
            req.request_date.strftime('%Y-%m-%d') if req.request_date else "N/A",
            req.status,
            req.requester.name if req.requester else "N/A",
            req.distributor.name if req.distributor else "N/A",
            req.bm_approver.name if req.bm_approver else "N/A",
            req.bm_approval_type if req.bm_approval_type else "N/A",
            req.bm_security_amount if req.bm_security_amount else "N/A",
            req.bm_foc_justification if req.bm_foc_justification else "N/A",
            req.rh_approver.name if req.rh_approver else "N/A",
            req.deployed_by.name if req.deployed_by else "N/A",
            req.deployment_date.strftime('%Y-%m-%d') if req.deployment_date else "N/A"
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

# --- API Routes ---
@core_bp.route('/api/distributors')
@login_required
def get_distributors():
    # ... (This function is unchanged from the blueprint version) ...
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

@core_bp.route('/api/check_phone/<phone>')
@login_required
def check_retailer_phone(phone):
    # ... (This function is unchanged from the blueprint version) ...
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

# --- THIS IS THE ROUTE TO SERVE LOCAL FILES ---
@core_bp.route('/uploads/<path:filename>')
@login_required
def uploaded_file(filename):
    """Serve uploaded files"""
    try:
        safe_filename = secure_filename(filename)
        return send_from_directory(current_app.config['UPLOAD_FOLDER'], safe_filename)
    except FileNotFoundError:
        return "File not found", 404