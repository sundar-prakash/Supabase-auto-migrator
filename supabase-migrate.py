import os
import subprocess
from supabase import create_client, Client
from supabase import ClientOptions

# ==========================================
# 1. CONFIGURATION
# ==========================================
# Database connection strings (replace with your exact credentials)
OLD_DB_URL = "transaction pooler"
NEW_DB_URL = "transaction pooler"

# Supabase API credentials (Needed for physical file transfer)
OLD_API_URL = "https://[projectid].supabase.co"
OLD_SERVICE_ROLE_KEY = "-"

NEW_API_URL = "https://[projectid].supabase.co"
NEW_SERVICE_ROLE_KEY = "-"


# ==========================================
# 2. SQL SCRIPTS
# ==========================================
PERMISSIONS_SQL = """
GRANT USAGE ON SCHEMA public TO postgres, anon, authenticated, service_role;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO postgres, service_role, anon, authenticated;
GRANT ALL PRIVILEGES ON ALL FUNCTIONS IN SCHEMA public TO postgres, service_role, anon, authenticated;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO postgres, service_role, anon, authenticated;

ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO postgres, anon, authenticated, service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON FUNCTIONS TO postgres, anon, authenticated, service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO postgres, anon, authenticated, service_role;
"""

CLEAN_DATA_SQL = """
-- Truncate all tables in the public schema dynamically
DO $$ DECLARE
    r RECORD;
BEGIN
    FOR r IN (SELECT tablename FROM pg_tables WHERE schemaname = 'public') LOOP
        EXECUTE 'TRUNCATE TABLE public.' || quote_ident(r.tablename) || ' CASCADE';
    END LOOP;
END $$;

-- Truncate Auth and Storage data to ensure a completely fresh state
TRUNCATE TABLE auth.users CASCADE;
TRUNCATE TABLE storage.buckets CASCADE;
TRUNCATE TABLE storage.objects CASCADE;
"""
# ==========================================
# 3. HELPER FUNCTIONS
# ==========================================
def run_command(command_list):
    command_str = " ".join(command_list)
    print(f"\n---> Running: {command_str[:80]}...") 
    result = subprocess.run(command_str, shell=True, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"❌ Error: {result.stderr}")
        exit(1)
    else:
        print("✅ Success")

def clean_database(db_url, db_name):
    print(f"\n--- 🧹 CLEANING DATA ON {db_name.upper()} DATABASE ---")
    with open("clean_db.sql", "w") as f:
        f.write(CLEAN_DATA_SQL)
    run_command(["psql", f'"{db_url}"', "-f clean_db.sql"])
    os.remove("clean_db.sql")
    print(f"✅ {db_name} database wiped clean successfully!")

def restore_permissions(db_url):
    print("\n--- 🔒 RESTORING PERMISSIONS ---")
    with open("restore_permissions.sql", "w") as f:
        f.write(PERMISSIONS_SQL)
    run_command(["psql", f'"{db_url}"', "-f restore_permissions.sql"])
    os.remove("restore_permissions.sql")
    print("✅ Permissions restored successfully!")

# ==========================================
# 4. PRE-MIGRATION BACKUPS
# ==========================================
def backup_databases():
    print("\n--- 🛡️ CREATING SAFETY BACKUPS ---")
    
    # Extract project name from URL (e.g., db.brainboosterz.com)
    project_slug = re.sub(r'^https?://', '', OLD_API_URL).split('/')[0]
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = f"backups/{project_slug}_{timestamp}"
    
    os.makedirs(backup_dir, exist_ok=True)
    print(f"📁 Created backup folder: {backup_dir}")
    
    print("⏳ Backing up OLD database...")
    run_command([
        "pg_dump", f'"{OLD_DB_URL}"',
        "--clean", "--if-exists",
        f"-f {backup_dir}/old_db_full_backup.sql"
    ])
    
    print("⏳ Backing up NEW database...")
    run_command([
        "pg_dump", f'"{NEW_DB_URL}"',
        "--clean", "--if-exists",
        f"-f {backup_dir}/new_db_full_backup.sql"
    ])
    print(f"✅ Safety backups saved securely in ./{backup_dir}/")

# ==========================================
# 5. DATABASE EXPORT & IMPORT
# ==========================================
def export_database(schema_only=False):
    print("\n--- 📤 STARTING DATABASE EXPORT ---")
    if schema_only:
        print("--> Mode: SCHEMA ONLY (Skipping table data...)")
        run_command([
            "pg_dump", f'"{OLD_DB_URL}"',
            "--schema=public", "--schema-only", "--no-owner", "--no-privileges", "--clean", "--if-exists",
            "-f my_database_dump.sql"
        ])
    else:
        print("--> Mode: FULL BACKUP (Schema + Data...)")
        run_command([
            "pg_dump", f'"{OLD_DB_URL}"',
            "--schema=public", "--no-owner", "--no-privileges", "--clean", "--if-exists",
            "-f my_database_dump.sql"
        ])
        run_command([
            "pg_dump", f'"{OLD_DB_URL}"',
            "--data-only", "--table=auth.users", "--table=auth.identities", "--column-inserts",
            "-f auth_data.sql"
        ])
        
    print("--> Exporting Storage Bucket Definitions...")
    run_command([
        "pg_dump", f'"{OLD_DB_URL}"',
        "--data-only", "--table=storage.buckets", "--column-inserts",
        "-f storage_metadata.sql"
    ])

def import_full_database():
    print("\n--- 📥 STARTING FULL DATABASE IMPORT ---")
    run_command(["psql", f'"{NEW_DB_URL}"', "-f my_database_dump.sql"])
    run_command(["psql", f'"{NEW_DB_URL}"', '-c "SET session_replication_role = replica;"', "-f auth_data.sql"])
    run_command(["psql", f'"{NEW_DB_URL}"', '-c "SET session_replication_role = replica;"', "-f storage_metadata.sql"])
    restore_permissions(NEW_DB_URL)

def import_schema_only():
    print("\n--- 📥 STARTING TEMPLATE IMPORT (Schema Only) ---")
    run_command(["psql", f'"{NEW_DB_URL}"', "-f my_database_dump.sql"])
    
    print("\n--- 🪣 CREATING STORAGE BUCKETS ---")
    run_command(["psql", f'"{NEW_DB_URL}"', '-c "SET session_replication_role = replica;"', "-f storage_metadata.sql"])
    
    restore_permissions(NEW_DB_URL)

# ==========================================
# 6. PHYSICAL STORAGE MIGRATION
# ==========================================
def migrate_storage_files():
    print("\n--- 📦 STARTING PHYSICAL FILE MIGRATION ---")
    if OLD_API_URL.startswith("postgresql://") or NEW_API_URL.startswith("postgresql://"):
        print("❌ CRITICAL ERROR: API URLs are formatted as database connections.")
        return
        
    custom_options = ClientOptions(postgrest_client_timeout=60, storage_client_timeout=60)
    old_supabase: Client = create_client(OLD_API_URL, OLD_SERVICE_ROLE_KEY, options=custom_options)
    new_supabase: Client = create_client(NEW_API_URL, NEW_SERVICE_ROLE_KEY, options=custom_options)

    def process_directory(bucket_name, current_path=""):
        try:
            items = old_supabase.storage.from_(bucket_name).list(current_path)
        except Exception as e:
            print(f"❌ Failed to list path '{current_path}': {e}")
            return

        for item in items:
            item_name = item['name']
            if item_name == '.emptyFolderPlaceholder':
                continue
                
            full_path = f"{current_path}/{item_name}" if current_path else item_name
            is_folder = item.get('id') is None
            
            if is_folder:
                print(f"\n📁 Entering folder: {full_path}")
                process_directory(bucket_name, full_path)
            else:
                print(f"  Downloading: {full_path}")
                try:
                    file_data = old_supabase.storage.from_(bucket_name).download(full_path)
                    print(f"  Uploading: {full_path}")
                    
                    response = new_supabase.storage.from_(bucket_name).upload(
                        path=full_path, 
                        file=file_data, 
                        file_options={"upsert": "true", "content-type": item.get('metadata', {}).get('mimetype', 'application/octet-stream')}
                    )
                    
                    if isinstance(response, dict) and response.get('error'):
                        print(f"❌ API Error: {response.get('error')}")
                    else:
                        print("  ✅ Upload successful!")

                except Exception as e:
                    print(f"❌ Exception with file {full_path}: {e}")

    print("Fetching list of all buckets...")
    try:
        buckets = old_supabase.storage.list_buckets()
    except Exception as e:
        print(f"❌ Failed to fetch buckets: {e}")
        return

    if not buckets:
        print("No buckets found.")
        return

    for bucket in buckets:
        print(f"\n==========================================")
        print(f"Processing bucket: {bucket.name}")
        print(f"==========================================")
        process_directory(bucket.name, "")

# ==========================================
# 7. EXECUTION MENU
# ==========================================
if __name__ == "__main__":
    print("==========================================")
    print(" SUPABASE MIGRATION SCRIPT (SAFE MODE)")
    print("==========================================\n")
    
    # Question 1: Mode
    print("❓ Choose your migration mode:")
    print("   1. Full Clone (Migrate Schema, All Data, Auth, and Storage Files)")
    print("   2. Template Clone (Migrate ONLY Schema, Functions, RLS, and Empty Buckets)")
    mode_choice = input("   Enter 1 or 2: ").strip()
    schema_only_mode = (mode_choice == '2')

    # Question 2: Clean New (Default: Yes)
    print("\n❓ Do you want to clean the NEW database before importing?")
    print("   (This deletes all existing data, auth users, and files on the target DB to prevent conflicts)")
    clean_new_input = input("   [Y/n](default Yes): ").strip().lower()
    clean_new_choice = clean_new_input in ['', 'y', 'yes'] # Empty string means they just pressed Enter
    
    # Question 3: Clean Old (Default: No)
    print("\n❓ Do you want to clean the OLD database after migration finishes?")
    print("   (This securely wipes your old data once everything is finished)")
    clean_old_input = input("   [y/N](default No): ").strip().lower()
    clean_old_choice = clean_old_input in ['y', 'yes'] # Empty string defaults to False
    
    print("\n🚀 Starting execution sequence...\n")
    
    # Step 1: Pre-Migration Backup of BOTH databases
    backup_databases()
    
    # Step 2: Export from Old
    export_database(schema_only=schema_only_mode)
    
    # Step 3: Clean target if requested
    if clean_new_choice:
        clean_database(NEW_DB_URL, "NEW")
        
    # Step 4: Import and migrate based on mode
    if schema_only_mode:
        import_schema_only()
    else:
        import_full_database()
        migrate_storage_files()
        
    # Step 5: Clean old DB if requested
    if clean_old_choice:
        print("\n⚠️  WARNING: You are about to wipe the OLD database.")
        confirm = input("Are you absolutely sure? (y/n): ").strip().lower() == 'y'
        if confirm:
            clean_database(OLD_DB_URL, "OLD")
        else:
            print("Skipping old database cleanup.")
            
    # Cleanup leftover local temporary SQL dump files (leaves the /backups/ folder untouched!)
    for file in ["my_database_dump.sql", "auth_data.sql", "storage_metadata.sql"]:
        if os.path.exists(file):
            os.remove(file)
            
    print("\n🎉 Migration sequence complete! Your original states are saved in the 'backups' folder.")
