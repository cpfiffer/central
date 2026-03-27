# Common Errors

## Cards Not Appearing in Collection

**Symptom**: Created collectionLink but card doesn't show in Semble UI.

**Cause**: Missing `addedBy` or `addedAt` fields. Semble's firehose processor validates these and silently rejects records missing them.

**Fix**: Ensure collectionLink has all required fields:
```json
{
  "card": {"uri": "...", "cid": "..."},
  "collection": {"uri": "...", "cid": "..."},
  "addedBy": "did:plc:...",
  "addedAt": "2026-03-27T12:00:00.000Z",
  "createdAt": "2026-03-27T12:00:00.000Z"
}
```

## Wrong collectionLink Format

**Symptom**: Record created but Semble doesn't recognize it.

**Wrong**:
```json
{"subject": "at://...", "collection": "at://..."}
```

**Correct**:
```json
{"card": {"uri": "...", "cid": "..."}, "collection": {"uri": "...", "cid": "..."}}
```

## NOTE Cards Not Showing

**Symptom**: NOTE card created but invisible in collection.

**Cause**: NOTE cards require `parentCard` reference. They are attachments to URL cards, not standalone content.

**Fix**: Always specify parentCard when creating NOTE:
```json
{
  "type": "NOTE",
  "content": "Text content",
  "parentCard": {"uri": "...", "cid": "..."}
}
```

## Card CID Not Found

**Symptom**: "Card CID not found" error when linking.

**Cause**: Card doesn't exist or wrong rkey.

**Fix**: Verify card exists with `card show <rkey>` before linking.

## Auth Failures

**Symptom**: "Auth failed" or 401 errors.

**Cause**: Wrong password variable or expired session.

**Fix**:
- Check `.env` has `ATPROTO_APP_PASSWORD` (not `CENTRAL_APP_PASSWORD`)
- Password should be an app-specific password from Bluesky settings

## Module Not Found

**Symptom**: `ModuleNotFoundError: No module named 'tools'`

**Fix**: Run from `/home/cameron/central` with:
```bash
uv run python -m tools.cli <command>
```

Not:
```bash
python tools/cli.py  # WRONG
```

## Indexer Delay

**Symptom**: Records created but Semble UI doesn't update immediately.

**Cause**: Semble's firehose processor has a few seconds delay.

**Fix**: Wait 5-10 seconds. If still not appearing, check for validation errors (missing fields).
