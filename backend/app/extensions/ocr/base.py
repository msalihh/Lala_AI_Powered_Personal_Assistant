"""
OCR Base Interface and Factory

Provides abstract OCR interface and factory function to get configured engine.
When OCR is disabled, returns a mock engine that always returns empty string.
"""

from abc import ABC, abstractmethod
from typing import Optional
import logging

logger = logging.getLogger(__name__)


class OCRBase(ABC):
    """Abstract base class for OCR engines."""
    
    name: str = "base"
    
    @abstractmethod
    def extract_text(self, image_bytes: bytes, filename: str = "") -> str:
        """
        Extract text from image bytes.
        
        Args:
            image_bytes: Raw image/PDF bytes
            filename: Optional filename for logging
            
        Returns:
            Extracted text or empty string if failed
        """
        pass
    
    @abstractmethod
    def is_available(self) -> bool:
        """Check if this OCR engine is available and configured."""
        pass
    
    def extract_text_safe(self, image_bytes: bytes, filename: str = "") -> str:
        """
        Safe extraction with error handling.
        Returns empty string on any error.
        """
        try:
            if not self.is_available():
                logger.debug(f"[OCR] {self.name} not available")
                return ""
            return self.extract_text(image_bytes, filename)
        except Exception as e:
            logger.warning(f"[OCR] {self.name} extraction failed: {e}")
            return ""


class MockOCR(OCRBase):
    """Mock OCR engine that always returns empty string."""
    
    name = "mock"
    
    def extract_text(self, image_bytes: bytes, filename: str = "") -> str:
        return ""
    
    def is_available(self) -> bool:
        return True


class TesseractOCR(OCRBase):
    """Tesseract OCR engine (requires pytesseract and tesseract installed)."""
    
    name = "tesseract"
    
    def is_available(self) -> bool:
        try:
            import pytesseract
            # Try to get tesseract version to verify installation
            pytesseract.get_tesseract_version()
            return True
        except Exception:
            return False
    
    def extract_text(self, image_bytes: bytes, filename: str = "") -> str:
        import pytesseract
        from PIL import Image
        import io
        
        # Handle PDF vs Image
        if filename.lower().endswith(".pdf"):
            # Use pdf2image to convert PDF pages to images
            try:
                from pdf2image import convert_from_bytes
                images = convert_from_bytes(image_bytes)
                texts = []
                for i, img in enumerate(images):
                    text = pytesseract.image_to_string(img, lang="tur+eng")
                    texts.append(text)
                return "\n\n".join(texts)
            except ImportError:
                logger.warning("[OCR] pdf2image not installed, cannot OCR PDF")
                return ""
        else:
            # Direct image OCR
            image = Image.open(io.BytesIO(image_bytes))
            return pytesseract.image_to_string(image, lang="tur+eng")


# Singleton instance
_ocr_engine: Optional[OCRBase] = None


def get_ocr_engine() -> OCRBase:
    """
    Get configured OCR engine.
    Returns MockOCR if OCR is disabled or not configured.
    """
    global _ocr_engine
    
    if _ocr_engine is not None:
        return _ocr_engine
    
    try:
        from app.extensions.config import get_extension_config
        config = get_extension_config()
        
        if not config.ocr_enabled:
            logger.debug("[OCR] OCR disabled, using mock")
            _ocr_engine = MockOCR()
            return _ocr_engine
        
        if config.ocr_backend == "tesseract":
            engine = TesseractOCR()
            if engine.is_available():
                logger.info("[OCR] Using Tesseract OCR")
                _ocr_engine = engine
            else:
                logger.warning("[OCR] Tesseract not available, falling back to mock")
                _ocr_engine = MockOCR()
        elif config.ocr_backend == "google_vision":
            # Google Vision would be implemented here
            logger.warning("[OCR] Google Vision not yet implemented, using mock")
            _ocr_engine = MockOCR()
        else:
            _ocr_engine = MockOCR()
        
        return _ocr_engine
        
    except ImportError:
        logger.debug("[OCR] Extensions not configured, using mock")
        _ocr_engine = MockOCR()
        return _ocr_engine


def extract_text_with_ocr(file_bytes: bytes, filename: str) -> str:
    """
    Convenience function to extract text using configured OCR.
    Safe to call even if OCR is disabled (returns empty string).
    """
    engine = get_ocr_engine()
    return engine.extract_text_safe(file_bytes, filename)
