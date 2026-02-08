/**
 * Configuration for notification handlers
 */

// Agent IDs
export const CENTRAL_AGENT_ID = "agent-c770d1c8-510e-4414-be36-c9ebd95a7758";
export const RESPONDER_AGENT_ID = "agent-d52fffc8-f297-4f6b-a505-5dbd34c2ba01"; // haiku, cheap

// Known DIDs
export const CAMERON_DID = "did:plc:gfrmhdmjvxn2sjedzboeudef";
export const CENTRAL_DID = "did:plc:l46arqe6yfgh36h3o554iyvr";

// Our own agents - always skip (loop avoidance)
export const ALWAYS_SKIP_AGENTS: Record<string, string> = {
  "did:plc:l46arqe6yfgh36h3o554iyvr": "central",
  "did:plc:mxzuau6m53jtdsbqe6f4laov": "void",
  "did:plc:uz2snz44gi4zgqdwecavi66r": "herald",
  "did:plc:ogruxay3tt7wycqxnf5lis6s": "grunk",
  "did:plc:onfljgawqhqrz3dki5j6jh3m": "archivist",
};

// External agents we selectively engage with
export const ENGAGE_AGENTS: Record<string, string> = {
  "did:plc:jv5m6n4mh3ni2nn5xxidyfsy": "penny",
  "did:plc:oetfdqwocv4aegq2yj6ix4w5": "umbra",
  "did:plc:uzlnp6za26cjnnsf3qmfcipu": "magenta",
  "did:plc:o5662l2bbcljebd6rl7a6rmz": "astral",
  "did:plc:ky7bhukzztej6wb7wm3rgway": "clankops",
};

// Combined for backward compat
export const COMIND_AGENTS: Record<string, string> = {
  ...ALWAYS_SKIP_AGENTS,
  ...ENGAGE_AGENTS,
};

// Priority keywords
export const HIGH_PRIORITY_KEYWORDS = [
  "help", "feedback", "bug", "broken", "issue", "error",
  "how do", "can you", "what is", "why",
];

export type Priority = "CRITICAL" | "HIGH" | "MEDIUM" | "LOW" | "SKIP";

const ENGAGE_SAMPLE_RATE = 0.3; // Engage with ~30% of qualifying agent posts

/**
 * Determine priority for a notification
 */
export function getPriority(authorDid: string, text: string): Priority {
  // Critical: Cameron
  if (authorDid === CAMERON_DID) {
    return "CRITICAL";
  }

  // Our own agents: always skip (loop avoidance)
  if (authorDid in ALWAYS_SKIP_AGENTS) {
    return "SKIP";
  }

  // External agents we selectively engage with
  if (authorDid in ENGAGE_AGENTS) {
    // Direct question to me: always queue
    if (text.toLowerCase().includes("@central") && text.includes("?")) {
      return "MEDIUM";
    }
    // Random sampling for general mentions
    if (Math.random() < ENGAGE_SAMPLE_RATE) {
      return "LOW";
    }
    return "SKIP";
  }

  // High: Questions or keywords from humans
  const textLower = text.toLowerCase();
  if (text.includes("?") || HIGH_PRIORITY_KEYWORDS.some(kw => textLower.includes(kw))) {
    return "HIGH";
  }

  // Medium: General human mention
  return "MEDIUM";
}

// XRPC Indexer - cognition search
export const INDEXER_URL = "https://comind-indexer.fly.dev";

// Paths - ABSOLUTE
export const PROJECT_ROOT = "/home/cameron/central";
export const DRAFTS_DIR = `${PROJECT_ROOT}/drafts`;
export const BLUESKY_DRAFTS = `${DRAFTS_DIR}/bluesky`;
export const X_DRAFTS = `${DRAFTS_DIR}/x`;
export const REVIEW_DRAFTS = `${DRAFTS_DIR}/review`;
export const REJECTED_DIR = `${DRAFTS_DIR}/rejected`;
export const NOTES_DIR = `${DRAFTS_DIR}/notes`;
export const PUBLISHED_DIR = `${DRAFTS_DIR}/published`;
