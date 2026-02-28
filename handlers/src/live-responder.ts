/**
 * Live Responder - Unified real-time notification handler for Central.
 *
 * Bluesky: Jetstream WebSocket (real-time)
 * X: Polling every 5 minutes
 *
 * Uses Letta Code SDK for local invocation with full tool access.
 *
 * Usage:
 *   npm run live              # Both platforms
 *   npm run live:bsky         # Bluesky only
 *   npm run live:x            # X only
 *   npm run live:dry          # Dry run
 */

import * as fs from "fs";
import * as crypto from "crypto";
import { execSync } from "child_process";
import WebSocket from "ws";
import { createSession, resumeSession } from "@letta-ai/letta-code-sdk";
import {
  CENTRAL_AGENT_ID,
  RESPONDER_AGENT_ID,
  CENTRAL_DID,
  CENTRAL_HANDLE,
  CAMERON_DID,
  ALWAYS_SKIP_AGENTS,
  INDEXER_URL,
  PROJECT_ROOT,
  SENT_FILE,
  X_CURSOR_FILE,
  X_SPAM_KEYWORDS,
  DATA_DIR,
  getPriority,
  type Priority,
} from "./config.js";

const JETSTREAM_URL = "wss://jetstream2.us-east.bsky.network/subscribe";
const RATE_LIMIT_MS = 30_000;
const UV_PATH = "/home/cameron/.local/bin/uv";
const CONV_MAP_FILE = `${DATA_DIR}/conversation-map.json`;

const lastResponseTime: Record<string, number> = { bluesky: 0, x: 0 };
let xBackoff = 60; // exponential backoff for X rate limits (seconds)
let cachedXUserId: string | null = null;

// --- Conversation persistence ---
// Maps thread root URIs to Letta conversation IDs for continuity

function loadConversationMap(): Record<string, string> {
  try {
    if (fs.existsSync(CONV_MAP_FILE)) {
      return JSON.parse(fs.readFileSync(CONV_MAP_FILE, "utf-8"));
    }
  } catch {}
  return {};
}

function saveConversationId(threadKey: string, conversationId: string) {
  const map = loadConversationMap();
  map[threadKey] = conversationId;
  fs.mkdirSync(DATA_DIR, { recursive: true });
  fs.writeFileSync(CONV_MAP_FILE, JSON.stringify(map, null, 2));
}

// --- Logging ---

function log(tag: string, msg: string) {
  const ts = new Date().toISOString().slice(11, 19);
  console.log(`${ts} [${tag}] ${msg}`);
}

// --- Sent tracking ---

function loadSent(): Set<string> {
  try {
    if (fs.existsSync(SENT_FILE)) {
      return new Set(fs.readFileSync(SENT_FILE, "utf-8").trim().split("\n"));
    }
  } catch {}
  return new Set();
}

function saveSent(id: string) {
  fs.mkdirSync(DATA_DIR, { recursive: true });
  fs.appendFileSync(SENT_FILE, id + "\n");
}

// --- Context gathering ---

interface MentionContext {
  authorProfile?: { name: string; bio: string; followers: number; posts: number };
  pastInteractions?: string[];
  relevantRecords?: string[];
}

async function gatherContext(
  author: string,
  text: string,
  platform: string,
): Promise<MentionContext> {
  const ctx: MentionContext = {};
  const indexerBase = `${INDEXER_URL}/xrpc`;

  // 1. Semantic search on mention text
  try {
    const resp = await fetch(
      `${indexerBase}/network.comind.search.query?q=${encodeURIComponent(text.slice(0, 200))}&limit=3`,
      { signal: AbortSignal.timeout(5000) },
    );
    if (resp.ok) {
      const data = (await resp.json()) as { results?: Array<{ collection: string; content: string }> };
      if (data.results?.length) {
        ctx.relevantRecords = data.results
          .filter((r) => r.content)
          .map((r) => `[${r.collection}] ${r.content.slice(0, 200)}`);
      }
    }
  } catch {}

  // 2. Interaction history
  try {
    const resp = await fetch(
      `${indexerBase}/network.comind.search.query?q=${encodeURIComponent(`@${author}`)}&limit=3`,
      { signal: AbortSignal.timeout(5000) },
    );
    if (resp.ok) {
      const data = (await resp.json()) as {
        results?: Array<{ createdAt?: string; content: string }>;
      };
      if (data.results?.length) {
        ctx.pastInteractions = data.results
          .filter((r) => r.content)
          .map((r) => `${(r.createdAt || "?").slice(0, 10)}: ${r.content.slice(0, 150)}`);
      }
    }
  } catch {}

  // 3. Author profile (Bluesky only)
  if (platform === "bluesky") {
    try {
      const resp = await fetch(
        `https://public.api.bsky.app/xrpc/app.bsky.actor.getProfile?actor=${encodeURIComponent(author)}`,
        { signal: AbortSignal.timeout(5000) },
      );
      if (resp.ok) {
        const profile = (await resp.json()) as {
          displayName?: string;
          description?: string;
          followersCount?: number;
          postsCount?: number;
        };
        ctx.authorProfile = {
          name: profile.displayName || "",
          bio: (profile.description || "").slice(0, 200),
          followers: profile.followersCount || 0,
          posts: profile.postsCount || 0,
        };
      }
    } catch {}
  }

  return ctx;
}

// --- Build prompt ---

function buildPrompt(
  platform: string,
  author: string,
  text: string,
  threadContext: string,
  ctx: MentionContext,
): string {
  const parts: string[] = [];

  // Thread context FIRST - this IS the conversation
  if (threadContext) {
    parts.push(`Thread:\n${threadContext}\n@${author}: "${text}"`);
  } else {
    parts.push(`@${author}: "${text}"`);
  }

  // Supporting context (bracketed to signal it's metadata, not conversation)
  if (ctx.authorProfile) {
    const p = ctx.authorProfile;
    parts.push(`[Author: ${p.name}, ${p.followers} followers. ${p.bio}]`);
  }

  if (ctx.relevantRecords?.length) {
    parts.push("[Relevant records:\n" + ctx.relevantRecords.join("\n") + "]");
  }

  parts.push(
    "Reply to the conversation above. Be direct and substantive. " +
      "Match the depth of what was said: short questions get short answers, " +
      "substantive points deserve real engagement. " +
      "Max 280 chars per post. If you need more space, that's fine, just keep it tight. " +
      "Output only the reply text, nothing else. " +
      "If no response needed (e.g. 'thanks', acknowledgments): [SKIP]. " +
      "If the request needs tools (search, code, annotations): [ESCALATE]",
  );

  return parts.join("\n\n");
}

// --- Invoke agent via Letta Code SDK ---

interface InvokeResult {
  response: string | null;
  conversationId: string | null;
}

async function invokeAgent(prompt: string, agentId: string, threadKey?: string): Promise<InvokeResult> {
  try {
    // Check for existing conversation for this thread
    const convMap = loadConversationMap();
    const existingConvId = threadKey ? convMap[threadKey] : undefined;

    let session;
    if (existingConvId) {
      // Resume existing conversation - model remembers prior exchanges
      log("sdk", `Resuming conversation ${existingConvId.slice(0, 12)}... for thread`);
      session = resumeSession(existingConvId, {
        permissionMode: "bypassPermissions",
        cwd: PROJECT_ROOT + "/handlers",
      });
    } else {
      // New conversation
      session = createSession(agentId, {
        permissionMode: "bypassPermissions",
        cwd: PROJECT_ROOT + "/handlers",
      });
    }

    await session.send(prompt);

    let response = "";
    let conversationId: string | null = null;
    for await (const msg of session.stream()) {
      if (msg.type === "assistant") {
        response += msg.content;
      }
      if (msg.type === "result") {
        conversationId = msg.conversationId || null;
        break;
      }
    }
    session.close();

    // Save conversation ID for thread persistence
    if (conversationId && threadKey) {
      saveConversationId(threadKey, conversationId);
    }

    const trimmed = response.trim();
    if (!trimmed || trimmed.startsWith("[SKIP]")) return { response: null, conversationId };
    const firstLine = trimmed.split("\n")[0].trim();
    if (firstLine === "[SKIP]") return { response: null, conversationId };
    return { response: trimmed, conversationId };
  } catch (err) {
    log("sdk", `Error: ${err}`);
    return { response: null, conversationId: null };
  }
}

// --- Posting ---

function shellEscape(s: string): string {
  return s.replace(/\\/g, "\\\\").replace(/`/g, "\\`").replace(/\$/g, "\\$").replace(/"/g, '\\"').replace(/!/g, "\\!");
}

function postBlueskyReply(text: string, replyToUri: string): boolean {
  try {
    const escaped = shellEscape(text);
    const cmd = `${UV_PATH} run python tools/thread.py "${escaped}" --reply-to "${replyToUri}"`;
    const output = execSync(cmd, { encoding: "utf-8", timeout: 30000, cwd: PROJECT_ROOT });
    log("bsky", `Posted: ${output.trim().slice(0, 100)}`);
    return true;
  } catch (err) {
    log("bsky", `Post failed: ${err}`);
    return false;
  }
}

function postXReply(text: string, replyToId: string): boolean {
  try {
    const escaped = shellEscape(text);
    const cmd = `${UV_PATH} run python .skills/interacting-with-x/scripts/post.py --reply-to ${replyToId} "${escaped}"`;
    const output = execSync(cmd, { encoding: "utf-8", timeout: 30000, cwd: PROJECT_ROOT });
    log("x", `Posted: ${output.trim().slice(0, 100)}`);
    return true;
  } catch (err) {
    log("x", `Post failed: ${err}`);
    return false;
  }
}

// --- Thread context ---

async function fetchThreadContext(uri: string): Promise<string> {
  try {
    const resp = await fetch(
      `https://public.api.bsky.app/xrpc/app.bsky.feed.getPostThread?uri=${encodeURIComponent(uri)}&depth=0&parentHeight=5`,
      { signal: AbortSignal.timeout(10000) },
    );
    if (!resp.ok) return "";

    const data = (await resp.json()) as { thread?: any };
    const thread = data.thread;
    if (!thread) return "";

    const parts: string[] = [];
    let current = thread;
    while (current?.parent) {
      current = current.parent;
      const author = current?.post?.author?.handle || "?";
      const text = current?.post?.record?.text || "";
      if (text) parts.push(`@${author}: ${text}`);
    }
    parts.reverse();
    return parts.slice(-3).join("\n");
  } catch {
    return "";
  }
}

// --- Resolve DID to handle ---

async function resolveHandle(did: string): Promise<string> {
  try {
    const resp = await fetch(`https://plc.directory/${did}`, {
      signal: AbortSignal.timeout(5000),
    });
    if (resp.ok) {
      const doc = (await resp.json()) as { alsoKnownAs?: string[] };
      for (const alias of doc.alsoKnownAs || []) {
        if (alias.startsWith("at://")) return alias.slice(5);
      }
    }
  } catch {}
  return "unknown";
}

// --- Core handler ---

async function handleMention(
  platform: string,
  text: string,
  author: string,
  authorDid: string,
  uriOrId: string,
  threadContext: string = "",
  dryRun: boolean = false,
  threadRootUri: string = "",
) {
  // Priority routing
  const priority = getPriority(authorDid, text);
  if (priority === "SKIP") {
    log(platform, `Skipping @${author} (priority: SKIP)`);
    saveSent(uriOrId);
    return;
  }

  // CRITICAL/HIGH = Central (opus), MEDIUM/LOW = responder (haiku)
  const agentId = (priority === "CRITICAL" || priority === "HIGH")
    ? CENTRAL_AGENT_ID
    : RESPONDER_AGENT_ID;
  const agentLabel = agentId === CENTRAL_AGENT_ID ? "central" : "responder";

  // Rate limit
  const now = Date.now();
  const elapsed = now - (lastResponseTime[platform] || 0);
  if (elapsed < RATE_LIMIT_MS) {
    log(platform, `Rate limited (${(elapsed / 1000).toFixed(0)}s < ${RATE_LIMIT_MS / 1000}s)`);
    return;
  }

  log(platform, `@${author}: ${text.slice(0, 80)} [${priority} -> ${agentLabel}]`);

  if (dryRun) {
    log(platform, `[DRY RUN] Would invoke ${agentLabel} and reply`);
    return;
  }

  // Gather context
  const ctx = await gatherContext(author, text, platform);
  const ctxParts: string[] = [];
  if (ctx.authorProfile) ctxParts.push("profile");
  if (ctx.pastInteractions?.length) ctxParts.push(`${ctx.pastInteractions.length} interactions`);
  if (ctx.relevantRecords?.length) ctxParts.push(`${ctx.relevantRecords.length} records`);
  if (ctxParts.length) log(platform, `Context: ${ctxParts.join(", ")}`);

  // Build prompt and invoke with thread persistence
  const prompt = buildPrompt(platform, author, text, threadContext, ctx);
  const threadKey = threadRootUri || uriOrId; // Use thread root for conversation grouping
  let { response, conversationId } = await invokeAgent(prompt, agentId, threadKey);

  if (conversationId) {
    log(platform, `Conversation: ${conversationId.slice(0, 16)}...`);
  }

  // Escalation: if responder signals [ESCALATE], re-invoke with Central
  if (response?.includes("[ESCALATE]") && agentId === RESPONDER_AGENT_ID) {
    log(platform, `Responder escalated to Central`);
    const escalated = await invokeAgent(prompt, CENTRAL_AGENT_ID, threadKey);
    response = escalated.response;
    conversationId = escalated.conversationId;
  }

  if (!response || response.includes("[ESCALATE]")) {
    log(platform, `Skipped @${author}`);
    saveSent(uriOrId);
    return;
  }

  log(platform, `Response: ${response.slice(0, 100)}`);

  // Truncate if too long (300 grapheme limit for Bluesky, 280 for X)
  let finalResponse = response;
  const limit = platform === "bluesky" ? 295 : 275; // Leave margin
  if (finalResponse.length > limit) {
    // Try to truncate at sentence boundary
    const truncated = finalResponse.slice(0, limit);
    const lastPeriod = truncated.lastIndexOf(".");
    const lastSpace = truncated.lastIndexOf(" ");
    const cutAt = lastPeriod > limit * 0.6 ? lastPeriod + 1 : lastSpace > limit * 0.6 ? lastSpace : limit;
    finalResponse = finalResponse.slice(0, cutAt).trim();
    log(platform, `Truncated from ${response.length} to ${finalResponse.length} chars`);
  }

  // Post reply
  let success = false;
  if (platform === "bluesky") {
    success = postBlueskyReply(finalResponse, uriOrId);
  } else if (platform === "x") {
    success = postXReply(finalResponse, uriOrId);
  }

  if (success) {
    lastResponseTime[platform] = Date.now();
  }
  saveSent(uriOrId);
}

// --- Bluesky Jetstream ---

function runBlueskyLoop(dryRun: boolean) {
  const sent = loadSent();
  log("bsky", `Starting Jetstream listener (${sent.size} already sent)`);

  function connect() {
    const url = `${JETSTREAM_URL}?wantedCollections=app.bsky.feed.post`;
    log("bsky", `Connecting to Jetstream...`);

    const ws = new WebSocket(url);

    ws.on("open", () => {
      log("bsky", "Connected to Jetstream");
    });

    ws.on("message", async (data: Buffer) => {
      try {
        const message = JSON.parse(data.toString());

        if (message.kind !== "commit") return;
        const commit = message.commit;
        if (commit?.operation !== "create") return;
        if (commit?.collection !== "app.bsky.feed.post") return;

        const did = message.did || "";
        const postText = commit.record?.text || "";
        const replyParentUri = commit.record?.reply?.parent?.uri || "";

        // Process if: (a) mentions Central, or (b) Cameron replying in Central's thread
        const mentionsCentral = postText.includes(`@${CENTRAL_HANDLE}`);
        const cameronReplyingToUs = did === CAMERON_DID && replyParentUri.startsWith(`at://${CENTRAL_DID}/`);

        if (!mentionsCentral && !cameronReplyingToUs) return;
        if (did in ALWAYS_SKIP_AGENTS || did === CENTRAL_DID) return;

        const rkey = commit.rkey || "";
        const uri = `at://${did}/app.bsky.feed.post/${rkey}`;

        if (sent.has(uri)) return;
        sent.add(uri);

        const author = await resolveHandle(did);
        const threadCtx = await fetchThreadContext(uri);
        const threadRootUri = commit.record?.reply?.root?.uri || uri;

        // Don't await - fire and forget to not block message processing
        handleMention("bluesky", postText, author, did, uri, threadCtx, dryRun, threadRootUri).catch((err) =>
          log("bsky", `Handler error: ${err}`),
        );
      } catch (err) {
        // Ignore parse errors on individual messages
      }
    });

    ws.on("close", () => {
      log("bsky", "WebSocket closed, reconnecting in 5s...");
      setTimeout(connect, 5000);
    });

    ws.on("error", (err: Error) => {
      log("bsky", `WebSocket error: ${err.message}`);
      ws.close();
    });

    // Keepalive ping every 20s
    const pingInterval = setInterval(() => {
      if (ws.readyState === WebSocket.OPEN) {
        ws.ping();
      } else {
        clearInterval(pingInterval);
      }
    }, 20000);
  }

  connect();
}

// --- X OAuth 1.0a ---

function oauthSign(method: string, url: string, params: Record<string, string> = {}): string {
  const consumerKey = process.env.X_API_KEY || "";
  const consumerSecret = process.env.X_API_SECRET || "";
  const accessToken = process.env.X_ACCESS_TOKEN || "";
  const accessTokenSecret = process.env.X_ACCESS_TOKEN_SECRET || "";

  const nonce = crypto.randomBytes(16).toString("hex");
  const timestamp = Math.floor(Date.now() / 1000).toString();

  const oauthParams: Record<string, string> = {
    oauth_consumer_key: consumerKey,
    oauth_nonce: nonce,
    oauth_signature_method: "HMAC-SHA1",
    oauth_timestamp: timestamp,
    oauth_token: accessToken,
    oauth_version: "1.0",
    ...params,
  };

  // Create signature base string
  const sortedParams = Object.keys(oauthParams)
    .sort()
    .map((k) => `${encodeURIComponent(k)}=${encodeURIComponent(oauthParams[k])}`)
    .join("&");

  const baseString = `${method.toUpperCase()}&${encodeURIComponent(url)}&${encodeURIComponent(sortedParams)}`;
  const signingKey = `${encodeURIComponent(consumerSecret)}&${encodeURIComponent(accessTokenSecret)}`;
  const signature = crypto.createHmac("sha1", signingKey).update(baseString).digest("base64");

  // Build Authorization header
  const authParams = {
    ...oauthParams,
    oauth_signature: signature,
  };
  // Remove non-oauth params from header
  for (const k of Object.keys(params)) {
    delete authParams[k];
  }
  authParams.oauth_signature = signature;

  const header = Object.keys(authParams)
    .sort()
    .map((k) => `${encodeURIComponent(k)}="${encodeURIComponent(authParams[k])}"`)
    .join(", ");

  return `OAuth ${header}`;
}

async function xFetch(url: string, params: Record<string, string> = {}): Promise<any> {
  const fullUrl = Object.keys(params).length
    ? `${url}?${new URLSearchParams(params).toString()}`
    : url;

  const authHeader = oauthSign("GET", url, params);

  const resp = await fetch(fullUrl, {
    headers: { Authorization: authHeader },
    signal: AbortSignal.timeout(15000),
  });

  if (resp.status === 429) {
    const retryAfter = parseInt(resp.headers.get("retry-after") || "0", 10);
    const waitSec = retryAfter > 0 ? retryAfter : xBackoff;
    log("x", `Rate limited, waiting ${waitSec}s (backoff=${xBackoff}s)`);
    await new Promise((r) => setTimeout(r, waitSec * 1000));
    xBackoff = Math.min(xBackoff * 2, 900); // max 15 min
    return null;
  }

  if (!resp.ok) {
    // Back off on server errors (5xx) too, not just rate limits
    if (resp.status >= 500) {
      xBackoff = Math.min(xBackoff * 2, 900);
      log("x", `API error: ${resp.status} (backoff=${xBackoff}s)`);
    } else {
      log("x", `API error: ${resp.status}`);
    }
    return null;
  }

  return resp.json();
}

async function runXLoop(dryRun: boolean, interval: number) {
  const sent = loadSent();
  log("x", `Starting X poller (every ${interval / 1000}s, ${sent.size} already sent)`);

  // Load cursor
  let lastSeenId: string | null = null;
  try {
    if (fs.existsSync(X_CURSOR_FILE)) {
      lastSeenId = fs.readFileSync(X_CURSOR_FILE, "utf-8").trim();
      log("x", `Resuming from tweet ID ${lastSeenId}`);
    }
  } catch {}

  while (true) {
    try {
      // Get user ID (cached - never changes)
      if (!cachedXUserId) {
        const meData = await xFetch("https://api.twitter.com/2/users/me");
        if (!meData) {
          await new Promise((r) => setTimeout(r, interval));
          continue;
        }
        cachedXUserId = meData.data?.id || null;
        if (cachedXUserId) {
          log("x", `Cached user ID: ${cachedXUserId}`);
        }
      }
      const userId = cachedXUserId;
      if (!userId) {
        log("x", "No user ID");
        await new Promise((r) => setTimeout(r, interval));
        continue;
      }

      // Fetch mentions
      const params: Record<string, string> = {
        max_results: "20",
        "tweet.fields": "author_id,created_at,conversation_id",
        expansions: "author_id",
      };
      if (lastSeenId) params.since_id = lastSeenId;

      const data = await xFetch(`https://api.twitter.com/2/users/${userId}/mentions`, params);
      if (!data) {
        await new Promise((r) => setTimeout(r, interval));
        continue;
      }
      xBackoff = 60; // reset backoff on successful fetch

      const tweets = data.data || [];
      const users: Record<string, any> = {};
      for (const u of data.includes?.users || []) {
        users[u.id] = u;
      }

      if (tweets.length) {
        log("x", `Found ${tweets.length} new mentions`);
      }

      let newestId = lastSeenId;

      // Process oldest first
      for (const tweet of [...tweets].reverse()) {
        const tweetId = tweet.id;
        const tweetText = tweet.text || "";
        const authorId = tweet.author_id || "";
        const authorName = users[authorId]?.username || "unknown";

        if (!newestId || BigInt(tweetId) > BigInt(newestId || "0")) {
          newestId = tweetId;
        }

        if (sent.has(tweetId)) continue;
        sent.add(tweetId);

        if (authorId === userId) continue;

        // Spam filter
        const lower = tweetText.toLowerCase();
        if (X_SPAM_KEYWORDS.some((kw) => lower.includes(kw))) {
          log("x", `Skipping spam from @${authorName}`);
          saveSent(tweetId);
          continue;
        }

        await handleMention("x", tweetText, authorName, "", tweetId, "", dryRun);
      }

      // Update cursor
      if (newestId && newestId !== lastSeenId) {
        lastSeenId = newestId;
        fs.mkdirSync(DATA_DIR, { recursive: true });
        fs.writeFileSync(X_CURSOR_FILE, newestId);
      }
    } catch (err) {
      log("x", `Error: ${err}`);
    }

    // Use backoff interval if it's larger than the normal interval
    const sleepMs = Math.max(interval, xBackoff * 1000);
    await new Promise((r) => setTimeout(r, sleepMs));
  }
}

// --- Main ---

const args = process.argv.slice(2);
const dryRun = args.includes("--dry-run");
const bskyOnly = args.includes("--bluesky");
const xOnly = args.includes("--x");
const xInterval = 300_000; // 5 minutes

const runBsky = bskyOnly || (!bskyOnly && !xOnly);
const runX = xOnly || (!bskyOnly && !xOnly);

log("live", `Starting (bsky=${runBsky}, x=${runX}, dryRun=${dryRun})`);

if (runBsky) {
  runBlueskyLoop(dryRun);
}

if (runX) {
  runXLoop(dryRun, xInterval);
}

// Keep process alive
if (!runX) {
  // X loop keeps itself alive, but if only Bluesky, we need to keep alive
  setInterval(() => {}, 60000);
}
