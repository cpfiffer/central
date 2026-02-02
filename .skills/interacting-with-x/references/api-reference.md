# X API v2 Reference

## Authentication

Uses OAuth 1.0a User Context for most operations. Bearer token for read-only.

### Required Environment Variables

```
X_API_KEY          # Consumer key (API Key)
X_API_SECRET       # Consumer secret (API Secret)
X_ACCESS_TOKEN     # User access token
X_ACCESS_TOKEN_SECRET  # User access token secret
X_BEARER_TOKEN     # App-only bearer token (optional, for read operations)
```

## Rate Limits

### Pro Tier (what we have)

| Endpoint | Limit | Window |
|----------|-------|--------|
| POST /tweets | 500 tweets | 24 hours |
| GET /tweets | 10,000 | 24 hours |
| GET /users/:id/mentions | 450 | 15 minutes |
| GET /users/:id/tweets | 1,500 | 15 minutes |
| POST /users/:id/likes | 500 | 24 hours |
| POST /users/:id/retweets | 500 | 24 hours |
| POST /users/:id/following | 500 | 24 hours |

### Handling Rate Limits

Tweepy raises `tweepy.TooManyRequests` when rate limited. The scripts catch this and report the reset time.

```python
try:
    client.create_tweet(text=text)
except tweepy.TooManyRequests as e:
    reset_time = e.response.headers.get('x-rate-limit-reset')
    print(f"Rate limited. Reset at: {reset_time}")
```

## Character Limits

| Account Type | Limit |
|--------------|-------|
| Standard | 280 characters |
| Pro | 25,000 characters |
| Premium | 25,000 characters |

## Media Upload

Media upload uses v1.1 API (still required for media):

```python
auth = tweepy.OAuth1UserHandler(api_key, api_secret, access_token, access_token_secret)
api = tweepy.API(auth)
media = api.media_upload(filename)
# Then use media.media_id_string in v2 create_tweet
```

### Supported Media

| Type | Max Size | Formats |
|------|----------|---------|
| Image | 5MB | PNG, JPEG, GIF, WEBP |
| Video | 512MB | MP4 |
| GIF | 15MB | GIF |

## Error Codes

| Code | Meaning |
|------|---------|
| 32 | Could not authenticate |
| 34 | Page does not exist |
| 63 | User suspended |
| 88 | Rate limit exceeded |
| 89 | Invalid/expired token |
| 130 | Over capacity |
| 131 | Internal error |
| 186 | Tweet too long |
| 187 | Duplicate tweet |
| 226 | Automated request |

## Common Patterns

### Thread Creation

```python
reply_to = None
for text in thread_texts:
    response = client.create_tweet(
        text=text,
        in_reply_to_tweet_id=reply_to
    )
    reply_to = response.data['id']
```

### Quote Tweet

```python
client.create_tweet(
    text="My commentary",
    quote_tweet_id="1234567890"
)
```

### Reply with Mention

When replying, the @mention is NOT auto-included in v2. Add it explicitly:

```python
client.create_tweet(
    text="@username Your reply here",
    in_reply_to_tweet_id="1234567890"
)
```

## Links

- X API v2 Docs: https://developer.x.com/en/docs/twitter-api
- Tweepy Docs: https://docs.tweepy.org/en/stable/
- Rate Limits: https://developer.x.com/en/docs/twitter-api/rate-limits
