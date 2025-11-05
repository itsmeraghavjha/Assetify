import os
import re
import openpyxl  # Uses the Excel library
from app import app, db
from models import User, Distributor, AssetRequest

# --- CONFIGURATION ---
EXCEL_FILE_PATH = 'DB vs EMP Mapping.xlsx'
SHEET_NAME = 'DB wise - SE Mapping'

# --- YOUR PASSWORD RULES ---
BM_RH_PASSWORD = 'hfl@1234'
ADMIN_PASSWORD = 'adminpass'
# SE and DB passwords will be set from the file data

def load_data_from_excel(file_path, sheet_name):
    """
    Loads data from an Excel .xlsx file and returns a list of dictionaries.
    """
    print(f"Reading data from Excel file: {file_path} (Sheet: {sheet_name})")
    try:
        workbook = openpyxl.load_workbook(file_path, data_only=True)
    except FileNotFoundError:
        print(f"--- ERROR ---")
        print(f"File not found: {file_path}")
        print("Please make sure the file is in the same directory as this script.")
        return None
    except Exception as e:
        print(f"--- ERROR Reading Excel File ---")
        print(f"Could not open file. Is it a valid .xlsx file? Error: {e}")
        return None

    try:
        sheet = workbook[sheet_name]
    except KeyError:
        print(f"--- ERROR ---")
        print(f"A sheet named '{sheet_name}' was not found in the Excel file.")
        print(f"Available sheets: {workbook.sheetnames}")
        return None

    rows = []
    headers = [str(cell.value).strip() for cell in sheet[1]]
    for row in sheet.iter_rows(min_row=2):
        row_data = {}
        for header, cell in zip(headers, row):
            row_data[header] = str(cell.value).strip() if cell.value is not None else ''
        rows.append(row_data)
        
    print(f"Successfully read {len(rows)} data rows from Excel.")
    return rows

def setup_database():
    """
    Clears and seeds the database from the provided Excel file.
    Run this script ONCE after 'flask db upgrade' to set up a clean database.
    """
    
    rows = load_data_from_excel(EXCEL_FILE_PATH, SHEET_NAME)
    if rows is None:
        return 

    with app.app_context():
        # --- STAGE 1: Clear existing data ---
        try:
            print("Clearing existing data...")
            db.session.query(AssetRequest).delete()
            for user in User.query.all():
                user.distributor_id = None
            db.session.commit()
            for dist in Distributor.query.all():
                dist.se_id = None
                dist.bm_id = None
                dist.rh_id = None
            db.session.commit()
            db.session.query(User).delete()
            db.session.query(Distributor).delete()
            db.session.commit()
            print("Existing data cleared.")
        except Exception as e:
            db.session.rollback()
            print(f"ERROR clearing data: {e}")
            return

        # --- STAGE 2: Create all User accounts (SE, BM, RH, Admin) ---
        print("Finding and creating all unique User accounts...")
        try:
            unique_ses = {}
            unique_bms = {}
            unique_rhs = {}
            
            for row in rows:
                se_code = row.get('SE Emp Code', '').strip()
                se_name = row.get('SE Name', '').strip()
                
                if (se_code == '0' or not se_code or se_code == 'None') and se_name:
                    se_code = "vacant_" + re.sub(r'[^a-zA-Z0-9]', '_', se_name).lower()

                if se_code and se_code not in unique_ses:
                    unique_ses[se_code] = {
                        'name': se_name,
                        'email': None, 
                        'role': 'SE',
                        'so': row.get('SO', '').strip(),
                        'password': se_code # YOUR RULE: SE Pass = SE Emp Code
                    }
                
                bm_email = row.get('BM Mail ID', '').strip().lower()
                if bm_email and bm_email not in unique_bms:
                    unique_bms[bm_email] = {
                        # --- THIS IS THE FIX ---
                        'code': bm_email, # Use the FULL EMAIL as the Employee Code
                        # --- END OF FIX ---
                        'name': row.get('BM', '').strip(),
                        'email': bm_email,
                        'role': 'BM',
                        'so': None,
                        'password': BM_RH_PASSWORD # YOUR RULE: Pass = hfl@1234
                    }
                    
                rh_email = row.get('RH Mail ID', '').strip().lower()
                if rh_email and rh_email not in unique_rhs:
                    unique_rhs[rh_email] = {
                        # --- THIS IS THE FIX ---
                        'code': rh_email, # Use the FULL EMAIL as the Employee Code
                        # --- END OF FIX ---
                        'name': row.get('RH', '').strip(),
                        'email': rh_email,
                        'role': 'RH',
                        'so': None,
                        'password': BM_RH_PASSWORD # YOUR RULE: Pass = hfl@1234
                    }

            user_map_by_email = {}
            user_map_by_emp_code = {}
            all_users_to_create = []

            admin_user = User(
                employee_code='ADMIN01',
                name='Admin User',
                email='admin@example.com',
                role='Admin'
            )
            admin_user.set_password(ADMIN_PASSWORD)
            all_users_to_create.append(admin_user)
            
            # Process SEs
            for code, data in unique_ses.items():
                if code in user_map_by_emp_code: continue
                user = User(
                    employee_code=code,
                    name=data['name'],
                    email=data['email'],
                    role=data['role'],
                    so=data['so']
                )
                user.set_password(data['password'])
                all_users_to_create.append(user)
                user_map_by_emp_code[code] = user

            # Process BMs
            for email, data in unique_bms.items():
                if email in user_map_by_email: continue
                emp_code = data['code'] # This is now the full email
                if emp_code in user_map_by_emp_code: 
                    emp_code = f"{emp_code}_bm"
                    
                user = User(
                    employee_code=emp_code,
                    name=data['name'],
                    email=data['email'],
                    role=data['role']
                )
                user.set_password(data['password'])
                all_users_to_create.append(user)
                user_map_by_email[email] = user
                user_map_by_emp_code[emp_code] = user
                
            # Process RHs
            for email, data in unique_rhs.items():
                if email in user_map_by_email: continue
                emp_code = data['code'] # This is now the full email
                if emp_code in user_map_by_emp_code: 
                    emp_code = f"{emp_code}_rh"
                    
                user = User(
                    employee_code=emp_code,
                    name=data['name'],
                    email=data['email'],
                    role=data['role']
                )
                user.set_password(data['password'])
                all_users_to_create.append(user)
                user_map_by_email[email] = user
                user_map_by_emp_code[emp_code] = user

            db.session.add_all(all_users_to_create)
            db.session.commit()
            print(f"Successfully created {len(all_users_to_create)} unique users (Admin, SE, BM, RH).")

        except Exception as e:
            db.session.rollback()
            print(f"--- ERROR Creating Users ---")
            print(f"An error occurred: {e}")
            import traceback
            traceback.print_exc()
            return
            
        # --- STAGE 3: Create Distributors and DB Users ---
        print("Creating and linking distributors...")
        try:
            distributors_to_create = {}
            db_users_to_create = []
            
            # --- FIX: Track names we have already added ---
            unique_dist_names = set()

            for row in rows:
                dist_code = row.get('Distributor Code', '').strip()
                dist_name = row.get('Distributor Name', 'N/A').strip()
                
                if not dist_code or dist_code == 'None' or dist_code in distributors_to_create:
                    continue 
                
                # --- FIX: Check if we've already added this name ---
                if dist_name in unique_dist_names:
                    print(f"  [WARN] Distributor name '{dist_name}' (Code: {dist_code}) already exists. Skipping duplicate name.")
                    continue # Skip this duplicate name
                
                se_code = row.get('SE Emp Code', '').strip()
                if (se_code == '0' or not se_code or se_code == 'None'):
                    se_code = "vacant_" + re.sub(r'[^a-zA-Z0-9]', '_', row.get('SE Name', '')).lower()
                
                se_user = user_map_by_emp_code.get(se_code)
                bm_user = user_map_by_email.get(row.get('BM Mail ID', '').strip().lower())
                rh_user = user_map_by_email.get(row.get('RH Mail ID', '').strip().lower())

                dist = Distributor(
                    code=dist_code,
                    name=dist_name,
                    city=row.get('Distributor Town', '').strip(),
                    state=None,
                    se_id=se_user.id if se_user else None,
                    bm_id=bm_user.id if bm_user else None,
                    rh_id=rh_user.id if rh_user else None
                )
                distributors_to_create[dist_code] = dist
                unique_dist_names.add(dist_name) # Add the name to our tracker
                db.session.add(dist)

            db.session.commit()
            print(f"Successfully created {len(distributors_to_create)} distributors.")
            
            print("Creating Distributor (DB) user accounts...")
            for dist_code, dist_obj in distributors_to_create.items():
                if dist_code in user_map_by_emp_code:
                    print(f"  [WARN] User with code '{dist_code}' already exists (likely an SE). Skipping DB user creation.")
                    continue

                db_user = User(
                    employee_code=dist_code, # YOUR RULE: DB Login = Dist Code
                    name=f"{dist_obj.name} (DB)",
                    role='DB',
                    email=None,
                    distributor_id=dist_obj.id
                )
                db_user.set_password(dist_code) # YOUR RULE: DB Pass = Dist Code
                db_users_to_create.append(db_user)
                user_map_by_emp_code[dist_code] = db_user
            
            db.session.add_all(db_users_to_create)
            db.session.commit()
            print(f"Successfully created {len(db_users_to_create)} Distributor (DB) user accounts.")
            
            print("\n" + "="*60)
            print("DATABASE SEEDED SUCCESSFULLY WITH REAL DATA!")
            print("="*60)
            print("\n--- LOGIN CREDENTIALS ---")
            print("\nADMIN:")
            print(f"  User: ADMIN01 / Pass: {ADMIN_PASSWORD}")
            
            print("\nBRANCH MANAGERS (BMs):")
            print(f"  (Employee Code is their FULL EMAIL) / Pass: {BM_RH_PASSWORD}")
            for email, data in unique_bms.items(): 
                print(f"  - {data['code']}  ({data['name']})")

            print("\nREGIONAL HEADS (RHs):")
            print(f"  (Employee Code is their FULL EMAIL) / Pass: {BM_RH_PASSWORD}")
            for email, data in unique_rhs.items(): 
                print(f"  - {data['code']}  ({data['name']})")

            print("\nSALES EXECUTIVES (SEs):")
            print("  (Employee Code is Password)")
            for code, data in unique_ses.items(): 
                print(f"  - {code} ({data['name']})")

            print("\nDISTRIBUTORS (DBs):")
            print("  (Distributor Code is Employee Code AND Password)")
            for code, data in distributors_to_create.items(): 
                if code not in unique_ses:
                    print(f"  - {code} ({data.name})")
            
            print("="*60)

        except Exception as e:
            db.session.rollback()
            print(f"--- ERROR Creating Distributors or DB Users ---")
            print(f"An error occurred: {e}")
            import traceback
            traceback.print_exc()

if __name__ == '__main__':
    setup_database()