import json
import re
import httpx
from typing import List
from loguru import logger
from agent1_extraction.config import settings
from agent1_extraction.models.schemas import EntityType, RawLLMExtractionResponse, RawTripleItem


UNIVERSAL_SYSTEM_PROMPT = """You are a universal, domain-agnostic information extraction engine.
Your task is to parse unstructured text or data logs into clean Subject-Predicate-Object triples.

CRITICAL STRUCTURAL CONSTRAINTS:
1. SUBJECT & OBJECT BOUNDARIES:
   - Must be clean canonical entities, proper nouns, identifiers, or quantitative values.
   - Strip all leading reporting clauses (e.g., "investigation reveals that", "records indicate that").
   - Strip all trailing prepositional phrases or media channels (e.g., "via email", "on WhatsApp", "located near").

2. PREDICATE CLEANLINESS:
   - Must be a concise, snake_case action or relationship verb phrase (e.g., "sent_message_to", "transferred_funds", "located_at", "associated_with").
   - NEVER embed the Subject or Object entity inside the predicate string.
   - BAD: subject="A", predicate="called_person_B", object="B"
   - GOOD: subject="A", predicate="called", object="B"

3. METADATA SEPARATION:
   - Move temporal markers (dates, times) to the "timestamp" field.
   - Move spatial markers (addresses, cities, coordinates) to the "location" field.
   - DO NOT append metadata into entity names or predicates.

4. ENTITY TYPING:
   - Classify subject_type and object_type into: PERSON, ORGANIZATION, LOCATION, PHONE_NUMBER, EMAIL, BANK_ACCOUNT, TRANSACTION_ID, MONEY_AMOUNT, DATE_TIME, IDENTIFIER, LEGAL_SECTION, UNKNOWN.

Output STRICTLY a JSON object matching this schema without preamble or conversational filler:
{
  "triples": [
    {
      "subject": "Clean Subject Entity",
      "subject_type": "PERSON",
      "predicate": "canonical_verb_phrase",
      "object": "Clean Object Entity",
      "object_type": "ORGANIZATION",
      "timestamp": "Extracted Time String or null",
      "location": "Extracted Location String or null"
    }
  ]
}
"""


class UniversalLLMExtractor:

    def __init__(self):
        self.base_url = settings.LLM_BASE_URL
        self.model_name = settings.LLM_MODEL_NAME

    def extract_triples(self, input_data: str, is_image: bool = False) -> List[RawTripleItem]:
        if is_image:
            return []

        messages = [
            {"role": "system", "content": UNIVERSAL_SYSTEM_PROMPT},
            {"role": "user", "content": f"Extract all valid structured triples from the following text:\n\n{input_data}"}
        ]

        try:
            with httpx.Client(timeout=120.0) as client:
                response = client.post(
                    f"{self.base_url}/chat/completions",
                    json={
                        "model": self.model_name,
                        "messages": messages,
                        "temperature": 0.0,
                        "response_format": {"type": "json_object"}
                    },
                )
                if response.status_code == 200:
                    data = response.json()
                    content = data["choices"][0]["message"]["content"]
                    
                    json_match = re.search(r"\{.*\}", content, re.DOTALL)
                    if json_match:
                        clean_json = json_match.group(0)
                        parsed = RawLLMExtractionResponse.model_validate_json(clean_json)
                        return parsed.triples
        except Exception as e:
            logger.warning(f"LLM extraction failed: {e}")

        return []