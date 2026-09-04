import json
import httpx
from typing import List, Union
from loguru import logger
from agent1_extraction.config import settings
from agent1_extraction.models.schemas import RawLLMExtractionResponse, RawTripleItem


SYSTEM_PROMPT = """You are a domain-agnostic forensic entity and triple extraction engine.
Analyze the given text or visual document and extract all explicit Subject-Predicate-Object triples.

CRITICAL CONSTRAINTS:
1. Subject and Object MUST be clean entity names, proper nouns, or values.
2. Strips out all introductory phrases, subordinate clauses, reporting verbs (e.g., 'according to', 'reveals that').
3. Strips out trailing prepositional phrases (e.g., 'on WhatsApp', 'near the station').
4. Predicates MUST be concise, snake_case relationship verb phrases (e.g., 'located_at', 'transferred_money_to', 'communicated_with', 'owns').
5. Map subject_type and object_type to one of: PERSON, ORGANIZATION, LOCATION, PHONE_NUMBER, EMAIL, BANK_ACCOUNT, TRANSACTION_ID, MONEY_AMOUNT, DATE_TIME, IDENTIFIER, LEGAL_SECTION, UNKNOWN.

Output strictly in JSON format matching this schema:
{
  "triples": [
    {
      "subject": "Entity A",
      "subject_type": "PERSON",
      "predicate": "relationship_name",
      "object": "Entity B",
      "object_type": "ORGANIZATION",
      "timestamp": "Optional raw time text",
      "location": "Optional location name"
    }
  ]
}
"""


class UniversalLLMExtractor:

    def __init__(self):
        self.base_url = settings.LLM_BASE_URL
        self.model_name = settings.LLM_MODEL_NAME

    def extract_triples(self, input_data: str, is_image: bool = False) -> List[RawTripleItem]:
        """
        Universal extraction handling both raw text and base64 encoded image URIs.
        """
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]

        if is_image:
            messages.append({
                "role": "user",
                "content": [
                    {"type": "text", "text": "Extract all entities and relationships visible in this image document."},
                    {"type": "image_url", "image_url": {"url": input_data}}
                ]
            })
        else:
            messages.append({
                "role": "user",
                "content": f"Extract all entities and triples from the following text:\n\n{input_data}"
            })

        try:
            with httpx.Client(timeout=30.0) as client:
                response = client.post(
                    f"{self.base_url}/chat/completions",
                    json={
                        "model": self.model_name,
                        "messages": messages,
                        "temperature": 0.0,
                        "response_format": {"type": "json_object"},
                    },
                )
                if response.status_code == 200:
                    data = response.json()
                    content = data["choices"][0]["message"]["content"]
                    parsed = RawLLMExtractionResponse.model_validate_json(content)
                    return parsed.triples
        except Exception as e:
            logger.warning(f"LLM call failed or unreachable: {e}. Returning empty triples array without crash.")
            
        return []