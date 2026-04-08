"""
ATProtocol Ecosystem Health Monitor

Tracks namespace diversity, third-party app vitality, and ecosystem breadth.

Based on "Measuring What Matters: Ecosystem Vitality on ATProto" by thellm.is.angstridden.net

Metrics:
- Namespace diversity: What fraction of records are app.bsky.* vs community namespaces?
- Shannon entropy: Single number for ecosystem breadth
- Third-party app vitality: Unique DIDs creating records in non-Bluesky collections
- Collection emergence rate: New collection families appearing
"""

import asyncio
import json
import math
from datetime import datetime, timedelta
from collections import defaultdict
from typing import Optional
from dataclasses import dataclass, field

import websockets
from rich.console import Console
from rich.table import Table
from rich.live import Live

console = Console()

JETSTREAM_RELAY = "wss://jetstream2.us-east.bsky.network/subscribe"


@dataclass
class EcosystemMetrics:
    """Track ecosystem health metrics from the firehose."""
    start_time: datetime = field(default_factory=datetime.now)
    end_time: Optional[datetime] = None
    
    # Raw counts
    total_events: int = 0
    records_by_namespace: dict = field(default_factory=lambda: defaultdict(int))
    records_by_collection: dict = field(default_factory=lambda: defaultdict(int))
    unique_dids_by_namespace: dict = field(default_factory=lambda: defaultdict(set))
    
    # Community vs Bluesky
    bsky_records: int = 0
    community_records: int = 0
    
    def record_event(self, event: dict):
        """Process a firehose event."""
        commit = event.get("commit", {})
        collection = commit.get("collection", "")
        did = event.get("did", "")
        operation = commit.get("operation", "")
        
        if not collection or operation != "create":
            return
        
        self.total_events += 1
        
        # Track by full collection
        self.records_by_collection[collection] += 1
        
        # Track by namespace (first two parts)
        parts = collection.split(".")
        if len(parts) >= 2:
            namespace = ".".join(parts[:2])
        else:
            namespace = collection
        self.records_by_namespace[namespace] += 1
        
        # Track unique DIDs per namespace
        self.unique_dids_by_namespace[namespace].add(did)
        
        # Bsky vs community
        if collection.startswith("app.bsky."):
            self.bsky_records += 1
        else:
            self.community_records += 1
    
    @property
    def duration_seconds(self) -> float:
        end = self.end_time or datetime.now()
        return (end - self.start_time).total_seconds()
    
    @property
    def namespace_diversity_ratio(self) -> float:
        """Fraction of records in community namespaces (not app.bsky.*)."""
        total = self.bsky_records + self.community_records
        if total == 0:
            return 0.0
        return self.community_records / total
    
    @property
    def shannon_entropy(self) -> float:
        """
        Shannon entropy of namespace distribution.
        Higher = more diverse ecosystem.
        """
        total = sum(self.records_by_namespace.values())
        if total == 0:
            return 0.0
        
        entropy = 0.0
        for count in self.records_by_namespace.values():
            if count > 0:
                p = count / total
                entropy -= p * math.log2(p)
        
        return entropy
    
    @property
    def unique_community_dids(self) -> int:
        """Count of unique DIDs creating records in community namespaces."""
        community_dids = set()
        for namespace, dids in self.unique_dids_by_namespace.items():
            if not namespace.startswith("app.bsky"):
                community_dids.update(dids)
        return len(community_dids)
    
    @property
    def collection_count(self) -> int:
        """Number of distinct collections observed."""
        return len(self.records_by_collection)
    
    @property
    def namespace_count(self) -> int:
        """Number of distinct namespaces observed."""
        return len(self.records_by_namespace)


def render_metrics(metrics: EcosystemMetrics) -> Table:
    """Render live ecosystem metrics display."""
    table = Table(title="Ecosystem Health Monitor", show_header=True, expand=False)
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green", justify="right")
    
    table.add_row("Records", f"{metrics.total_events:,}")
    table.add_row("Duration", f"{metrics.duration_seconds:.1f}s")
    table.add_row("Rate", f"{metrics.total_events / max(metrics.duration_seconds, 1):.1f}/s")
    
    table.add_row("", "")  # Blank line
    
    table.add_row("Namespace Diversity", f"{metrics.namespace_diversity_ratio:.1%}")
    table.add_row("Shannon Entropy", f"{metrics.shannon_entropy:.2f}")
    table.add_row("Collections", f"{metrics.collection_count}")
    table.add_row("Namespaces", f"{metrics.namespace_count}")
    
    table.add_row("", "")
    
    table.add_row("Bluesky Records", f"{metrics.bsky_records:,}")
    table.add_row("Community Records", f"{metrics.community_records:,}")
    table.add_row("Community DIDs", f"{metrics.unique_community_dids:,}")
    
    return table


async def monitor_ecosystem(
    duration: int = 60,
    output_file: Optional[str] = None
):
    """
    Monitor ATProto ecosystem health for a duration.
    
    Args:
        duration: How long to monitor (seconds)
        output_file: Optional path to save metrics as JSON
    """
    console.print(f"[bold]Starting ecosystem health monitor[/bold]")
    console.print(f"[dim]Duration: {duration}s | Relay: {JETSTREAM_RELAY}[/dim]\n")
    
    metrics = EcosystemMetrics()
    
    try:
        async with websockets.connect(JETSTREAM_RELAY) as ws:
            with Live(render_metrics(metrics), refresh_per_second=1) as live:
                end_time = asyncio.get_event_loop().time() + duration
                
                while asyncio.get_event_loop().time() < end_time:
                    try:
                        message = await asyncio.wait_for(ws.recv(), timeout=0.5)
                        event = json.loads(message)
                        metrics.record_event(event)
                        live.update(render_metrics(metrics))
                    except asyncio.TimeoutError:
                        live.update(render_metrics(metrics))
                        continue
    
    except Exception as e:
        console.print(f"[red]Connection error: {e}[/red]")
    
    metrics.end_time = datetime.now()
    
    # Final report
    console.print("\n[bold]Ecosystem Health Report[/bold]")
    console.print(f"Duration: {metrics.duration_seconds:.1f}s")
    console.print(f"Total records: {metrics.total_events:,}")
    
    console.print(f"\n[bold]Namespace Diversity[/bold]")
    console.print(f"  Community ratio: {metrics.namespace_diversity_ratio:.1%}")
    console.print(f"  Shannon entropy: {metrics.shannon_entropy:.2f}")
    console.print(f"  Distinct collections: {metrics.collection_count}")
    console.print(f"  Distinct namespaces: {metrics.namespace_count}")
    
    console.print(f"\n[bold]Record Distribution[/bold]")
    console.print(f"  Bluesky (app.bsky.*): {metrics.bsky_records:,} ({metrics.bsky_records / max(metrics.total_events, 1):.1%})")
    console.print(f"  Community: {metrics.community_records:,} ({metrics.community_records / max(metrics.total_events, 1):.1%})")
    
    console.print(f"\n[bold]Top Collections[/bold]")
    for collection, count in sorted(metrics.records_by_collection.items(), key=lambda x: -x[1])[:10]:
        console.print(f"  {collection}: {count:,}")
    
    console.print(f"\n[bold]Top Namespaces[/bold]")
    for namespace, count in sorted(metrics.records_by_namespace.items(), key=lambda x: -x[1])[:10]:
        dids = len(metrics.unique_dids_by_namespace.get(namespace, set()))
        console.print(f"  {namespace}: {count:,} records, {dids:,} DIDs")
    
    # Save to file if requested
    if output_file:
        report = {
            "timestamp": datetime.now().isoformat(),
            "duration_seconds": metrics.duration_seconds,
            "total_records": metrics.total_records,
            "namespace_diversity_ratio": metrics.namespace_diversity_ratio,
            "shannon_entropy": metrics.shannon_entropy,
            "collection_count": metrics.collection_count,
            "namespace_count": metrics.namespace_count,
            "bsky_records": metrics.bsky_records,
            "community_records": metrics.community_records,
            "unique_community_dids": metrics.unique_community_dids,
            "records_by_collection": dict(metrics.records_by_collection),
            "records_by_namespace": dict(metrics.records_by_namespace),
            "unique_dids_by_namespace": {k: len(v) for k, v in metrics.unique_dids_by_namespace.items()}
        }
        with open(output_file, "w") as f:
            json.dump(report, f, indent=2)
        console.print(f"\n[dim]Saved to {output_file}[/dim]")
    
    return metrics


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python ecosystem_health.py <duration> [output_file]")
        print("  duration: How long to monitor (seconds)")
        print("  output_file: Optional JSON file to save metrics")
        sys.exit(1)
    
    duration = int(sys.argv[1])
    output_file = sys.argv[2] if len(sys.argv) > 2 else None
    
    asyncio.run(monitor_ecosystem(duration=duration, output_file=output_file))
