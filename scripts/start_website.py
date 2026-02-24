"""Convenience launcher for the subscriber website server.

Usage:
    python scripts/start_website.py
    python scripts/start_website.py --port 8001
    python scripts/start_website.py --reload      # hot-reload for development
"""
import argparse
import sys
from pathlib import Path

# Ensure project root is on sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

import uvicorn


def main() -> None:
    parser = argparse.ArgumentParser(description="Start the subscriber website server")
    parser.add_argument("--port", type=int, default=8001, help="Port to listen on (default: 8001)")
    parser.add_argument("--reload", action="store_true", help="Enable hot-reload (development only)")
    args = parser.parse_args()

    uvicorn.run(
        "website.server:app",
        host="0.0.0.0",
        port=args.port,
        reload=args.reload,
    )


if __name__ == "__main__":
    main()
