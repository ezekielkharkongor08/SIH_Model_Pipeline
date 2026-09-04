import re
from typing import Optional
from agent1_extraction.models.schemas import CharacterSpan


class SpanVerifier:
    """General-purpose noise removal and character span matching engine."""

    # Generic linguistic prefix noise (Reporting clauses & determiners across any domain)
    GENERIC_PREFIXES = [
        r"^(?:it is|investigation|records|cctv|sources?|according to|as reported by|evidence|report|document|data|log)\s+(?:reveals?|shows?|confirms?|indicates?|states?|found)\s+(?:that\s+)?",
        r"^(?:the|a|an)\s+(?:accused|complainant|suspect|victim|witness|subject|patient|user|client)\s+",
        r"^(?:reported|stated|declared|observed)\s+that\s+",
        r"^(?:confirms|reveals|indicates|shows)\s+that\s+"
    ]

    # Generic suffix noise (Communication channels, transit modes, temporal attachments)
    GENERIC_SUFFIXES = [
        r"\s+on\s+(?:whatsapp|telegram|signal|phone|email|chat|slack|teams).*$",
        r"\s+(?:near|at|around|beside|inside|located in)\s+.*$",
        r"\s+via\s+(?:rtgs|neft|hawala|transfer|wire|bank|smtp|http).*$",
        r"\s+at\s+\d{1,2}:\d{2}.*$"
    ]

    @classmethod
    def sanitize_entity_name(cls, raw_name: str) -> str:
        """Strips structural noise from entity strings universally."""
        cleaned = raw_name.strip()

        for pattern in cls.GENERIC_PREFIXES:
            cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)

        for pattern in cls.GENERIC_SUFFIXES:
            cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)

        return cleaned.strip()

    @classmethod
    def sanitize_predicate(cls, predicate: str, object_name: str) -> str:
        """Algorithmic predicate sanitization (strips duplicate object tokens without hardcoding entities)."""
        clean_pred = predicate.strip().lower().replace(" ", "_")
        clean_obj = cls.sanitize_entity_name(object_name).lower().replace(" ", "_")

        # Dynamically strip object name if embedded at the end of predicate
        if clean_obj and len(clean_obj) > 2 and clean_pred.endswith(f"_{clean_obj}"):
            clean_pred = clean_pred[:-len(f"_{clean_obj}")]

        # Standardize formatting to snake_case verbs
        clean_pred = re.sub(r"[^\w\s_]", "", clean_pred)
        return clean_pred.strip("_")

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