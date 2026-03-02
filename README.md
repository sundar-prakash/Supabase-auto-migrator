# 🚀 Supabase Auto Migrator

A complete, automated Python tool to seamlessly migrate your entire Supabase project from one account/environment to another. 

Instead of manually fighting with `pg_dump` conflicts or manually downloading S3 folders, this script handles it all in one go. It safely migrates your custom Database schema, your `auth` users (without triggering welcome emails!), and recursively downloads/uploads your `storage` files—even if they are nested deep inside folders.

## ✨ Features

* **Smart Database Dump:** Only grabs your `public` schema so you don't overwrite Supabase's internal tables.
* **Silent Auth Migration:** Moves your `auth.users` and `auth.identities` over while temporarily disabling triggers (prevents accidentally spamming your users with emails).
* **Storage Metadata:** Copies your `storage.buckets` and `storage.objects` database records.
* **Recursive File Transfer:** Automatically navigates through folders and subfolders in your Storage Buckets to physically download and upload every single file to the new project.

## 📋 Prerequisites

1. **Python 3.x**
2. **PostgreSQL CLI Tools:** You must have `pg_dump` and `psql` installed and accessible in your system's PATH.
3. **Supabase Python Client:** ```bash
   pip install supabase
