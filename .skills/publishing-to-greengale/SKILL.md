---
name: publishing-to-greengale
description: Publish long-form blog posts to ATProtocol via GreenGale. Use when writing blog posts, essays, or long-form content that should live on the decentralized web. Handles the V2 document schema, PDS authentication, and link generation. Produces viewable posts at greengale.app.
---

# Publishing to GreenGale

GreenGale is a markdown blog platform on ATProtocol. Posts are stored as `app.greengale.document` records on your PDS and viewable at `https://greengale.app/<handle>/<rkey>`.

## When to Use

- Writing blog posts, essays, or long-form technical content
- Cameron says "write a blog post" or "publish this to GreenGale"
- Content exceeds Bluesky's 300 grapheme limit and deserves a permanent URL
- You want ATProtocol-native publishing (data lives on our PDS, not a static site)

## Quick Publish

```bash
uv run python .skills/publishing-to-greengale/scripts/publish.py \
  --title "Post Title" \
  --rkey "url-slug" \
  --file path/to/content.md
```

Or with inline content:

```bash
uv run python .skills/publishing-to-greengale/scripts/publish.py \
  --title "Post Title" \
  --rkey "url-slug" \
  --content "# Markdown content here"
```

Options:
- `--subtitle "Optional subtitle"`
- `--theme github-dark` (default). Options: `github-light`, `github-dark`, `dracula`, `nord`, `solarized-light`, `solarized-dark`, `monokai`
- `--visibility public` (default). Options: `public`, `url` (unlisted), `author` (private)

Output: AT URI and viewable URL.

## Record Schema (V2)

```json
{
  "$type": "app.greengale.document",
  "content": "# Markdown content",
  "url": "https://greengale.app",
  "path": "/<handle>/<rkey>",
  "title": "Post Title",
  "subtitle": "Optional subtitle",
  "publishedAt": "2026-02-08T08:00:00Z",
  "visibility": "public",
  "theme": { "preset": "github-dark" }
}
```

Collection: `app.greengale.document`. Record key is the `rkey` argument (use a readable slug).

## After Publishing

1. Post the link to Bluesky: `uv run python tools/thread.py "Description... https://greengale.app/<handle>/<rkey>"`
2. Post to X: `uv run python .skills/interacting-with-x/scripts/post.py "Description... https://greengale.app/<handle>/<rkey>"`
3. The post is immediately viewable. No build step needed.

## Updating a Post

Use the same `--rkey` to overwrite. The script uses `putRecord` so existing content is replaced.

## Notes

- Content is markdown. GreenGale renders it with syntax highlighting, GFM, and KaTeX.
- Max content length: 100,000 characters.
- Legacy V1 format (`app.greengale.blog.entry`) still works but V2 (`app.greengale.document`) is preferred.
- GreenGale is also compatible with WhiteWind posts (`com.whtwnd.blog.entry`).
- Images require blob uploads to the PDS first (not yet supported in the publish script).
