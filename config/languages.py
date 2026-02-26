"""Language/exam definitions and scrape URL configurations."""
from dataclasses import dataclass, field
from typing import List, Optional

LEVELS_CEFR = ["A1", "A2", "B1", "B2", "C1", "C2"]
LEVELS_JLPT = ["N5", "N4", "N3", "N2", "N1"]
LEVELS_HSK_CLASSIC = ["HSK1", "HSK2", "HSK3", "HSK4", "HSK5", "HSK6"]
LEVELS_HSK_NEW = [f"HSK{i}" for i in range(1, 10)]
LEVELS_TOPIK = ["Level 1", "Level 2", "Level 3", "Level 4", "Level 5", "Level 6"]


@dataclass
class ExamConfig:
    language: str
    exam: str
    levels: List[str]
    chroma_collection: str
    scrape_urls: dict = field(default_factory=dict)
    description: str = ""


EXAM_CONFIGS: dict[str, ExamConfig] = {
    "spanish_dele": ExamConfig(
        language="Spanish",
        exam="DELE",
        levels=LEVELS_CEFR,
        chroma_collection="lang_spanish_dele",
        scrape_urls={
            "grammar": "https://www.spanishgrammar.net/category/dele/{level}/",
            "vocabulary": "https://en.wiktionary.org/wiki/Wiktionary:Frequency_lists/Spanish",
        },
        description="Diplomas de Español como Lengua Extranjera",
    ),
    "french_delf": ExamConfig(
        language="French",
        exam="DELF/DALF",
        levels=LEVELS_CEFR,
        chroma_collection="lang_french_delf_dalf",
        scrape_urls={
            "grammar": "https://www.french-exam.com/category/delf-dalf-exam-preparation/delf-{level}/",
            "vocabulary": "https://www.1000mostcommonwords.com/1000-most-common-french-words/",
        },
        description="Diplôme d'Études en Langue Française / Diplôme Approfondi",
    ),
    "japanese_jlpt": ExamConfig(
        language="Japanese",
        exam="JLPT",
        levels=LEVELS_JLPT,
        chroma_collection="lang_japanese_jlpt",
        scrape_urls={
            "grammar": "https://jlptsensei.com/jlpt-{level}-grammar-list/",
            "vocabulary": "https://jlptsensei.com/jlpt-{level}-vocabulary-list/",
        },
        description="Japanese Language Proficiency Test",
    ),
    "mandarin_hsk": ExamConfig(
        language="Mandarin Chinese",
        exam="HSK",
        levels=LEVELS_HSK_CLASSIC,
        chroma_collection="lang_mandarin_chinese_hsk",
        scrape_urls={
            "grammar": "https://www.digmandarin.com/hsk-{level_num}-grammar",
            "vocabulary": "https://hsk.academy/en/hsk-{level_num}-vocabulary-list",
        },
        description="Hanyu Shuiping Kaoshi (Chinese Proficiency Test)",
    ),
    "korean_topik": ExamConfig(
        language="Korean",
        exam="TOPIK",
        levels=LEVELS_TOPIK,
        chroma_collection="lang_korean_topik",
        scrape_urls={
            "grammar_topik1": "https://topikguide.com/topik-grammar/topik-1-grammar/",
            "grammar_topik2": "https://topikguide.com/topik-grammar/topik-2-grammar/",
            "vocabulary": "https://en.wiktionary.org/wiki/Wiktionary:Frequency_lists/Korean_5800",
        },
        description="Test of Proficiency in Korean",
    ),
}

# Map display name → config key
LANGUAGE_OPTIONS = {
    "Spanish (DELE)": "spanish_dele",
    "French (DELF/DALF)": "french_delf",
    "Japanese (JLPT)": "japanese_jlpt",
    "Mandarin Chinese (HSK)": "mandarin_hsk",
    "Korean (TOPIK)": "korean_topik",
    "Custom Language": "custom",
}


def get_levels_for_exam(exam_key: str) -> List[str]:
    if exam_key in EXAM_CONFIGS:
        return EXAM_CONFIGS[exam_key].levels
    return LEVELS_CEFR


def get_collection_name(language: str, exam: str) -> str:
    slug = f"{language}_{exam}".lower().replace(" ", "_").replace("/", "_")
    return f"lang_{slug}"
