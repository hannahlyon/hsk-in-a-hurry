"""CLI script — social media asset generation for an existing post.

Usage examples:
    python scripts/generate_social.py --list-posts
    python scripts/generate_social.py --post-id 7
    python scripts/generate_social.py --post-id 7 --platforms Instagram LinkedIn
"""
import re
import sys
from pathlib import Path

# Ensure project root is on sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

import argparse

from database.db import init_db, get_generated_post, get_generated_posts, insert_social_post
from tabs.tab_social import PLATFORMS, _make_dalle_prompt, _generate_caption, _generate_image
from config.settings import DATA_DIR


def _print_posts(posts: list) -> None:
    if not posts:
        print("No generated posts found. Run generate_content.py first.")
        return
    print(f"{'ID':<6} {'Language':<22} {'Exam':<8} {'Level':<8} {'Format':<12} Title")
    print("-" * 90)
    for p in posts[:30]:
        title = (p["title"] or "")[:40]
        print(
            f"{p['id']:<6} {(p['language'] or ''):<22} {(p['exam'] or ''):<8} "
            f"{(p['level'] or ''):<8} {(p['content_type'] or ''):<12} {title}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate social media images and captions for an existing post.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--post-id", type=int, default=None,
                        help="ID of the generated_post to use")
    parser.add_argument("--platforms", type=str, nargs="+",
                        choices=list(PLATFORMS.keys()),
                        metavar="PLATFORM",
                        help=(
                            "Platforms to generate for "
                            f"(default: all). Choices: {', '.join(PLATFORMS.keys())}"
                        ))
    parser.add_argument("--list-posts", action="store_true",
                        help="Print recent generated posts and exit")
    args = parser.parse_args()

    init_db()

    if args.list_posts:
        _print_posts(get_generated_posts())
        sys.exit(0)

    if args.post_id is None:
        parser.error("--post-id is required. Use --list-posts to see available posts.")

    post = get_generated_post(args.post_id)
    if post is None:
        print(f"ERROR: No generated_post with id={args.post_id}", file=sys.stderr)
        sys.exit(1)

    platforms = args.platforms or list(PLATFORMS.keys())

    print(
        f"Post      : id={post['id']}  \"{post['title']}\"\n"
        f"Language  : {post['language']}  Exam: {post['exam']}  Level: {post['level']}\n"
        f"Platforms : {', '.join(platforms)}\n"
    )

    for platform in platforms:
        specs = PLATFORMS[platform]
        platform_slug = re.sub(r"[^a-z0-9]+", "_", platform.lower()).strip("_")

        print(f"[{platform}] Generating image prompt…", end=" ", flush=True)
        dalle_prompt = _make_dalle_prompt(post, platform)
        print("done.")

        print(f"[{platform}] Writing caption…", end=" ", flush=True)
        caption = _generate_caption(post, platform, specs)
        print("done.")

        print(f"[{platform}] Generating DALL-E image…", end=" ", flush=True)
        img_bytes = _generate_image(dalle_prompt, specs["image_size"])
        print(f"{len(img_bytes):,} bytes.")

        img_dir = DATA_DIR / "social_images" / str(post["id"])
        img_dir.mkdir(parents=True, exist_ok=True)
        img_path = img_dir / f"{platform_slug}.png"
        img_path.write_bytes(img_bytes)

        social_id = insert_social_post(
            generated_post_id=post["id"],
            platform=platform,
            copy_text=caption,
            image_prompt=dalle_prompt,
            image_path=str(img_path),
            image_size=specs["image_size"],
        )
        print(f"  {platform}: image saved → {img_path}  (social_post id={social_id})")

    print("\nDone.")


if __name__ == "__main__":
    main()
