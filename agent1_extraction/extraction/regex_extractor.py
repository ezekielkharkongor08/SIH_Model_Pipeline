import re
from typing import List
from agent1_extraction.models.schemas import CharacterSpan, EntityType, ExtractedEntity


class DeterministicExtractor:
    """Universal domain-agnostic regular expression extractor."""

    PATTERNS = {
        EntityType.PHONE_NUMBER: r"\b(?:\+?91[\-\s]?)?[6-9]\d{9}\b",
        EntityType.EMAIL: r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b",
        EntityType.MONEY_AMOUNT: r"(?:\$|€|£|₹|Rs\.\s?)\s?[\d,]+(?:\.\d{2})?(?:\s*(?:lakhs?|crores?|million|billion))?",
        EntityType.TRANSACTION_ID: r"\b(?:RTGS|NEFT|IMPS|TXN|REF)\b[\:\-\s]?[A-Za-z0-9]*\d[A-Za-z0-9]*\b",
        EntityType.DATE_TIME: r"\b\d{1,4}[\/\-\.]\d{1,2}[\/\-\.]\d{1,4}\b|\b\d{1,2}:\d{2}(?::\d{2})?\s*(?:hrs|AM|PM)?\b",
        EntityType.LEGAL_SECTION: r"\b(?:IPC|IT Act|Section|Art\.|Article)\s+(?:Section\s+)?\d+[A-Za-z]?\b",
        EntityType.BANK_ACCOUNT: r"\bAcc(?:ount)?\s*[\#\:\-]?\s*\d{9,18}\b",
    }

    def extract(self, text: str) -> List[ExtractedEntity]:
        extracted = []
        seen_spans = set()

        # Skip regex matching if text is base64 image data
        if text.startswith("data:image"):
            return extracted

        # IMPORTANT: match against a normalized copy so multi-line OCR text
        # (e.g. "Rs.\n5,00,000") doesn't get swallowed with a literal \n
        # baked into the match. Replacing \n/\r with a single space is a
        # 1-for-1 character swap, so it does NOT shift any offsets — the
        # start/end indices are still valid positions in the ORIGINAL text.
        search_text = re.sub(r"[\r\n]", " ", text)

        for entity_type, pattern in self.PATTERNS.items():
            for match in re.finditer(pattern, search_text, re.IGNORECASE):
                start, end = match.span()

                if (start, end) in seen_spans:
                    continue
                seen_spans.add((start, end))

                # Always slice exact_text from the ORIGINAL raw text, not
                # the normalized copy, so downstream consumers get an
                # exact_text that is guaranteed to equal
                # raw_text[start_char:end_char].
                exact_text = text[start:end]

                # canonical_name is the "clean" identity used for entity
                # dedup/registry lookups — collapse internal whitespace
                # here only, never touch exact_text/span.
                canonical_name = re.sub(r"\s+", " ", exact_text).strip()

                if not canonical_name:
                    continue

                extracted.append(
                    ExtractedEntity(
                        canonical_name=canonical_name,
                        entity_type=entity_type,
                        span=CharacterSpan(
                            start_char=start,
                            end_char=end,
                            exact_text=exact_text,
                        ),
                        confidence=1.0,
                    )
                )
        return extracted