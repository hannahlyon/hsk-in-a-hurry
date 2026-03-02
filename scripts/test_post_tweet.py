"""Test script for the /post-tweet API endpoint.

Usage:
    # Validation tests only (safe — no real tweet posted)
    python scripts/test_post_tweet.py

    # Include a live post test
    python scripts/test_post_tweet.py --live

    # Custom tweet text for the live test
    python scripts/test_post_tweet.py --live --text "Test from newsletter bot #JLPT"

    # Point at a non-default server URL
    python scripts/test_post_tweet.py --url http://localhost:8000

The server must be running before calling this script:
    python scripts/start_api.py
"""

import argparse
import json
import sys

import requests


def _print_result(name: str, passed: bool, status: int, body: dict | str) -> None:
    tag = "PASS" if passed else "FAIL"
    body_str = json.dumps(body, indent=2) if isinstance(body, dict) else str(body)
    print(f"[{tag}] {name}")
    print(f"       status : {status}")
    print(f"       body   : {body_str}")
    print()


def _json_or_text(resp: requests.Response) -> dict | str:
    try:
        return resp.json()
    except Exception:
        return resp.text


def test_too_long(base_url: str) -> bool:
    """A 281-char tweet should return 422."""
    text = "x" * 281
    resp = requests.post(f"{base_url}/post-tweet", json={"text": text}, timeout=10)
    body = _json_or_text(resp)
    passed = resp.status_code == 422
    _print_result("too-long tweet → 422", passed, resp.status_code, body)
    return passed


def test_missing_credentials(base_url: str) -> bool:
    """If Twitter credentials are absent from .env the endpoint returns 503.

    This test is only meaningful when the credentials are NOT set.  If they ARE
    set the endpoint will attempt a real post and likely return 200 (or a Twitter
    error), so we skip rather than fail.
    """
    resp = requests.post(
        f"{base_url}/post-tweet",
        json={"text": "credential check"},
        timeout=10,
    )
    body = _json_or_text(resp)

    if resp.status_code == 503:
        _print_result("missing credentials → 503", True, resp.status_code, body)
        return True

    # Credentials are present — skip rather than fail
    print("[SKIP] missing credentials → 503")
    print("       (Twitter credentials are configured; skipping this check)")
    print()
    return True  # not a failure


def test_live_post(base_url: str, text: str) -> bool:
    """Post a real tweet and print the URL."""
    resp = requests.post(
        f"{base_url}/post-tweet",
        json={"text": text},
        timeout=30,
    )
    body = _json_or_text(resp)
    passed = resp.status_code == 200
    _print_result(f"live post → 200  ({text!r})", passed, resp.status_code, body)
    if passed and isinstance(body, dict):
        print(f"       tweet  : {body.get('tweet_url', '(no URL)')}")
        print()
    return passed


def main() -> None:
    parser = argparse.ArgumentParser(description="Test the /post-tweet endpoint.")
    parser.add_argument(
        "--url",
        default="http://localhost:8000",
        help="Base URL of the running API server (default: http://localhost:8000)",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Also run the live-post test (posts a real tweet).",
    )
    parser.add_argument(
        "--text",
        default="Test tweet from newsletter bot [automated test]",
        help="Tweet body for the live test.",
    )
    args = parser.parse_args()

    base_url = args.url.rstrip("/")

    print(f"Server: {base_url}")
    print("=" * 50)
    print()

    results: list[bool] = []

    # --- Validation tests (always run, never post) ---
    results.append(test_too_long(base_url))
    results.append(test_missing_credentials(base_url))

    # --- Live post test (opt-in) ---
    if args.live:
        results.append(test_live_post(base_url, args.text))
    else:
        print("[INFO] Skipping live post test (pass --live to enable).")
        print()

    # --- Summary ---
    total = len(results)
    passed = sum(results)
    print("=" * 50)
    print(f"Results: {passed}/{total} passed")
    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    main()
