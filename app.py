"""
Milestone 5 — Gradio interface for The Unofficial Guide.

A simple web UI over the grounded RAG backend in query.py: type a question, get a
grounded answer, a readable source list, and (for debugging) the retrieved chunks.

Run:  python app.py   ->   http://localhost:7860
"""

import gradio as gr
from starlette.requests import Request
from starlette.templating import Jinja2Templates

# Compatibility shim for Gradio 4.44.1 with newer Starlette/Jinja2.
# Gradio calls Jinja2Templates.TemplateResponse(template_name, context)
# while newer Starlette expects TemplateResponse(request, template_name, context).
_old_template_response = Jinja2Templates.TemplateResponse

def _template_response(self, request_or_name, name_or_context=None, context=None, status_code=200, headers=None, media_type=None, background=None):
    if not isinstance(request_or_name, Request):
        template_name = request_or_name
        context = name_or_context or {}
        request = context.get("request")
        return _old_template_response(self, request, template_name, context, status_code=status_code, headers=headers, media_type=media_type, background=background)
    return _old_template_response(self, request_or_name, name_or_context, context, status_code=status_code, headers=headers, media_type=media_type, background=background)

Jinja2Templates.TemplateResponse = _template_response

from query import ask


def format_sources(sources):
    """Render the programmatic source list as readable bullet points."""
    if not sources:
        return "(no sources)"
    lines = []
    for s in sources:
        line = f"- {s['professor']} | {s['course']} | {s['source_file']}"
        if s.get("source_url"):
            line += f" | {s['source_url']}"
        lines.append(line)
    return "\n".join(lines)


def format_chunks(chunks):
    """Render retrieved chunks with distance + metadata for debugging."""
    if not chunks:
        return "(no chunks retrieved)"
    blocks = []
    for i, hit in enumerate(chunks, start=1):
        meta = hit["metadata"]
        blocks.append(
            f"[{i}] distance={hit['distance']:.4f} | "
            f"{meta['professor']} | {meta['course']} | {meta['source_file']}\n"
            f"{hit['text']}"
        )
    return "\n\n".join(blocks)


def answer_question(question):
    """Gradio handler: run one question through the RAG backend and format it."""
    question = (question or "").strip()
    if not question:
        return "Please enter a question.", "", ""

    result = ask(question)
    return (
        result["answer"],
        format_sources(result["sources"]),
        format_chunks(result["retrieved_chunks"]),
    )


with gr.Blocks(title="Unofficial Guide: UIUC CS Professor Reviews") as demo:
    gr.Markdown(
        "# Unofficial Guide: UIUC CS Professor Reviews\n"
        "Ask about UIUC CS professors based on student reviews. "
        "Answers are grounded **only** in the retrieved reviews."
    )

    question_box = gr.Textbox(
        label="Your question",
        placeholder="e.g. What do students say about Lawrence Angrave in CS241?",
        lines=2,
    )
    ask_button = gr.Button("Ask", variant="primary")

    gr.Markdown("### Suggested questions")
    gr.Examples(
        examples=[
            "What do students say about Lawrence Angrave's teaching style in CS241?",
            "What are the common complaints about Abdussalam Alawini's CS411 reviews?",
            "Are there any professors whose reviews mention unclear grading or "
            "poor course organization?",
            "Which professors are described as accessible, helpful, or caring "
            "outside of class?",
            "Which professor reviews mention that the class is difficult but "
            "still worthwhile?",
        ],
        inputs=question_box,  # clicking an example fills the question textbox
        label="Click an example to fill the question box",
    )

    answer_box = gr.Textbox(label="Answer", lines=5)
    sources_box = gr.Textbox(label="Sources", lines=4)
    chunks_box = gr.Textbox(label="Retrieved chunks (debug)", lines=12)

    # Trigger on button click and on pressing Enter in the question box.
    ask_button.click(
        answer_question,
        inputs=question_box,
        outputs=[answer_box, sources_box, chunks_box],
    )
    question_box.submit(
        answer_question,
        inputs=question_box,
        outputs=[answer_box, sources_box, chunks_box],
    )


if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=7861, share=True)
