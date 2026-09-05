import json
from agent1_extraction.pipeline import UniversalExtractionPipeline

# Sample Documents
DOC_CDR = json.dumps({
    "evidence_id": "EV-CDR-2024-002",
    "source_type": "cdr",
    "call_records": [
        {
            "caller": "9820198201",
            "receiver": "9892098920",
            "timestamp": "2024-08-14 14:35:10",
            "duration": 184,
            "cell_tower": "Bandra West Tower 4"
        },
        {
            "caller": "9892098920",
            "receiver": "9811198111",
            "timestamp": "2024-08-14 15:10:05",
            "duration": 45,
            "cell_tower": "Kurla Central Tower 1"
        }
    ],
    "metadata": {
        "provider": "Telecom India",
        "subscriber_id": "SUB-99410"
    }
}).encode("utf-8")

DOC_CHAT = json.dumps({
    "evidence_id": "EV-CHAT-2024-003",
    "source_type": "message",
    "messages": [
        {
            "sender": "Vikram Malhotra",
            "recipient": "Rajesh Sharma",
            "timestamp": "2024-08-14 16:00:00",
            "message": "Payment sent to account."
        },
        {
            "sender": "Rajesh Sharma",
            "recipient": "Amit Verma",
            "timestamp": "2024-08-14 16:15:00",
            "message": "Rajesh Sharma works_with Amit Verma on the consignment."
        }
    ],
    "metadata": {
        "platform": "WhatsApp Export",
        "device_imei": "864209048123456"
    }
}).encode("utf-8")

DOC_FIR_JSON = json.dumps({
    "evidence_id": "EV-FIR-2024-001",
    "source_type": "fir",
    "language": "en",
    "timestamp": "2024-08-14T14:30:00",
    "geo": "Bandra West, Mumbai",
    "metadata": {
        "fir_number": "FIR-402/2024",
        "police_station": "Crime Branch Unit 9, Bandra",
        "sections": ["IPC 384", "IPC 120B", "Arms Act 25"]
    },
    "raw_text": "On 14 August 2024 at 14:30 hrs, complainant Rajiv Seth reported that Rajesh Sharma called Vikram Malhotra demanding 10 lakh extortion payment. Witness stated Rajesh Sharma was seen_with Amit Verma near Bandra West. Accused Rajesh Sharma transferred_money_to Suresh Patil through hawala operator. Rajesh Sharma uses 9820198201."
}).encode("utf-8")

DOC_FIR_TXT = """FIRST INFORMATION REPORT (FIR)
FIR No.: 187/2024
Police Station: Cyber Crime Cell, Andheri East, Mumbai
Date of Filing: 22 September 2024
Time of Filing: 10:15 hrs

COMPLAINANT DETAILS:
Name: Priya Kapoor
Father's Name: Ramesh Kapoor
Address: 42-B, Lotus Apartments, Versova, Andheri West, Mumbai - 400061
Contact: 9876543210

DETAILS OF THE OFFENCE:
On 20 September 2024 at approximately 18:45 hrs, complainant Priya Kapoor reported that
she received a threatening phone call from an unknown number 9123456789. The caller
identified himself as Deepak Rana and demanded a sum of Rs. 25,00,000 (Twenty-Five Lakhs)
as protection money. Deepak Rana called Priya Kapoor three times between 18:45 hrs and
20:00 hrs on the same date.

Investigation reveals that Deepak Rana messaged Sanjay Gupta on WhatsApp at 20:15 hrs
instructing him to collect the payment. Sanjay Gupta was seen_with Mohit Agarwal near
Lokhandwala Circle, Andheri West at approximately 21:00 hrs on the same evening.

CCTV footage from Lotus Apartments confirms that Mohit Agarwal visited the premises at
21:30 hrs. Bank records show that Sanjay Gupta transferred_money_to Deepak Rana via
RTGS transaction ref. RTGS-2024092201 amounting to Rs. 5,00,000 on 21 September 2024.

Deepak Rana uses phone number 9123456789 registered under a fake identity. The accused
Deepak Rana is associated_with a known extortion syndicate operating in Western Mumbai.
Sanjay Gupta works_with Mohit Agarwal and both are located_at Goregaon East, Mumbai.

SECTIONS APPLIED: IPC 384, IPC 506, IPC 120B, IT Act Section 66A

Investigating Officer: Inspector Vikram Patil, Badge No. 4421
""".encode("utf-8")


def run_demo():
    pipeline = UniversalExtractionPipeline()

    test_files = [
        ("EV-CDR-2024-002", "cdr_002_intercept.json", DOC_CDR),
        ("EV-CHAT-2024-003", "chat_003_arms_deal.json", DOC_CHAT),
        ("EV-FIR-2024-001", "fir_001_extortion.json", DOC_FIR_JSON),
        ("EV-FIR-2024-004", "fir_004_cybercrime.txt", DOC_FIR_TXT),
    ]

    print("=" * 85)
    print("UNIVERSAL EXTRACTION PIPELINE DEMO - ALL TEST DOCUMENTS")
    print("=" * 85)

    for evidence_id, filename, content in test_files:
        print(f"\n Processing: {filename} (ID: {evidence_id})")
        payload = pipeline.process(
            evidence_id=evidence_id,
            raw_content=content,
            filename=filename
        )

        print(f"   Status          : {payload.status}")
        print(f"   Format Detected : {payload.input_format}")
        print(f"   Evidence Hash   : {payload.evidence_hash[:16]}...")
        print(f"   Execution Time  : {payload.execution_time_ms} ms")
        print(f"   Total Entities  : {len(payload.entities)}")
        print(f"   Total Triples   : {len(payload.triples)}")

        if payload.triples:
            print("   Triples Extracted:")
            for idx, t in enumerate(payload.triples, 1):
                sub = t.subject.canonical_name
                pred = t.predicate
                obj = t.object.canonical_name
                time_info = f" [{t.raw_timestamp}]" if t.raw_timestamp else ""
                print(f"      {idx:02d}. ({sub}) ──[{pred}]──> ({obj}){time_info}")
        else:
            print("   No triples generated.")

        print("-" * 85)


if __name__ == "__main__":
    run_demo()