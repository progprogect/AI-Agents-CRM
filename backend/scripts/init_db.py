#!/usr/bin/env python3
"""Initialize PostgreSQL database schema. Run with DATABASE_URL or DATABASE_PUBLIC_URL."""

import asyncio
import os
import sys

# Add parent to path for app imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


async def main() -> None:
    database_url = os.environ.get("DATABASE_URL") or os.environ.get("DATABASE_PUBLIC_URL")
    if not database_url:
        print("Error: DATABASE_URL or DATABASE_PUBLIC_URL must be set")
        sys.exit(1)

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

    conn = await asyncpg.connect(database_url)
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
