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
import { 
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

  // Process in batches
  const batches = chunk(pending, 5);
  
  for (let i = 0; i < batches.length; i++) {
    const batch = batches[i];
    console.log(`\nProcessing batch ${i + 1}/${batches.length} (${batch.length} items)...`);
    
    // Write drafts directly for each notification
    for (const item of batch) {
      try {
        // Determine output directory based on priority
        const isHighPriority = ["HIGH", "CRITICAL"].includes(item.priority);
        const outputDir = isHighPriority ? REVIEW_DRAFTS : X_DRAFTS;
        const filename = `${isHighPriority ? "x-" : ""}reply-${item.id}.txt`;
        const filePath = path.join(outputDir, filename);

        // Build YAML frontmatter
        const frontmatter = {
          platform: "x",
          type: "reply",
          reply_to: item.id,
          author: item.author,
          priority: item.priority,
          original_text: item.text.substring(0, 200),
          drafted_at: new Date().toISOString(),
        };

        // Build draft content with frontmatter
        let content = `---\n${yaml.stringify(frontmatter)}---\n`;
        content += `[DRAFT NEEDED] @${item.author}: "${item.text.substring(0, 150)}"\n`;

        // Ensure directory exists
        if (!fs.existsSync(outputDir)) {
          fs.mkdirSync(outputDir, { recursive: true });
        }

        // Write draft file
        fs.writeFileSync(filePath, content);
        console.log(`  ✓ Draft: ${filename}`);
      } catch (error) {
        console.error(`  ✗ Failed to write draft for ${item.id}:`, error);
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
