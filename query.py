"""
Milestone 5 — Grounded Generation.

End-to-end RAG query: retrieve the top-5 review chunks (Milestone 4), pass ONLY
those chunks to the Groq LLM as context, and return a grounded answer plus
programmatic source attribution.

    question -> retrieve() -> context -> Groq (llama-3.3-70b) -> {answer, sources, chunks}

Run:  python query.py
"""

import os

from dotenv import load_dotenv
from groq import Groq

from retrieve import retrieve, TOP_K

# Load GROQ_API_KEY from .env (never hardcode the key).
load_dotenv()

LLM_MODEL = "llama-3.3-70b-versatile"
NOT_ENOUGH = "I don't have enough information on that from the provided documents."

client = Groq(api_key=os.getenv("GROQ_API_KEY"))

# The system prompt is where grounding is enforced.
SYSTEM_PROMPT = f"""You are a factual assistant for a guide to UIUC CS professor reviews.
Answer the user's question using ONLY the retrieved review context provided in the user message.

Rules:
- Use only the retrieved context. Do not use outside or general knowledge.
- Do not invent, assume, or guess facts. Do not add UIUC/CS knowledge of your own.
- If the context does not clearly contain enough information to answer, reply with
  EXACTLY this sentence and nothing else:
  "{NOT_ENOUGH}"
- Keep the answer concise (2-4 sentences) and tie it directly to what the reviews say.
- Refer to professors and courses by the names/codes shown in the context."""


def format_context(hits):
    """Render retrieved chunks into a numbered context block for the prompt."""
    blocks = []
    for i, hit in enumerate(hits, start=1):
        meta = hit["metadata"]
        blocks.append(
            f"[Source {i}] professor: {meta['professor']} | "
            f"course: {meta['course']} | file: {meta['source_file']}\n"
            f"{hit['text']}"
        )
    return "\n\n".join(blocks)


def build_sources(hits):
    """Programmatically build the source list from chunk metadata (deduplicated).

    Source attribution does NOT depend on the LLM — it comes straight from the
    retrieved chunks' metadata, so it is always accurate.
    """
    sources = []
    seen = set()
    for hit in hits:
        meta = hit["metadata"]
        key = (meta["source_file"], meta["professor"], meta["course"])
        if key in seen:
            continue
        seen.add(key)
        source = {
            "source_file": meta["source_file"],
            "professor": meta["professor"],
            "course": meta["course"],
        }
        if meta.get("source_url") and meta["source_url"] != "N/A":
            source["source_url"] = meta["source_url"]
        sources.append(source)
    return sources


def ask(question):
    """Retrieve context, generate a grounded answer, and return everything.

    Returns a dict with:
      - answer           : the grounded answer string (or the refusal sentence)
      - sources          : list of source dicts (file, professor, course, url)
      - retrieved_chunks : the raw retrieved hits (text + metadata + distance)
    """
    hits = retrieve(question, top_k=TOP_K)

    # No chunks at all -> refuse without calling the LLM.
    if not hits:
        return {"answer": NOT_ENOUGH, "sources": [], "retrieved_chunks": []}

    user_message = (
        f"Retrieved context:\n\n{format_context(hits)}\n\n"
        f"Question: {question}"
    )

    completion = client.chat.completions.create(
        model=LLM_MODEL,
        temperature=0,  # deterministic, factual answers
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ],
    )
    answer = completion.choices[0].message.content.strip()

    # Only attach sources when the model actually answered from the context.
    sources = [] if answer == NOT_ENOUGH else build_sources(hits)

    return {"answer": answer, "sources": sources, "retrieved_chunks": hits}


def _format_sources(sources):
    if not sources:
        return "(no sources)"
    lines = []
    for s in sources:
        line = f"- {s['professor']} | {s['course']} | {s['source_file']}"
        if "source_url" in s:
            line += f" | {s['source_url']}"
        lines.append(line)
    return "\n".join(lines)


if __name__ == "__main__":
    test_questions = [
        "What do students say about Lawrence Angrave's teaching style in CS241?",
        "What are the common complaints about Abdussalam Alawini's CS411 reviews?",
        "Are there any professors whose reviews mention unclear grading or "
        "poor course organization?",
        "What is the weather in Champaign tomorrow?",  # out-of-domain -> refuse
    ]
    for question in test_questions:
        result = ask(question)
        print("\n" + "=" * 80)
        print(f"Q: {question}")
        print("=" * 80)
        print(f"\nANSWER:\n{result['answer']}")
        print(f"\nSOURCES:\n{_format_sources(result['sources'])}")
