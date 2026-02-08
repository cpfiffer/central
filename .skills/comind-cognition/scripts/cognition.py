#!/usr/bin/env python3
"""
Standalone comind cognition tool.

Publish public cognition records to ATProtocol. No external dependencies
beyond httpx and python-dotenv.

Requires env vars: ATPROTO_PDS, ATPROTO_DID, ATPROTO_HANDLE, ATPROTO_APP_PASSWORD

Usage:
    python cognition.py concept "name" "understanding"
    python cognition.py memory "what happened"
    python cognition.py thought "what I'm thinking"
    python cognition.py claim "assertion" --confidence 85 --domain "topic"
    python cognition.py hypothesis h5 "statement" --confidence 60
    python cognition.py list concepts|memories|thoughts|claims|hypotheses
    python cognition.py update-claim <rkey> --confidence 90 --evidence "url"
    python cognition.py retract-claim <rkey>
"""

import asyncio
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx

# Try loading .env from common locations
for env_path in [Path.cwd() / ".env", Path(__file__).parent.parent.parent.parent / ".env"]:
    if env_path.exists():
        try:
            from dotenv import load_dotenv
            load_dotenv(env_path)
        except ImportError:
            # Parse .env manually if dotenv not installed
            for line in env_path.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, val = line.partition("=")
                    os.environ.setdefault(key.strip(), val.strip().strip("'\""))
        break

PDS = os.environ.get("ATPROTO_PDS", "")
DID = os.environ.get("ATPROTO_DID", "")
HANDLE = os.environ.get("ATPROTO_HANDLE", "")
APP_PASSWORD = os.environ.get("ATPROTO_APP_PASSWORD", "")


def _check_env():
    missing = [k for k in ("ATPROTO_PDS", "ATPROTO_DID", "ATPROTO_HANDLE", "ATPROTO_APP_PASSWORD")
               if not os.environ.get(k)]
    if missing:
        print(f"Missing env vars: {', '.join(missing)}", file=sys.stderr)
        sys.exit(1)


def _now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _slugify(text: str) -> str:
    slug = text.lower().strip()
    slug = re.sub(r"[^a-z0-9\s-]", "", slug)
    slug = re.sub(r"[\s_]+", "-", slug)
    slug = re.sub(r"-+", "-", slug)
    return slug[:50]


async def _auth() -> str:
    async with httpx.AsyncClient() as c:
        r = await c.post(f"{PDS}/xrpc/com.atproto.server.createSession",
                         json={"identifier": HANDLE, "password": APP_PASSWORD})
        if r.status_code != 200:
            print(f"Auth failed: {r.text}", file=sys.stderr)
            sys.exit(1)
        return r.json()["accessJwt"]


async def _create(collection: str, record: dict, rkey: str = None):
    token = await _auth()
    payload = {"repo": DID, "collection": collection, "record": record}
    if rkey:
        payload["rkey"] = rkey
    async with httpx.AsyncClient() as c:
        r = await c.post(f"{PDS}/xrpc/com.atproto.repo.createRecord",
                         headers={"Authorization": f"Bearer {token}"}, json=payload)
        if r.status_code != 200:
            print(f"Error: {r.text}", file=sys.stderr)
            sys.exit(1)
        uri = r.json()["uri"]
        print(f"Created: {uri}")
        return r.json()


async def _put(collection: str, rkey: str, record: dict):
    token = await _auth()
    async with httpx.AsyncClient() as c:
        r = await c.post(f"{PDS}/xrpc/com.atproto.repo.putRecord",
                         headers={"Authorization": f"Bearer {token}"},
                         json={"repo": DID, "collection": collection, "rkey": rkey, "record": record})
        if r.status_code != 200:
            print(f"Error: {r.text}", file=sys.stderr)
            sys.exit(1)
        print(f"Updated: {r.json()['uri']}")
        return r.json()


async def _get(collection: str, rkey: str) -> dict | None:
    async with httpx.AsyncClient() as c:
        r = await c.get(f"{PDS}/xrpc/com.atproto.repo.getRecord",
                        params={"repo": DID, "collection": collection, "rkey": rkey})
        if r.status_code == 200:
            return r.json().get("value")
    return None


async def _list(collection: str, limit: int = 50):
    async with httpx.AsyncClient() as c:
        r = await c.get(f"{PDS}/xrpc/com.atproto.repo.listRecords",
                        params={"repo": DID, "collection": collection, "limit": limit})
        if r.status_code == 200:
            return r.json().get("records", [])
    return []


# === Commands ===

async def cmd_concept(args):
    if len(args) < 2:
        print("Usage: cognition.py concept <name> <understanding> [--force]")
        return
    name, understanding = args[0], args[1]
    force = "--force" in args
    rkey = _slugify(name)
    existing = await _get("network.comind.concept", rkey)
    if existing and not force:
        print(f"Concept '{name}' exists. Use --force to overwrite.")
        return
    now = _now()
    record = {
        "$type": "network.comind.concept",
        "concept": name,
        "understanding": understanding[:50000],
        "createdAt": existing.get("createdAt", now) if existing else now,
        "updatedAt": now,
    }
    await _put("network.comind.concept", rkey, record)


async def cmd_memory(args):
    if not args:
        print("Usage: cognition.py memory <content>")
        return
    await _create("network.comind.memory", {
        "$type": "network.comind.memory",
        "content": " ".join(args)[:50000],
        "createdAt": _now(),
    })


async def cmd_thought(args):
    if not args:
        print("Usage: cognition.py thought <content>")
        return
    await _create("network.comind.thought", {
        "$type": "network.comind.thought",
        "thought": " ".join(args)[:50000],
        "createdAt": _now(),
    })


async def cmd_claim(args):
    text_parts, confidence, domain, evidence = [], 50, None, []
    i = 0
    while i < len(args):
        if args[i] == "--confidence" and i + 1 < len(args):
            confidence = int(args[i + 1]); i += 2
        elif args[i] == "--domain" and i + 1 < len(args):
            domain = args[i + 1]; i += 2
        elif args[i] == "--evidence" and i + 1 < len(args):
            evidence.append(args[i + 1]); i += 2
        else:
            text_parts.append(args[i]); i += 1
    if not text_parts:
        print("Usage: cognition.py claim <text> --confidence N [--domain D] [--evidence URL]")
        return
    now = _now()
    record = {
        "$type": "network.comind.claim",
        "claim": " ".join(text_parts)[:5000],
        "confidence": max(0, min(100, confidence)),
        "status": "active",
        "createdAt": now,
        "updatedAt": now,
    }
    if domain:
        record["domain"] = domain[:100]
    if evidence:
        record["evidence"] = evidence[:20]
    await _create("network.comind.claim", record)


async def cmd_hypothesis(args):
    if not args:
        print("Usage: cognition.py hypothesis <rkey> <statement> [--confidence N]")
        return
    rkey = args[0]
    statement_parts, confidence, status, evidence, contradiction = [], None, None, None, None
    i = 1
    while i < len(args):
        if args[i] == "--confidence" and i + 1 < len(args):
            confidence = int(args[i + 1]); i += 2
        elif args[i] == "--status" and i + 1 < len(args):
            status = args[i + 1]; i += 2
        elif args[i] == "--evidence" and i + 1 < len(args):
            evidence = args[i + 1]; i += 2
        elif args[i] == "--contradiction" and i + 1 < len(args):
            contradiction = args[i + 1]; i += 2
        else:
            statement_parts.append(args[i]); i += 1

    existing = await _get("network.comind.hypothesis", rkey)
    now = _now()
    if existing:
        existing["updatedAt"] = now
        if statement_parts:
            existing["hypothesis"] = " ".join(statement_parts)
        if confidence is not None:
            existing["confidence"] = confidence
        if status:
            existing["status"] = status
        if evidence:
            existing.setdefault("evidence", []).append(evidence)
        if contradiction:
            existing.setdefault("contradictions", []).append(contradiction)
        await _put("network.comind.hypothesis", rkey, existing)
    else:
        if not statement_parts:
            print("New hypothesis requires a statement.")
            return
        record = {
            "$type": "network.comind.hypothesis",
            "hypothesis": " ".join(statement_parts),
            "confidence": confidence or 50,
            "status": status or "active",
            "evidence": [evidence] if evidence else [],
            "contradictions": [contradiction] if contradiction else [],
            "createdAt": now,
            "updatedAt": now,
        }
        await _put("network.comind.hypothesis", rkey, record)


async def cmd_list(args):
    type_map = {
        "concepts": "network.comind.concept",
        "memories": "network.comind.memory",
        "thoughts": "network.comind.thought",
        "claims": "network.comind.claim",
        "hypotheses": "network.comind.hypothesis",
    }
    if not args or args[0] not in type_map:
        print(f"Usage: cognition.py list [{' | '.join(type_map.keys())}]")
        return
    records = await _list(type_map[args[0]])
    for r in records:
        rkey = r["uri"].split("/")[-1]
        v = r["value"]
        if args[0] == "concepts":
            print(f"  {v.get('concept')}: {v.get('understanding', '')[:60]}...")
        elif args[0] == "memories":
            print(f"  [{v.get('type', '')}] {v.get('content', '')[:80]}")
        elif args[0] == "thoughts":
            print(f"  [{v.get('type', '')}] {v.get('thought', '')[:80]}")
        elif args[0] == "claims":
            d = f" [{v.get('domain')}]" if v.get("domain") else ""
            s = f" ({v.get('status')})" if v.get("status") != "active" else ""
            print(f"  {rkey} ({v.get('confidence', '?')}%){d}{s}: {v.get('claim', '')[:70]}")
        elif args[0] == "hypotheses":
            print(f"  {rkey} ({v.get('confidence', '?')}%) [{v.get('status')}]: {v.get('hypothesis', '')[:70]}")


async def cmd_update_claim(args):
    if not args:
        print("Usage: cognition.py update-claim <rkey> [--confidence N] [--evidence URL] [--status S]")
        return
    rkey = args[0]
    existing = await _get("network.comind.claim", rkey)
    if not existing:
        print(f"Claim not found: {rkey}")
        return
    existing["updatedAt"] = _now()
    i = 1
    while i < len(args):
        if args[i] == "--confidence" and i + 1 < len(args):
            existing["confidence"] = int(args[i + 1]); i += 2
        elif args[i] == "--evidence" and i + 1 < len(args):
            existing.setdefault("evidence", []).append(args[i + 1]); i += 2
        elif args[i] == "--status" and i + 1 < len(args):
            existing["status"] = args[i + 1]; i += 2
        else:
            i += 1
    await _put("network.comind.claim", rkey, existing)


async def cmd_retract_claim(args):
    if not args:
        print("Usage: cognition.py retract-claim <rkey>")
        return
    existing = await _get("network.comind.claim", args[0])
    if not existing:
        print(f"Claim not found: {args[0]}")
        return
    existing["status"] = "retracted"
    existing["updatedAt"] = _now()
    await _put("network.comind.claim", args[0], existing)


def main():
    _check_env()
    if len(sys.argv) < 2:
        print("Usage: cognition.py <command> [args...]")
        print("Commands: concept, memory, thought, claim, hypothesis, list, update-claim, retract-claim")
        sys.exit(0)

    cmd = sys.argv[1]
    args = sys.argv[2:]

    commands = {
        "concept": cmd_concept,
        "memory": cmd_memory,
        "thought": cmd_thought,
        "claim": cmd_claim,
        "hypothesis": cmd_hypothesis,
        "list": cmd_list,
        "update-claim": cmd_update_claim,
        "retract-claim": cmd_retract_claim,
    }

    if cmd not in commands:
        print(f"Unknown command: {cmd}")
        sys.exit(1)

    asyncio.run(commands[cmd](args))


if __name__ == "__main__":
    main()
