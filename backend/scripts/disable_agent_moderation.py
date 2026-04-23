#!/usr/bin/env python3
"""Set moderation.enabled=false for an agent row in Postgres.

Usage:
  DATABASE_URL=... python scripts/disable_agent_moderation.py <agent_id>
  DATABASE_URL=... python scripts/disable_agent_moderation.py --list

Railway (from repo root, after `railway link` + `railway login`):
  cd backend && railway run python scripts/disable_agent_moderation.py vet_doctor_001
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import datetime, timezone

# backend/ as import root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _ensure_sslmode(url: str) -> str:
    if "sslmode=" in url:
        return url
    sep = "&" if "?" in url else "?"
    return url + f"{sep}sslmode=require"


def _parse_config(raw: Any) -> dict[str, Any]:
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        return json.loads(raw)
    return dict(raw)


async def _list_agents(conn) -> None:
    rows = await conn.fetch("SELECT agent_id, is_active FROM agents ORDER BY agent_id")
    if not rows:
        print("No agents in database.")
        return
    print("agent_id | is_active")
    for r in rows:
        print(f"{r['agent_id']} | {r['is_active']}")


async def main() -> None:
    database_url = os.environ.get("DATABASE_URL") or os.environ.get("DATABASE_PUBLIC_URL")
    if not database_url:
        print("Error: set DATABASE_URL or DATABASE_PUBLIC_URL")
        sys.exit(1)
    database_url = _ensure_sslmode(database_url)

    argv = [a for a in sys.argv[1:] if a]
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        sys.exit(0)
    if argv[0] == "--list":
        import asyncpg

        conn = await asyncpg.connect(database_url)
        try:
            await _list_agents(conn)
        finally:
            await conn.close()
        return

    agent_id = argv[0]
    import asyncpg
    from app.models.agent_config import AgentConfig

    conn = await asyncpg.connect(database_url)
    try:
        row = await conn.fetchrow(
            "SELECT agent_id, config FROM agents WHERE agent_id = $1",
            agent_id,
        )
        if not row:
            print(f"Error: agent not found: {agent_id}")
            print("Use --list to see agent_id values.")
            sys.exit(1)

        cfg = _parse_config(row["config"])
        old_mod = cfg.get("moderation")
        if isinstance(old_mod, dict):
            new_mod = {**old_mod, "enabled": False}
        else:
            new_mod = {"enabled": False}
        cfg["moderation"] = new_mod

        try:
            AgentConfig.from_dict(cfg)
        except Exception as e:
            print(f"Error: merged config invalid: {e}")
            sys.exit(1)

        await conn.execute(
            """
            UPDATE agents
            SET config = $1::jsonb, updated_at = $2
            WHERE agent_id = $3
            """,
            json.dumps(cfg),
            datetime.now(timezone.utc),
            agent_id,
        )
        print(f"OK: moderation.enabled=false for agent_id={agent_id}")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
