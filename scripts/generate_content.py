"""CLI script — batch newsletter content generation.

Usage examples:
    python scripts/generate_content.py --list
    python scripts/generate_content.py \\
        --language "Mandarin Chinese" --exam HSK \\
        --level HSK3 HSK4 \\
        --theme "ordering food at a restaurant" \\
        --format story
    python scripts/generate_content.py --newsletter-id 1 --level HSK3 --theme "travel"
"""
import argparse
import sys
from pathlib import Path

# Ensure project root is on sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from database.db import init_db, get_newsletters, insert_generated_post
from rag.retriever import retrieve_for_generation
from rag.generator import generate_content, generate_title


FORMATS = ["blurb", "story", "dialogue", "matching"]


def _print_newsletters(newsletters: list) -> None:
    if not newsletters:
        print("No newsletters found. Create one in the Streamlit UI (Tab 1).")
        return
    print(f"{'ID':<6} {'Language':<22} {'Exam':<10} Name")
    print("-" * 70)
    for n in newsletters:
        print(f"{n['id']:<6} {n['language']:<22} {n['exam']:<10} {n['name']}")


def _resolve_newsletter(args, newsletters: list) -> dict:
    if args.newsletter_id is not None:
        for n in newsletters:
            if n["id"] == args.newsletter_id:
                return n
        print(f"ERROR: No newsletter with id={args.newsletter_id}", file=sys.stderr)
        sys.exit(1)

    if args.language and args.exam:
        lang_lower = args.language.lower()
        exam_lower = args.exam.lower()
        for n in newsletters:
            if n["language"].lower() == lang_lower and n["exam"].lower() == exam_lower:
                return n
        print(
            f"ERROR: No newsletter matching language='{args.language}' exam='{args.exam}'",
            file=sys.stderr,
        )
        sys.exit(1)

    print(
        "ERROR: Provide --newsletter-id OR both --language and --exam.\n"
        "Run with --list to see available newsletters.",
        file=sys.stderr,
    )
    sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate newsletter content posts from the CLI.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--newsletter-id", type=int, default=None,
                        help="Newsletter DB id (see --list)")
    parser.add_argument("--language", type=str, default=None,
                        help="Language display name (e.g. 'Mandarin Chinese')")
    parser.add_argument("--exam", type=str, default=None,
                        help="Exam name (e.g. 'HSK')")
    parser.add_argument("--level", type=str, nargs="+", metavar="LEVEL",
                        help="One or more levels (e.g. HSK3 HSK4)")
    parser.add_argument("--theme", type=str, default=None,
                        help="Theme / topic for retrieval and generation")
    parser.add_argument("--format", type=str, choices=FORMATS, default="story",
                        dest="content_format",
                        help="Content format (default: story)")
    parser.add_argument("--list", action="store_true",
                        help="Print all newsletters and exit")
    args = parser.parse_args()

    init_db()
    newsletters = get_newsletters()

    if args.list:
        _print_newsletters(newsletters)
        sys.exit(0)

    if not args.level:
        parser.error("--level is required when generating content")
    if not args.theme:
        parser.error("--theme is required when generating content")

    newsletter = _resolve_newsletter(args, newsletters)
    language = newsletter["language"]
    exam = newsletter["exam"]

    print(
        f"Newsletter : {newsletter['name']}\n"
        f"Language  : {language}  Exam: {exam}\n"
        f"Levels    : {', '.join(args.level)}\n"
        f"Theme     : {args.theme}\n"
        f"Format    : {args.content_format}\n"
    )

    for level in args.level:
        print(f"[{level}] Retrieving context…", end=" ", flush=True)
        grammar_chunks, vocab_chunks = retrieve_for_generation(language, exam, level, args.theme)
        print(f"got {len(grammar_chunks)} grammar + {len(vocab_chunks)} vocab chunks.")

        print(f"[{level}] Generating content…", end=" ", flush=True)
        content_raw = generate_content(
            language, exam, level, args.theme, args.content_format,
            grammar_chunks, vocab_chunks,
        )
        print(f"{len(content_raw)} chars.")

        print(f"[{level}] Generating title…", end=" ", flush=True)
        title = generate_title(content_raw, language, level)
        print(f'"{title}"')

        post_id = insert_generated_post(
            newsletter_id=newsletter["id"],
            title=title,
            content_type=args.content_format,
            language=language,
            exam=exam,
            level=level,
            content_raw=content_raw,
        )
        print(f'  Post saved: id={post_id}  "{title}"  ({level})')

    print("\nDone.")


if __name__ == "__main__":
    main()
