import json
from agent1_extraction.pipeline import UniversalExtractionPipeline

def test_universal_pipeline():
    pipeline = UniversalExtractionPipeline()

    # Test Sample 1: Pre-Structured JSON Input
    json_data = json.dumps([
        {
            "subject": "Acme Corp", "subject_type": "ORGANIZATION",
            "predicate": "transferred_funds",
            "object": "Global Logistics LLC", "object_type": "ORGANIZATION",
            "timestamp": "2026-08-15", "location": "New York"
        }
    ]).encode("utf-8")

    # Test Sample 2: CSV Tabular Data
    csv_data = b"TransactionID,Sender,Receiver,Amount\nTXN9901,Alice Smith,Bob Jones,$5000\n"

    # Test Sample 3: Free-Text Legal Document
    text_data = b"On 12 October 2024, Inspector Rahul Sharma investigated Vikram Patel at Connaught Place, New Delhi."

    print("=" * 80)
    print("RUNNING MULTI-FORMAT UNIVERSAL PIPELINE TEST")
    print("=" * 80)

    for idx, (filename, content) in enumerate([("data.json", json_data), ("records.csv", csv_data), ("case_note.txt", text_data)], 1):
        print(f"\n[{idx}] Testing Input File: {filename}")
        payload = pipeline.process(f"EV-TEST-00{idx}", content, filename)
        
        print(f"    • Detected Format: {payload.input_format}")
        print(f"    • Entities Extracted: {len(payload.entities)}")
        print(f"    • Triples Generated: {len(payload.triples)}")
        
        for t in payload.triples:
            print(f"      -> ({t.subject.canonical_name}) ──[{t.predicate}]──> ({t.object.canonical_name})")

    print("\n" + "=" * 80)

if __name__ == "__main__":
    test_universal_pipeline()