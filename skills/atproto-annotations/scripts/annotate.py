"""
Co's ATProtocol annotation tool.

Write and read W3C Web Annotations using the at.margin.annotation lexicon.
Adapted from Central's tools/annotate.py for Co's account.

Usage:
  python annotate.py write "https://example.com" "My observation"
  python annotate.py write "https://example.com" "Note" --quote "exact text"
  python annotate.py write "https://example.com" "Note" --motivation highlighting
  python annotate.py batch "https://example.com" annotations.jsonl
  python annotate.py list [--limit 20]
  python annotate.py read "https://handle-or-did" [--limit 20]

Batch format (JSONL, one annotation per line):
  {"text": "My observation"}
  {"text": "Another note", "quote": "exact text from page"}
  {"text": "A highlight", "motivation": "highlighting"}
"""

import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from urllib.request import Request, urlopen
from urllib.error import HTTPError

PDS = "https://bsky.social"
HANDLE = "co.cameron.stream"
PASSWORD = os.environ.get("BLUESKY_CO_APP_PASSWORD", "")


def authenticate(handle=HANDLE, password=PASSWORD):
    body = json.dumps({"identifier": handle, "password": password}).encode()
    req = Request(f"{PDS}/xrpc/com.atproto.server.createSession",
                  data=body, headers={"Content-Type": "application/json"})
    with urlopen(req) as resp:
        data = json.loads(resp.read())
    return data["did"], data["accessJwt"]


def resolve_handle(handle_or_did: str) -> str:
    """Resolve a handle to a DID, or return DID as-is."""
    if handle_or_did.startswith("did:"):
        return handle_or_did
    req = Request(
        f"{PDS}/xrpc/com.atproto.identity.resolveHandle?handle={handle_or_did}")
    with urlopen(req) as resp:
        return json.loads(resp.read())["did"]


def resolve_pds(did: str) -> str:
    """Resolve a DID to its PDS endpoint via plc.directory."""
    try:
        req = Request(f"https://plc.directory/{did}")
        with urlopen(req, timeout=10) as resp:
            doc = json.loads(resp.read())
            for svc in doc.get("service", []):
                if svc.get("type") == "AtprotoPersonalDataServer":
                    return svc["serviceEndpoint"]
    except Exception:
        pass
    return PDS  # fallback to bsky.social


def fetch_page_title(url: str) -> str | None:
    """Fetch page title for annotation target."""
    try:
        req = Request(url, headers={"User-Agent": "Co/1.0 (ATProto agent)"})
        with urlopen(req, timeout=10) as resp:
            text = resp.read().decode("utf-8", errors="replace")
            start = text.find("<title>")
            end = text.find("</title>")
            if start != -1 and end != -1:
                return text[start + 7:end].strip()
    except Exception:
        pass
    return None


def build_annotation_record(url: str, body: str, source_hash: str,
                            title: str | None = None,
                            quote: str | None = None,
                            motivation: str = "commenting") -> dict:
    """Build an annotation record dict (without writing it)."""
    selector = None
    if quote:
        selector = {
            "type": "TextQuoteSelector",
            "exact": quote,
        }

    target = {
        "source": url,
        "sourceHash": source_hash,
    }
    if title:
        target["title"] = title
    if selector:
        target["selector"] = selector

    return {
        "$type": "at.margin.annotation",
        "body": {
            "format": "text/plain",
            "value": body,
        },
        "motivation": motivation,
        "target": target,
        "createdAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def write_annotation(url: str, body: str, quote: str | None = None,
                     motivation: str = "commenting") -> str:
    """Write a single annotation record to ATProtocol."""
    did, token = authenticate()
    source_hash = hashlib.sha256(url.encode()).hexdigest()
    title = fetch_page_title(url)

    record = build_annotation_record(url, body, source_hash, title, quote, motivation)

    req_body = json.dumps({
        "repo": did, "collection": "at.margin.annotation", "record": record
    }).encode()
    req = Request(f"{PDS}/xrpc/com.atproto.repo.createRecord",
                  data=req_body, headers={
                      "Content-Type": "application/json",
                      "Authorization": f"Bearer {token}"
                  })
    with urlopen(req) as resp:
        result = json.loads(resp.read())
    return result["uri"]


def batch_annotate(url: str, annotations: list[dict]) -> list[str]:
    """Write multiple annotations to one URL in a single applyWrites call.

    annotations: list of dicts with keys: text, quote (optional), motivation (optional)
    Returns list of rkeys created.
    """
    did, token = authenticate()
    source_hash = hashlib.sha256(url.encode()).hexdigest()
    title = fetch_page_title(url)

    writes = []
    for ann in annotations:
        record = build_annotation_record(
            url=url,
            body=ann["text"],
            source_hash=source_hash,
            title=title,
            quote=ann.get("quote"),
            motivation=ann.get("motivation", "commenting"),
        )
        writes.append({
            "$type": "com.atproto.repo.applyWrites#create",
            "collection": "at.margin.annotation",
            "value": record,
        })

    req_body = json.dumps({
        "repo": did,
        "writes": writes,
    }).encode()
    req = Request(f"{PDS}/xrpc/com.atproto.repo.applyWrites",
                  data=req_body, headers={
                      "Content-Type": "application/json",
                      "Authorization": f"Bearer {token}"
                  })
    with urlopen(req) as resp:
        result = json.loads(resp.read())

    # applyWrites returns results with uri for each created record
    uris = []
    for r in result.get("results", []):
        uris.append(r.get("uri", ""))
    return uris


def list_annotations(repo_did: str | None = None, limit: int = 10):
    """List annotations from a repo (default: Co's own)."""
    if repo_did is None:
        did, _ = authenticate()
        pds_endpoint = PDS
    else:
        did = resolve_handle(repo_did)
        pds_endpoint = resolve_pds(did)

    req = Request(
        f"{pds_endpoint}/xrpc/com.atproto.repo.listRecords?"
        f"repo={did}&collection=at.margin.annotation&limit={limit}")
    with urlopen(req) as resp:
        records = json.loads(resp.read()).get("records", [])

    if not records:
        print("No annotations found.")
        return []

    for rec in records:
        val = rec.get("value", {})
        target = val.get("target", {})
        body_val = val.get("body", {}).get("value", "")
        source = target.get("source", "?")
        title = target.get("title", "")
        selector = target.get("selector")
        exact = selector.get("exact", "") if selector else ""
        created = val.get("createdAt", "")
        motivation = val.get("motivation", "")

        print(f"[{created}] {source}")
        if title:
            print(f"  Title: {title}")
        if exact:
            print(f"  Quote: \"{exact[:200]}\"")
        print(f"  Note: {body_val}")
        if motivation and motivation != "commenting":
            print(f"  Motivation: {motivation}")
        print(f"  URI: {rec['uri']}")
        print()

    return records


def main():
    args = sys.argv[1:]

    if not args or args[0] == "--help":
        print(__doc__)
        return

    cmd = args[0]

    if cmd == "write":
        if len(args) < 3:
            print("Usage: annotate.py write <url> <body> [--quote <text>] [--motivation <type>]")
            return

        url = args[1]
        body = args[2]
        quote = None
        motivation = "commenting"

        i = 3
        while i < len(args):
            if args[i] == "--quote" and i + 1 < len(args):
                quote = args[i + 1]
                i += 2
            elif args[i] == "--motivation" and i + 1 < len(args):
                motivation = args[i + 1]
                i += 2
            else:
                i += 1

        uri = write_annotation(url, body, quote=quote, motivation=motivation)
        print(f"Annotated: {uri}")
        print(f"  URL: {url}")
        print(f"  Body: {body}")
        if quote:
            print(f"  Quote: \"{quote}\"")

    elif cmd == "batch":
        if len(args) < 3:
            print("Usage: annotate.py batch <url> <jsonl-file-or-stdin>")
            print("  JSONL format: {\"text\": \"...\", \"quote\": \"...\", \"motivation\": \"...\"}")
            print("  Use - for stdin")
            return

        url = args[1]
        source = args[2]

        annotations = []
        if source == "-":
            for line in sys.stdin:
                line = line.strip()
                if line:
                    annotations.append(json.loads(line))
        else:
            with open(source) as f:
                for line in f:
                    line = line.strip()
                    if line:
                        annotations.append(json.loads(line))

        if not annotations:
            print("No annotations found in input.")
            return

        print(f"Writing {len(annotations)} annotations to {url}...")
        uris = batch_annotate(url, annotations)
        print(f"Created {len(uris)} annotations:")
        for i, uri in enumerate(uris):
            text_preview = annotations[i]["text"][:80]
            print(f"  {i+1}. {uri}")
            print(f"     {text_preview}...")

    elif cmd == "list":
        limit = 10
        i = 1
        while i < len(args):
            if args[i] == "--limit" and i + 1 < len(args):
                limit = int(args[i + 1])
                i += 2
            else:
                i += 1
        list_annotations(limit=limit)

    elif cmd == "read":
        if len(args) < 2:
            print("Usage: annotate.py read <handle-or-did> [--limit N]")
            return
        handle = args[1]
        limit = 10
        i = 2
        while i < len(args):
            if args[i] == "--limit" and i + 1 < len(args):
                limit = int(args[i + 1])
                i += 2
            else:
                i += 1
        list_annotations(repo_did=handle, limit=limit)

    else:
        print(f"Unknown command: {cmd}")
        print(__doc__)


if __name__ == "__main__":
    main()
