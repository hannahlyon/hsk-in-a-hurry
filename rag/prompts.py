"""System and content prompt templates for RAG generation."""
from typing import List

SYSTEM_TEMPLATE = """You are an expert language learning content creator specialising in {language} for {level} {exam} exam learners.

Your content must:
- Be pedagogically appropriate for {level} proficiency
- Naturally incorporate the provided grammar structures and vocabulary
- Be engaging, culturally authentic, and exam-focused
- Use correct {language} with clear English explanations where needed

Always write in the requested format. Do not deviate from the format instructions."""


def build_system_prompt(language: str, exam: str, level: str) -> str:
    return SYSTEM_TEMPLATE.format(language=language, exam=exam, level=level)


def build_content_prompt(
    content_format: str,
    theme: str,
    language: str,
    level: str,
    grammar_chunks: List[str],
    vocab_chunks: List[str],
) -> str:
    if grammar_chunks:
        grammar_header = f"RETRIEVED GRAMMAR STRUCTURES — {len(grammar_chunks)} items — use EACH ONE at least once:"
        grammar_text = "\n\n".join(f"[G{i+1}] {chunk}" for i, chunk in enumerate(grammar_chunks))
    else:
        grammar_header = "RETRIEVED GRAMMAR STRUCTURES — 0 items:"
        grammar_text = "(No grammar data retrieved — use appropriate structures for this level)"

    if vocab_chunks:
        vocab_header = f"RETRIEVED VOCABULARY — {len(vocab_chunks)} items — use EACH ONE at least once:"
        vocab_text = "\n".join(f"[V{i+1}] {chunk}" for i, chunk in enumerate(vocab_chunks))
    else:
        vocab_header = "RETRIEVED VOCABULARY — 0 items:"
        vocab_text = "(No vocabulary data retrieved — use appropriate words for this level)"

    format_instructions = _get_format_instructions(content_format)

    return f"""{grammar_header}
{grammar_text}

{vocab_header}
{vocab_text}

TASK: Write a {content_format} for {language} {level} learners on the theme: "{theme}"

These are real curriculum items from a {level} database. Build the content AROUND them.
Do not substitute them with other grammar or vocabulary.
In the closing "Grammar & Vocabulary" section, reference each item by its [G#] / [V#] tag.

{format_instructions}"""


def _get_format_instructions(content_format: str) -> str:
    instructions = {
        "blurb": """FORMAT REQUIREMENTS:
- 150–200 words in the target language
- Keep language natural and conversational
- End with this section in English:

## Grammar & Vocabulary

### Grammar Used
For each grammar structure used, provide:
- **Pattern** — the structure or pattern name
- **Example** — the sentence from your blurb that uses it (target language + English translation)
- **Note** — one sentence explaining when/how to use it

### Vocabulary Used
A markdown table of every notable word or phrase from your blurb:
| Word / Phrase | Reading | English | Usage note |
|---|---|---|---|""",

        "story": """FORMAT REQUIREMENTS:
- 400–600 words of narrative in the target language
- Include a title on its own line before the story
- Use vivid, culturally authentic details
- End with this section in English:

## Grammar & Vocabulary

### Grammar Used
For each grammar structure used in the story, provide:
- **Pattern** — the structure or pattern name
- **Example** — copy the sentence from your story that uses it (target language + English translation)
- **Note** — one sentence explaining when/how to use it

### Vocabulary Used
A markdown table of every notable word or phrase from your story:
| Word / Phrase | Reading | English | Example sentence from story |
|---|---|---|---|""",

        "dialogue": """FORMAT REQUIREMENTS:
- 10–16 exchanges between 2 speakers (label as Speaker A / Speaker B)
- Set the scene in one sentence before the dialogue
- Make the conversation natural and idiomatic
- End with these two sections in English:

## Key Phrases
For each important phrase from the dialogue:
- **Phrase** (target language) — literal English translation — usage note

## Grammar & Vocabulary

### Grammar Used
For each grammar structure used in the dialogue, provide:
- **Pattern** — the structure or pattern name
- **Example** — copy the line from your dialogue that uses it (target language + English translation)
- **Note** — one sentence explaining when/how to use it

### Vocabulary Used
A markdown table of every notable word or phrase from your dialogue:
| Word / Phrase | Reading | English | Used in line |
|---|---|---|---|""",

        "matching": """FORMAT REQUIREMENTS:
- Create a 10-item matching table with two columns:
  | Target Language Sentence | English Meaning |
  |---|---|
- Use the grammar structures and vocabulary naturally in each sentence
- After the table, include:

## Answer Key
[Numbered list confirming the correct matches]

## Grammar & Vocabulary

### Grammar Used
For each grammar structure used in the sentences, provide:
- **Pattern** — the structure or pattern name
- **Example** — the sentence from the table that uses it (target language + English translation)
- **Note** — one sentence explaining when/how to use it

### Vocabulary Used
A markdown table of every notable word or phrase from the sentences:
| Word / Phrase | Reading | English | Usage note |
|---|---|---|---|""",
    }
    return instructions.get(content_format, instructions["blurb"])


def build_social_copy_prompt(platform: str, post_title: str, post_summary: str,
                               language: str, level: str,
                               max_chars: int, num_hashtags: int) -> str:
    return f"""Write engaging social media copy for {platform} to promote a {language} language learning newsletter post.

Post title: {post_title}
Post summary: {post_summary}
Target audience: {language} learners at {level} level

Requirements:
- Maximum {max_chars} characters for the copy text
- Include exactly {num_hashtags} relevant hashtags
- Tone should match {platform}'s culture ({"professional" if platform == "LinkedIn" else "engaging and conversational"})
- Include a call-to-action
- Optionally include 1-2 words/phrases in {language} with translation

Return your response as valid JSON with this exact structure:
{{
  "copy_text": "your copy here",
  "hashtags": ["hashtag1", "hashtag2", ...]
}}"""


def build_dalle_prompt(post_title: str, language: str, level: str, theme: str) -> str:
    return (
        f"A vibrant, educational illustration for a {language} language learning newsletter. "
        f"Theme: {theme}. Style: modern, clean infographic aesthetic with soft gradients, "
        f"cultural elements from {language}-speaking countries. "
        f"No text or words in the image. Professional, inviting, suitable for social media."
    )
