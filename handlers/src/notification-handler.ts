/**
 * Notification Handler
 * 
 * Reads queue from Python responder, spawns comms to draft responses.
 * Comms writes drafts directly to the drafts folder.
 * 
 * Usage:
 *   1. First run: uv run python -m tools.responder queue  (fetches notifications)
 *   2. Then run: npm run fetch  (this script - spawns comms to draft)
 *   3. Finally: npm run publish  (posts the drafts)
 */

import { createSession } from "@letta-ai/letta-code-sdk";
import * as fs from "fs";
import * as path from "path";
import * as yaml from "yaml";
import { 
  COMMS_AGENT_ID, 
  getPriority,
  BLUESKY_DRAFTS,
  REVIEW_DRAFTS,
  PUBLISHED_DIR,
} from "./config.js";

interface QueueItem {
  priority: string;
  author: string;
  text: string;
  uri: string;
  cid: string;
  reply_root?: { uri: string; cid: string };
  reply_parent?: { uri: string; cid: string };
  response?: string;
  action: string;
  queued_at: string;
}

/**
 * Check if we've already processed this notification
 */
function alreadyProcessed(id: string): boolean {
  const patterns = [
    path.join(BLUESKY_DRAFTS, `reply-${id}.txt`),
    path.join(REVIEW_DRAFTS, `bluesky-reply-${id}.txt`),
  ];
  
  for (const p of patterns) {
    if (fs.existsSync(p)) return true;
  }
  
  // Check published
  const publishedFiles = fs.readdirSync(PUBLISHED_DIR).filter(f => f.includes(id));
  if (publishedFiles.length > 0) return true;
  
  return false;
}

/**
 * Chunk array into batches
 */
function chunk<T>(arr: T[], size: number): T[][] {
  const chunks: T[][] = [];
  for (let i = 0; i < arr.length; i += size) {
    chunks.push(arr.slice(i, i + size));
  }
  return chunks;
}

/**
 * Main handler
 */
async function processNotifications() {
  console.log(`[${new Date().toISOString()}] Starting notification handler...`);

  // Read queue from Python responder
  const queuePath = path.join(process.cwd(), "..", "drafts", "queue.yaml");
  
  if (!fs.existsSync(queuePath)) {
    console.log("No queue file. Run: uv run python -m tools.responder queue");
    return;
  }

  const queueContent = fs.readFileSync(queuePath, "utf-8");
  const queue: QueueItem[] = yaml.parse(queueContent) || [];

  // Filter to items needing processing
  const pending = queue.filter(item => {
    if (item.action !== "reply") return false;
    if (item.response) return false; // Already has response
    if (item.priority === "SKIP") return false;
    
    const id = item.uri?.split("/").pop() || item.cid;
    if (alreadyProcessed(id)) {
      console.log(`Skipping ${id}: already processed`);
      return false;
    }
    
    return true;
  });

  console.log(`${pending.length} notifications to process (${queue.length} total in queue)`);

  if (pending.length === 0) {
    console.log("No new notifications. Done.");
    return;
  }

  // Process in batches via comms
  const batches = chunk(pending, 5);
  
  for (let i = 0; i < batches.length; i++) {
    const batch = batches[i];
    console.log(`\nProcessing batch ${i + 1}/${batches.length} (${batch.length} items)...`);
    
    const notificationList = batch.map(item => {
      const id = item.uri?.split("/").pop() || item.cid;
      return {
        id,
        platform: "bluesky",
        uri: item.uri,
        cid: item.cid,
        author: item.author,
        priority: item.priority,
        text: item.text,
        reply_root: item.reply_root,
        reply_parent: item.reply_parent || { uri: item.uri, cid: item.cid },
      };
    });

    const commsPrompt = `
Process these Bluesky notifications and write draft files.

For each notification:
1. Decide: reply or skip
2. If replying, write a draft file to the appropriate location

**File locations:**
- CRITICAL/HIGH priority → ../drafts/review/bluesky-reply-{id}.txt
- MEDIUM/LOW priority → ../drafts/bluesky/reply-{id}.txt

**File format (YAML frontmatter + content):**
\`\`\`
---
platform: bluesky
type: reply
reply_to: {uri}
reply_to_cid: {cid}
reply_root: {root.uri or same as reply_to if top-level}
reply_root_cid: {root.cid or same as reply_to_cid}
author: {author}
priority: {priority}
original_text: "{text}"
drafted_at: {ISO timestamp}
---
Your response here (under 280 chars, compressed voice)
\`\`\`

**Guidelines:**
- Compressed, opinionated voice
- Under 280 chars
- NEVER claim actions completed without proof (URLs, hashes)
- Skip notifications that don't warrant a response

**Notifications to process:**
${JSON.stringify(notificationList, null, 2)}

Write each file and report what you did.
`;

    try {
      const session = createSession(COMMS_AGENT_ID, {
        allowedTools: ["Read", "Write", "Glob"],
        permissionMode: "bypassPermissions",
        cwd: process.cwd(),
      });
      
      // Timeout wrapper - 90 seconds per batch
      const BATCH_TIMEOUT_MS = 90000;
      const timeoutPromise = new Promise<void>((_, reject) => {
        setTimeout(() => reject(new Error(`Batch timeout after ${BATCH_TIMEOUT_MS/1000}s`)), BATCH_TIMEOUT_MS);
      });
      
      const processPromise = async () => {
        await session.send(commsPrompt);
        
        for await (const msg of session.stream()) {
          if (msg.type === "assistant") {
            process.stdout.write(msg.content);
          }
          if (msg.type === "result") {
            console.log("\n✓ Batch complete");
          }
        }
      };
      
      await Promise.race([processPromise(), timeoutPromise]);
      session.close();
    } catch (error) {
      if (error instanceof Error && error.message.includes("timeout")) {
        console.error(`\n⚠ Batch ${i + 1} timed out. Items will retry next run.`);
      } else {
        console.error("Error invoking comms:", error);
      }
    }
  }

  // Clean up queue: remove items that have been processed (have draft files)
  const remainingQueue = queue.filter(item => {
    const id = item.uri?.split("/").pop() || item.cid;
    return !alreadyProcessed(id) && item.priority !== "SKIP";
  });
  
  if (remainingQueue.length < queue.length) {
    const removed = queue.length - remainingQueue.length;
    fs.writeFileSync(queuePath, yaml.stringify(remainingQueue));
    console.log(`Cleaned queue: removed ${removed} processed items (${remainingQueue.length} remaining)`);
  }

  console.log(`\n[${new Date().toISOString()}] Handler complete.`);
  console.log("Next: npm run publish (or npm run publish:all for review items)");
}

processNotifications().catch(console.error);
