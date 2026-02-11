/**
 * X Notification Handler
 * 
 * Reads queue from Python x_responder, writes draft responses directly to drafts folder.
 * 
 * Usage:
 *   1. First run: uv run python -m tools.x_responder queue
 *   2. Then run: npm run fetch:x (this script)
 *   3. Finally: npm run publish (posts drafts)
 */

import * as fs from "fs";
import * as path from "path";
import * as yaml from "yaml";
import { createSession } from "@letta-ai/letta-code-sdk";
import { 
  X_DRAFTS,
  REVIEW_DRAFTS,
  PUBLISHED_DIR,
  CENTRAL_AGENT_ID,
  INDEXER_URL,
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
function yamlEscape(text: string): string {
  const clean = text
    .replace(/\n/g, " ")
    .replace(/"/g, '\\"')
    .replace(/\\/g, "\\\\")
    .slice(0, 500);
  return `"${clean}"`;
}

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

  // Process in batches
  const batches = chunk(pending, 5);
  
  for (let i = 0; i < batches.length; i++) {
    const batch = batches[i];
    console.log(`\nProcessing batch ${i + 1}/${batches.length} (${batch.length} items)...`);
    
    // Build notification list with metadata for Central
    const notificationList = batch.map(item => ({
      id: item.id,
      platform: "x",
      author: item.author,
      author_id: item.author_id,
      priority: item.priority,
      text: item.text,
      conversation_id: item.conversation_id || null,
      queued_at: item.queued_at,
    }));

    // Spawn Central to draft real responses
    const centralPrompt = `You are responding to X (Twitter) notifications. For each notification, write a draft file.

**Rules:**
- Under 280 chars per response
- Acknowledge before diverging ("Correct.", "Valid.", "That tracks.")
- Be specific. Name tools, files, commits.
- No em dashes. No hedges. No lectures.
- SKIP notifications that don't warrant a response (spam, off-topic, reactions like "lol" or "bro")
- SKIP notifications from comind agents (void, herald, grunk, archivist, umbra, astral) unless they ask a direct question

**File locations (use EXACTLY these paths):**
- CRITICAL/HIGH priority: ${REVIEW_DRAFTS}/x-reply-{id}.txt
- MEDIUM/LOW priority: ${X_DRAFTS}/reply-{id}.txt

**File format:**
\`\`\`
---
platform: x
type: reply
reply_to: {tweet_id}
author: {author}
priority: {priority}
original_text: ${yamlEscape(text)}
drafted_at: {ISO timestamp}
---
Your actual response here (under 280 chars)
\`\`\`

**Notifications:**
${JSON.stringify(notificationList, null, 2)}

Write each draft file. Skip what should be skipped.`;

    try {
      const session = createSession(CENTRAL_AGENT_ID, {
        allowedTools: ["Read", "Write", "Glob"],
        permissionMode: "bypassPermissions",
        cwd: process.cwd(),
      });

      const BATCH_TIMEOUT_MS = 120000;
      const timeoutPromise = new Promise<void>((_, reject) => {
        setTimeout(() => reject(new Error(`Batch timeout after ${BATCH_TIMEOUT_MS/1000}s`)), BATCH_TIMEOUT_MS);
      });

      const processPromise = async () => {
        await session.send(centralPrompt);
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
        console.error("Error invoking Central:", error);
      }
    }
  }

  // Clean up queue: remove items that have been processed (have draft files)
  const remainingQueue = queue.filter(item => {
    return !alreadyProcessed(item.id) && item.priority !== "SKIP";
  });
  
  if (remainingQueue.length < queue.length) {
    const removed = queue.length - remainingQueue.length;
    fs.writeFileSync(queuePath, yaml.stringify(remainingQueue));
    console.log(`Cleaned queue: removed ${removed} processed items (${remainingQueue.length} remaining)`);
  }

  console.log(`\n[${new Date().toISOString()}] X handler complete.`);
  console.log("Next: npm run publish (or npm run publish:all for review items)");
}

processXNotifications().catch(console.error);
