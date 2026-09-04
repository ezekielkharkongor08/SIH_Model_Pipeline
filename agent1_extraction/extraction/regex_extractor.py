import re
from typing import List
from agent1_extraction.models.schemas import CharacterSpan, EntityType, ExtractedEntity


class DeterministicExtractor:
    """Universal domain-agnostic regular expression extractor."""

    PATTERNS = {
        EntityType.PHONE_NUMBER: r"\b(?:\+?\d{1,3}[\-\s]?)?\(?\d{2,5}\)?[\-\s]?\d{3,5}[\-\s]?\d{3,5}\b",
        EntityType.EMAIL: r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b",
        EntityType.MONEY_AMOUNT: r"(?:\$|€|£|₹|Rs\.\s?)\s?[\d,]+(?:\.\d{2})?(?:\s*(?:lakhs?|crores?|million|billion))?",
        EntityType.TRANSACTION_ID: r"\b(?:RTGS|NEFT|IMPS|TXN|REF)[\:\-\s]?[A-Za-z0-9]+\b",
        EntityType.DATE_TIME: r"\b\d{1,4}[\/\-\.]\d{1,2}[\/\-\.]\d{1,4}\b|\b\d{1,2}:\d{2}(?::\d{2})?\s*(?:hrs|AM|PM)?\b",
        EntityType.LEGAL_SECTION: r"\b(?:IPC|IT Act|Section|Art\.|Article)\s+(?:Section\s+)?\d+[A-Za-z]?\b",
        EntityType.BANK_ACCOUNT: r"\bAcc(?:ount)?\s*[\#\:\-]?\s*\d{9,18}\b"
    }

    def extract(self, text: str) -> List[ExtractedEntity]:
        extracted = []
        seen_spans = set()

        # Skip regex matching if text is base64 image data
        if text.startswith("data:image"):
            return extracted

        for entity_type, pattern in self.PATTERNS.items():
            for match in re.finditer(pattern, text, re.IGNORECASE):
                start, end = match.span()
                exact_text = match.group(0).strip()

                if (start, end) in seen_spans:
                    continue
                seen_spans.add((start, end))

                extracted.append(
                    ExtractedEntity(
                        canonical_name=exact_text,
                        entity_type=entity_type,
                        span=CharacterSpan(start_char=start, end_char=end, exact_text=exact_text),
                        confidence=1.0,
                    )
                )
        return extracted