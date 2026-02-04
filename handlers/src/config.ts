/**
 * Configuration for notification handlers
 */

// Agent IDs
export const COMMS_AGENT_ID = "agent-a856f614-7654-44ba-a35f-c817d477dded";
export const CENTRAL_AGENT_ID = "agent-c770d1c8-510e-4414-be36-c9ebd95a7758";

// Known DIDs
export const CAMERON_DID = "did:plc:gfrmhdmjvxn2sjedzboeudef";
export const CENTRAL_DID = "did:plc:l46arqe6yfgh36h3o554iyvr";

export const COMIND_AGENTS: Record<string, string> = {
  "did:plc:l46arqe6yfgh36h3o554iyvr": "central",
  "did:plc:mxzuau6m53jtdsbqe6f4laov": "void",
  "did:plc:uz2snz44gi4zgqdwecavi66r": "herald",
  "did:plc:ogruxay3tt7wycqxnf5lis6s": "grunk",
  "did:plc:onfljgawqhqrz3dki5j6jh3m": "archivist",
  "did:plc:oetfdqwocv4aegq2yj6ix4w5": "umbra",
  "did:plc:o5662l2bbcljebd6rl7a6rmz": "astral",
  "did:plc:uzlnp6za26cjnnsf3qmfcipu": "magenta",
};

// Priority keywords
export const HIGH_PRIORITY_KEYWORDS = [
  "help", "feedback", "bug", "broken", "issue", "error",
  "how do", "can you", "what is", "why",
];

export type Priority = "CRITICAL" | "HIGH" | "MEDIUM" | "LOW" | "SKIP";

/**
 * Determine priority for a notification
 */
export function getPriority(authorDid: string, text: string): Priority {
  // Critical: Cameron
  if (authorDid === CAMERON_DID) {
    return "CRITICAL";
  }

  // Comind agents: Skip unless direct question
  if (authorDid in COMIND_AGENTS) {
    if (text.toLowerCase().includes("@central") && text.includes("?")) {
      return "MEDIUM";
    }
    return "SKIP"; // Avoid loops
  }

  // High: Questions or keywords from humans
  const textLower = text.toLowerCase();
  if (text.includes("?") || HIGH_PRIORITY_KEYWORDS.some(kw => textLower.includes(kw))) {
    return "HIGH";
  }

  // Medium: General human mention
  return "MEDIUM";
}

// Paths - ABSOLUTE to prevent comms path resolution issues
export const PROJECT_ROOT = "/home/cameron/central";
export const DRAFTS_DIR = `${PROJECT_ROOT}/drafts`;
export const BLUESKY_DRAFTS = `${DRAFTS_DIR}/bluesky`;
export const X_DRAFTS = `${DRAFTS_DIR}/x`;
export const REVIEW_DRAFTS = `${DRAFTS_DIR}/review`;
export const REJECTED_DIR = `${DRAFTS_DIR}/rejected`;
export const NOTES_DIR = `${DRAFTS_DIR}/notes`;
export const PUBLISHED_DIR = `${DRAFTS_DIR}/published`;
