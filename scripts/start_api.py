"""Convenience launcher for the FastAPI webhook server.

Usage:
    python scripts/start_api.py
    python scripts/start_api.py --port 8080
    python scripts/start_api.py --reload      # hot-reload for development
"""
import argparse
import sys
from pathlib import Path

# Ensure project root is on sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

import uvicorn


def main() -> None:
    parser = argparse.ArgumentParser(description="Start the newsletter automation API server")
    parser.add_argument("--port", type=int, default=8000, help="Port to listen on (default: 8000)")
    parser.add_argument("--reload", action="store_true", help="Enable hot-reload (development only)")
    args = parser.parse_args()

    uvicorn.run(
        "api.main:app",
        host="0.0.0.0",
        port=args.port,
        reload=args.reload,
    )


if __name__ == "__main__":
    main()
