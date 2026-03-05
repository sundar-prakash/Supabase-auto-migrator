# 🚀 Supabase Auto Migrator

**A complete, interactive migration tool for Supabase projects.** Moving between Supabase accounts is notoriously tricky because of internal schemas, storage folder recursion, and Auth triggers. This Python tool automates the heavy lifting: it surgically exports your public data, injects your users safely, and recursively moves every single file in your Storage buckets—even those nested deep in subfolders.

## ✨ Key Features

* **Interactive CLI Menu:** Choose your migration path and safety options via an easy-to-use terminal interface before execution begins.
* **Two Migration Modes:**
* **Full Clone:** Migrates your schema, all table data, Auth users, and recursively downloads/uploads every physical storage file.
* **Template Clone:** Migrates ONLY your schema, functions, triggers, RLS policies, and empty storage bucket definitions. Perfect for spinning up fresh instances based on an existing architecture.


* **Automatic Safety Backups:** Before running any destructive commands, the script automatically generates full `.sql` backups of *both* your old and new databases and saves them in a local, timestamped `backups/` folder.
* **Target Database Cleaning:** Optionally auto-wipe the target (NEW) database's data, users, and files before importing to prevent unique constraint conflicts and guarantee a clean slate.
* **Source Database Decommissioning:** Optionally securely wipe the source (OLD) database only after the migration has fully succeeded.
* **Silent Auth Migration:** Transfers `auth.users` and `auth.identities` while temporarily disabling database triggers to prevent accidental "Welcome" emails to your users.
* **Recursive Storage Sync:** Crawls through your old storage buckets and uploads every file to the new project, maintaining exact nested folder structures.

---

## 📋 Prerequisites

Before running the script, ensure you have the following installed:

1. **Python 3.8+**
2. **PostgreSQL Client Tools:** You must have `pg_dump` and `psql` installed on your machine.
* *Mac:* `brew install postgresql`
* *Ubuntu:* `sudo apt-get install postgresql-client`


3. **Supabase Python Client:**
```bash
pip install supabase

```



---

## ⚙️ Setup & Configuration

### 1. Project Preparation

In your **NEW** Supabase project, go to the Dashboard and enable any extensions you used in the old project (e.g., `uuid-ossp`, `pgcrypto`, `postgis`).

### 2. Get Your Credentials

You will need four pieces of information for **both** the Old and New projects:

| Credential | Where to find in Supabase Dashboard |
| --- | --- |
| **Database URL** | Settings > Database > Connection String > URI |
| **API URL** | Settings > API > Project URL |
| **Service Role Key** | Settings > API > `service_role` (secret) |

### 3. Update the Script

Open the Python script and fill in the `CONFIGURATION` section at the top:

```python
# Database connection strings
OLD_DB_URL = "postgresql://postgres:[PASS]@old-host:5432/postgres"
NEW_DB_URL = "postgresql://postgres:[PASS]@new-host:5432/postgres"

# Supabase API credentials
OLD_API_URL = "https://your-old-project.supabase.co"
OLD_SERVICE_ROLE_KEY = "your-old-service-role-key"

NEW_API_URL = "https://your-new-project.supabase.co"
NEW_SERVICE_ROLE_KEY = "your-new-service-role-key"

```

---

## 🚀 Running the Migration

Run the script from your terminal:

```bash
python3 supabase-migrate.py

```

### The Execution Flow:

1. **Prompts:** The script will ask you to select a migration mode (Full vs. Template) and whether you want to clean the New and/or Old databases.
2. **Backups:** Automatically creates a timestamped folder (e.g., `backups/your-project_20260305_123000`) containing full raw dumps of both databases.
3. **Clean (Optional):** Dynamically truncates tables, auth users, and storage objects on the target database if requested.
4. **Export:** Generates temporary SQL files for your Public schema, Auth users, and Storage metadata based on your selected mode.
5. **Import:** Injects the schema and records using `session_replication_role = replica` to temporarily bypass foreign key constraints and triggers.
6. **Sync Files:** Uses the Supabase API to recursively migrate physical storage objects (if Full Clone mode is selected).
7. **Restore:** Automatically reapplies correct RLS and usage permissions to the `public` schema.
8. **Cleanup:** Removes temporary dump files and (optionally) wipes the old database.

---

## 🛠 Troubleshooting

* **Permission Denied for Schema Public:** The script attempts to restore permissions automatically, but if your API fails after migration, run this in your New Supabase SQL Editor:
```sql
GRANT USAGE ON SCHEMA public TO anon, authenticated, service_role;
GRANT ALL ON ALL TABLES IN SCHEMA public TO anon, authenticated, service_role;
GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO anon, authenticated, service_role;

```


* **Relation Does Not Exist:** This often happens during the `--clean` phase of `psql` and is harmless if the tables are created successfully afterward.
* **Timeouts:** If you have massive storage buckets, the physical file migration may take a while. Ensure your machine doesn't go to sleep during the process.

---

## 📜 License

Distributed under the MIT License. See `LICENSE` for more information.

## 👤 Author

**Sundar Prakash**

* GitHub: [@sundar-prakash](https://github.com/sundar-prakash)
