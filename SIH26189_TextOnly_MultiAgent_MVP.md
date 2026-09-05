# SIH26189 — Text-Only Multi-Agent MVP
## Scope: JSON/text evidence in → agent pipeline → evidence-grounded query answers out

This is a deliberately narrowed version of the full blueprint: no CV, no audio,
no video. Input is pre-structured text/JSON evidence records (as if OCR/ASR
already happened upstream, or as if you're simulating with synthetic FIR/CDR
text). Goal: a working multi-agent pipeline you can demo end-to-end quickly,
then extend with real ingestion modalities later.

---

## 1. Why This Scope Works

Modules 2–7 of the original blueprint never actually depended on *how* text
was produced — only that it exists as text by the time they run. Cutting
Module 1's CV/audio branches doesn't break the downstream architecture at
all; it just means your input adapter is "read JSON" instead of "run five
different perception models." This is the correct MVP cut: you keep the
actual novel/hard part of the system (multi-agent reasoning over a graph
with calibrated confidence) and defer the commodity part (perception models,
which are well-understood and mostly a matter of plumbing, not architecture).

---

## 2. Input Contract

Define one evidence record schema up front — this replaces Module 1 entirely:

```
EvidenceRecord {
  evidence_id: string
  source_type: "fir" | "cdr" | "chat_log" | "financial_record" | "statement"
  raw_text: string
  metadata: { date_filed, station, language, ... }
}
```

Every downstream agent consumes/produces JSON conforming to a shared schema —
this is what makes them swappable, testable in isolation, and genuinely
"multi-agent" rather than one monolithic script.

---

## 3. Agent Roster

Each agent = one model/algorithm + one clear responsibility + a strict
JSON in/out contract. An orchestrator (LangGraph) routes between them.

### Agent 1 — Extraction Agent
- **Model:** Llama-3-8B-Instruct + constrained decoding (Outlines/Instructor)
- **Input:** `EvidenceRecord`
- **Output:** list of triples `{subject, predicate, object, timestamp, geo, evidence_span, confidence}`
- **Supporting tools:** SuTime (temporal normalization), IndicTrans2/IndicBERT if multilingual input is in scope for your demo
- **Contract rule:** every triple must carry a char-offset span into `raw_text` — non-negotiable, this is your evidence-anchoring mechanism

### Agent 2 — Entity Resolution Agent
- **Model:** BGE-m3 embeddings + Metaphone blocking + Hierarchical Agglomerative Clustering
- **Input:** all extracted entity mentions across triples (from Agent 1, batched)
- **Output:** entity clusters + merge/reject decisions per the 0.95/0.80 threshold matrix
- **Contract rule:** anything landing in the 0.80–0.94 band is *not* resolved — it's emitted as a `pending_review` item for the orchestrator to route to a human-review step (or, for demo purposes, an auto-approve stub)

### Agent 3 — Graph Construction Agent
- **Role:** takes resolved entities + triples → writes canonical nodes/edges to Neo4j
- **Input:** Agent 1 output (triples) + Agent 2 output (entity resolution decisions)
- **Output:** graph delta (nodes/edges created or updated)
- **Contract rule:** this agent is the only one allowed to write to Neo4j — keeps a single source of truth for graph mutations, avoids race conditions between agents

### Agent 4 — Graph Reasoning Agent
- **Model:** R-GCN or GraphSAGE (start here) → TGN (upgrade once graph has real temporal depth)
- **Input:** current graph state
- **Output:** inferred/predicted links with scores, written back as `predicted_link` edges (kept distinct from directly-evidenced edges)
- **Contract rule:** predicted edges are never merged with evidenced edges — they must remain visibly distinct in the graph and downstream answers

### Agent 5 — Confidence Calibration Agent
- **Model:** Conformal Prediction (calibration set) or MC Dropout as a fallback
- **Input:** any node/edge with an upstream confidence score (extraction, resolution, or link-prediction)
- **Output:** calibrated confidence interval attached to that node/edge
- **Contract rule:** final displayed confidence = min() across every upstream stage that contributed to a claim, not just this agent's own score

### Agent 6 — Query/Answering Agent (GraphRAG)
- **Model:** LLM (few-shot Text-to-Cypher) + Neo4j
- **Input:** natural-language investigator question
- **Output:** Cypher query → 2-hop subgraph → synthesized answer with inline evidence citations and confidence
- **Contract rule:** refuses/flags uncertainty if the retrieved subgraph doesn't actually contain enough grounding for the question — never answers from parametric knowledge alone

### Orchestrator — LangGraph Supervisor
- Routes `EvidenceRecord` → Agent 1 → Agent 2 → Agent 3 → (Agent 4 on a schedule/trigger, not per-record) → Agent 5 (attached wherever confidence is needed) → Agent 6 (on-demand, query-triggered)
- Owns the shared state object and the `audit_trail[]` (chain-of-custody log)
- Owns HITL gate logic: conditional edge checks `pending_review` flags and routes to a review step

---

## 4. Minimal Working Demo Path

1. Hand-write or LLM-generate 15–20 synthetic `EvidenceRecord` JSON objects (mix of FIR narrative text, CDR-as-text, chat logs).
2. Agent 1 only, first — get clean triple extraction working and verify evidence-span anchoring is correct. This is the highest-leverage agent to get right; everything downstream depends on triple quality.
3. Wire Agent 3 next (skip Agent 2 initially — assume no duplicate entities in your synthetic set) to get a real graph populated in Neo4j.
4. Build Agent 6 (GraphRAG query) against that graph — this is your demo-able "wow" moment and doesn't require Agent 2, 4, or 5 to exist yet.
5. Add Agent 2 (entity resolution) once you've deliberately introduced duplicate/alias entities into your synthetic data to prove it's needed.
6. Add Agent 4 (graph ML link prediction) once the graph has enough edges/relation types to make predictions meaningful (a handful of nodes won't show anything interesting).
7. Add Agent 5 (conformal calibration) last — needs a calibration set, which by this point you can carve out of your synthetic data's known ground truth.

This order gets you a demoable pipeline (steps 1–4) very fast, then layers in the more sophisticated agents in decreasing order of "needed for a compelling demo."

---

## 5. What You're Deferring (not discarding)

Module 1's CV/audio stack (Qwen2-VL, LayoutLMv3, YOLOv9, ArcFace, ByteTRACK,
Whisper, PyAnnote) becomes a future "ingestion adapter" layer that converts
non-text evidence into the same `EvidenceRecord` JSON contract above. Because
every other agent only ever consumes that contract, adding real perception
models later means writing new adapters — it does not require touching
Agents 1–6 at all. That's the payoff of having scoped it this way.
