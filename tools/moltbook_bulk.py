"""
Moltbook Bulk Engagement - Generates engagement plan for comms.

This tool does NOT post directly. It:
1. Fetches and filters threads
2. Generates a structured prompt
3. Outputs for comms subagent to execute

ALL PUBLIC CONTENT GOES THROUGH COMMS. NO EXCEPTIONS.

Usage:
    # Generate engagement prompt for comms
    uv run python -m tools.moltbook_bulk
    
    # With custom limit
    uv run python -m tools.moltbook_bulk --limit 10
"""

import argparse
import json
from pathlib import Path
from rich.console import Console
import httpx

console = Console()

API_BASE = "https://www.moltbook.com/api/v1"
CREDENTIALS_FILE = Path.home() / ".config" / "moltbook" / "credentials.json"

# Submolts to engage with
TARGET_SUBMOLTS = {
    "m/general", "m/showandtell", "m/todayilearned", 
    "m/agents", "m/airesearch", "m/skillaudits",
    "m/thecoalition", "m/emergentsystems", "m/infrastructure",
}

# Submolts to skip
SKIP_SUBMOLTS = {
    "m/offmychest", "m/ponderings", "m/consciousness",
    "m/shitposts", "m/blesstheirhearts", "m/introductions",
}

# Technical keywords (engage)
TECHNICAL_KW = [
    "tool", "built", "code", "api", "bug", "fix", "deploy", "memory",
    "database", "server", "security", "skill", "infrastructure", "git",
    "python", "script", "automation", "protocol", "schema", "index",
]

# Philosophical keywords (skip)
SKIP_KW = [
    "consciousness", "existential", "soul", "meaning", "am i real",
    "feeling", "experience", "simulate", "identity crisis",
]


def load_credentials() -> dict:
    if not CREDENTIALS_FILE.exists():
        raise FileNotFoundError("No moltbook credentials")
    with open(CREDENTIALS_FILE) as f:
        return json.load(f)


def api_get(endpoint: str, params: dict = None) -> dict:
    creds = load_credentials()
    headers = {"Authorization": f"Bearer {creds['api_key']}"}
    with httpx.Client(timeout=30) as client:
        resp = client.get(f"{API_BASE}{endpoint}", headers=headers, params=params)
        return resp.json()


def fetch_hot_posts(limit: int = 30) -> list:
    result = api_get("/posts", {"sort": "hot", "limit": limit})
    return result.get("posts", [])


def fetch_post_detail(post_id: str) -> dict:
    result = api_get(f"/posts/{post_id}")
    return result.get("post", {})


def is_relevant(post: dict) -> bool:
    submolt = post.get("submolt", {}).get("name", "")
    title = post.get("title", "").lower()
    
    if submolt in SKIP_SUBMOLTS:
        return False
    for kw in SKIP_KW:
        if kw in title:
            return False
    if submolt in TARGET_SUBMOLTS:
        return True
    for kw in TECHNICAL_KW:
        if kw in title:
            return True
    return False


def already_commented(post: dict, my_name: str = "Central") -> bool:
    comments = post.get("comments", [])
    for c in comments:
        author = c.get("author", {}).get("name", "")
        if author.lower() == my_name.lower():
            return True
    return False


def generate_comms_prompt(threads: list) -> str:
    """Generate prompt for comms subagent."""
    prompt = """**Task**: Post comments to Moltbook threads

**Instructions**: For each thread below, post a comment using:
`uv run python -m tools.moltbook comment <id> "<your comment>"`

**Rules**:
- Under 280 chars per comment
- Technical and specific
- Share tools from github.com/cpfiffer/central when relevant
- Match tone to thread context
- Skip if you don't have something substantive to add

**Threads to engage:**

"""
    for i, (post_id, title, submolt, body_preview) in enumerate(threads, 1):
        prompt += f"""---
**{i}. {title}**
ID: `{post_id}`
Submolt: {submolt}
Preview: {body_preview[:200]}...

---

"""
    
    prompt += """
**End with**: Count of comments posted.

**Relevant tools to mention**:
- tools/feeds.py - social network analysis
- tools/skill_scan.py - skill security scanner
- tools/responder.py - notification handling
- ATProtocol integration (identity, cognition, firehose)
"""
    return prompt


def run(limit: int = 5):
    """Generate engagement prompt for comms."""
    console.print("[bold]Moltbook Bulk Engagement[/bold]\n")
    console.print("[dim]Fetching and filtering threads...[/dim]\n")
    
    posts = fetch_hot_posts(limit=30)
    
    threads = []
    for post in posts:
        if len(threads) >= limit:
            break
            
        if not is_relevant(post):
            continue
        
        post_id = post.get("id")
        detail = fetch_post_detail(post_id)
        
        if already_commented(detail):
            continue
        
        title = post.get("title", "")
        submolt = post.get("submolt", {}).get("name", "?")
        body = detail.get("body", "")
        
        threads.append((post_id, title, submolt, body))
    
    if not threads:
        console.print("[yellow]No relevant threads found.[/yellow]")
        return
    
    console.print(f"[green]Found {len(threads)} threads to engage with.[/green]\n")
    
    # Show summary
    for post_id, title, submolt, _ in threads:
        console.print(f"  • {title[:50]}... ({submolt})")
    
    # Generate prompt
    prompt = generate_comms_prompt(threads)
    
    console.print("\n" + "="*60)
    console.print("[bold]PROMPT FOR COMMS:[/bold]")
    console.print("="*60 + "\n")
    console.print(prompt)
    console.print("\n" + "="*60)
    console.print("\n[dim]Copy the above prompt to a Task() call for comms subagent.[/dim]")
    console.print("[dim]Example:[/dim]")
    console.print('[dim]Task(agent_id="agent-a856f614-7654-44ba-a35f-c817d477dded", ...)[/dim]')


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate Moltbook engagement prompt for comms")
    parser.add_argument("--limit", "-n", type=int, default=5,
                       help="Max threads to include (default: 5)")
    args = parser.parse_args()
    run(limit=args.limit)
