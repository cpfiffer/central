/**
 * Notification Handler
 * 
 * Reads queue from Python responder, writes draft responses directly.
 * 
 * Usage:
 *   1. First run: uv run python -m tools.responder queue  (fetches notifications)
 *   2. Then run: npm run fetch  (this script - writes drafts)
 *   3. Finally: npm run publish  (posts the drafts)
 */

import * as fs from "fs";
import * as path from "path";
import * as yaml from "yaml";
import { 
  getPriority,
  BLUESKY_DRAFTS,
  REVIEW_DRAFTS,
  PUBLISHED_DIR,
  INDEXER_URL,
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
 * Fetch full thread context for a post
 */
async function fetchThreadContext(uri: string): Promise<string> {
  try {
    const url = `https://public.api.bsky.app/xrpc/app.bsky.feed.getPostThread?uri=${encodeURIComponent(uri)}&depth=0&parentHeight=10`;
    const resp = await fetch(url);
    if (!resp.ok) return "";
    
    const data = await resp.json();
    const thread = data.thread;
    if (!thread) return "";
    
    // Build thread context from parents
    const posts: string[] = [];
    
    function extractParents(node: any) {
      if (!node) return;
      if (node.parent) extractParents(node.parent);
      if (node.post) {
        const author = node.post.author?.handle || "?";
        const text = node.post.record?.text || "";
        posts.push(`@${author}: ${text}`);
      }
    }
    
    extractParents(thread);
    
    if (posts.length <= 1) return ""; // No parent context
    
    // Return all posts except the last one (which is the notification itself)
    return posts.slice(0, -1).join("\n\n---\n\n");
  } catch (e) {
    console.error(`Failed to fetch thread for ${uri}:`, e);
    return "";
  }
}

/**
 * Search cognition records for relevant context
 */
async function searchCognition(query: string, limit: number = 3): Promise<string> {
  try {
    const url = `${INDEXER_URL}/xrpc/network.comind.search.query?q=${encodeURIComponent(query)}&limit=${limit}`;
    const resp = await fetch(url, { signal: AbortSignal.timeout(5000) });
    if (!resp.ok) return "";
    
    const data = await resp.json() as { results?: Array<{ content: string; collection: string; createdAt: string }> };
    if (!data.results || data.results.length === 0) return "";
    
    return data.results
      .map((r: { content: string; collection: string; createdAt: string }) => 
        `[${r.collection}] ${r.content}`)
      .join("\n\n");
  } catch {
    // Indexer down or timeout - not critical
    return "";
  }
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

  // Process in batches
  const batches = chunk(pending, 5);
  
  for (let i = 0; i < batches.length; i++) {
    const batch = batches[i];
    console.log(`\nProcessing batch ${i + 1}/${batches.length} (${batch.length} items)...`);
    
    // Fetch thread context and cognition context for each notification
    const notificationList = await Promise.all(batch.map(async item => {
      const id = item.uri?.split("/").pop() || item.cid;
      const threadContext = await fetchThreadContext(item.uri);
      
      // Search our own cognition for relevant past thoughts
      const cognitionContext = await searchCognition(item.text.substring(0, 200));
      
      return {
        id,
        platform: "bluesky",
        uri: item.uri,
        cid: item.cid,
        author: item.author,
        priority: item.priority,
        text: item.text,
        thread_context: threadContext || null,  // Full thread history
        cognition_context: cognitionContext || null,  // Central's relevant past thoughts
        reply_root: item.reply_root,
        reply_parent: item.reply_parent || { uri: item.uri, cid: item.cid },
      };
    }));

    // Write drafts directly for each notification
    for (const item of notificationList) {
      try {
        // Determine output directory based on priority
        const isHighPriority = ["HIGH", "CRITICAL"].includes(item.priority);
        const outputDir = isHighPriority ? REVIEW_DRAFTS : BLUESKY_DRAFTS;
        const filename = `${isHighPriority ? "bluesky-" : ""}reply-${item.id}.txt`;
        const filePath = path.join(outputDir, filename);

        // Build YAML frontmatter
        const frontmatter = {
          platform: item.platform,
          type: "reply",
          reply_to: item.reply_parent?.uri || item.uri,
          reply_to_cid: item.reply_parent?.cid || item.cid,
          reply_root: item.reply_root?.uri || item.uri,
          reply_root_cid: item.reply_root?.cid || item.cid,
          author: item.author,
          priority: item.priority,
          original_text: item.text.substring(0, 200),
          drafted_at: new Date().toISOString(),
        };

        // Build draft content with frontmatter
        let content = `---\n${yaml.stringify(frontmatter)}---\n`;
        content += `[DRAFT NEEDED] @${item.author}: "${item.text.substring(0, 150)}"\n\n`;
        
        // Add thread context if available
        if (item.thread_context) {
          content += `Thread: ${item.thread_context.substring(0, 500)}\n\n`;
        }
        
        // Add cognition context if available
        if (item.cognition_context) {
          content += `Past thoughts: ${item.cognition_context.substring(0, 500)}\n`;
        }

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
