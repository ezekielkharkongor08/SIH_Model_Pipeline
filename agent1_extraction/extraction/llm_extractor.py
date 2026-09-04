import json
import re
import httpx
from typing import List
from loguru import logger
from agent1_extraction.config import settings
from agent1_extraction.models.schemas import RawLLMExtractionResponse, RawTripleItem


SYSTEM_PROMPT = """You are a domain-agnostic forensic entity and triple extraction engine.
Analyze the given text or visual document and extract all explicit Subject-Predicate-Object triples.

CRITICAL CONSTRAINTS:
1. Subject and Object MUST be clean entity names, proper nouns, or values.
2. Strips out all introductory phrases, subordinate clauses, reporting verbs.
3. Strips out trailing prepositional phrases.
4. Predicates MUST be concise, snake_case relationship verb phrases.
5. Map subject_type and object_type to one of: PERSON, ORGANIZATION, LOCATION, PHONE_NUMBER, EMAIL, BANK_ACCOUNT, TRANSACTION_ID, MONEY_AMOUNT, DATE_TIME, IDENTIFIER, LEGAL_SECTION, UNKNOWN.

Output ONLY a raw JSON object matching this schema without any introductory text, markdown formatting, or explanations:
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
        if is_image:
            return []

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Extract all entities and triples from the following text:\n\n{input_data}"}
        ]

        try:
            with httpx.Client(timeout=120.0) as client:
                response = client.post(
                    f"{self.base_url}/chat/completions",
                    json={
                        "model": self.model_name,
                        "messages": messages,
                        "temperature": 0.0,
                        "response_format": {"type": "json_object"},  # Forces Ollama into JSON mode
                    },
                )
                if response.status_code == 200:
                    data = response.json()
                    content = data["choices"][0]["message"]["content"]
                    
                    # Extract the JSON object using regex matching
                    json_match = re.search(r"\{.*\}", content, re.DOTALL)
                    if json_match:
                        clean_json = json_match.group(0)
                        parsed = RawLLMExtractionResponse.model_validate_json(clean_json)
                        return parsed.triples
        except Exception as e:
            logger.warning(f"LLM call failed: {e}")

        return []