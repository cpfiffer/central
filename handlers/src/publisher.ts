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
  REJECTED_DIR,
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
    const match = raw.match(/^---\n([\s\S]*?)\n---\n?([\s\S]*)$/);
    
    if (!match) {
      console.warn(`Invalid draft format: ${filePath}`);
      return null;
    }

    let frontmatter: DraftFrontmatter;
    try {
      frontmatter = yaml.parse(match[1], { intAsBigInt: true }) as DraftFrontmatter;
    } catch (yamlError) {
      // YAML parse failed (usually unquoted original_text with special chars).
      // Strip the problematic field and retry.
      const cleaned = match[1]
        .split("\n")
        .filter(line => !line.startsWith("original_text:"))
        .join("\n");
      try {
        frontmatter = yaml.parse(cleaned, { intAsBigInt: true }) as DraftFrontmatter;
        console.warn(`[YAML recovery] Stripped original_text from ${filePath}`);
      } catch {
        console.error(`Error parsing draft ${filePath} (even after cleanup):`, yamlError);
        return null;
      }
    }

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
 * Validate a draft has required fields
 */
function validateDraft(draft: Draft): string[] {
  const errors: string[] = [];
  const { frontmatter, content } = draft;
  
  if (!frontmatter.platform) {
    errors.push("Missing: platform");
  }
  if (!frontmatter.type) {
    errors.push("Missing: type");
  }
  if (frontmatter.type === "reply" && !frontmatter.reply_to) {
    errors.push("Missing: reply_to (required for replies)");
  }
  if (!content || content.trim().length < 5) {
    errors.push("Content too short or missing");
  }
  if (content && content.trim().startsWith("[DRAFT NEEDED]")) {
    errors.push("Draft stub - needs human-written content before publishing");
  }
  
  return errors;
}

/**
 * Move a malformed draft to rejected folder
 */
function moveToRejected(draftPath: string): void {
  const filename = path.basename(draftPath);
  const rejectedPath = path.join(REJECTED_DIR, `${Date.now()}-${filename}`);
  
  try {
    if (!fs.existsSync(REJECTED_DIR)) {
      fs.mkdirSync(REJECTED_DIR, { recursive: true });
    }
    fs.renameSync(draftPath, rejectedPath);
    console.log(`Moved to rejected: ${rejectedPath}`);
  } catch (error) {
    console.error(`Failed to move to rejected:`, error);
  }
}

/**
 * Check if we've already published a reply to this target
 */
function alreadyPublishedReplyTo(platform: string, replyTo: string): boolean {
  if (!fs.existsSync(PUBLISHED_DIR)) return false;
  
  const publishedFiles = fs.readdirSync(PUBLISHED_DIR);
  for (const file of publishedFiles) {
    // Check if file matches platform
    if (!file.includes(platform) && !file.includes(platform === "bluesky" ? "bluesky" : "x-")) {
      continue;
    }
    
    try {
      const content = fs.readFileSync(path.join(PUBLISHED_DIR, file), "utf-8");
      // Check if this file has the same reply_to
      if (content.includes(`reply_to: ${replyTo}`) || 
          content.includes(`reply_to: "${replyTo}"`) ||
          content.includes(`reply_to: '${replyTo}'`)) {
        console.log(`[DUPLICATE] Already published reply to ${replyTo} in ${file}`);
        return true;
      }
    } catch {
      // Skip files we can't read
    }
  }
  return false;
}

/**
 * Escape content for safe shell interpolation in double quotes.
 * Escapes: \ ` $ " ! 
 */
function shellEscape(s: string): string {
  return s
    .replace(/\\/g, '\\\\')
    .replace(/`/g, '\\`')
    .replace(/\$/g, '\\$')
    .replace(/"/g, '\\"')
    .replace(/!/g, '\\!');
}

/**
 * Post to Bluesky using thread.py
 */
function postToBluesky(draft: Draft): boolean {
  const { frontmatter, content } = draft;
  const escaped = shellEscape(content);
  
  if (frontmatter.type === "reply" && frontmatter.reply_to) {
    // Use thread.py for replies
    const cmd = `cd .. && uv run python tools/thread.py "${escaped}" --reply-to "${frontmatter.reply_to}"`;
    
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
  const cmd = `cd .. && uv run python tools/thread.py "${escaped}"`;
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
  const escaped = shellEscape(content);
  
  const scriptPath = ".skills/interacting-with-x/scripts/post.py";
  
  if (frontmatter.type === "reply" && frontmatter.reply_to) {
    const cmd = `cd .. && uv run python ${scriptPath} --reply-to ${frontmatter.reply_to} "${escaped}"`;
    
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
  const cmd = `cd .. && uv run python ${scriptPath} "${escaped}"`;
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
 * Check if Central is currently active (has an active Letta Code session)
 */
function isCentralActive(): boolean {
  // Use import.meta.url for ES modules
  const currentDir = path.dirname(new URL(import.meta.url).pathname);
  const activeFile = path.join(currentDir, "..", "..", ".central-active");
  return fs.existsSync(activeFile);
}

/**
 * Main publisher function
 */
async function publishDrafts(options: { all?: boolean; auto?: boolean }) {
  console.log(`[${new Date().toISOString()}] Starting publisher...`);

  // Check if Central is active - if so, auto-approve CRITICAL/HIGH
  const centralActive = isCentralActive();
  if (centralActive) {
    console.log(`[Central Active] Auto-approving CRITICAL/HIGH items`);
  }

  // Find drafts
  const draftPatterns = [];
  
  if (options.all || centralActive) {
    // Include review folder (CRITICAL/HIGH) when:
    // - Explicitly requested with --all
    // - Central is active (can auto-approve)
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

    // Handle escalation files from responder agent
    if (draft.frontmatter.type === "escalate" as any) {
      console.log(`\n⬆ Escalation: ${filePath}`);
      console.log(`  Reason: ${(draft.frontmatter as any).reason || "unknown"}`);
      console.log(`  Moving to review queue for Central to handle`);
      // Move to review dir with escalate prefix so handler picks it up next cycle
      let filename = path.basename(filePath);
      // Strip any existing escalate/escalated prefixes to prevent name growth
      filename = filename.replace(/^(escalated?-)+/, "");
      const reviewPath = path.join(REVIEW_DRAFTS, `escalate-${filename}`);
      fs.renameSync(filePath, reviewPath);
      continue;
    }

    // Validate draft before publishing
    const errors = validateDraft(draft);
    if (errors.length > 0) {
      console.error(`\n❌ Rejecting malformed draft: ${filePath}`);
      errors.forEach(e => console.error(`   - ${e}`));
      moveToRejected(filePath);
      continue;
    }

    console.log(`\nPublishing: ${filePath}`);
    console.log(`  Platform: ${draft.frontmatter.platform}`);
    console.log(`  Type: ${draft.frontmatter.type}`);
    console.log(`  Content: ${draft.content.substring(0, 60)}...`);

    // Check for duplicate replies
    if (draft.frontmatter.type === "reply" && draft.frontmatter.reply_to) {
      if (alreadyPublishedReplyTo(draft.frontmatter.platform, draft.frontmatter.reply_to)) {
        console.log(`⚠ Skipping duplicate reply to ${draft.frontmatter.reply_to}`);
        moveToRejected(filePath);
        continue;
      }
    }

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
