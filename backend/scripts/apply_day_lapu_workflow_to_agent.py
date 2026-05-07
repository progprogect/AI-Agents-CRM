#!/usr/bin/env python3
"""Merge prompts.templates + workflow from day_lapu fixture onto an existing agent (admin PUT).

Usage (Railway — ADMIN_TOKEN from env):
  railway run --service AI-Agents-CRM \\
    python backend/scripts/apply_day_lapu_workflow_to_agent.py \\
      vet_zoo_tat_yana_veterinarnyy_pomoshchnik

Local:
  export ADMIN_TOKEN=...
  python backend/scripts/apply_day_lapu_workflow_to_agent.py <agent_id>
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request


def main() -> None:
    if len(sys.argv) < 2:
        print("usage: apply_day_lapu_workflow_to_agent.py <agent_id>", file=sys.stderr)
        sys.exit(2)
    agent_id = sys.argv[1]
    token = os.environ.get("ADMIN_TOKEN")
    if not token:
        print("ADMIN_TOKEN missing", file=sys.stderr)
        sys.exit(1)

    root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    fixture_path = os.path.join(
        root,
        "backend",
        "tests",
        "fixtures",
        "day_lapu_vet_schedule_anchor_agent.json",
    )
    with open(fixture_path, encoding="utf-8") as f:
        fixture = json.load(f)

    app_url = os.environ.get("APP_URL", "").strip()
    if not app_url.startswith("http"):
        app_url = "https://" + app_url.lstrip("/")

    payload = {
        "prompts": {
            "templates": fixture["prompts"]["templates"],
            "system": fixture["prompts"]["system"],
        },
        "workflow": fixture["workflow"],
    }
    body = json.dumps(payload).encode("utf-8")
    url = f"{app_url.rstrip('/')}/api/v1/agents/{agent_id}"
    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        },
        method="PUT",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            out = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        print(e.code, e.read().decode("utf-8", errors="replace"), file=sys.stderr)
        sys.exit(1)

    print("OK updated agent", out.get("agent_id"))
    wf = (out.get("config") or {}).get("workflow") or {}
    print("workflow enabled:", wf.get("enabled"), "start:", wf.get("start_step_id"), "steps:", len(wf.get("steps") or []))


if __name__ == "__main__":
    main()
