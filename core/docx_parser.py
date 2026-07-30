from docx import Document
from docx.table import Table
from docx.text.paragraph import Paragraph


def _iter_block_items(document: Document):
    """Yield paragraphs and tables in document order."""
    body = document.element.body
    for child in body.iterchildren():
        if child.tag.endswith("}p"):
            yield Paragraph(child, document)
        elif child.tag.endswith("}tbl"):
            yield Table(child, document)


def extract_text_from_docx(file) -> str:
    """Extract text from a .docx file, preserving paragraph and table order.

    `file` can be a path or a file-like object (e.g. Streamlit's UploadedFile).
    """
    document = Document(file)
    lines: list[str] = []

    for block in _iter_block_items(document):
        if isinstance(block, Paragraph):
            text = block.text.strip()
            if text:
                lines.append(text)
        elif isinstance(block, Table):
            for row in block.rows:
                cells = [cell.text.strip() for cell in row.cells]
                if any(cells):
                    lines.append(" | ".join(cells))

    return "\n".join(lines)
