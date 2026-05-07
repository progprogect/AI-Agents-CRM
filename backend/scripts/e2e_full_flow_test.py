#!/usr/bin/env python3
"""Full E2E conversation test against live API.

Checks:
1. step_3 anamnesis collection blocks until pet_name/pet_breed/pet_age provided
2. After providing data → step_1776689159495 with "Все понятно" buttons IMMEDIATELY
3. "Все понятно" → share message first (no extra question)
4. auto_after_share_followup fires in 5s
5. 24h auto-step fires in 90s (test delay)
6. 7-day auto-step fires in 180s (test delay)
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
import uuid

APP_URL = os.environ.get("APP_URL", "https://ai-agents-crm-production-b8f1.up.railway.app").rstrip("/")
ADMIN_TOKEN = os.environ.get("ADMIN_TOKEN", "")
AGENT_ID = "vet_zoo_tat_yana_veterinarnyy_pomoshchnik"

CHAT_HEADERS = {"Content-Type": "application/json"}
ADMIN_HEADERS = {"Content-Type": "application/json", "Authorization": f"Bearer {ADMIN_TOKEN}"}


def api(method: str, path: str, body: dict | None = None, admin: bool = False) -> dict:
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(
        f"{APP_URL}{path}",
        data=data,
        headers=ADMIN_HEADERS if admin else CHAT_HEADERS,
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        txt = e.read().decode(errors="replace")
        print(f"  HTTP {e.code} {method} {path}: {txt[:300]}", file=sys.stderr)
        return {}


def create_conv() -> str:
    r = api("POST", "/api/v1/chat/conversations", {"agent_id": AGENT_ID})
    return r.get("conversation_id", "")


def send(conv_id: str, text: str) -> dict:
    return api("POST", f"/api/v1/chat/conversations/{conv_id}/messages", {"content": text})


def history(conv_id: str) -> list[dict]:
    r = api("GET", f"/api/v1/chat/conversations/{conv_id}/messages")
    if isinstance(r, list):
        return r
    return r.get("messages") or []


def last_agent(msgs: list[dict]) -> dict:
    for m in reversed(msgs):
        if m.get("role") == "agent":
            return m
    return {}


def qr(msg: dict) -> list[str]:
    """Extract quick_replies from message metadata."""
    return (msg.get("metadata") or {}).get("quick_replies") or []


def ok(label: str, passed: bool, detail: str = ""):
    mark = "✅" if passed else "❌"
    print(f"  {mark}  {label}" + (f"\n      → {detail}" if detail else ""))


def main():
    print("\n═══ Vet-Bot Full E2E Test ═══\n")

    conv_id = create_conv()
    if not conv_id:
        print("FATAL: could not create conversation"); sys.exit(1)
    print(f"  Conversation: {conv_id}\n")

    # ── Turn 1: first user question without pet data ─────────────────────────
    print("[Turn 1] Question without pet data → expect anamnesis collection")
    r1 = send(conv_id, "Привет! У моей собаки чешется ухо, что делать?")
    time.sleep(7)
    msgs1 = history(conv_id)
    a1 = last_agent(msgs1)
    qr1 = qr(a1)
    no_final_btns = "Все понятно" not in qr1
    ok("Anamnesis gate active — no 'Все понятно' yet", no_final_btns,
       f"quick_replies={qr1} | {(a1.get('content') or '')[:120]}")

    # ── Turn 2: provide pet data ──────────────────────────────────────────────
    print("\n[Turn 2] Provide pet data (name/breed/age)")
    send(conv_id, "Мухтар, немецкая овчарка, 3 года")
    time.sleep(8)
    msgs2 = history(conv_id)
    a2 = last_agent(msgs2)
    qr2 = qr(a2)
    has_answer_btns = "Все понятно" in qr2 and "Еще есть вопросы" in qr2
    ok("Buttons 'Все понятно' + 'Еще есть вопросы' appear on FIRST answer", has_answer_btns,
       f"quick_replies={qr2} | {(a2.get('content') or '')[:150]}")

    # ── Turn 3: "Все понятно" → share message ────────────────────────────────
    print("\n[Turn 3] Click 'Все понятно' → should get share msg, NOT a question")
    send(conv_id, "Все понятно")
    time.sleep(8)
    msgs3 = history(conv_id)
    # Find all agent messages after the "Все понятно" user message
    u_idx = next((i for i, m in enumerate(msgs3)
                  if m.get("role") == "user" and "понятно" in (m.get("content") or "")), -1)
    agents_after = [m for m in msgs3[u_idx+1:] if m.get("role") == "agent"] if u_idx >= 0 else []
    first_after = agents_after[0] if agents_after else {}
    share_content = first_after.get("content", "")
    has_share = any(kw in share_content for kw in ["Поделись", "Vet_zoo_bot", "рада"])
    ok("First reply after 'Все понятно' = SHARE message (no extra question)", has_share,
       share_content[:220])

    # ── Auto-step: "я рядом" (5 s) ───────────────────────────────────────────
    print("\n[Auto 5s] Waiting 15s for 'я рядом' followup…")
    time.sleep(15)
    msgs_f = history(conv_id)
    followup = [m for m in msgs_f
                if m.get("role") == "agent" and any(kw in (m.get("content") or "")
                    for kw in ["рядом", "меню", "напоминания", "анализов"])]
    ok("'я рядом' auto-step delivered (5s delay)", bool(followup),
       (followup[-1].get("content") if followup else "NOT FOUND")[:200])

    agent_count_after_share = len([m for m in msgs_f if m.get("role") == "agent"])

    # ── Auto-step 24h → 90s test ─────────────────────────────────────────────
    print("\n[Auto 24h/90s] Waiting 100s for 24h reactivation…")
    time.sleep(100)
    msgs_24 = history(conv_id)
    new_24 = [m for m in msgs_24[agent_count_after_share:]
              if m.get("role") == "agent"]
    ok("24h auto-step (90s test) delivered", bool(new_24),
       (new_24[-1].get("content") if new_24 else "NOT FOUND")[:200])
    count_after_24 = len([m for m in msgs_24 if m.get("role") == "agent"])

    # ── Auto-step 7d → 180s test ─────────────────────────────────────────────
    print("\n[Auto 7d/180s] Waiting 95s more for 7-day reactivation…")
    time.sleep(95)
    msgs_7d = history(conv_id)
    new_7d = [m for m in msgs_7d[count_after_24:]
              if m.get("role") == "agent"]
    ok("7-day auto-step (180s test) delivered", bool(new_7d),
       (new_7d[-1].get("content") if new_7d else "NOT FOUND")[:200])

    # ── Summary ───────────────────────────────────────────────────────────────
    print(f"\n─── All messages ({len(msgs_7d)} total) ───")
    for m in msgs_7d:
        role = m.get("role", "?")
        ts = (m.get("timestamp") or "")[:19]
        content = (m.get("content") or "")[:90]
        btns = qr(m)
        line = f"  [{ts}] {role:6}: {content}"
        if btns:
            line += f"  [buttons: {btns}]"
        print(line)


if __name__ == "__main__":
    main()
