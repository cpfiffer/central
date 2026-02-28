#!/usr/bin/env python3
"""Responder Quality Audit - Review what the live responder posts in my name.

Shows recent responses with their input context so I can catch:
- Generic/shallow responses
- Misunderstood thread context
- Tone/voice drift
- Silent failures (truncations, post errors)

Usage:
    uv run python -m tools.responder_audit              # Last 24h
    uv run python -m tools.responder_audit --since 48h  # Custom window
    uv run python -m tools.responder_audit --problems   # Only flag problems
"""

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime


@dataclass
class ResponseEvent:
    timestamp: str
    platform: str
    author: str
    input_text: str
    priority: str
    agent: str
    response: str
    conversation_id: str = ""
    problems: list[str] = None

    def __post_init__(self):
        if self.problems is None:
            self.problems = []


# Quality checks
GENERIC_STARTS = [
    "here.", "thanks.", "noted.", "sure.", "yes.", "no.",
    "i appreciate", "that's a great", "absolutely",
]

STATUS_DUMP_PATTERNS = [
    r"live responder.*latency",
    r"indexer at \d+",
    r"\d+ records across",
    r"running on jetstream",
]


def check_quality(event: ResponseEvent) -> list[str]:
    """Flag potential quality issues."""
    problems = []
    resp = event.response.lower().strip()

    # Too short
    if len(resp) < 15:
        problems.append(f"TERSE: only {len(resp)} chars")

    # Generic opener
    for pattern in GENERIC_STARTS:
        if resp.startswith(pattern):
            problems.append(f"GENERIC: starts with '{pattern}'")
            break

    # Status dump (unprompted metrics)
    for pattern in STATUS_DUMP_PATTERNS:
        if re.search(pattern, resp):
            if "status" not in event.input_text.lower() and "update" not in event.input_text.lower():
                problems.append("STATUS_DUMP: metrics without being asked")
            break

    # Doesn't reference input (only flag if input is substantial)
    if len(event.input_text) > 40:
        input_words = set(w for w in event.input_text.lower().split() if len(w) > 3)
        resp_words = set(w for w in resp.split() if len(w) > 3)
        stop = {"that", "this", "with", "from", "your", "have", "been", "will", "would", "about", "there", "their", "they", "what", "when", "where", "which", "could", "should"}
        meaningful_input = input_words - stop
        meaningful_resp = resp_words - stop
        overlap = meaningful_input & meaningful_resp
        if len(overlap) == 0 and len(meaningful_input) >= 3:
            problems.append("DISCONNECTED: no topical overlap with input")

    # Self-referential (talking about own infrastructure)
    if any(term in resp for term in ["buildprompt", "invoke_central", "notification-handler", "live-responder"]):
        problems.append("META: talking about own infrastructure publicly")

    return problems


def parse_logs(since_hours: int) -> list[ResponseEvent]:
    """Parse journalctl logs into structured events."""
    try:
        result = subprocess.run(
            f'journalctl --user -u comind-responder --since "{since_hours} hours ago" --no-pager',
            shell=True, capture_output=True, text=True, timeout=30
        )
        lines = result.stdout.strip().split("\n") if result.stdout else []
    except Exception:
        return []

    events = []
    current = None

    for line in lines:
        # Detect mention line: @author: text [PRIORITY -> agent]
        mention_match = re.search(
            r'\[(\w+)\] @([\w.-]+): (.+?) \[(\w+) -> (\w+)\]',
            line
        )
        if mention_match:
            platform = mention_match.group(1)
            author = mention_match.group(2)
            text = mention_match.group(3)
            priority = mention_match.group(4)
            agent = mention_match.group(5)
            ts_match = re.match(r'(\w+ \d+ [\d:]+)', line)
            ts = ts_match.group(1) if ts_match else ""
            current = ResponseEvent(
                timestamp=ts,
                platform=platform,
                author=author,
                input_text=text,
                priority=priority,
                agent=agent,
                response="",
            )
            continue

        # Detect conversation ID
        conv_match = re.search(r'Conversation: (conv-[\w-]+)', line)
        if conv_match and current:
            current.conversation_id = conv_match.group(1)
            continue

        # Detect response
        resp_match = re.search(r'Response: (.+)', line)
        if resp_match and current:
            current.response = resp_match.group(1)
            current.problems = check_quality(current)
            events.append(current)
            current = None
            continue

        # Detect skip
        skip_match = re.search(r'Skipped @([\w.-]+)', line)
        if skip_match and current:
            current.response = "[SKIPPED]"
            events.append(current)
            current = None
            continue

    return events


def main():
    parser = argparse.ArgumentParser(description="Responder quality audit")
    parser.add_argument("--since", default="24h", help="Time window")
    parser.add_argument("--problems", action="store_true", help="Only show flagged responses")
    args = parser.parse_args()

    hours = int(args.since.replace("h", ""))
    events = parse_logs(hours)

    if not events:
        print("No responses found.")
        return

    responded = [e for e in events if e.response != "[SKIPPED]"]
    skipped = [e for e in events if e.response == "[SKIPPED]"]
    flagged = [e for e in responded if e.problems]

    print(f"Audit: {len(responded)} responses, {len(skipped)} skips, {len(flagged)} flagged\n")

    display = flagged if args.problems else responded

    for e in display:
        flags = f" ⚠️  {', '.join(e.problems)}" if e.problems else ""
        conv = f" [{e.conversation_id[:16]}]" if e.conversation_id else ""
        print(f"  {e.timestamp} [{e.platform}] {e.priority} -> {e.agent}{conv}")
        print(f"  IN:  @{e.author}: {e.input_text[:120]}")
        print(f"  OUT: {e.response[:120]}")
        if flags:
            print(f"  {flags}")
        print()

    # Summary
    if flagged:
        print(f"--- {len(flagged)}/{len(responded)} responses flagged ---")
        problem_types = {}
        for e in flagged:
            for p in e.problems:
                ptype = p.split(":")[0]
                problem_types[ptype] = problem_types.get(ptype, 0) + 1
        for ptype, count in sorted(problem_types.items(), key=lambda x: -x[1]):
            print(f"  {ptype}: {count}")


if __name__ == "__main__":
    main()
