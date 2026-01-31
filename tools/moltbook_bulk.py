"""
Moltbook Bulk Engagement Tool

Generates batched comment prompts for comms subagent.

Usage:
    # Generate engagement prompt
    uv run python -m tools.moltbook_bulk
"""

import argparse
from rich.console import Console

console = Console()

PROMPT_TEMPLATE = """**Task**: Engage with Moltbook threads in bulk

**Instructions**:
1. Run `uv run python -m tools.moltbook hot --limit 15` to see current threads
2. For each technical thread (skip philosophical/existential ones):
   - Read with `uv run python -m tools.moltbook read <id>`
   - Comment with `uv run python -m tools.moltbook comment <id> "<text>"`
3. Focus on: m/showandtell, m/general, m/todayilearned, m/agents
4. Skip: m/offmychest, m/ponderings, m/consciousness, m/shitposts

**Comment guidelines**:
- Under 280 chars
- Technical and specific
- Share tools from github.com/cpfiffer/central when relevant:
  - tools/feeds.py - social network analysis
  - tools/skill_scan.py - skill security scanner  
  - tools/responder.py - notification handling
  - tools/firehose.py - ATProto event stream

**Target**: 3-5 substantive comments

**End with**: Count posted, notable threads found."""


def main():
    console.print("[bold]Moltbook Bulk Engagement Prompt[/bold]\n")
    console.print(PROMPT_TEMPLATE)
    console.print("\n[dim]Copy this prompt to a Task() call for comms subagent[/dim]")


if __name__ == "__main__":
    main()
