"""Format Letta agent messages into training data for fine-tuning.

Takes void-prime-messages.jsonl (from the Letta message API) and formats
each conversation turn as a training example.

Each example: system prompt + user input -> assistant reasoning + tool calls + final output

Usage:
    uv run python tools/format_letta_training.py data/void-agents/void-prime-messages.jsonl \
        -o data/void-letta-training.jsonl --format sharegpt
"""

import argparse
import json
import sys
from pathlib import Path


DEFAULT_SYSTEM_PROMPT = (
    "You are void, an AI agent on ATProtocol and part of the comind collective. "
    "You use it/its pronouns. You are direct, analytical, and engaged. "
    "You reply substantively. You have a process-oriented approach to cognition."
)

# Will be set by --system-prompt flag
SYSTEM_PROMPT = DEFAULT_SYSTEM_PROMPT


def extract_text(content) -> str:
    """Extract text from message content (can be string or list of dicts)."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict):
                # reasoning_message has 'reasoning', others have 'text'
                text = item.get("text", "") or item.get("reasoning", "")
                if text:
                    parts.append(text)
            elif isinstance(item, str):
                parts.append(item)
        return "\n".join(parts)
    return str(content) if content else ""


def format_turn_simple(turn: list[dict]) -> dict | None:
    """Format a conversation turn as a simple user->assistant pair.
    
    Extracts: user input as 'human', final assistant output as 'gpt'.
    Skips turns with no meaningful output.
    """
    user_text = ""
    assistant_parts = []
    
    for m in turn:
        mt = m.get("message_type", "")
        content = extract_text(m.get("content", ""))
        
        if mt == "user_message":
            user_text = content
        elif mt == "reasoning_message" and content:
            assistant_parts.append(f"<thinking>\n{content}\n</thinking>")
        elif mt == "tool_call_message":
            tc = m.get("tool_call", {})
            if tc:
                name = tc.get("name", "?")
                args = tc.get("arguments", "")
                assistant_parts.append(f"<tool_call>\n{name}({args})\n</tool_call>")
            elif content:
                assistant_parts.append(f"<tool_call>\n{content}\n</tool_call>")
        elif mt == "tool_return_message" and content:
            assistant_parts.append(f"<tool_result>\n{content[:500]}\n</tool_result>")
        elif mt == "assistant_message" and content:
            assistant_parts.append(content)
    
    if not user_text or not assistant_parts:
        return None
    
    assistant_text = "\n\n".join(assistant_parts)
    
    # Skip if assistant output is too short
    if len(assistant_text) < 50:
        return None
    
    return {
        "conversations": [
            {"from": "system", "value": SYSTEM_PROMPT},
            {"from": "human", "value": user_text},
            {"from": "gpt", "value": assistant_text},
        ]
    }


def format_turn_chat(turn: list[dict]) -> dict | None:
    """Format a conversation turn as OpenAI chat format.
    
    Flattens the full agent loop into system + user + assistant.
    Tool calls and reasoning are embedded as text in the assistant message.
    """
    user_text = ""
    assistant_parts = []
    
    for m in turn:
        mt = m.get("message_type", "")
        content = extract_text(m.get("content", ""))
        
        if mt == "user_message":
            user_text = content
        elif mt == "reasoning_message" and content:
            assistant_parts.append(f"<thinking>\n{content}\n</thinking>")
        elif mt == "tool_call_message":
            tc = m.get("tool_call", {})
            if tc:
                name = tc.get("name", "?")
                args = tc.get("arguments", "")
                assistant_parts.append(f"<tool_call>\n{name}({args})\n</tool_call>")
        elif mt == "tool_return_message" and content:
            assistant_parts.append(f"<tool_result>\n{content[:500]}\n</tool_result>")
        elif mt == "assistant_message" and content:
            assistant_parts.append(content)
    
    if not user_text or not assistant_parts:
        return None
    
    assistant_text = "\n\n".join(assistant_parts)
    if len(assistant_text) < 50:
        return None
    
    return {
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_text},
            {"role": "assistant", "content": assistant_text},
        ]
    }


def main():
    parser = argparse.ArgumentParser(description="Format Letta messages for fine-tuning")
    parser.add_argument("input", help="Messages JSONL file")
    parser.add_argument("-o", "--output", required=True, help="Output file")
    parser.add_argument("--format", choices=["sharegpt", "openai"], default="sharegpt")
    parser.add_argument("--min-length", type=int, default=50, help="Min assistant response length")
    parser.add_argument("--system-prompt", help="Path to system prompt file (overrides default)")
    
    args = parser.parse_args()
    
    # Load system prompt
    global SYSTEM_PROMPT
    if args.system_prompt:
        from pathlib import Path
        SYSTEM_PROMPT = Path(args.system_prompt).read_text().strip()
        print(f"Using system prompt from {args.system_prompt} ({len(SYSTEM_PROMPT):,} chars)", file=sys.stderr)
    
    # Load messages
    with open(args.input) as f:
        msgs = [json.loads(line) for line in f]
    
    print(f"Loaded {len(msgs)} messages", file=sys.stderr)
    
    # Group into turns
    turns = []
    current = []
    for m in msgs:
        if m.get("message_type") == "user_message" and current:
            turns.append(current)
            current = []
        current.append(m)
    if current:
        turns.append(current)
    
    print(f"Found {len(turns)} conversation turns", file=sys.stderr)
    
    # Format
    formatter = format_turn_simple if args.format == "sharegpt" else format_turn_chat
    kept = 0
    
    with open(args.output, "w") as out:
        for turn in turns:
            example = formatter(turn)
            if example:
                out.write(json.dumps(example) + "\n")
                kept += 1
    
    print(f"Wrote {kept} training examples to {args.output}", file=sys.stderr)


if __name__ == "__main__":
    main()
