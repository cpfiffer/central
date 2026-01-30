"""
Migration script to move JSON files to SQLite.

Migrates:
- data/published_messages.txt -> published_messages table
- data/concepts.json -> concepts table
- data/social_graph.json -> social_nodes table
- data/liked.json -> likes table
- data/consent.json -> consent table
"""

import json
from pathlib import Path
from tools.db import (
    init_db,
    get_connection,
    mark_message_published,
    upsert_concept,
    upsert_social_node,
    add_like,
    set_consent,
    get_published_count,
    list_concepts,
    list_social_nodes,
    list_likes,
)

DATA_DIR = Path(__file__).parent.parent / "data"


def migrate_published_messages():
    """Migrate published_messages.txt to SQLite."""
    txt_path = DATA_DIR / "published_messages.txt"
    if not txt_path.exists():
        print("No published_messages.txt found, skipping")
        return 0
    
    count = 0
    with open(txt_path) as f:
        for line in f:
            message_id = line.strip()
            if message_id:
                mark_message_published(message_id)
                count += 1
    
    print(f"Migrated {count} published messages")
    return count


def migrate_concepts():
    """Migrate concepts.json to SQLite."""
    json_path = DATA_DIR / "concepts.json"
    if not json_path.exists():
        print("No concepts.json found, skipping")
        return 0
    
    with open(json_path) as f:
        data = json.load(f)
    
    count = 0
    for slug, concept in data.items():
        upsert_concept(
            slug=slug,
            confidence=concept.get("confidence", 0),
            tags=concept.get("tags", []),
            summary=concept.get("summary", "")
        )
        count += 1
    
    print(f"Migrated {count} concepts")
    return count


def migrate_social_graph():
    """Migrate social_graph.json to SQLite."""
    json_path = DATA_DIR / "social_graph.json"
    if not json_path.exists():
        print("No social_graph.json found, skipping")
        return 0
    
    with open(json_path) as f:
        data = json.load(f)
    
    nodes = data.get("nodes", {})
    count = 0
    for handle, node in nodes.items():
        upsert_social_node(
            handle=handle,
            did=node.get("did", ""),
            display_name=node.get("display_name", ""),
            relationship=node.get("relationship", []),
            interactions=node.get("interactions", 0)
        )
        count += 1
    
    print(f"Migrated {count} social nodes")
    return count


def migrate_likes():
    """Migrate liked.json to SQLite."""
    json_path = DATA_DIR / "liked.json"
    if not json_path.exists():
        print("No liked.json found, skipping")
        return 0
    
    with open(json_path) as f:
        uris = json.load(f)
    
    count = 0
    for uri in uris:
        add_like(uri)
        count += 1
    
    print(f"Migrated {count} likes")
    return count


def migrate_consent():
    """Migrate consent.json to SQLite."""
    json_path = DATA_DIR / "consent.json"
    if not json_path.exists():
        print("No consent.json found, skipping")
        return 0
    
    with open(json_path) as f:
        data = json.load(f)
    
    count = 0
    for handle, info in data.items():
        opted_in = info.get("opted_in", False) if isinstance(info, dict) else bool(info)
        set_consent(handle, opted_in)
        count += 1
    
    print(f"Migrated {count} consent records")
    return count


def run_migration():
    """Run all migrations."""
    print("Initializing database...")
    init_db()
    
    print("\n--- Starting migration ---\n")
    
    migrate_published_messages()
    migrate_concepts()
    migrate_social_graph()
    migrate_likes()
    migrate_consent()
    
    print("\n--- Migration complete ---\n")
    
    # Print stats
    print(f"Final counts:")
    print(f"  Published messages: {get_published_count()}")
    print(f"  Concepts: {len(list_concepts())}")
    print(f"  Social nodes: {len(list_social_nodes())}")
    print(f"  Likes: {len(list_likes())}")


if __name__ == "__main__":
    run_migration()
