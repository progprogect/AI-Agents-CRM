#!/usr/bin/env python3
"""Initialize PostgreSQL database schema. Run with DATABASE_URL or DATABASE_PUBLIC_URL."""

import asyncio
import os
import sys

# Add parent to path for app imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _ensure_sslmode(url: str) -> str:
    """Railway PostgreSQL requires SSL. Add sslmode if not present."""
    if "sslmode=" in url:
        return url
    sep = "&" if "?" in url else "?"
    return url + f"{sep}sslmode=require"


async def main() -> None:
    database_url = os.environ.get("DATABASE_URL") or os.environ.get("DATABASE_PUBLIC_URL")
    if not database_url:
        print("Error: DATABASE_URL or DATABASE_PUBLIC_URL must be set")
        print("Railway: Variables -> Add Reference -> select Postgres DATABASE_URL")
        sys.exit(1)
    database_url = _ensure_sslmode(database_url)
    print("Connecting to database...")

    try:
        import asyncpg
    except ImportError:
        print("Error: asyncpg not installed. Run: pip install asyncpg")
        sys.exit(1)

    migrations_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "migrations")
    migration_files = [
        "001_initial.sql",
        "002_secrets.sql",
        "003_doctor_to_agent_display_name.sql",
        "004_rag_folders_and_documents.sql",
        "005_admin_users.sql",
        "006_crm_stages.sql",
        "007_admin_passwords.sql",
    ]

    statements = []
    for name in migration_files:
        path = os.path.join(migrations_dir, name)
        if not os.path.exists(path):
            print(f"Warning: {name} not found, skipping")
            continue
        with open(path, "r") as f:
            sql = f.read()
        for block in sql.split(";"):
            lines = []
            for line in block.split("\n"):
                if line.strip().startswith("--"):
                    continue
                lines.append(line)
            stmt = "\n".join(lines).strip()
            if stmt:
                statements.append(stmt + ";")

    urls_to_try = [database_url]
    other = os.environ.get("DATABASE_PUBLIC_URL") or os.environ.get("DATABASE_URL")
    if other and other != database_url:
        urls_to_try.append(_ensure_sslmode(other))

    conn = None
    last_error = None
    for url in urls_to_try:
        for attempt in range(3):
            try:
                conn = await asyncpg.connect(url, timeout=30)
                break
            except Exception as e:
                last_error = e
                if attempt < 2:
                    print(f"Attempt {attempt + 1} failed, retrying in 3s: {e}")
                    await asyncio.sleep(3)
                else:
                    print(f"URL failed after 3 attempts")
        if conn is not None:
            break
    if conn is None:
        print(f"Failed to connect. Last error: {last_error}")
        print("Railway: Variables -> Postgres ref: service name must match (Postgres/PostgreSQL/postgres)")
        raise last_error
    try:
        for i, stmt in enumerate(statements):
            try:
                await conn.execute(stmt)
                first_line = stmt.split("\n")[0][:70]
                print(f"OK: {first_line}...")
            except Exception as e:
                err_msg = str(e).lower()
                if "already exists" in err_msg:
                    print(f"Skip (exists): {stmt.split(chr(10))[0][:50]}...")
                elif "duplicate key" in err_msg or "unique constraint" in err_msg:
                    print(f"Skip (duplicate): {stmt.split(chr(10))[0][:50]}...")
                elif "extension" in err_msg and "not available" in err_msg:
                    print(f"Skip (extension not available): {stmt.split(chr(10))[0][:50]}...")
                else:
                    print(f"Error executing statement {i + 1}: {e}")
                    raise
        print("Migration completed successfully.")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
