"""
Milestone 4 — Embed Your Chunks and Test Retrieval.

Pipeline stage (see Architecture in planning.md):

    chunks.jsonl  ->  Embedding (all-MiniLM-L6-v2)  ->  ChromaDB  ->  Retrieval (top-5)

This script loads the chunks produced in Milestone 3, embeds their text locally
with the all-MiniLM-L6-v2 sentence-transformer, stores them in a persistent
ChromaDB collection (text as the document, chunk metadata alongside), and runs a
few Evaluation Plan questions through a simple top-5 semantic search.

No LLM generation here — this milestone is only embeddings, storage, retrieval.

Run:  python retrieve.py
"""

import json

import chromadb
from chromadb.utils import embedding_functions

# ----------------------------------------------------------------------------
# Config (matches the Retrieval Approach section of planning.md)
# ----------------------------------------------------------------------------
CHUNKS_PATH = "processed/chunks.jsonl"
EMBEDDING_MODEL = "all-MiniLM-L6-v2"
CHROMA_PATH = "./chroma_db"
CHROMA_COLLECTION = "unofficial_guide"
TOP_K = 5

# Metadata fields to copy from each chunk into ChromaDB (for source attribution).
METADATA_FIELDS = (
    "source_file",
    "professor",
    "source_url",
    "course",
    "quality",
    "difficulty",
    "review_date",
)


# ----------------------------------------------------------------------------
# 1. Load chunks
# ----------------------------------------------------------------------------
def load_chunks(path):
    """Read processed/chunks.jsonl into a list of chunk dicts (one per line)."""
    chunks = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                chunks.append(json.loads(line))
    return chunks


# ----------------------------------------------------------------------------
# 2 + 3. Embedding model and ChromaDB collection
# ----------------------------------------------------------------------------
# SentenceTransformerEmbeddingFunction wraps SentenceTransformer("all-MiniLM-L6-v2").
# ChromaDB calls it automatically to turn text into vectors for BOTH the chunks
# we store and the queries we search with, so the same model embeds both sides.
# The model downloads once (~30-60s) and is cached locally afterward.
embedding_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
    model_name=EMBEDDING_MODEL
)

# PersistentClient writes the store to disk so embeddings survive between runs.
client = chromadb.PersistentClient(path=CHROMA_PATH)

# "hnsw:space": "cosine" scores similarity with cosine distance, where a LOWER
# distance means MORE similar (0 = identical direction).
collection = client.get_or_create_collection(
    name=CHROMA_COLLECTION,
    embedding_function=embedding_fn,
    metadata={"hnsw:space": "cosine"},
)


def build_vector_store(chunks):
    """Embed every chunk's text and store it in ChromaDB with metadata.

    upsert() takes three position-aligned lists:
      - documents : the chunk text (ChromaDB embeds these for us)
      - metadatas : one dict per chunk for source attribution
      - ids       : chunk_id, the stable unique identifier
    upsert (not add) makes re-running safe: existing ids are overwritten.
    ChromaDB metadata can't hold None, so missing values become "N/A".
    """
    documents = [c["text"] for c in chunks]
    ids = [c["chunk_id"] for c in chunks]
    metadatas = [
        {field: (c.get(field) if c.get(field) is not None else "N/A")
         for field in METADATA_FIELDS}
        for c in chunks
    ]
    collection.upsert(documents=documents, metadatas=metadatas, ids=ids)
    print(f"Stored {collection.count()} chunks in ChromaDB "
          f"(collection: '{CHROMA_COLLECTION}').")


# ----------------------------------------------------------------------------
# 4. Retrieval
# ----------------------------------------------------------------------------
def retrieve(query, top_k=TOP_K):
    """Return the top_k most relevant chunks for a query string.

    ChromaDB embeds the query with the same model, compares it to every stored
    vector by cosine distance, and returns the closest matches (lowest distance).
    """
    results = collection.query(
        query_texts=[query],
        n_results=top_k,
        include=["documents", "metadatas", "distances"],
    )
    # query() returns list-of-lists (one per query); we sent one, so use [0].
    hits = []
    for doc, meta, dist in zip(
        results["documents"][0],
        results["metadatas"][0],
        results["distances"][0],
    ):
        hits.append({"text": doc, "metadata": meta, "distance": dist})
    return hits


def print_results(query, hits):
    """Print each retrieved chunk with rank, distance, and source attribution."""
    print("\n" + "=" * 80)
    print(f"QUERY: {query}")
    print("=" * 80)
    for rank, hit in enumerate(hits, start=1):
        meta = hit["metadata"]
        print(f"\n[Rank {rank}]  distance={hit['distance']:.4f}")
        print(f"  Professor : {meta['professor']}")
        print(f"  Course    : {meta['course']}")
        print(f"  Source    : {meta['source_file']}")
        print(f"  URL       : {meta['source_url']}")
        print("  Chunk text:")
        for line in hit["text"].split("\n"):
            print(f"    {line}")


# ----------------------------------------------------------------------------
# Main: build the store, then test retrieval on Evaluation Plan questions
# ----------------------------------------------------------------------------
def main():
    chunks = load_chunks(CHUNKS_PATH)
    print(f"Loaded {len(chunks)} chunks from {CHUNKS_PATH}.")
    build_vector_store(chunks)

    test_questions = [
        "What do students say about Lawrence Angrave's teaching style in CS241?",
        "Are there any professors whose reviews mention unclear grading or "
        "poor course organization?",
        "What are the common complaints about Abdussalam Alawini's CS411 reviews?",
    ]
    for question in test_questions:
        print_results(question, retrieve(question))


if __name__ == "__main__":
    main()
