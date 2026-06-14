"""
Milestone 3 — Document Pipeline for "The Unofficial Guide"

Loads the professor-review .txt documents, cleans them, splits them into
professor-review chunks (per planning.md), and writes them to
processed/chunks.jsonl with metadata for retrieval in Milestone 4.

Run:  python build_chunks.py
"""

import os
import re
import json
import glob
import html

# ----------------------------------------------------------------------------
# Config (matches the Chunking Strategy section of planning.md)
# ----------------------------------------------------------------------------
DOCUMENTS_DIR = "documents"
OUTPUT_PATH = "processed/chunks.jsonl"

MAX_CHUNK_CHARS = 500   # oversized-review fallback limit
OVERLAP_CHARS = 75      # sliding-window overlap for oversized reviews

# Metadata field labels that appear inside a review block but are NOT review text.
# We KEEP these (not discard them) by mapping each label to a chunk field.
METADATA_FIELDS = {
    "For Credit:": "for_credit",
    "Attendance:": "attendance",
    "Would Take Again:": "would_take_again",
    "Grade:": "grade",
    "Textbook:": "textbook",
    "Online Class:": "online_class",
}
# Structural lines that are neither review text nor useful metadata; skip them
# but do NOT let them drop the review block (e.g. a "Reviewed:" line before Quality).
SKIP_PREFIXES = ("Reviewed:",)

# A course code looks like CS424, CS433, INFO102, ACCY202 ...
COURSE_RE = re.compile(r"^[A-Z]{2,5}\s?\d{3}[A-Z]?$")
# A review date looks like "Mar 9th, 2025"
DATE_RE = re.compile(r"^[A-Z][a-z]{2,8}\s+\d{1,2}(st|nd|rd|th)?,\s+\d{4}$")
# A professor-section header looks like "1. 3.1/ 5"
SECTION_HEADER_RE = re.compile(r"^\d+\.\s*[\d.]+\s*/\s*5\s*$")
URL_RE = re.compile(r"^URL\s*-\s*(\S+)")


# ----------------------------------------------------------------------------
# 1. Loading
# ----------------------------------------------------------------------------
def load_documents(documents_dir):
    """Read every .txt file in documents_dir. Returns [(filename, raw_text)]."""
    paths = sorted(glob.glob(os.path.join(documents_dir, "*.txt")))
    docs = []
    for path in paths:
        with open(path, "r", encoding="utf-8") as f:
            docs.append((os.path.basename(path), f.read()))
    return docs


# ----------------------------------------------------------------------------
# 2. Cleaning
# ----------------------------------------------------------------------------
def clean_text(text):
    """Remove HTML artifacts and normalize whitespace, while keeping the blank
    lines that separate review blocks."""
    # Unescape HTML entities (&amp; -> &) then strip any HTML tags (<br>, <p>).
    text = html.unescape(text)
    text = re.sub(r"<[^>]+>", " ", text)
    # Remove the "Computer Icon" UI artifact that prefixes online-course codes
    # (e.g. "Computer IconCS498" -> "CS498").
    text = text.replace("Computer Icon", "")

    cleaned_lines = []
    for line in text.splitlines():
        # Collapse runs of spaces/tabs and trim the edges of each line.
        line = re.sub(r"[ \t]+", " ", line).strip()
        cleaned_lines.append(line)

    text = "\n".join(cleaned_lines)
    # Collapse 2+ consecutive blank lines into a single blank line.
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# ----------------------------------------------------------------------------
# 3. Parsing into professor-review blocks
# ----------------------------------------------------------------------------
def parse_professor_sections(text):
    """Split a cleaned document into per-professor sections.

    Returns a list of dicts: {professor, url, blocks: [block_text, ...]}.
    """
    lines = text.split("\n")
    sections = []
    current = None

    i = 0
    while i < len(lines):
        line = lines[i]
        if SECTION_HEADER_RE.match(line):
            # Start a new professor section.
            # Layout: header / "Overall Quality Based on N ratings" / name / URL line.
            professor = lines[i + 2].strip() if i + 2 < len(lines) else ""
            url = ""
            url_match = URL_RE.match(lines[i + 3]) if i + 3 < len(lines) else None
            if url_match:
                url = url_match.group(1)
            current = {"professor": professor, "url": url, "body_lines": []}
            sections.append(current)
            i += 4
            continue
        if current is not None:
            current["body_lines"].append(line)
        i += 1

    # Split each section's body into review blocks on blank lines.
    for section in sections:
        body = "\n".join(section["body_lines"]).strip()
        blocks = [b.strip() for b in re.split(r"\n\s*\n", body) if b.strip()]
        # A real review block has a "Quality" line (it may be preceded by a
        # "Reviewed:" line, so don't require the block to *start* with Quality).
        section["blocks"] = [
            b for b in blocks
            if any(ln.strip().startswith("Quality") for ln in b.split("\n"))
        ]
        del section["body_lines"]

    return sections


def parse_review_block(block):
    """Pull structured fields + review text out of one review block."""
    quality = difficulty = course = date = None
    metadata = {}          # kept fields: for_credit, attendance, grade, ...
    review_parts = []

    for line in block.split("\n"):
        line = line.strip()
        if not line:
            continue
        if line.startswith("Quality"):
            quality = line.replace("Quality", "").strip()
        elif line.startswith("Difficulty"):
            difficulty = line.replace("Difficulty", "").strip()
        elif COURSE_RE.match(line):
            course = line.replace(" ", "")
        elif DATE_RE.match(line):
            date = line
        elif line.startswith(SKIP_PREFIXES):
            continue  # structural noise (e.g. "Reviewed:"), not review text
        elif any(line.startswith(label) for label in METADATA_FIELDS):
            # Keep this metadata: store "Grade: A" under metadata["grade"] = "A".
            label = next(l for l in METADATA_FIELDS if line.startswith(l))
            metadata[METADATA_FIELDS[label]] = line[len(label):].strip()
        else:
            review_parts.append(line)

    return {
        "quality": quality,
        "difficulty": difficulty,
        "course": course,
        "date": date,
        "metadata": metadata,
        "review_text": " ".join(review_parts).strip(),
    }


# ----------------------------------------------------------------------------
# 4. Chunking (professor-review block = primary unit)
# ----------------------------------------------------------------------------
def split_into_sentences(text):
    """Break text into sentences. A "sentence" that is still longer than the
    chunk budget is further split on word boundaries so we never cut mid-word."""
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return [p.strip() for p in parts if p.strip()]


def word_split(sentence, budget):
    """Split one over-budget sentence on spaces into <=budget pieces."""
    words = sentence.split()
    pieces, current = [], ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if current and len(candidate) > budget:
            pieces.append(current)
            current = word
        else:
            current = candidate
    if current:
        pieces.append(current)
    return pieces


def split_review_text(text, budget, overlap):
    """Pack sentences into windows that fit in `budget` characters, overlapping
    by whole sentences (~`overlap` chars) so chunks never start/end mid-word."""
    # Sentence units, with any over-long sentence pre-split on word boundaries.
    units = []
    for sentence in split_into_sentences(text):
        units.extend(word_split(sentence, budget))

    windows = []
    i = 0
    while i < len(units):
        # Greedily fill the current window with whole sentences.
        current, length, j = [], 0, i
        while j < len(units):
            extra = len(units[j]) + (1 if current else 0)
            if current and length + extra > budget:
                break
            current.append(units[j])
            length += extra
            j += 1
        windows.append(" ".join(current))
        if j >= len(units):
            break
        # Step back so the last sentences (up to `overlap` chars) repeat in the
        # next window — sentence-level overlap keeps the boundary readable.
        back, olen, k = 0, 0, j - 1
        while k > i and olen + len(units[k]) <= overlap:
            olen += len(units[k]) + 1
            back += 1
            k -= 1
        i = max(i + 1, j - back)  # always make progress
    return windows


def build_chunks_for_block(fields, professor, url):
    """Turn one parsed review block into one or more chunk texts.

    The full header (professor, course, ratings, date, details) is repeated on
    every chunk, so even an overflow chunk is self-contained and retrieval never
    loses the "who/what" context (see planning.md). Only the review text is
    windowed, and only at sentence boundaries.
    """
    header_lines = [
        f"Professor: {professor} | Course: {fields['course'] or 'N/A'}",
        f"Quality: {fields['quality'] or 'N/A'} | "
        f"Difficulty: {fields['difficulty'] or 'N/A'} | "
        f"Date: {fields['date'] or 'N/A'}",
    ]
    # Render kept metadata (For Credit, Attendance, Grade, ...) as a readable line.
    meta = fields["metadata"]
    if meta:
        pairs = ", ".join(f"{k.replace('_', ' ').title()}: {v}" for k, v in meta.items())
        header_lines.append(f"Details: {pairs}")
    header = "\n".join(header_lines) + "\nReview: "

    review = fields["review_text"]
    if len(header + review) <= MAX_CHUNK_CHARS:
        return [header + review]

    # Oversized review: sentence-aware split of the review text, with the full
    # header re-attached to every window.
    budget = max(MAX_CHUNK_CHARS - len(header), 100)
    return [header + segment for segment in
            split_review_text(review, budget, OVERLAP_CHARS)]


def build_all_chunks(docs):
    """Load -> parse -> chunk every document. Returns a list of chunk dicts."""
    chunks = []
    chunk_counter = 0

    for filename, raw_text in docs:
        cleaned = clean_text(raw_text)
        for section in parse_professor_sections(cleaned):
            for block in section["blocks"]:
                fields = parse_review_block(block)
                if not fields["review_text"]:
                    continue  # nothing useful to retrieve
                for text in build_chunks_for_block(
                    fields, section["professor"], section["url"]
                ):
                    chunk_counter += 1
                    chunks.append({
                        "chunk_id": f"chunk-{chunk_counter:04d}",
                        "source_file": filename,
                        "professor": section["professor"],
                        "source_url": section["url"],
                        "course": fields["course"],
                        "quality": fields["quality"],
                        "difficulty": fields["difficulty"],
                        "review_date": fields["date"],
                        **fields["metadata"],  # for_credit, attendance, grade, ...
                        "text": text,
                    })
    return chunks


# ----------------------------------------------------------------------------
# 5. Save + verify
# ----------------------------------------------------------------------------
def save_chunks(chunks, output_path):
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        for chunk in chunks:
            f.write(json.dumps(chunk, ensure_ascii=False) + "\n")


def main():
    docs = load_documents(DOCUMENTS_DIR)
    chunks = build_all_chunks(docs)
    save_chunks(chunks, OUTPUT_PATH)

    print(f"Documents loaded : {len(docs)}")
    print(f"Total chunks     : {len(chunks)}")
    print(f"Saved to         : {OUTPUT_PATH}")
    print("\n--- 5 representative chunks ---")
    # Spread the samples across the file instead of taking the first 5.
    step = max(1, len(chunks) // 5)
    for chunk in chunks[::step][:5]:
        print(f"\n[{chunk['chunk_id']}] "
              f"{chunk['professor']} — {chunk['course']} "
              f"({chunk['source_file']})")
        print(chunk["text"])


if __name__ == "__main__":
    main()
