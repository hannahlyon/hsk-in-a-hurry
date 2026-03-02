"""CLI script — post a tweet via Twitter API v2.

Usage:
    # Inline text
    python scripts/post_to_twitter.py --text "Hello from the newsletter! #JLPT #Japanese"

    # Read tweet text from a file
    python scripts/post_to_twitter.py --file tweet.txt

    # Pipe text in
    echo "Hello world" | python scripts/post_to_twitter.py

Required env vars (set in .env):
    TWITTER_API_KEY, TWITTER_API_SECRET,
    TWITTER_ACCESS_TOKEN, TWITTER_ACCESS_TOKEN_SECRET
"""
import argparse
import sys
from pathlib import Path

# Ensure project root is on sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from config.settings import (
    TWITTER_API_KEY,
    TWITTER_API_SECRET,
    TWITTER_ACCESS_TOKEN,
    TWITTER_ACCESS_TOKEN_SECRET,
)


def _check_credentials() -> None:
    missing = [
        name for name, val in {
            "TWITTER_API_KEY": TWITTER_API_KEY,
            "TWITTER_API_SECRET": TWITTER_API_SECRET,
            "TWITTER_ACCESS_TOKEN": TWITTER_ACCESS_TOKEN,
            "TWITTER_ACCESS_TOKEN_SECRET": TWITTER_ACCESS_TOKEN_SECRET,
        }.items()
        if not val
    ]
    if missing:
        print(
            f"ERROR: Missing Twitter credentials in .env: {', '.join(missing)}\n"
            "See .env.example for instructions.",
            file=sys.stderr,
        )
        sys.exit(1)


def post_tweet(text: str) -> dict:
    """Post *text* as a tweet. Returns dict with tweet_id and tweet_url."""
    import tweepy

    client = tweepy.Client(
        consumer_key=TWITTER_API_KEY,
        consumer_secret=TWITTER_API_SECRET,
        access_token=TWITTER_ACCESS_TOKEN,
        access_token_secret=TWITTER_ACCESS_TOKEN_SECRET,
    )
    response = client.create_tweet(text=text)
    tweet_id = str(response.data["id"])
    return {
        "tweet_id": tweet_id,
        "tweet_url": f"https://x.com/i/web/status/{tweet_id}",
        "text": text,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Post a tweet via Twitter API v2.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--text", "-t", type=str, help="Tweet text (max 280 chars)")
    group.add_argument("--file", "-f", type=str, help="Path to a .txt file containing the tweet")
    args = parser.parse_args()

    # Resolve tweet text from --text, --file, or stdin
    if args.text:
        text = args.text.strip()
    elif args.file:
        text = Path(args.file).read_text(encoding="utf-8").strip()
    elif not sys.stdin.isatty():
        text = sys.stdin.read().strip()
    else:
        parser.error("Provide --text, --file, or pipe text via stdin.")

    if not text:
        print("ERROR: Tweet text is empty.", file=sys.stderr)
        sys.exit(1)

    if len(text) > 280:
        print(
            f"ERROR: Tweet is {len(text)} characters — Twitter limit is 280.\n"
            f"Truncate your text before posting.",
            file=sys.stderr,
        )
        sys.exit(1)

    _check_credentials()

    print(f"Posting tweet ({len(text)} chars)…")
    result = post_tweet(text)
    print(f"  tweet_id : {result['tweet_id']}")
    print(f"  url      : {result['tweet_url']}")
    print(f"  text     : {result['text']}")


if __name__ == "__main__":
    main()
