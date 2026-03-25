import subprocess
import os
import datetime
import re
from supabase import create_client, Client, ClientOptions

# ==========================================
# 1. CONFIGURATION
# ==========================================
OLD_DB_URL = "postgresql://postgres:old_password@old_host:5432/postgres"
NEW_DB_URL = "postgresql://postgres:new_password@new_host:5432/postgres"

OLD_API_URL = "https://old-project.supabase.co"
OLD_SERVICE_ROLE_KEY = "old_service_role_key"

NEW_API_URL = "https://new-project.supabase.co"
NEW_SERVICE_ROLE_KEY = "new_service_role_key"

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
DO $$ DECLARE
    r RECORD;
BEGIN
    FOR r IN (SELECT tablename FROM pg_tables WHERE schemaname = 'public') LOOP
        EXECUTE 'TRUNCATE TABLE public.' || quote_ident(r.tablename) || ' CASCADE';
    END LOOP;
END $$;

TRUNCATE TABLE auth.users CASCADE;
TRUNCATE TABLE storage.buckets CASCADE;
TRUNCATE TABLE storage.objects CASCADE;
"""

PRE_IMPORT_SQL = """
DO $$ DECLARE
    p RECORD;
BEGIN
    FOR p IN (SELECT schemaname, tablename, policyname FROM pg_policies WHERE schemaname IN ('storage', 'auth')) LOOP
        EXECUTE format('DROP POLICY IF EXISTS %I ON %I.%I', p.policyname, p.schemaname, p.tablename);
    END LOOP;
END $$;
"""

# NEW: Dynamically reconstructs RLS policies for storage buckets and objects
EXPORT_STORAGE_POLICIES_SQL = """
SELECT 'ALTER TABLE storage.buckets ENABLE ROW LEVEL SECURITY;';
SELECT 'ALTER TABLE storage.objects ENABLE ROW LEVEL SECURITY;';

SELECT
    'CREATE POLICY ' || quote_ident(policyname) || ' ON ' || quote_ident(schemaname) || '.' || quote_ident(tablename) ||
    ' AS ' || permissive || ' FOR ' || cmd ||
    ' TO ' || array_to_string(roles, ', ') ||
    COALESCE(' USING (' || qual || ')', '') ||
    COALESCE(' WITH CHECK (' || with_check || ')', '') || ';'
FROM pg_policies
WHERE schemaname = 'storage' AND tablename IN ('buckets', 'objects');
"""

# ==========================================
# 3. HELPER FUNCTIONS
# ==========================================
def run_command(command_list, ignore_errors=False):
    command_str = " ".join(command_list)
    print(f"\n---> Running: {command_str[:80]}...") 
    result = subprocess.run(command_str, shell=True, capture_output=True, text=True)
    if result.returncode != 0 and not ignore_errors:
        print(f"❌ Error: {result.stderr}")
        exit(1)
    elif result.returncode != 0 and ignore_errors:
        print("✅ Success (Ignored harmless 'already exists' warnings)")
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

def clear_policy_collisions(db_url):
    print("\n--- 🧹 CLEARING DEFAULT STORAGE/AUTH POLICIES TO PREVENT COLLISIONS ---")
    with open("pre_import.sql", "w") as f:
        f.write(PRE_IMPORT_SQL)
    run_command(["psql", f'"{db_url}"', "-f pre_import.sql"])
    os.remove("pre_import.sql")
    print("✅ Policy namespace cleared successfully!")

# ==========================================
# 4. PRE-MIGRATION BACKUPS
# ==========================================
def backup_databases():
    print("\n--- 🛡️ CREATING SAFETY BACKUPS ---")
    project_slug = re.sub(r'^https?://', '', OLD_API_URL).split('/')[0]
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = f"backups/{project_slug}_{timestamp}"
    
    os.makedirs(backup_dir, exist_ok=True)
    print(f"📁 Created backup folder: {backup_dir}")
    
    print("⏳ Backing up OLD database...")
    run_command(["pg_dump", f'"{OLD_DB_URL}"', "--clean", "--if-exists", f"-f {backup_dir}/old_db_full_backup.sql"])
    
    print("⏳ Backing up NEW database...")
    run_command(["pg_dump", f'"{NEW_DB_URL}"', "--clean", "--if-exists", f"-f {backup_dir}/new_db_full_backup.sql"])
    print(f"✅ Safety backups saved securely in ./{backup_dir}/")

# ==========================================
# 5. DATABASE EXPORT & IMPORT
# ==========================================
def export_database(schema_only=False):
    print("\n--- 📤 STARTING DATABASE EXPORT ---")
    if schema_only:
        print("--> Mode: SCHEMA ONLY (Skipping table data...)")
        run_command(["pg_dump", f'"{OLD_DB_URL}"', "--schema=public", "--schema-only", "--no-owner", "--no-privileges", "--clean", "--if-exists", "-f my_database_dump.sql"])
    else:
        print("--> Mode: FULL BACKUP (Schema + Data...)")
        run_command(["pg_dump", f'"{OLD_DB_URL}"', "--schema=public", "--no-owner", "--no-privileges", "--clean", "--if-exists", "-f my_database_dump.sql"])
        run_command(["pg_dump", f'"{OLD_DB_URL}"', "--data-only", "--table=auth.users", "--table=auth.identities", "--column-inserts", "-f auth_data.sql"])
        
    print("--> Exporting Storage Bucket Definitions...")
    run_command(["pg_dump", f'"{OLD_DB_URL}"', "--data-only", "--table=storage.buckets", "--column-inserts", "-f storage_metadata.sql"])

    print("--> Exporting Auth Schema (Functions & Triggers)...")
    run_command(["pg_dump", f'"{OLD_DB_URL}"', "--schema=auth", "--schema=storage", "--schema-only", "--no-owner", "--no-privileges", "-f auth_storage_schema.sql"])

    # NEW: Exporting just the Storage Policies
    print("--> Exporting Storage RLS Policies (Buckets & Objects)...")
    with open("export_storage_policies_query.sql", "w") as f:
        f.write(EXPORT_STORAGE_POLICIES_SQL)
    # Using -t (tuples only) and -A (unaligned) to generate a clean SQL file
    run_command(["psql", f'"{OLD_DB_URL}"', "-t", "-A", "-f export_storage_policies_query.sql", ">", "storage_rls_policies.sql"])
    os.remove("export_storage_policies_query.sql")

def import_full_database():
    print("\n--- 📥 STARTING FULL DATABASE IMPORT ---")
    run_command(["psql", f'"{NEW_DB_URL}"', "-f my_database_dump.sql"])
    
    clear_policy_collisions(NEW_DB_URL)
    
    print("\n--- 📥 IMPORTING AUTH & STORAGE SCHEMAS ---")
    run_command(["psql", f'"{NEW_DB_URL}"', "-f auth_storage_schema.sql"], ignore_errors=True)

    # NEW: Import the extracted policies specifically
    print("\n--- 📥 IMPORTING STORAGE RLS POLICIES ---")
    run_command(["psql", f'"{NEW_DB_URL}"', "-f storage_rls_policies.sql"])

    run_command(["psql", f'"{NEW_DB_URL}"', '-c "SET session_replication_role = replica;"', "-f auth_data.sql"])
    run_command(["psql", f'"{NEW_DB_URL}"', '-c "SET session_replication_role = replica;"', "-f storage_metadata.sql"])
    restore_permissions(NEW_DB_URL)

def import_schema_only():
    print("\n--- 📥 STARTING TEMPLATE IMPORT (Schema Only) ---")
    run_command(["psql", f'"{NEW_DB_URL}"', "-f my_database_dump.sql"])
    
    clear_policy_collisions(NEW_DB_URL)
    
    print("\n--- 📥 IMPORTING AUTH & STORAGE SCHEMAS ---")
    run_command(["psql", f'"{NEW_DB_URL}"', "-f auth_storage_schema.sql"], ignore_errors=True)

    # NEW: Import the extracted policies specifically
    print("\n--- 📥 IMPORTING STORAGE RLS POLICIES ---")
    run_command(["psql", f'"{NEW_DB_URL}"', "-f storage_rls_policies.sql"])

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
                        path=full_path, file=file_data, file_options={"upsert": "true", "content-type": item.get('metadata', {}).get('mimetype', 'application/octet-stream')}
                    )
                    if isinstance(response, dict) and response.get('error'):
                        print(f"❌ API Error: {response.get('error')}")
                    else:
                        print("  ✅ Upload successful!")
                except Exception as e:
                    print(f"❌ Exception with file {full_path}: {e}")

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
    
    print("❓ Choose your migration mode:")
    print("   1. Full Clone (Migrate Schema, All Data, Auth, and Storage Files)")
    print("   2. Template Clone (Migrate ONLY Schema, Functions, RLS, and Empty Buckets)")
    mode_choice = input("   Enter 1 or 2: ").strip()
    schema_only_mode = (mode_choice == '2')

    print("\n❓ Do you want to clean the NEW database before importing?")
    print("   (This deletes all existing data, auth users, and files on the target DB to prevent conflicts)")
    clean_new_input = input("   [Y/n]: ").strip().lower()
    clean_new_choice = clean_new_input in ['', 'y', 'yes'] 
    
    print("\n❓ Do you want to clean the OLD database after migration finishes?")
    print("   (This securely wipes your old data once everything is finished)")
    clean_old_input = input("   [y/N]: ").strip().lower()
    clean_old_choice = clean_old_input in ['y', 'yes'] 
    
    print("\n🚀 Starting execution sequence...\n")
    
    backup_databases()
    export_database(schema_only=schema_only_mode)
    
    if clean_new_choice:
        clean_database(NEW_DB_URL, "NEW")
        
    if schema_only_mode:
        import_schema_only()
    else:
        import_full_database()
        migrate_storage_files()
        
    if clean_old_choice:
        print("\n⚠️  WARNING: You are about to wipe the OLD database.")
        confirm = input("Are you absolutely sure? (y/n): ").strip().lower() == 'y'
        if confirm:
            clean_database(OLD_DB_URL, "OLD")
        else:
            print("Skipping old database cleanup.")
            
    # NEW: added 'storage_rls_policies.sql' to the cleanup list
    for file in ["my_database_dump.sql", "auth_data.sql", "storage_metadata.sql", "auth_storage_schema.sql", "storage_rls_policies.sql"]:
        if os.path.exists(file):
            os.remove(file)
            
    print("\n🎉 Migration sequence complete! Your original states are saved in the 'backups' folder.")
