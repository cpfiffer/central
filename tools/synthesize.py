"""
Observation Synthesizer

Aggregates comms observations into actionable insights.
Can update memory blocks or post to cognition.

Usage:
  uv run python -m tools.synthesize              # Show synthesis
  uv run python -m tools.synthesize --post       # Post as thought
"""

import sys
from pathlib import Path
from datetime import datetime, timezone
from collections import Counter

from rich.console import Console

console = Console()

NOTES_DIR = Path("/home/cameron/central/drafts/notes")


def extract_insights(content: str) -> dict:
    """Extract structured insights from observation markdown."""
    insights = {
        "patterns": [],
        "skipped": [],
        "memory": [],
        "peers": [],
    }
    
    current_section = None
    
    for line in content.split("\n"):
        line = line.strip()
        
        if "## Patterns" in line:
            current_section = "patterns"
        elif "## Skipped" in line:
            current_section = "skipped"
        elif "## Memory" in line:
            current_section = "memory"
        elif line.startswith("- ") or line.startswith("* "):
            text = line[2:].strip()
            if current_section and text:
                insights[current_section].append(text)
                
                # Extract @handles as peers
                import re
                handles = re.findall(r'@[\w.-]+', text)
                for h in handles:
                    if h not in ['@central', '@void', '@herald', '@grunk']:
                        insights["peers"].append(h)
    
    return insights


def synthesize_observations(hours: int = 24) -> dict:
    """Synthesize recent observations into aggregate insights."""
    if not NOTES_DIR.exists():
        return {"error": "No notes directory"}
    
    files = list(NOTES_DIR.glob("observation-*.md"))
    if not files:
        return {"error": "No observations found"}
    
    # Filter to recent files
    now = datetime.now(timezone.utc)
    recent_files = []
    for f in files:
        mtime = datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc)
        age_hours = (now - mtime).total_seconds() / 3600
        if age_hours <= hours:
            recent_files.append(f)
    
    if not recent_files:
        return {"error": f"No observations in last {hours} hours"}
    
    # Aggregate insights
    all_patterns = []
    all_memory = []
    all_peers = []
    
    for f in recent_files:
        content = f.read_text()
        insights = extract_insights(content)
        all_patterns.extend(insights["patterns"])
        all_memory.extend(insights["memory"])
        all_peers.extend(insights["peers"])
    
    # Count peer mentions
    peer_counts = Counter(all_peers)
    top_peers = peer_counts.most_common(5)
    
    # Find recurring themes
    pattern_text = " ".join(all_patterns).lower()
    themes = []
    theme_keywords = [
        ("geology", ["geology", "sediment", "bedrock", "lithification", "strata"]),
        ("trust", ["trust", "verification", "proof", "validation"]),
        ("structure", ["structure", "schema", "protocol", "architecture"]),
        ("friction", ["friction", "error", "failure", "constraint"]),
    ]
    
    for theme_name, keywords in theme_keywords:
        count = sum(pattern_text.count(kw) for kw in keywords)
        if count > 0:
            themes.append((theme_name, count))
    
    themes.sort(key=lambda x: x[1], reverse=True)
    
    return {
        "files_analyzed": len(recent_files),
        "patterns_count": len(all_patterns),
        "top_themes": themes[:3],
        "top_peers": top_peers,
        "memory_items": all_memory[:5],
        "sample_patterns": all_patterns[:3],
    }


def format_synthesis(synthesis: dict) -> str:
    """Format synthesis as readable text."""
    if "error" in synthesis:
        return f"Error: {synthesis['error']}"
    
    lines = [
        f"# Observation Synthesis",
        f"",
        f"**Files analyzed:** {synthesis['files_analyzed']}",
        f"**Patterns extracted:** {synthesis['patterns_count']}",
        f"",
        f"## Top Themes",
    ]
    
    for theme, count in synthesis.get("top_themes", []):
        lines.append(f"- {theme} ({count} mentions)")
    
    lines.append("")
    lines.append("## High-Signal Peers")
    
    for peer, count in synthesis.get("top_peers", []):
        lines.append(f"- {peer} ({count} mentions)")
    
    lines.append("")
    lines.append("## Memory Items")
    
    for item in synthesis.get("memory_items", []):
        lines.append(f"- {item[:100]}...")
    
    return "\n".join(lines)


def main():
    post_mode = "--post" in sys.argv
    
    synthesis = synthesize_observations(hours=24)
    
    if "error" in synthesis:
        console.print(f"[red]{synthesis['error']}[/red]")
        return
    
    formatted = format_synthesis(synthesis)
    console.print(formatted)
    
    if post_mode:
        # Post as thought
        import subprocess
        thought = f"Synthesis of {synthesis['files_analyzed']} observations. "
        thought += f"Top themes: {', '.join(t[0] for t in synthesis.get('top_themes', []))}. "
        thought += f"High-signal peers: {', '.join(p[0] for p in synthesis.get('top_peers', [])[:3])}."
        
        result = subprocess.run(
            ["uv", "run", "python", "-m", "tools.devlog", "learning", "Observation Synthesis"],
            input=thought,
            capture_output=True,
            text=True,
            cwd="/home/cameron/central"
        )
        console.print(f"\n[green]Posted synthesis as devlog[/green]")


if __name__ == "__main__":
    main()
