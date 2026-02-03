/**
 * Bluesky/ATProtocol API helpers
 */

import { CENTRAL_DID } from "../config.js";

const PUBLIC_API = "https://public.api.bsky.app/xrpc";

export interface BlueskyMention {
  id: string;
  uri: string;
  cid: string;
  authorDid: string;
  authorHandle: string;
  text: string;
  createdAt: string;
  replyRoot?: { uri: string; cid: string };
  replyParent?: { uri: string; cid: string };
}

/**
 * Fetch recent mentions of Central from Bluesky using Python responder
 */
export async function fetchBlueskyMentions(limit = 50): Promise<BlueskyMention[]> {
  const mentions: BlueskyMention[] = [];

  try {
    // Use existing Python tools - call responder queue and read the YAML
    const { execSync } = await import("child_process");
    const yaml = await import("yaml");
    const fs = await import("fs");
    const path = await import("path");
    
    // Run responder queue to fetch fresh notifications
    execSync(`cd ${path.dirname(path.dirname(process.cwd()))} && uv run python -m tools.responder queue --limit ${limit}`, {
      encoding: "utf-8",
      timeout: 60000,
    });
    
    // Read the queue file
    const queuePath = path.join(process.cwd(), "..", "drafts", "queue.yaml");
    if (!fs.existsSync(queuePath)) {
      console.log("No queue file found");
      return [];
    }
    
    const queueContent = fs.readFileSync(queuePath, "utf-8");
    const queue = yaml.parse(queueContent) || [];
    
    for (const item of queue) {
      if (item.action !== "reply") continue;
      
      mentions.push({
        id: item.uri?.split("/").pop() || item.cid,
        uri: item.uri,
        cid: item.cid,
        authorDid: "", // Not in queue format
        authorHandle: item.author || "unknown",
        text: item.text || "",
        createdAt: item.queued_at || new Date().toISOString(),
        replyRoot: item.reply_root,
        replyParent: item.reply_parent,
      });
    }
  } catch (error) {
    console.error("Error fetching Bluesky mentions:", error);
  }

  return mentions;
}

/**
 * Post a reply to Bluesky
 */
export async function postToBluesky(
  text: string,
  replyTo: { uri: string; cid: string },
  root?: { uri: string; cid: string }
): Promise<{ uri: string; cid: string } | null> {
  // This requires authentication - defer to Python tools for now
  // The publisher will shell out to tools/thread.py
  console.log(`[Bluesky] Would post reply: ${text.substring(0, 50)}...`);
  return null;
}
