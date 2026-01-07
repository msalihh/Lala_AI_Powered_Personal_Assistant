"""
OCR Extension

Provides text extraction from scanned PDFs and images.
Default: DISABLED (fallback to empty string)
"""

from app.extensions.ocr.base import OCRBase, get_ocr_engine

__all__ = ["OCRBase", "get_ocr_engine"]
