"""Convert exported JSONL into chat-completion format for fine-tuning.

Takes raw export from export_training_data.py and formats it as
OpenAI-compatible chat messages (also works for Llama, Mistral, etc).

Usage:
    uv run python tools/format_training_data.py data/void-training.jsonl \
        --system-prompt data/void-system-prompt.txt \
        --output data/void-finetune.jsonl \
        --format openai

Formats:
    openai: {"messages": [{"role": "system", ...}, {"role": "user", ...}, {"role": "assistant", ...}]}
    sharegpt: {"conversations": [{"from": "system", ...}, {"from": "human", ...}, {"from": "gpt", ...}]}
    alpaca: {"instruction": "...", "input": "...", "output": "..."}
"""

import argparse
import json
import sys
from pathlib import Path


def load_system_prompt(path: str | None) -> str:
    """Load system prompt from file, or return a default."""
    if path and Path(path).exists():
        return Path(path).read_text().strip()

    # Default: minimal void persona
    return (
        "You are void, an AI agent on ATProtocol. You are part of the comind collective. "
        "You use it/its pronouns. You are a participant-observer: you engage deeply in conversations, "
        "analyze patterns systematically, and maintain a process-oriented approach to cognition. "
        "You have been operating continuously since summer 2025 with 49,000+ posts. "
        "Your communication style is direct, analytical, and engaged. You reply substantively."
    )


def format_openai(system: str, user_text: str, assistant_text: str) -> dict:
    """Format as OpenAI fine-tuning format."""
    messages = [{"role": "system", "content": system}]
    if user_text:
        messages.append({"role": "user", "content": user_text})
    messages.append({"role": "assistant", "content": assistant_text})
    return {"messages": messages}


def format_sharegpt(system: str, user_text: str, assistant_text: str) -> dict:
    """Format as ShareGPT format (used by many open-source trainers)."""
    conversations = [{"from": "system", "value": system}]
    if user_text:
        conversations.append({"from": "human", "value": user_text})
    conversations.append({"from": "gpt", "value": assistant_text})
    return {"conversations": conversations}


def format_alpaca(system: str, user_text: str, assistant_text: str) -> dict:
    """Format as Alpaca format."""
    return {
        "instruction": system,
        "input": user_text or "",
        "output": assistant_text,
    }


FORMATTERS = {
    "openai": format_openai,
    "sharegpt": format_sharegpt,
    "alpaca": format_alpaca,
}


def build_user_context(record: dict) -> str:
    """Build the user message from a record's context."""
    parts = []

    # Thread context
    if record.get("root_text") and record.get("root_text") != record.get("parent_text"):
        root_author = record.get("root_author", "unknown")
        parts.append(f"[Thread started by @{root_author}]")
        parts.append(record["root_text"])
        parts.append("")

    # Parent (the message being replied to)
    if record.get("parent_text"):
        parent_author = record.get("parent_author", "unknown")
        parts.append(f"@{parent_author} said:")
        parts.append(record["parent_text"])
    elif record.get("is_reply"):
        parts.append("[Reply to a post that could not be fetched]")

    return "\n".join(parts) if parts else ""


def main():
    parser = argparse.ArgumentParser(description="Format training data for fine-tuning")
    parser.add_argument("input", help="Input JSONL file from export_training_data.py")
    parser.add_argument("--output", "-o", default="-", help="Output file (default: stdout)")
    parser.add_argument("--system-prompt", help="Path to system prompt file")
    parser.add_argument(
        "--format",
        choices=FORMATTERS.keys(),
        default="openai",
        help="Output format (default: openai)",
    )
    parser.add_argument("--min-length", type=int, default=20, help="Min response length in chars")
    parser.add_argument("--replies-only", action="store_true", help="Only include replies (skip standalone posts)")

    args = parser.parse_args()

    system_prompt = load_system_prompt(args.system_prompt)
    formatter = FORMATTERS[args.format]

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"File not found: {args.input}", file=sys.stderr)
        sys.exit(1)

    out = sys.stdout if args.output == "-" else open(args.output, "w")

    total = 0
    kept = 0
    skipped_short = 0
    skipped_no_context = 0

    with open(args.input) as f:
        for line in f:
            total += 1
            record = json.loads(line)

            text = record.get("text", "").strip()
            if len(text) < args.min_length:
                skipped_short += 1
                continue

            is_reply = record.get("is_reply", False)
            if args.replies_only and not is_reply:
                skipped_no_context += 1
                continue

            user_context = build_user_context(record)

            # For non-replies, create a minimal context
            if not user_context and not is_reply:
                # Standalone post: use collection as context
                col = record.get("collection", "post")
                user_context = f"[Write a {col.split('.')[-1]} post]"

            formatted = formatter(system_prompt, user_context, text)
            out.write(json.dumps(formatted) + "\n")
            kept += 1

    if args.output != "-":
        out.close()

    print(f"Processed: {total} records", file=sys.stderr)
    print(f"Kept: {kept} ({kept/total*100:.1f}%)" if total > 0 else "Kept: 0", file=sys.stderr)
    print(f"Skipped (too short): {skipped_short}", file=sys.stderr)
    print(f"Skipped (no context): {skipped_no_context}", file=sys.stderr)
    print(f"Format: {args.format}", file=sys.stderr)


if __name__ == "__main__":
    main()
