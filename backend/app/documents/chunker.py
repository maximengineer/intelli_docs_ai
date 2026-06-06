import re

from app.core.settings import get_settings
from app.documents.schemas import DocumentChunk, ParsedDocument

TOKEN_RE = re.compile(r"\S+")


def chunk_document(parsed: ParsedDocument) -> list[DocumentChunk]:
    settings = get_settings()
    chunks: list[DocumentChunk] = []
    chunk_index = 0
    for page in parsed.pages:
        sections = _split_sections(page.text)
        for section_title, section_text in sections:
            tokens = TOKEN_RE.findall(section_text)
            if not tokens:
                continue
            start = 0
            while start < len(tokens):
                end = min(start + settings.chunk_size_tokens, len(tokens))
                text = " ".join(tokens[start:end]).strip()
                if text:
                    chunks.append(
                        DocumentChunk(
                            chunk_id=f"{parsed.document_id}_chunk_{chunk_index:04d}",
                            document_id=parsed.document_id,
                            filename=parsed.filename,
                            text=text,
                            page_number=page.page_number,
                            section_title=section_title or page.section_title,
                            chunk_index=chunk_index,
                        )
                    )
                    chunk_index += 1
                if end == len(tokens):
                    break
                start = max(end - settings.chunk_overlap_tokens, start + 1)
    return chunks


def _split_sections(text: str) -> list[tuple[str | None, str]]:
    lines = [line.rstrip() for line in text.splitlines()]
    sections: list[tuple[str | None, list[str]]] = []
    current_title: str | None = None
    current_lines: list[str] = []

    for line in lines:
        stripped = line.strip()
        is_heading = (
            bool(stripped)
            and len(stripped) <= 80
            and (stripped.endswith(":") or stripped.isupper())
        )
        if is_heading and current_lines:
            sections.append((current_title, current_lines))
            current_title = stripped.rstrip(":")
            current_lines = [stripped]
        else:
            if is_heading and current_title is None:
                current_title = stripped.rstrip(":")
            current_lines.append(line)

    if current_lines:
        sections.append((current_title, current_lines))
    return [(title, "\n".join(section_lines).strip()) for title, section_lines in sections]
