from flask_login import UserMixin
from datetime import datetime
from werkzeug.security import generate_password_hash
from assetify_app import db  # Use the db instance from the app factory

class User(UserMixin, db.Model):
    """User model for authentication and roles."""
    id = db.Column(db.Integer, primary_key=True)
    
    # --- ADDED index=True ---
    employee_code = db.Column(db.String(120), unique=True, nullable=False, index=True)
    
    name = db.Column(db.String(100), nullable=False)
    
    # --- ADDED index=True ---
    email = db.Column(db.String(120), unique=True, nullable=True, index=True)
    role = db.Column(db.String(20), nullable=False, index=True)
    
    password_hash = db.Column(db.String(256))
    so = db.Column(db.String(100), nullable=True)
    
    # --- ADDED index=True (Foreign Key) ---
    distributor_id = db.Column(db.Integer, db.ForeignKey('distributor.id'), nullable=True, index=True)
    
    requests = db.relationship('AssetRequest', foreign_keys='AssetRequest.requester_id', backref='requester', lazy=True)
    assigned_distributors = db.relationship('Distributor', foreign_keys='Distributor.se_id', backref='sales_executive', lazy=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def __repr__(self):
        return f'<User {self.name} ({self.role})>'

class Distributor(db.Model):
    """Distributor model."""
    id = db.Column(db.Integer, primary_key=True)
    
    # --- ADDED index=True ---
    code = db.Column(db.String(50), unique=True, nullable=True, index=True)
    name = db.Column(db.String(150), unique=True, nullable=False, index=True)
    
    city = db.Column(db.String(100))
    state = db.Column(db.String(100))
    
    # --- OLD FIELDS (Can be removed after migration) ---
    asm_bm_name = db.Column(db.String(100), nullable=True) 
    bm_email = db.Column(db.String(120), nullable=True)  
    rh_name = db.Column(db.String(100), nullable=True) 
    rh_email = db.Column(db.String(120), nullable=True)  

    # --- ADDED index=True (Foreign Keys) ---
    se_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True, index=True)
    bm_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True, index=True)
    rh_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True, index=True)

    requests = db.relationship('AssetRequest', backref='distributor', lazy=True)
    branch_manager = db.relationship('User', foreign_keys=[bm_id])
    regional_head = db.relationship('User', foreign_keys=[rh_id])
    distributor_users = db.relationship('User', foreign_keys=[User.distributor_id], backref='assigned_distributor', lazy=True)

    def __repr__(self):
        return f'<Distributor {self.name}>'

class AssetRequest(db.Model):
    """Asset Request model."""
    id = db.Column(db.Integer, primary_key=True)
    
    # --- ADDED index=True (Foreign Keys) ---
    requester_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    distributor_id = db.Column(db.Integer, db.ForeignKey('distributor.id'), nullable=False, index=True)
    
    request_date = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True) # <-- Good to index dates
    
    # --- ADDED index=True (Common Filter) ---
    status = db.Column(db.String(50), nullable=False, default='Pending BM Approval', index=True)
    
    asset_model = db.Column(db.String(100), nullable=False)
    category = db.Column(db.String(100), nullable=False)
    placement_date = db.Column(db.Date, nullable=True)
    latitude = db.Column(db.Float, nullable=True)
    longitude = db.Column(db.Float, nullable=True)
    retailer_name = db.Column(db.String(150), nullable=False)
    
    # --- ADDED index=True (Unique Search) ---
    retailer_contact = db.Column(db.String(15), nullable=False, unique=True, index=True)
    
    area_town = db.Column(db.String(100), nullable=True)
    landmark = db.Column(db.String(200), nullable=True)
    retailer_address = db.Column(db.Text, nullable=True)
    retailer_email = db.Column(db.String(120), nullable=True)
    selling_ice_cream = db.Column(db.String(10), nullable=True)
    monthly_sales = db.Column(db.Integer, nullable=True)
    ice_cream_brands = db.Column(db.Text, nullable=True)
    photo_filename = db.Column(db.String(200), nullable=True)
    competitor_assets = db.Column(db.String(10), nullable=True)
    signage_availability = db.Column(db.String(10), nullable=True)
    willing_for_signage = db.Column(db.String(10), nullable=True)
    
    # --- ADDED index=True (Foreign Keys) ---
    bm_approver_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True, index=True)
    rh_approver_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True, index=True)
    
    bm_remarks = db.Column(db.Text, nullable=True)
    rh_remarks = db.Column(db.Text, nullable=True)
    bm_approval_type = db.Column(db.String(50), nullable=True)
    bm_security_amount = db.Column(db.Integer, nullable=True)
    bm_foc_justification = db.Column(db.Text, nullable=True)
    deployed_make = db.Column(db.String(100), nullable=True)
    
    # --- ADDED index=True (Unique Search) ---
    deployed_serial_no = db.Column(db.String(100), nullable=True, unique=True, index=True)
    
    deployment_photo1_filename = db.Column(db.String(200), nullable=True)
    deployment_photo2_filename = db.Column(db.String(200), nullable=True)
    deployment_date = db.Column(db.DateTime, nullable=True)
    
    # --- ADDED index=True (Foreign Key) ---
    deployed_by_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True, index=True)
    
    bm_approver = db.relationship('User', foreign_keys=[bm_approver_id])
    rh_approver = db.relationship('User', foreign_keys=[rh_approver_id])
    deployed_by = db.relationship('User', foreign_keys=[deployed_by_id])

    def __repr__(self):
        return f'<AssetRequest ID: {self.id} for {self.distributor.name}>'