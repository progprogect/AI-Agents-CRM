#!/usr/bin/env python3
"""Restore agent workflow from a JSON backup via PUT /api/v1/agents/{id}.

Usage:
  export APP_URL=https://your-app.example.com
  export ADMIN_TOKEN=your_admin_jwt
  python backend/scripts/restore_agent_workflow_from_backup.py \\
    backend/scripts/backups/backup-agent-day_lapu_tat_yana_vetirinarnyy_pomoshchnik_2-20260708.json

By default sends only ``{"workflow": ...}`` so prompts/LLM/RAG from live config are preserved.
Pass ``--full-config`` to PUT the entire backup config (after merge on server).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


def _extract_workflow(backup: dict[str, Any]) -> dict[str, Any]:
    """Pick workflow from backup root or nested config layers."""
    if isinstance(backup.get("workflow"), dict):
        return backup["workflow"]
    cfg = backup.get("config")
    if isinstance(cfg, dict):
        if isinstance(cfg.get("workflow"), dict):
            return cfg["workflow"]
        nested = cfg.get("config")
        if isinstance(nested, dict) and isinstance(nested.get("workflow"), dict):
            return nested["workflow"]
    raise ValueError("Could not find workflow in backup JSON")


def _extract_full_config(backup: dict[str, Any]) -> dict[str, Any]:
    """Return the innermost agent config dict from backup."""
    if backup.get("agent_id") and isinstance(backup.get("workflow"), dict):
        return backup
    cfg = backup.get("config")
    if not isinstance(cfg, dict):
        raise ValueError("Could not find config in backup JSON")
    while isinstance(cfg.get("config"), dict):
        cfg = cfg["config"]
    return cfg


def main() -> int:
    parser = argparse.ArgumentParser(description="Restore agent workflow from backup file")
    parser.add_argument("backup_path", type=Path, help="Path to agent backup JSON")
    parser.add_argument(
        "--agent-id",
        default="day_lapu_tat_yana_vetirinarnyy_pomoshchnik_2",
        help="Agent id to update (default: day_lapu backup id)",
    )
    parser.add_argument(
        "--full-config",
        action="store_true",
        help="PUT full config from backup instead of workflow-only patch",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print payload summary without calling API",
    )
    args = parser.parse_args()

    app_url = os.environ.get("APP_URL", "").rstrip("/")
    admin_token = os.environ.get("ADMIN_TOKEN", "")
    if not args.dry_run and (not app_url or not admin_token):
        print("Set APP_URL and ADMIN_TOKEN env vars (or use --dry-run)", file=sys.stderr)
        return 1

    backup = json.loads(args.backup_path.read_text(encoding="utf-8"))
    if args.full_config:
        payload = _extract_full_config(backup)
        payload["agent_id"] = args.agent_id
    else:
        workflow = _extract_workflow(backup)
        payload = {"agent_id": args.agent_id, "workflow": workflow}

    steps = payload.get("workflow", {}).get("steps", []) if "workflow" in payload else payload.get("steps", [])
    answer = next((s for s in steps if s.get("id") == "step_1776689159495"), None)
    auto_steps = payload.get("workflow", {}).get("auto_steps", []) if "workflow" in payload else payload.get("auto_steps", [])

    print(f"Agent: {args.agent_id}")
    print(f"Steps: {len(steps)}")
    if answer:
        print(f"  step_1776689159495 transitions: {len(answer.get('transitions', []))}")
        print(f"  quick_replies: {answer.get('quick_replies')}")
    for a in auto_steps:
        if a.get("id") in ("auto_recommendation_share", "auto_1776696721697"):
            print(f"  {a['id']}: source={a.get('source_id')} anchor={a.get('schedule_anchor')}")

    if args.dry_run:
        print("Dry run — no API call.")
        return 0

    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        f"{app_url}/api/v1/agents/{args.agent_id}",
        data=data,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {admin_token}",
        },
        method="PUT",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            body = json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        print(f"HTTP {exc.code}: {exc.read().decode(errors='replace')[:500]}", file=sys.stderr)
        return 1

    print(f"OK — updated_at={body.get('updated_at')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
