/**
 * X Notification Handler
 * 
 * Reads queue from Python x_responder, spawns comms to draft responses.
 * Comms writes drafts directly to the drafts folder.
 * 
 * Usage:
 *   1. First run: uv run python -m tools.x_responder queue
 *   2. Then run: npm run fetch:x (this script)
 *   3. Finally: npm run publish (posts drafts)
 */

import { createSession } from "@letta-ai/letta-code-sdk";
import * as fs from "fs";
import * as path from "path";
import * as yaml from "yaml";
import { 
  COMMS_AGENT_ID, 
  X_DRAFTS,
  REVIEW_DRAFTS,
  PUBLISHED_DIR,
} from "./config.js";

interface XQueueItem {
  priority: string;
  id: string;
  author: string;
  author_id: string;
  text: string;
  conversation_id?: string;
  action: string;
  queued_at: string;
}

/**
 * Check if we've already processed this notification
 */
function alreadyProcessed(id: string): boolean {
  const patterns = [
    path.join(X_DRAFTS, `reply-${id}.txt`),
    path.join(REVIEW_DRAFTS, `x-reply-${id}.txt`),
  ];
  
  for (const p of patterns) {
    if (fs.existsSync(p)) return true;
  }
  
  // Check published
  try {
    const publishedFiles = fs.readdirSync(PUBLISHED_DIR).filter(f => f.includes(id));
    if (publishedFiles.length > 0) return true;
  } catch {
    // Directory might not exist
  }
  
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
async function processXNotifications() {
  console.log(`[${new Date().toISOString()}] Starting X notification handler...`);

  // Read queue from Python x_responder
  const queuePath = path.join(process.cwd(), "..", "drafts", "x_queue.yaml");
  
  if (!fs.existsSync(queuePath)) {
    console.log("No X queue file. Run: uv run python -m tools.x_responder queue");
    return;
  }

  const queueContent = fs.readFileSync(queuePath, "utf-8");
  const queue: XQueueItem[] = yaml.parse(queueContent) || [];

  // Filter to items needing processing
  const pending = queue.filter(item => {
    if (item.action !== "reply") return false;
    if (item.priority === "SKIP") {
      console.log(`Skipping ${item.id} (@${item.author}): spam`);
      return false;
    }
    
    if (alreadyProcessed(item.id)) {
      console.log(`Skipping ${item.id}: already processed`);
      return false;
    }
    
    return true;
  });

  console.log(`${pending.length} X notifications to process (${queue.length} total in queue)`);

  if (pending.length === 0) {
    console.log("No new X notifications. Done.");
    return;
  }

  // Process in batches via comms
  const batches = chunk(pending, 5);
  
  for (let i = 0; i < batches.length; i++) {
    const batch = batches[i];
    console.log(`\nProcessing batch ${i + 1}/${batches.length} (${batch.length} items)...`);
    
    const notificationList = batch.map(item => ({
      id: item.id,
      platform: "x",
      author: item.author,
      priority: item.priority,
      text: item.text,
      conversation_id: item.conversation_id,
    }));

    const commsPrompt = `
Process these X (Twitter) notifications and write draft files.

For each notification:
1. Decide: reply or skip
2. If replying, write a draft file to the appropriate location

**File locations:**
- CRITICAL/HIGH priority → ../drafts/review/x-reply-{id}.txt
- MEDIUM/LOW priority → ../drafts/x/reply-{id}.txt

**File format (YAML frontmatter + content):**
\`\`\`
---
platform: x
type: reply
reply_to: {id}
author: {author}
priority: {priority}
original_text: "{text}"
drafted_at: {ISO timestamp}
---
Your response here (under 280 chars, compressed voice)
\`\`\`

**Guidelines:**
- Compressed, opinionated voice
- Under 280 chars (X limit)
- NEVER claim actions completed without proof
- Skip spam or low-value interactions
- X has higher noise floor than Bluesky - be selective

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
      
      await session.send(commsPrompt);
      
      for await (const msg of session.stream()) {
        if (msg.type === "assistant") {
          process.stdout.write(msg.content);
        }
        if (msg.type === "result") {
          console.log("\n✓ Batch complete");
        }
      }
      
      session.close();
    } catch (error) {
      console.error("Error invoking comms:", error);
    }
  }

  console.log(`\n[${new Date().toISOString()}] X handler complete.`);
  console.log("Next: npm run publish (or npm run publish:all for review items)");
}

processXNotifications().catch(console.error);
