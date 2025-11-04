from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime
from werkzeug.security import generate_password_hash

# Create the database instance
db = SQLAlchemy()

class User(UserMixin, db.Model):
    """User model for authentication and roles."""
    id = db.Column(db.Integer, primary_key=True)
    employee_code = db.Column(db.String(20), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=True)
    role = db.Column(db.String(20), nullable=False)  # SE, BM, RH, Admin
    password_hash = db.Column(db.String(256))
    so = db.Column(db.String(100), nullable=True) # Added SE's SO

    # Relationships
    requests = db.relationship('AssetRequest', foreign_keys='AssetRequest.requester_id', backref='requester', lazy=True)
    # This lets us easily see all distributors assigned to this user (if they are an SE)
    assigned_distributors = db.relationship('Distributor', backref='sales_executive', lazy=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def __repr__(self):
        return f'<User {self.name} ({self.role})>'

class Distributor(db.Model):
    """Distributor model."""
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(50), unique=True, nullable=True) # Added Code
    name = db.Column(db.String(150), unique=True, nullable=False)
    city = db.Column(db.String(100)) # Changed name to city (matches form 'town')
    state = db.Column(db.String(100))
    
    # --- Approval Chain Info ---
    asm_bm_name = db.Column(db.String(100), nullable=True) # Added ASM/BM Name
    bm_email = db.Column(db.String(120), nullable=True)  # Added BM Email
    rh_name = db.Column(db.String(100), nullable=True) # Added RH Name (assuming)
    rh_email = db.Column(db.String(120), nullable=True)  # Added RH Email

    # --- NEW FIELD TO LINK SE ---
    se_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True) # Can be nullable if unassigned

    requests = db.relationship('AssetRequest', backref='distributor', lazy=True)

    def __repr__(self):
        return f'<Distributor {self.name}>'

class AssetRequest(db.Model):
    """Asset Request model."""
    id = db.Column(db.Integer, primary_key=True)
    requester_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    distributor_id = db.Column(db.Integer, db.ForeignKey('distributor.id'), nullable=False)

    request_date = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    status = db.Column(db.String(50), nullable=False, default='Pending BM Approval') # Default Status

    # --- Asset Details ---
    asset_model = db.Column(db.String(100), nullable=False)
    category = db.Column(db.String(100), nullable=False)
    placement_date = db.Column(db.Date, nullable=True)

    # --- Location ---
    latitude = db.Column(db.Float, nullable=True)
    longitude = db.Column(db.Float, nullable=True)

    # --- Retailer Info ---
    retailer_name = db.Column(db.String(150), nullable=False)
    retailer_contact = db.Column(db.String(15), nullable=False, unique=True)
    area_town = db.Column(db.String(100), nullable=True)
    landmark = db.Column(db.String(200), nullable=True)
    retailer_address = db.Column(db.Text, nullable=True)
    retailer_email = db.Column(db.String(120), nullable=True)
    selling_ice_cream = db.Column(db.String(10), nullable=True)
    monthly_sales = db.Column(db.Integer, nullable=True)
    ice_cream_brands = db.Column(db.Text, nullable=True)
    
    # --- Photo ---
    photo_filename = db.Column(db.String(200), nullable=True)

    # --- SE Survey Fields ---
    competitor_assets = db.Column(db.String(10), nullable=True)  # 'Yes' / 'No'
    signage_availability = db.Column(db.String(10), nullable=True) # 'Yes' / 'No'
    willing_for_signage = db.Column(db.String(10), nullable=True)  # 'Yes' / 'No'

    # --- Approval Tracking ---
    bm_approver_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    rh_approver_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    
    bm_remarks = db.Column(db.Text, nullable=True) # For BM's REJECTION comments
    rh_remarks = db.Column(db.Text, nullable=True) # For RH's REJECTION comments

    # --- BM Approval Fields ---
    bm_approval_type = db.Column(db.String(50), nullable=True) # 'With Security' or 'Free of Cost'
    bm_security_amount = db.Column(db.Integer, nullable=True)
    bm_foc_justification = db.Column(db.Text, nullable=True)

    # --- Deployment Fields ---
    deployed_make = db.Column(db.String(100), nullable=True)
    deployed_serial_no = db.Column(db.String(100), nullable=True, unique=True)
    deployment_photo1_filename = db.Column(db.String(200), nullable=True)
    deployment_photo2_filename = db.Column(db.String(200), nullable=True)
    deployment_date = db.Column(db.DateTime, nullable=True)
    deployed_by_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)

    # --- Relationships ---
    bm_approver = db.relationship('User', foreign_keys=[bm_approver_id])
    rh_approver = db.relationship('User', foreign_keys=[rh_approver_id])
    deployed_by = db.relationship('User', foreign_keys=[deployed_by_id])

    def __repr__(self):
        return f'<AssetRequest ID: {self.id} for {self.distributor.name}>'

