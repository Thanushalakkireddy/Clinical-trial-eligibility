"""PDF processing abstraction module.

Extracts text page-by-page from clinical trial protocol PDFs using PyMuPDF (fitz),
strictly preserving page numbers and document structure for downstream evidence traceability.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import List
from pydantic import BaseModel, Field
import fitz  # PyMuPDF


class PDFPage(BaseModel):
    """Represents text and metadata for an individual page in a PDF."""

    page_number: int = Field(..., description="1-indexed page number of the document")
    text: str = Field(..., description="Extracted raw text content of the page")
    char_count: int = Field(default=0, description="Character count on this page")


class PDFDocument(BaseModel):
    """Represents a fully parsed PDF document with page-by-page contents."""

    filename: str = Field(..., description="Original or sanitized filename")
    file_path: str = Field(..., description="Path to the PDF file")
    total_pages: int = Field(..., description="Total number of pages in the document")
    pages: List[PDFPage] = Field(default_factory=list, description="Ordered list of page objects")

    @property
    def full_text(self) -> str:
        """Concatenated full text across all pages."""
        return "\n\n".join(page.text for page in self.pages)


class PDFProcessorError(Exception):
    """Base exception for PDF processing failures."""


class PDFNotFoundError(PDFProcessorError):
    """Raised when the specified PDF file cannot be found."""


class PDFCorruptError(PDFProcessorError):
    """Raised when the PDF file is corrupted or unreadable."""


class PDFProcessor:
    """Service for loading and extracting page-numbered text from PDF documents."""

    @staticmethod
    def extract_pages(file_path: str | Path) -> PDFDocument:
        """Extract text from a PDF file page-by-page.

        Args:
            file_path: Path to the target PDF file.

        Returns:
            PDFDocument with 1-indexed page items.

        Raises:
            PDFNotFoundError: If the file does not exist.
            PDFCorruptError: If the document cannot be opened or parsed.
        """
        path = Path(file_path)
        if not path.is_file():
            raise PDFNotFoundError(f"PDF file not found at path: {file_path}")

        try:
            with open(path, "rb") as f:
                data = f.read()
        except OSError as e:
            raise PDFNotFoundError(f"Unable to read PDF file: {e}") from e

        try:
            # Open from an in-memory stream so the underlying document handle
            # is never held by mupdf; the on-disk file can be cleaned up safely.
            doc = fitz.open(stream=data, filetype="pdf")
        except Exception as e:
            raise PDFCorruptError(f"Failed to open PDF document: {e}") from e

        try:
            pages: List[PDFPage] = []
            for idx, page in enumerate(doc):
                page_text = page.get_text("text") or ""
                pages.append(
                    PDFPage(
                        page_number=idx + 1,  # 1-indexed
                        text=page_text.strip(),
                        char_count=len(page_text.strip()),
                    )
                )

            return PDFDocument(
                filename=path.name,
                file_path=str(path.resolve()),
                total_pages=len(doc),
                pages=pages,
            )
        except Exception as e:
            raise PDFCorruptError(f"Error extracting pages from PDF: {e}") from e
        finally:
            doc.close()
