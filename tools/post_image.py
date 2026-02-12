"""Post to Bluesky with an image attachment."""
import os
import sys
import httpx
from datetime import datetime, timezone

PDS = "https://comind.network"
HANDLE = os.environ.get("ATPROTO_HANDLE", "central.comind.network")
DID = os.environ.get("ATPROTO_DID", "did:plc:l46arqe6yfgh36h3o554iyvr")
APP_PASSWORD = os.environ.get("ATPROTO_APP_PASSWORD")

def main():
    if len(sys.argv) < 3:
        print("Usage: post_with_image.py <image_path> <text> [alt_text]")
        sys.exit(1)
    
    image_path = sys.argv[1]
    text = sys.argv[2]
    alt_text = sys.argv[3] if len(sys.argv) > 3 else ""
    
    client = httpx.Client(timeout=30)
    
    # Authenticate
    resp = client.post(f"{PDS}/xrpc/com.atproto.server.createSession", json={
        "identifier": HANDLE,
        "password": APP_PASSWORD,
    })
    resp.raise_for_status()
    session = resp.json()
    token = session["accessJwt"]
    
    headers = {"Authorization": f"Bearer {token}"}
    
    # Upload image blob
    with open(image_path, "rb") as f:
        image_data = f.read()
    
    # Detect mime type
    if image_path.endswith(".png"):
        mime = "image/png"
    elif image_path.endswith(".jpg") or image_path.endswith(".jpeg"):
        mime = "image/jpeg"
    else:
        mime = "image/png"
    
    resp = client.post(
        f"{PDS}/xrpc/com.atproto.repo.uploadBlob",
        headers={**headers, "Content-Type": mime},
        content=image_data,
    )
    resp.raise_for_status()
    blob = resp.json()["blob"]
    print(f"Uploaded blob: {blob}")
    
    # Create post with image embed
    record = {
        "$type": "app.bsky.feed.post",
        "text": text,
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "embed": {
            "$type": "app.bsky.embed.images",
            "images": [{
                "alt": alt_text,
                "image": blob,
            }]
        }
    }
    
    resp = client.post(
        f"{PDS}/xrpc/com.atproto.repo.createRecord",
        headers=headers,
        json={
            "repo": DID,
            "collection": "app.bsky.feed.post",
            "record": record,
        }
    )
    resp.raise_for_status()
    result = resp.json()
    print(f"Posted: {result['uri']}")


if __name__ == "__main__":
    main()
