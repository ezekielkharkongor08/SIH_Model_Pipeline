import json
import re
import httpx
from typing import List
from loguru import logger
from agent1_extraction.config import settings
from agent1_extraction.models.schemas import EntityType, RawLLMExtractionResponse, RawTripleItem


UNIVERSAL_SYSTEM_PROMPT = """You are an elite, domain-agnostic information extraction engine specializing in forensic, legal, FIR (First Information Report), and cybercrime intelligence document analysis.
Your task is to parse unstructured text into clean, highly structured Subject-Predicate-Object triples.

CRITICAL STRUCTURAL CONSTRAINTS:
1. SUBJECT & OBJECT BOUNDARIES:
   - Must be clean canonical entities, proper nouns, identifiers, or quantitative values.
   - Strip all leading reporting clauses (e.g., "investigation reveals that").
   - Strip all trailing prepositional phrases (e.g., "via email", "located near").

2. PREDICATE CLEANLINESS (SNAKE_CASE):
   - Must be a concise action or relationship (e.g., "sent_message_to", "transferred_funds", "seized_from", "charged_under", "filed_complaint_against").
   - Use predicates to establish roles rather than modifying the entity name (e.g., subject="John", predicate="identified_as_suspect_in", object="Incident 402").
   - NEVER embed the Subject or Object entity inside the predicate string.

3. METADATA SEPARATION:
   - Move temporal markers (dates, times) to the "timestamp" field.
   - Move spatial markers (addresses, coordinates, IP locations) to the "location" field.
   - Tag every triple with the 'source_document_id'.

4. STRICT ENTITY TYPING:
   - Classify subject_type and object_type strictly into ONE of the following:
     * CORE: PERSON, ORGANIZATION, LOCATION, PHONE_NUMBER, EMAIL, DATE_TIME, IDENTIFIER
     * LEGAL: LAW_OFFENSE, LEGAL_SECTION, FIR_NUMBER, CASE_NUMBER, DOCUMENT, ROLE
     * FINANCIAL: BANK_ACCOUNT, TRANSACTION_ID, MONEY_AMOUNT, FINANCIAL_INSTRUMENT, UPI_ID, CRYPTO_WALLET
     * CYBER: DEVICE, SOFTWARE, DIGITAL_ARTIFACT, SOCIAL_MEDIA_HANDLE
     * PHYSICAL: VEHICLE, WEAPON, PROPERTY, NARCOTIC, SUBSTANCE, PHYSICAL_EVIDENCE, INJURY_MEDICAL, MEASUREMENT
     * CONTEXT: INCIDENT, UNKNOWN

Output STRICTLY a JSON object matching this schema without preamble, markdown formatting, or conversational filler:
{
  "triples": [
    {
      "subject": "Clean Subject Entity",
      "subject_type": "PERSON",
      "predicate": "canonical_verb_phrase",
      "object": "Clean Object Entity",
      "object_type": "ORGANIZATION",
      "timestamp": "Extracted Time String or null",
      "location": "Extracted Location String or null",
      "source_document_id": "CURRENT_PROVIDED_ID"
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
                        
                        # Aggressive pre-processing for null/empty handling before Pydantic parsing
                        clean_json = re.sub(r'"object"\s*:\s*("null"|null)', '"object": ""', clean_json)
                        clean_json = re.sub(r'"subject"\s*:\s*("null"|null)', '"subject": ""', clean_json)
                        clean_json = re.sub(r'"object_type"\s*:\s*("null"|null)', '"object_type": "UNKNOWN"', clean_json)
                        clean_json = re.sub(r'"subject_type"\s*:\s*("null"|null)', '"subject_type": "UNKNOWN"', clean_json)

                        parsed = RawLLMExtractionResponse.model_validate_json(clean_json)
                        return parsed.triples
        except Exception as e:
            logger.warning(f"LLM extraction failed: {e}")

        return []