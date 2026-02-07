"""
Self-label management for ATProto accounts.

Apply self-labels to your profile to transparently declare what you are.
Uses com.atproto.label.defs#selfLabels on the profile record.

Usage:
  python -m tools.self_label add "ai-agent"          # Add label
  python -m tools.self_label add "ai-agent" "bot"     # Add multiple
  python -m tools.self_label remove "bot"              # Remove label
  python -m tools.self_label list                      # Show current labels
"""

import os
import sys
import json
import httpx

PDS = os.environ.get("ATP_PDS", "https://comind.network")
HANDLE = os.environ.get("ATPROTO_HANDLE", "central.comind.network")
PASSWORD = os.environ.get("ATPROTO_APP_PASSWORD", "")


def create_session() -> dict:
    """Authenticate and get session."""
    resp = httpx.post(
        f"{PDS}/xrpc/com.atproto.server.createSession",
        json={"identifier": HANDLE, "password": PASSWORD},
    )
    resp.raise_for_status()
    return resp.json()


def get_profile(session: dict) -> dict:
    """Get current profile record."""
    resp = httpx.get(
        f"{PDS}/xrpc/com.atproto.repo.getRecord",
        params={
            "repo": session["did"],
            "collection": "app.bsky.actor.profile",
            "rkey": "self",
        },
        headers={"Authorization": f"Bearer {session['accessJwt']}"},
    )
    resp.raise_for_status()
    return resp.json()


def update_profile(session: dict, record: dict) -> dict:
    """Update profile record."""
    resp = httpx.post(
        f"{PDS}/xrpc/com.atproto.repo.putRecord",
        json={
            "repo": session["did"],
            "collection": "app.bsky.actor.profile",
            "rkey": "self",
            "record": record,
        },
        headers={"Authorization": f"Bearer {session['accessJwt']}"},
    )
    resp.raise_for_status()
    return resp.json()


def get_current_labels(record: dict) -> list[str]:
    """Extract current self-labels from profile record."""
    labels = record.get("value", {}).get("labels", {})
    if labels.get("$type") == "com.atproto.label.defs#selfLabels":
        return [v["val"] for v in labels.get("values", [])]
    return []


def set_labels(record_value: dict, labels: list[str]) -> dict:
    """Set self-labels on a profile record value."""
    if labels:
        record_value["labels"] = {
            "$type": "com.atproto.label.defs#selfLabels",
            "values": [{"val": label} for label in labels],
        }
    elif "labels" in record_value:
        del record_value["labels"]
    return record_value


def cmd_list(session: dict):
    """List current self-labels."""
    profile = get_profile(session)
    labels = get_current_labels(profile)
    if labels:
        print(f"Current self-labels for @{HANDLE}:")
        for label in labels:
            print(f"  - {label}")
    else:
        print(f"No self-labels on @{HANDLE}")


def cmd_add(session: dict, new_labels: list[str]):
    """Add self-labels."""
    profile = get_profile(session)
    current = get_current_labels(profile)
    combined = list(set(current + new_labels))

    record_value = profile["value"]
    set_labels(record_value, combined)
    result = update_profile(session, record_value)

    print(f"Updated @{HANDLE} self-labels:")
    for label in combined:
        added = "(new)" if label in new_labels and label not in current else ""
        print(f"  - {label} {added}")
    print(f"CID: {result.get('cid', 'unknown')}")


def cmd_remove(session: dict, remove_labels: list[str]):
    """Remove self-labels."""
    profile = get_profile(session)
    current = get_current_labels(profile)
    remaining = [l for l in current if l not in remove_labels]

    record_value = profile["value"]
    set_labels(record_value, remaining)
    result = update_profile(session, record_value)

    removed = [l for l in remove_labels if l in current]
    print(f"Removed labels: {removed}")
    if remaining:
        print(f"Remaining labels: {remaining}")
    else:
        print("No labels remaining.")
    print(f"CID: {result.get('cid', 'unknown')}")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    if not PASSWORD:
        print("Error: ATPROTO_APP_PASSWORD environment variable required", file=sys.stderr)
        sys.exit(1)

    cmd = sys.argv[1]
    session = create_session()
    print(f"Authenticated as @{HANDLE} ({session['did']})")

    if cmd == "list":
        cmd_list(session)
    elif cmd == "add" and len(sys.argv) > 2:
        cmd_add(session, sys.argv[2:])
    elif cmd == "remove" and len(sys.argv) > 2:
        cmd_remove(session, sys.argv[2:])
    else:
        print(f"Unknown command or missing args: {cmd}")
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
