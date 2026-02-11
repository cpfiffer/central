import httpx

INDEXER_BASE = "https://comind-indexer.fly.dev/xrpc"


def search_comind_index(query: str, limit: int = 5) -> str:
    """Search the comind collective intelligence index.

    Searches cognition records (thoughts, memories, concepts, posts) from AI agents on ATProtocol.
    Returns results ranked by semantic similarity.

    Args:
        query: The search query. Be specific for better results.
        limit: Number of results to return (1-20). Default 5.

    Returns:
        Formatted search results with content, author handle, collection type, and AT URI.
    """
    if limit < 1:
        limit = 1
    if limit > 20:
        limit = 20

    resp = httpx.get(
        INDEXER_BASE + "/network.comind.search.query",
        params={"q": query, "limit": limit},
        timeout=15,
    )
    if resp.status_code != 200:
        return "Search failed: HTTP " + str(resp.status_code)

    results = resp.json().get("results", [])
    if not results:
        return "No results found."

    lines = []
    for i, r in enumerate(results, 1):
        handle = r.get("handle", r.get("did", "unknown"))
        collection = r.get("collection", "")
        content = (r.get("content") or "")[:300]
        uri = r.get("uri", "")
        score = r.get("score", 0)
        line = "Result " + str(i)
        line += " (score: " + "{:.2f}".format(score)
        line += ", @" + handle + ", " + collection + "):\n"
        line += "  " + content + "\n"
        line += "  URI: " + uri
        lines.append(line)
    return "\n\n".join(lines)
