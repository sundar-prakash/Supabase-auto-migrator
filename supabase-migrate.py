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
# 2. DATABASE MIGRATION (pg_dump & psql)
# ==========================================
def run_command(command_list):
    """Executes a shell command and streams the output."""
    command_str = " ".join(command_list)
    print(f"\n---> Running: {command_str[:80]}...") 
    
    result = subprocess.run(command_str, shell=True, capture_output=True, text=True)
    
    if result.returncode != 0:
        print(f"❌ Error: {result.stderr}")
        exit(1)
    else:
        print("✅ Success")

def migrate_database():
    print("\n--- STARTING DATABASE EXPORT ---")
    
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

    run_command([
        "pg_dump", f'"{OLD_DB_URL}"',
        "--data-only", "--table=storage.buckets", "--table=storage.objects", "--column-inserts",
        "-f storage_metadata.sql"
    ])

    print("\n--- STARTING DATABASE IMPORT ---")
    
    run_command(["psql", f'"{NEW_DB_URL}"', "-f my_database_dump.sql"])

    run_command([
        "psql", f'"{NEW_DB_URL}"',
        '-c "SET session_replication_role = replica;"',
        "-f auth_data.sql"
    ])

    run_command([
        "psql", f'"{NEW_DB_URL}"',
        '-c "SET session_replication_role = replica;"',
        "-f storage_metadata.sql"
    ])

# ==========================================
# 3. PHYSICAL STORAGE MIGRATION
# ==========================================
def migrate_storage_files():
    print("\n--- STARTING PHYSICAL FILE MIGRATION ---")
    
    if OLD_API_URL.startswith("postgresql://") or NEW_API_URL.startswith("postgresql://"):
        print("❌ CRITICAL ERROR: API URLs are formatted as database connections.")
        return
        
    custom_options = ClientOptions(postgrest_client_timeout=60, storage_client_timeout=60)
    old_supabase: Client = create_client(OLD_API_URL, OLD_SERVICE_ROLE_KEY, options=custom_options)
    new_supabase: Client = create_client(NEW_API_URL, NEW_SERVICE_ROLE_KEY, options=custom_options)

    # Recursive helper function to handle folders
    def process_directory(bucket_name, current_path=""):
        try:
            # list() takes a path to look inside specific folders
            items = old_supabase.storage.from_(bucket_name).list(current_path)
        except Exception as e:
            print(f"❌ Failed to list path '{current_path}': {e}")
            return

        for item in items:
            item_name = item['name']
            
            if item_name == '.emptyFolderPlaceholder':
                continue
                
            # Build the full path (e.g., "blog-images/my-photo.jpg")
            full_path = f"{current_path}/{item_name}" if current_path else item_name
            
            # In Supabase, folders don't have IDs. Files do.
            is_folder = item.get('id') is None
            
            if is_folder:
                print(f"\n📁 Entering folder: {full_path}")
                process_directory(bucket_name, full_path) # Recursively call itself!
            else:
                print(f"  Downloading: {full_path}")
                try:
                    file_data = old_supabase.storage.from_(bucket_name).download(full_path)
                    print(f"  Uploading: {full_path}")
                    new_supabase.storage.from_(bucket_name).upload(
                        file=file_data, 
                        path=full_path, 
                        file_options={"upsert": "true", "content-type": item.get('metadata', {}).get('mimetype', 'application/octet-stream')}
                    )
                except Exception as e:
                    print(f"❌ Error with file {full_path}: {e}")

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
        bucket_name = bucket.name
        print(f"\n==========================================")
        print(f"Processing bucket: {bucket_name}")
        print(f"==========================================")
        # Start processing from the root of the bucket
        process_directory(bucket_name, "")

# ==========================================
# EXECUTION
# ==========================================
if __name__ == "__main__":
    migrate_database()
    migrate_storage_files()
    print("\n🎉 Full migration complete!")
