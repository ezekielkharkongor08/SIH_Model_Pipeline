import re
from typing import Optional
from agent1_extraction.models.schemas import CharacterSpan


class SpanVerifier:
    """Universal, domain-agnostic noise reduction and character span matching engine."""

    # Generic linguistic noise patterns
    GENERIC_PREFIXES = [
        r"^(?:it is|investigation|records|cctv|sources?|according to|as reported by|evidence|report|document)\s+(?:reveals?|shows?|confirms?|indicates?|states?)\s+(?:that\s+)?",
        r"^(?:the|a|an)\s+(?:accused|complainant|suspect|victim|witness|subject)\s+",
        r"^(?:reported|stated|declared)\s+that\s+"
    ]

    GENERIC_SUFFIXES = [
        r"\s+on\s+(?:whatsapp|telegram|signal|phone|email).*$",
        r"\s+(?:near|at|around|beside|inside)\s+.*$",
        r"\s+via\s+.*$",
        r"\s+at\s+\d{1,2}:\d{2}.*$"
    ]

    @classmethod
    def sanitize_entity_name(cls, raw_name: str) -> str:
        cleaned = raw_name.strip()

        for pattern in cls.GENERIC_PREFIXES:
            cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)

        for pattern in cls.GENERIC_SUFFIXES:
            cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)

        return cleaned.strip()

    @classmethod
    def find_span(cls, source_text: str, entity_name: str) -> Optional[CharacterSpan]:
        if source_text.startswith("data:image"):
            return None

        clean_name = cls.sanitize_entity_name(entity_name)
        if not clean_name:
            return None

        pattern = re.escape(clean_name)
        match = re.search(pattern, source_text, re.IGNORECASE)

        if match:
            start, end = match.span()
            return CharacterSpan(
                start_char=start,
                end_char=end,
                exact_text=source_text[start:end]
            )

        return None