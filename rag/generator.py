"""Claude API calls for content generation with streaming support."""
from typing import Generator, List, Optional

import anthropic

from config.settings import ANTHROPIC_API_KEY, CLAUDE_MODEL
from rag.prompts import build_system_prompt, build_content_prompt
from utils.logger import get_logger

log = get_logger(__name__)


def _get_client() -> anthropic.Anthropic:
    if not ANTHROPIC_API_KEY:
        raise ValueError("ANTHROPIC_API_KEY not set in .env")
    return anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)


def generate_content(
    language: str,
    exam: str,
    level: str,
    theme: str,
    content_format: str,
    grammar_chunks: List[str],
    vocab_chunks: List[str],
    max_tokens: int = 2048,
) -> str:
    """
    Generate newsletter content using Claude (non-streaming).
    Returns the full generated text.
    """
    client = _get_client()
    system = build_system_prompt(language, exam, level)
    user = build_content_prompt(
        content_format, theme, language, level, grammar_chunks, vocab_chunks
    )

    log.info(
        "Generating %s content: %s %s %s theme='%s'",
        content_format, language, exam, level, theme,
    )

    response = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    text = response.content[0].text
    log.info("Generated %d chars", len(text))
    return text


def stream_content(
    language: str,
    exam: str,
    level: str,
    theme: str,
    content_format: str,
    grammar_chunks: List[str],
    vocab_chunks: List[str],
    max_tokens: int = 2048,
) -> Generator[str, None, None]:
    """
    Stream content generation from Claude.
    Yields text chunks as they arrive.
    """
    client = _get_client()
    system = build_system_prompt(language, exam, level)
    user = build_content_prompt(
        content_format, theme, language, level, grammar_chunks, vocab_chunks
    )

    log.info(
        "Streaming %s content: %s %s %s theme='%s'",
        content_format, language, exam, level, theme,
    )

    with client.messages.stream(
        model=CLAUDE_MODEL,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user}],
    ) as stream:
        for text_chunk in stream.text_stream:
            yield text_chunk


def generate_title(content_raw: str, language: str, level: str) -> str:
    """Generate a concise newsletter post title from raw content."""
    client = _get_client()
    prompt = (
        f"Generate a compelling, concise newsletter post title (max 70 chars) "
        f"for this {language} {level} language learning content. "
        f"Return only the title, no quotes or explanation.\n\n"
        f"Content preview:\n{content_raw[:500]}"
    )
    response = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=100,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text.strip()
