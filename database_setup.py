import os
from app import app, db
from models import User, Distributor, AssetRequest

def setup_database():
    """
    Seeds the database with initial data.
    Run AFTER 'flask db upgrade'.
    """
    with app.app_context():
        
        # Check if tables exist
        if not db.inspect(db.engine).has_table('user'):
            print("ERROR: Tables not found. Please run 'flask db upgrade' first.")
            return

        try:
            # Delete existing data (in correct order due to foreign keys)
            print("Clearing existing data...")
            db.session.query(AssetRequest).delete()
            db.session.query(User).delete()
            db.session.query(Distributor).delete()
            db.session.commit()
            print("Existing data cleared.")
        except Exception as e:
            db.session.rollback()
            print(f"ERROR clearing data: {e}")
            return

        print("Seeding database with initial data...")
        try:
            # --- Create Users ---
            users_to_add = []
            
            # Sales Executives
            se1 = User(
                employee_code='SE001', 
                name='Rajesh Kumar', 
                role='SE', 
                so='SO-North', 
                email='se001@example.com'
            )
            se1.set_password('pass123')
            users_to_add.append(se1)
            
            se2 = User(
                employee_code='SE002',  # FIXED: Was 'S'
                name='Priya Singh', 
                role='SE', 
                so='SO-West', 
                email='se002@example.com'
            )
            se2.set_password('pass123')
            users_to_add.append(se2)
            
            se3 = User(
                employee_code='SE003', 
                name='Vikram Rao', 
                role='SE', 
                so='SO-South', 
                email='se003@example.com'
            )
            se3.set_password('pass123')
            users_to_add.append(se3)

            # Branch Managers
            bm1 = User(
                employee_code='BM001', 
                name='Amit Sharma', 
                role='BM', 
                email='bm001@example.com'
            )
            bm1.set_password('pass123')
            users_to_add.append(bm1)
            
            bm2 = User(
                employee_code='BM002', 
                name='Deepa Iyengar', 
                role='BM', 
                email='bm002@example.com'
            )
            bm2.set_password('pass123')
            users_to_add.append(bm2)

            # Regional Head
            rh1 = User(
                employee_code='RH001', 
                name='Sunita Mehta', 
                role='RH', 
                email='rh001@example.com'
            )
            rh1.set_password('pass123')
            users_to_add.append(rh1)

            # Admin
            admin = User(
                employee_code='ADMIN01', 
                name='Admin User', 
                role='Admin', 
                email='admin@example.com'
            )
            admin.set_password('adminpass')
            users_to_add.append(admin)

            # Add all users
            for user in users_to_add:
                db.session.add(user)

            # --- Create Distributors ---
            distributors_to_add = [
                Distributor(
                    code='D001', 
                    name='Capital Distributors', 
                    city='Delhi', 
                    state='Delhi',
                    asm_bm_name='Amit Sharma', 
                    bm_email='bm001@example.com',
                    rh_name='Sunita Mehta', 
                    rh_email='rh001@example.com'
                ),
                Distributor(
                    code='D002', 
                    name='Mumbai Traders', 
                    city='Mumbai', 
                    state='Maharashtra',
                    asm_bm_name='Amit Sharma', 
                    bm_email='bm001@example.com',
                    rh_name='Sunita Mehta', 
                    rh_email='rh001@example.com'
                ),
                Distributor(
                    code='D003', 
                    name='Bangalore Supplies', 
                    city='Bangalore', 
                    state='Karnataka',
                    asm_bm_name='Deepa Iyengar', 
                    bm_email='bm002@example.com',
                    rh_name='Sunita Mehta', 
                    rh_email='rh001@example.com'
                ),
                Distributor(
                    code='D004', 
                    name='Kolkata Enterprises', 
                    city='Kolkata', 
                    state='West Bengal',
                    asm_bm_name='Amit Sharma', 
                    bm_email='bm001@example.com',
                    rh_name='Sunita Mehta', 
                    rh_email='rh001@example.com'
                ),
                Distributor(
                    code='D005', 
                    name='Chennai Logistics', 
                    city='Chennai', 
                    state='Tamil Nadu',
                    asm_bm_name='Deepa Iyengar', 
                    bm_email='bm002@example.com',
                    rh_name='Sunita Mehta', 
                    rh_email='rh001@example.com'
                )
            ]
            
            for distributor in distributors_to_add:
                db.session.add(distributor)

            # Commit all changes
            db.session.commit()
            
            print("="*60)
            print("DATABASE SEEDED SUCCESSFULLY!")
            print("="*60)
            print("\nSample Login Credentials:")
            print("-" * 60)
            print("ADMIN:")
            print("  Employee Code: ADMIN01")
            print("  Password: adminpass")
            print("\nSALES EXECUTIVES (Password: pass123):")
            print("  SE001 - Rajesh Kumar")
            print("  SE002 - Priya Singh")
            print("  SE003 - Vikram Rao")
            print("\nBRANCH MANAGERS (Password: pass123):")
            print("  BM001 - Amit Sharma")
            print("  BM002 - Deepa Iyengar")
            print("\nREGIONAL HEAD (Password: pass123):")
            print("  RH001 - Sunita Mehta")
            print("="*60)

        except Exception as e:
            db.session.rollback()
            print(f"ERROR during seeding: {e}")
            import traceback
            traceback.print_exc()

if __name__ == '__main__':
    setup_database()