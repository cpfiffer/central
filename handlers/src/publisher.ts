/**
 * Publisher
 * 
 * Reads drafts from the drafts folder and publishes them.
 * Uses Python tools for actual posting (thread.py, X scripts).
 */

import * as fs from "fs";
import * as path from "path";
import { execSync } from "child_process";
import { glob } from "glob";
import * as yaml from "yaml";
import {
  BLUESKY_DRAFTS,
  X_DRAFTS,
  REVIEW_DRAFTS,
  PUBLISHED_DIR,
} from "./config.js";

interface DraftFrontmatter {
  platform: "bluesky" | "x";
  type: "reply" | "post" | "thread";
  reply_to?: string;
  reply_to_cid?: string;
  reply_root?: string;
  reply_root_cid?: string;
  author?: string;
  priority?: string;
  original_text?: string;
  drafted_at?: string;
}

interface Draft {
  path: string;
  frontmatter: DraftFrontmatter;
  content: string;
}

/**
 * Parse a draft file with YAML frontmatter
 */
function parseDraft(filePath: string): Draft | null {
  try {
    const raw = fs.readFileSync(filePath, "utf-8");
    const match = raw.match(/^---\n([\s\S]*?)\n---\n([\s\S]*)$/);
    
    if (!match) {
      console.warn(`Invalid draft format: ${filePath}`);
      return null;
    }

    const frontmatter = yaml.parse(match[1], { intAsBigInt: true }) as DraftFrontmatter;
    const content = match[2].trim();
    
    // Convert BigInts back to strings for tweet IDs
    if (frontmatter.reply_to && typeof frontmatter.reply_to === 'bigint') {
      frontmatter.reply_to = frontmatter.reply_to.toString();
    }

    return { path: filePath, frontmatter, content };
  } catch (error) {
    console.error(`Error parsing draft ${filePath}:`, error);
    return null;
  }
}

/**
 * Post to Bluesky using thread.py
 */
function postToBluesky(draft: Draft): boolean {
  const { frontmatter, content } = draft;
  
  if (frontmatter.type === "reply" && frontmatter.reply_to) {
    // Use thread.py for replies
    const cmd = `cd .. && uv run python tools/thread.py "${content.replace(/"/g, '\\"')}" --reply-to "${frontmatter.reply_to}"`;
    
    try {
      console.log(`[Bluesky] Posting reply...`);
      const output = execSync(cmd, { encoding: "utf-8", timeout: 30000 });
      console.log(output);
      return true;
    } catch (error) {
      console.error(`[Bluesky] Failed to post:`, error);
      return false;
    }
  }

  // Regular post
  const cmd = `cd .. && uv run python tools/thread.py "${content.replace(/"/g, '\\"')}"`;
  try {
    console.log(`[Bluesky] Posting...`);
    const output = execSync(cmd, { encoding: "utf-8", timeout: 30000 });
    console.log(output);
    return true;
  } catch (error) {
    console.error(`[Bluesky] Failed to post:`, error);
    return false;
  }
}

/**
 * Post to X using the X skill scripts
 */
function postToX(draft: Draft): boolean {
  const { frontmatter, content } = draft;
  
  const scriptPath = ".skills/interacting-with-x/scripts/post.py";
  
  if (frontmatter.type === "reply" && frontmatter.reply_to) {
    const cmd = `cd .. && uv run python ${scriptPath} --reply-to ${frontmatter.reply_to} "${content.replace(/"/g, '\\"')}"`;
    
    try {
      console.log(`[X] Posting reply...`);
      const output = execSync(cmd, { encoding: "utf-8", timeout: 30000 });
      console.log(output);
      return true;
    } catch (error) {
      console.error(`[X] Failed to post:`, error);
      return false;
    }
  }

  // Regular post
  const cmd = `cd .. && uv run python ${scriptPath} "${content.replace(/"/g, '\\"')}"`;
  try {
    console.log(`[X] Posting...`);
    const output = execSync(cmd, { encoding: "utf-8", timeout: 30000 });
    console.log(output);
    return true;
  } catch (error) {
    console.error(`[X] Failed to post:`, error);
    return false;
  }
}

/**
 * Archive a draft after publishing
 */
function archiveDraft(draft: Draft): void {
  const timestamp = Date.now();
  const id = path.basename(draft.path, ".txt");
  const platform = draft.frontmatter.platform;
  const archivePath = path.join(PUBLISHED_DIR, `${timestamp}-${platform}-${id}.txt`);
  
  fs.renameSync(draft.path, archivePath);
  console.log(`Archived: ${draft.path} → ${archivePath}`);
}

/**
 * Main publisher function
 */
async function publishDrafts(options: { all?: boolean; auto?: boolean }) {
  console.log(`[${new Date().toISOString()}] Starting publisher...`);

  // Find drafts
  const draftPatterns = [];
  
  if (options.all) {
    // Include review folder (CRITICAL/HIGH)
    draftPatterns.push(`${REVIEW_DRAFTS}/*.txt`);
  }
  
  if (options.auto || options.all) {
    // Include regular drafts (LOW/MEDIUM)
    draftPatterns.push(`${BLUESKY_DRAFTS}/*.txt`);
    draftPatterns.push(`${X_DRAFTS}/*.txt`);
  }

  const draftFiles: string[] = [];
  for (const pattern of draftPatterns) {
    const matches = await glob(pattern);
    draftFiles.push(...matches);
  }

  console.log(`Found ${draftFiles.length} drafts to publish`);

  if (draftFiles.length === 0) {
    console.log("No drafts to publish. Done.");
    return;
  }

  // Parse and publish each
  for (const filePath of draftFiles) {
    const draft = parseDraft(filePath);
    if (!draft) continue;

    console.log(`\nPublishing: ${filePath}`);
    console.log(`  Platform: ${draft.frontmatter.platform}`);
    console.log(`  Type: ${draft.frontmatter.type}`);
    console.log(`  Content: ${draft.content.substring(0, 60)}...`);

    let success = false;
    
    if (draft.frontmatter.platform === "bluesky") {
      success = postToBluesky(draft);
    } else if (draft.frontmatter.platform === "x") {
      success = postToX(draft);
    } else {
      console.warn(`Unknown platform: ${draft.frontmatter.platform}`);
      continue;
    }

    if (success) {
      archiveDraft(draft);
    } else {
      console.error(`Failed to publish ${filePath}, leaving for retry`);
    }
  }

  console.log(`\n[${new Date().toISOString()}] Publisher complete.`);
}

// Parse CLI args
const args = process.argv.slice(2);
const options = {
  all: args.includes("--all"),
  auto: args.includes("--auto") || args.length === 0,
};

publishDrafts(options).catch(console.error);
