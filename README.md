# The Unofficial Guide — UIUC CS Professor Reviews

A RAG system for asking questions about UIUC CS professors using student review data. The app retrieves relevant reviews, sends only those reviews to an LLM, and returns a short answer with sources. If the reviews do not cover the question, the system should say that it does not have enough information.

---

## Demo


---

## Domain

This project is an unofficial guide to UIUC CS professors, based on student feedback from Rate My Professors-style reviews. The reviews include comments about teaching style, lecture clarity, exam difficulty, grading, workload, attendance, and whether a professor is helpful outside class.

This is useful because official course pages explain what a course covers, but they do not show what students say about taking the course with a specific professor. Student reviews contain that kind of information, but they are spread across separate pages and are not easy to search together.

---

## Document Sources

All documents come from Rate My Professors pages for 11 UIUC CS or CS-related professors. I collected the reviews into one local text file, documents/CS_Professor_Reviews.txt, which is the file actually ingested. The URLs below are listed for attribution.

| # | Source | Type | URL or file path |
|---|--------|------|-----------------|
| 1 | CS professor reviews | Local corpus file (ingested) | `documents/CS_Professor_Reviews.txt` |
| 2 | Rate My Professors — Tarek Abdelzaher | Student reviews | https://www.ratemyprofessors.com/professor/797719 |
| 3 | Rate My Professors — Sarita Adve | Student reviews | https://www.ratemyprofessors.com/professor/119673 |
| 4 | Rate My Professors — Vikram Adve | Student reviews | https://www.ratemyprofessors.com/professor/1654175 |
| 5 | Rate My Professors — Rishika Agarwal | Student reviews | https://www.ratemyprofessors.com/professor/2640650 |
| 6 | Rate My Professors — Abdussalam Alawini | Student reviews | https://www.ratemyprofessors.com/professor/2442487 |
| 7 | Rate My Professors — Roy Campbell | Student reviews | https://www.ratemyprofessors.com/professor/180294 |
| 8 | Rate My Professors — Lawrence Angrave | Student reviews | https://www.ratemyprofessors.com/professor/1117293 |
| 9 | Rate My Professors — Arindam Banerjee | Student reviews | https://www.ratemyprofessors.com/professor/2750212 |
| 10 | Rate My Professors — Matthew Caesar | Student reviews | https://www.ratemyprofessors.com/professor/1233560 |
| 11 | Rate My Professors — Chandra Chekuri | Student reviews | https://www.ratemyprofessors.com/professor/1901793 |
| 12 | Rate My Professors — Charles Martin Jr. | Student reviews | https://www.ratemyprofessors.com/professor/1698097 |

---

## Chunking Strategy

The system chunks one student review per chunk instead of using a simple fixed-size split. This fits the data because each review is already a natural unit.

**How documents are split (in `build_chunks.py`):**

- The file is first split into professor sections.
- Each professor section is split into individual review blocks.
- Each chunk keeps the professor name, course code, quality rating, difficulty rating, date, metadata, and review text together.
- The cleaning step removes HTML tags/entities, extra spaces, blank lines, and small artifacts such as Computer Icon.

**Fallback for long reviews:** if a review is longer than 500 characters, it is split into smaller pieces with 75-character overlap. I adjusted this so chunks do not start in the middle of a word or sentence, and the professor/course header is repeated on each piece.

**Why this fits my documents:** A fixed-size split could separate a review from the professor or course it belongs to. Keeping each review with its metadata makes the retrieved chunks easier to understand on their own.

**Final chunk count:** 58 chunks, saved in `processed/chunks.jsonl`.

---

## Embedding Model

**Model used:** `all-MiniLM-L6-v2`

**Production tradeoff reflection:** A stronger embedding model could improve retrieval, especially for broad or tricky questions. One issue I saw was that the model treated “clear grading” and “unclear grading” as very similar because both are about grading. A better model or reranking step could help with that. The tradeoff is that stronger hosted models usually add cost, latency, and dependency on an external API.

---

## Grounded Generation

**System prompt grounding instruction:** Generation is in `query.py` using the
Groq model `llama-3.3-70b-versatile`. For each question, the system retrieves the top 5 chunks and sends only those chunks to the model.

The prompt tells the model to:

- use only the retrieved review context;
- not use outside knowledge;
- not invent facts;
- keep the answer concise;
- say exactly this when the context is not enough: "I don't have enough information on that from the provided documents."

I also set temperature to 0 to keep answers more consistent.

**How source attribution is surfaced:** Sources are built in code from the retrieved chunk metadata, not left only to the LLM. The Gradio app shows the answer, the source list, and the retrieved chunks/debug view. If the model gives the “not enough information” response, no sources are shown.

---

## Evaluation Report

I ran all 5 of my planning questions through the live system. Short version: the
professor-specific questions (Angrave, Alawini) work really well. The broader
"find all professors who…" questions are hit or miss, because they depend on
retrieval surfacing the *right* reviews out of all 58 chunks.

| # | Question | Expected answer | System response (summarized) | Retrieval quality | Response accuracy |
|---|----------|-----------------|------------------------------|-------------------|-------------------|
| 1 | What do students say about Lawrence Angrave's teaching style in CS241? | Engaging, passionate, helpful; makes a hard class manageable. | Returned Angrave CS241 reviews; summarized him as engaging, passionate, entertaining, and helpful. | Relevant | Accurate |
| 2 | Which professor reviews mention the class is difficult but still worthwhile? | Adve, Angrave, Vikram Adve, Chekuri. | Found some relevant examples (Angrave, Caesar) but missed a few expected professors. | Partially relevant | Partially accurate |
| 3 | Are there professors whose reviews mention unclear grading or poor organization? | Abdelzaher, Alawini, Matthew Caesar. | Found some relevant professors, but also pulled a "clear grading criteria" review — the opposite of the query. | Partially relevant | Partially accurate |
| 4 | Which professors are described as accessible, helpful, or caring outside of class? | Adve, Angrave, Chekuri, Caesar. | Found some related reviews (mostly Caesar) but missed several good examples. | Partially relevant | Partially accurate |
| 5 | What are the common complaints about Abdussalam Alawini's CS411 reviews? | Unclear instructions, lecture structure, tricky exams, group project complaints. | Returned Alawini CS411 reviews and summarized those complaints correctly. | Relevant | Accurate |

**Out-of-domain check:** I also asked "What is the weather in Champaign tomorrow?" The system correctly responded with:
"I don't have enough information on that from the provided documents."
It also showed no sources.

---

## Failure Case Analysis

**Question that failed:** Are there any professors whose reviews mention unclear
grading or poor course organization?

**What the system returned:** It found some useful results, but it also retrieved a review that said “clear grading criteria.” That review is related to grading, but it means the opposite of what the question asked.

**Root cause (tied to a specific pipeline stage):** This is mainly a retrieval issue. The embedding model matched the topic “grading,” but it did not fully capture the difference between “clear” and “unclear.” Because that chunk appeared in the top 5, the LLM had to answer from context that was partly off-target.

**What I'd change to fix it:**

- retrieve more candidates and rerank them;
- add keyword filtering for words like unclear, confusing, and disorganized;
- use a stronger embedding model or reranker;
- add a negation-aware check for phrases like “clear” vs “unclear.”

I left this as a documented limitation instead of adding more complexity for this milestone.

---

## Spec Reflection

**One way the spec helped:** The spec made me inspect chunks before moving on to retrieval. That helped me catch awkward chunks early and improve the chunking logic.

**One way my implementation diverged from the spec:** My original plan used a plain 500-character sliding window for long reviews. After inspecting the output, I saw that some chunks started in the middle of words. I changed the fallback to be more sentence-aware while still keeping the same 500-character and 75-overlap idea. I also added extra cleaning for small artifacts that appeared in the data.

---

## AI Usage

**Instance 1 — building the chunking pipeline**

- *What I gave the AI:* My Documents and Chunking Strategy sections from planning.md, the review file, and the rule to keep professor/course metadata attached to each review.
- *What it produced:* A first version of build_chunks.py that loaded the file, cleaned it, split reviews into chunks, and saved JSONL output.
- *What I changed or overrode:* I inspected the chunks and found that some long reviews were split awkwardly. I adjusted the fallback chunking to avoid cutting words/sentences and to keep the professor/course header attached.

**Instance 2 — retrieval, generation, UI, and environment debugging**

- *What I gave the AI:* My Retrieval Approach, chunk format, and requirements for ChromaDB retrieval, grounded generation, and a Gradio interface.
- *What it produced:* Draft versions of retrieve.py, query.py, and app.py.
- *What I changed or overrode:* I separated backend logic into query.py and the UI into app.py. I also debugged environment issues with ChromaDB, NumPy, PyTorch, and sentence-transformers. I chose to document the retrieval limitation instead of adding reranking for this version.

---

## How to Run

```bash
# 1. Build the chunks from the documents (Milestone 3)
python build_chunks.py

# 2. Embed the chunks into ChromaDB and test retrieval (Milestone 4)
python retrieve.py

# 3. Test the grounded answers in the terminal (Milestone 5 backend)
python query.py

# 4. Launch the Gradio app (Milestone 5 UI)
python app.py
```

You'll need a `GROQ_API_KEY` in a `.env` file for the answer generation step.
The embedding model downloads automatically the first time you run `retrieve.py`.
