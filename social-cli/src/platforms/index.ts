/**
 * Platform registry.
 * Lazily initializes platforms only when first accessed.
 */

import { existsSync } from "node:fs"
import { resolve } from "node:path"
import { config as loadDotenv } from "dotenv"
import type { SocialPlatform } from "./types.js"

// Load .env before checking available platforms
const envPath = resolve(process.cwd(), ".env")
if (existsSync(envPath)) {
  loadDotenv({ path: envPath, override: true, quiet: true })
}

const registry: Record<string, () => SocialPlatform> = {
  bsky: () => {
    const { bluesky } = require("./bluesky.js") as typeof import("./bluesky.js")
    return bluesky
  },
  x: () => {
    const { x } = require("./x.js") as typeof import("./x.js")
    return x
  },
}

const loaded: Record<string, SocialPlatform> = {}

export function getPlatform(name: string): SocialPlatform {
  if (loaded[name]) return loaded[name]
  const factory = registry[name]
  if (!factory) throw new Error(`Unknown platform: ${name}. Available: ${Object.keys(registry).join(", ")}`)
  loaded[name] = factory()
  return loaded[name]
}

export function availablePlatforms(): string[] {
  // Only return platforms that have credentials configured
  const available: string[] = []

  // Check bsky credentials
  if (process.env.ATPROTO_HANDLE || process.env.BSKY_USERNAME) {
    available.push("bsky")
  }

  // Check x credentials
  if (process.env.X_API_KEY && process.env.X_API_SECRET &&
      process.env.X_ACCESS_TOKEN && process.env.X_ACCESS_TOKEN_SECRET) {
    available.push("x")
  }

  return available.length > 0 ? available : Object.keys(registry)
}

export async function getPlatformAsync(name: string): Promise<SocialPlatform> {
  if (loaded[name]) return loaded[name]

  if (name === "bsky") {
    const mod = await import("./bluesky.js")
    loaded[name] = mod.bluesky
  } else if (name === "x") {
    const mod = await import("./x.js")
    loaded[name] = mod.x
  } else {
    throw new Error(`Unknown platform: ${name}. Available: ${Object.keys(registry).join(", ")}`)
  }

  return loaded[name]
}
