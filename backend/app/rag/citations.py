import re

from app.rag.generator import FALLBACK_ANSWER
from app.rag.schemas import RetrievedChunk, SourceCitation

CITE_RE = re.compile(r"<cite\s+index=\"(?P<index>\d+)\"\s*>")


def map_citations(
    answer: str, context: list[RetrievedChunk]
) -> tuple[str, list[SourceCitation], bool]:
    indexes = [int(match.group("index")) for match in CITE_RE.finditer(answer)]
    if not indexes:
        # No citations means the answer is not grounded; it is not "supported".
        return answer, [], False
    if any(index >= len(context) for index in indexes):
        return FALLBACK_ANSWER, [], False

    clean_answer = CITE_RE.sub("", answer).strip()
    citations: list[SourceCitation] = []
    seen: set[int] = set()
    for index in indexes:
        if index in seen:
            continue
        seen.add(index)
        chunk = context[index]
        citations.append(
            SourceCitation(
                document_id=chunk.document_id,
                filename=chunk.filename,
                page_number=chunk.page_number,
                section_title=chunk.section_title,
                chunk_id=chunk.chunk_id,
                snippet=_snippet(chunk.text),
            )
        )
    return clean_answer, citations, True


def _snippet(text: str) -> str:
    clean = re.sub(r"\s+", " ", text).strip()
    return clean[:240]
