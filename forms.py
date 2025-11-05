from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField, SubmitField, SelectField, IntegerField, TextAreaField, DateField, FloatField, HiddenField
from wtforms.validators import DataRequired, Length, NumberRange, Optional, Email, Regexp, EqualTo
from wtforms.validators import DataRequired, Length, Optional, Email
from flask_wtf.file import FileField, FileRequired, FileAllowed


# --- UPDATED LoginForm ---
class LoginForm(FlaskForm):
    """Form for user login."""
    # --- THIS IS THE FIX ---
    # Increased max length from 20 to 120
    employee_code = StringField('Employee Code', validators=[DataRequired(), Length(min=4, max=120)])
    # --- END OF FIX ---
    
    password = PasswordField('Password', validators=[DataRequired()])
    remember_me = BooleanField('Remember Me')
    submit = SubmitField('Login')

# --- UPDATED UserForm ---
class UserForm(FlaskForm):
    """Form for admins to add or edit users."""
    name = StringField('Full Name', validators=[DataRequired(), Length(max=100)])
    
    # --- THIS IS THE FIX ---
    # Increased max length from 20 to 120
    employee_code = StringField('Employee Code', validators=[DataRequired(), Length(min=4, max=120)])
    # --- END OF FIX ---

    email = StringField('Email', validators=[Optional(), Email(), Length(max=120)])
    so = StringField('Sales Office (SO)', validators=[Optional(), Length(max=100)])
    
    role = SelectField('Role',
                       choices=[
                           ('SE', 'Sales Executive (SE)'),
                           ('BM', 'Branch Manager (BM)'),
                           ('RH', 'Regional Head (RH)'),
                           ('DB', 'Distributor'),
                           ('Admin', 'Administrator')
                       ],
                       validators=[DataRequired()])
    
    password = PasswordField('Password',
                             validators=[
                                 Optional(), 
                                 Length(min=6, message='Password must be at least 6 characters long.'),
                                 EqualTo('confirm_password', message='Passwords must match.')
                             ])
    confirm_password = PasswordField('Confirm Password')
    distributor_id = SelectField('Assign to Distributor (if role is "Distributor")', coerce=int, validators=[Optional()])
    submit = SubmitField('Save User')


# --- AssetRequestForm (No changes needed) ---
class AssetRequestForm(FlaskForm):
    """Form for creating a new asset request, based on provided HTML."""
    distributor_name = SelectField('Distributor Name', validators=[DataRequired()])
    asset_model = SelectField('Required Asset Model',
                              choices=[
                                  ('', 'Select Model'),
                                  ('300 GT', '300 GT'),
                                  ('400 GT', '400 GT'),
                                  ('500 HT', '500 HT'),
                                  ('500 GT', '500 GT'),
                                  ('Glycol (PC)', 'Glycol (PC)')
                              ],
                              validators=[DataRequired(message="Please select an asset model.")]) 
    category = SelectField('Category',
                           choices=[
                               ('', 'Select Category'),
                               ('Hotel, Restaurant & Coffee Shop', 'Hotel, Restaurant & Coffee Shop'),
                               ('Bakery', 'Bakery'),
                               ('Kirana Store', 'Kirana Store'),
                               ('MRF', 'MRF'),
                               ('General Store', 'General Store'),
                               ('School/Collage Canteen', 'School/Collage Canteen'),
                               ('Office Canteen', 'Office Canteen'),
                               ('Convience Store', 'Convience Store'),
                               ('Ecom/Qcom', 'Ecom/Qcom'),
                               ('Sweet Shop', 'Sweet Shop'),
                               ('Stationary Shop', 'Stationary Shop'),
                               ('PC', 'PC'),
                               ('HDC', 'HDC'),
                               ('Others', 'Others')
                           ],
                           validators=[DataRequired(message="Please select a category.")])
    placement_date = DateField('Placement Expected Date', format='%Y-%m-%d', validators=[DataRequired()])
    latitude = FloatField('Latitude', validators=[DataRequired(message="Please capture your location.")])
    longitude = FloatField('Longitude', validators=[DataRequired(message="Please capture your location.")]) 
    retailer_name = StringField('Retailer Name', validators=[DataRequired(), Length(max=150)])
    retailer_contact = StringField('Retailer Contact',
                                   validators=[
                                       DataRequired(),
                                       Regexp(r'^\d{10}$', message='Enter 10 digits only.')
                                   ])
    area_town = StringField('Area/Town', validators=[DataRequired(), Length(max=100)])
    landmark = StringField('Nearest Landmark', validators=[Optional(), Length(max=200)])
    retailer_address = TextAreaField('Retailer Address', validators=[Optional(), Length(max=500)])
    retailer_email = StringField('Retailer Email (optional)', validators=[Optional(), Email(), Length(max=120)])
    selling_ice_cream = SelectField('Presently selling Ice Cream?',
                                    choices=[('', 'Select'), ('yes', 'Yes'), ('no', 'No')],
                                    validators=[DataRequired()])
    monthly_sales = IntegerField('Monthly Sales Value (₹)', validators=[Optional(), NumberRange(min=0)])
    ice_cream_brands = TextAreaField('Ice Cream Brands Available', validators=[Optional(), Length(max=500)])
    competitor_assets = SelectField('Competitor assets?',
                                    choices=[('', 'Select'), ('Yes', 'Yes'), ('No', 'No')],
                                    validators=[Optional()])
    signage_availability = SelectField('Signage Availability?',
                                       choices=[('', 'Select'), ('Yes', 'Yes'), ('No', 'No')],
                                       validators=[Optional()])
    willing_for_signage = SelectField('Willing for HFL Signage?',
                                      choices=[('', 'Select'), ('Yes', 'Yes'), ('No', 'No')],
                                      validators=[DataRequired(message="Please select an option.")])
    captured_photo = HiddenField('Captured Photo Data', validators=[DataRequired(message="Please capture a photo.")])
    distributor_code_hidden = HiddenField("Distributor Code")
    distributor_town_hidden = HiddenField("Distributor Town")
    bm_email_hidden = HiddenField("BM Email")
    rh_email_hidden = HiddenField("RH Email")
    latitude = HiddenField('Latitude', validators=[
        DataRequired(message="Geolocation is required. Please use the 'Get Location' button.")
    ])
    longitude = HiddenField('Longitude', validators=[
        DataRequired(message="Geolocation is required. Please use the 'Get Location' button.")
    ])
    captured_photo = HiddenField('Shop Photo', validators=[
        DataRequired(message="A shop photo is required. Please use the camera.")
    ])
    submit = SubmitField('Submit Request')


# --- DistributorForm (No changes needed) ---
class DistributorForm(FlaskForm):
    """Form for admins to add or edit distributors."""
    code = StringField('Distributor Code', validators=[DataRequired(), Length(max=50)])
    name = StringField('Distributor Name', validators=[DataRequired(), Length(max=150)])
    city = StringField('City / Town', validators=[Optional(), Length(max=100)])
    state = StringField('State', validators=[Optional(), Length(max=100)])
    
    se_id = SelectField('Assigned Sales Executive (SE)', coerce=int, validators=[Optional()])
    bm_id = SelectField('Assigned Branch Manager (BM)', coerce=int, validators=[DataRequired(message="A BM must be assigned.")])
    rh_id = SelectField('Assigned Regional Head (RH)', coerce=int, validators=[Optional()])
    
    submit = SubmitField('Save Distributor')


# DeploymentForm remains the same
class DeploymentForm(FlaskForm):
    """Form for SE to confirm asset deployment."""
    deployed_make = StringField('Asset Make/Manufacturer', validators=[DataRequired(), Length(max=100)])
    deployed_serial_no = StringField('Asset Serial Number', validators=[DataRequired(), Length(max=100)])
    deployment_photo1 = HiddenField('Photo 1 Data', validators=[DataRequired(message="Please capture the first photo.")])
    deployment_photo2 = HiddenField('Photo 2 Data', validators=[DataRequired(message="Please capture the second photo.")])
    submit = SubmitField('Confirm Deployment')