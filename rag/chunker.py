"""Grammar-entry, vocab-batch, and paragraph chunking strategies."""
import re
from typing import List


def chunk_grammar_entry(text: str, source_url: str,
                         language: str, exam: str, level: str) -> List[dict]:
    """
    Split a long grammar page into individual entry chunks.
    Splits on double newline or numbered-item patterns.
    """
    chunks = []
    # Try to split on numbered patterns or header lines
    entries = re.split(r"\n{2,}|\n(?=\d+\.\s|\#{1,3}\s)", text)
    for i, entry in enumerate(entries):
        entry = entry.strip()
        if len(entry) < 30:
            continue
        chunks.append({
            "language": language,
            "exam": exam,
            "level": level,
            "content_type": "grammar",
            "source_url": source_url,
            "chunk_text": entry[:1000],
            "chunk_index": i,
            "grammar_point": _extract_grammar_point(entry),
        })
    return chunks


def chunk_vocab_batch(words: List[str], source_url: str,
                       language: str, exam: str, level: str,
                       batch_size: int = 10) -> List[dict]:
    """Batch vocabulary words into chunks of batch_size."""
    chunks = []
    for i in range(0, len(words), batch_size):
        batch = words[i:i + batch_size]
        if not batch:
            continue
        chunks.append({
            "language": language,
            "exam": exam,
            "level": level,
            "content_type": "vocabulary",
            "source_url": source_url,
            "chunk_text": "Vocabulary:\n" + "\n".join(batch),
            "chunk_index": i // batch_size,
            "grammar_point": None,
        })
    return chunks


def chunk_paragraph(text: str, source_url: str,
                     language: str, exam: str, level: str,
                     content_type: str = "grammar",
                     max_chars: int = 800) -> List[dict]:
    """Split arbitrary text into paragraph-sized chunks."""
    paragraphs = re.split(r"\n{2,}", text.strip())
    chunks = []
    buffer = ""
    chunk_idx = 0

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        if len(buffer) + len(para) > max_chars and buffer:
            chunks.append({
                "language": language,
                "exam": exam,
                "level": level,
                "content_type": content_type,
                "source_url": source_url,
                "chunk_text": buffer.strip(),
                "chunk_index": chunk_idx,
                "grammar_point": _extract_grammar_point(buffer),
            })
            chunk_idx += 1
            buffer = para
        else:
            buffer = (buffer + "\n\n" + para).strip()

    if buffer:
        chunks.append({
            "language": language,
            "exam": exam,
            "level": level,
            "content_type": content_type,
            "source_url": source_url,
            "chunk_text": buffer,
            "chunk_index": chunk_idx,
            "grammar_point": _extract_grammar_point(buffer),
        })
    return chunks


def _extract_grammar_point(text: str) -> str:
    """Heuristically extract a grammar point label from the first line."""
    first_line = text.split("\n")[0].strip()
    # Remove markdown headers
    first_line = re.sub(r"^#{1,3}\s*", "", first_line)
    # Remove numbering
    first_line = re.sub(r"^\d+\.\s*", "", first_line)
    return first_line[:100]
