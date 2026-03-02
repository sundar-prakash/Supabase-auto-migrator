# 🚀 Supabase Auto Migrator

**A complete, one-click migration tool for Supabase projects.** Moving between Supabase accounts is notoriously tricky because of internal schemas, storage folder recursion, and Auth triggers. This Python tool automates the heavy lifting: it surgically exports your public data, injects your users safely, and recursively moves every single file in your Storage buckets—even those nested deep in subfolders.

## ✨ Key Features

* **Database Schema & Data:** Surgically extracts the `public` schema while ignoring Supabase internal system tables.
* **Silent Auth Migration:** Transfers `auth.users` and `auth.identities` while temporarily disabling database triggers to prevent accidental "Welcome" emails to your users.
* **Storage Metadata:** Syncs your bucket definitions and file object records.
* **Recursive Storage Sync:** Downloads and uploads physical files from old buckets to new ones, automatically handling nested folder structures.
* **Safety First:** Uses `replica` session roles during import to bypass foreign key constraints and triggers during the data population phase.

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
| **Transaction Pooler URL** | Settings > Database > Connection String > URI (Ensure it's the **Transaction** mode, port 6543 or 5432) |
| **API URL** | Settings > API > Project URL |
| **Service Role Key** | Settings > API > `service_role` (secret) |

### 3. Update the Script

Open `supabase-migrate.py` and fill in the `CONFIGURATION` section:

```python
# Database connection strings
OLD_DB_URL = "postgresql://postgres.[REF]:[PASS]@aws-0-[REG].pooler.supabase.com:6543/postgres"
NEW_DB_URL = "postgresql://postgres.[REF]:[PASS]@aws-0-[REG].pooler.supabase.com:6543/postgres"

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

### What the script does:

1. **Exports** three SQL files: `my_database_dump.sql` (Public schema), `auth_data.sql` (Users), and `storage_metadata.sql` (Buckets).
2. **Imports** the public schema into the new project.
3. **Imports** Auth and Storage records using `session_replication_role = replica` to ensure a smooth data injection.
4. **Syncs Files:** Recursively crawls through your old storage buckets and uploads every file to the new project.

---

## 🛠 Troubleshooting

* **Permission Denied for Schema Public:** After migration, if your API fails, run this in the Supabase SQL Editor:
```sql
GRANT USAGE ON SCHEMA public TO anon, authenticated, service_role;
GRANT ALL ON ALL TABLES IN SCHEMA public TO anon, authenticated, service_role;
GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO anon, authenticated, service_role;

```


* **Relation Does Not Exist:** This often happens during the `--clean` phase of `psql` and is usually harmless if the tables are created successfully afterward.
* **Timeouts:** If you have massive storage buckets, the script may take a while. Ensure your machine doesn't go to sleep during the process.

---

## 📜 License

Distributed under the MIT License. See `LICENSE` for more information.

## 👤 Author

**Sundar Prakash**

* GitHub: [@sundar-prakash](https://github.com/sundar-prakash)
