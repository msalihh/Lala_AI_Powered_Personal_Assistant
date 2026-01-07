"""
Image analysis module - OCR and vision model integration.
Handles text extraction from images and semantic analysis.
"""
import logging
import os
import base64
from typing import Optional, Dict, Tuple
from datetime import datetime
from io import BytesIO
from PIL import Image

logger = logging.getLogger(__name__)

# OCR and Vision are optional - system should work even if they fail
OCR_ENABLED = os.getenv("OCR_ENABLED", "false").lower() == "true"
VISION_ENABLED = os.getenv("VISION_ENABLED", "false").lower() == "true"

# Max image dimensions (to prevent memory issues)
MAX_IMAGE_WIDTH = 4096
MAX_IMAGE_HEIGHT = 4096


def resize_image_if_needed(image: Image.Image) -> Image.Image:
    """
    Resize image if it exceeds max dimensions.
    """
    width, height = image.size
    if width > MAX_IMAGE_WIDTH or height > MAX_IMAGE_HEIGHT:
        # Calculate scaling factor
        scale = min(MAX_IMAGE_WIDTH / width, MAX_IMAGE_HEIGHT / height)
        new_width = int(width * scale)
        new_height = int(height * scale)
        logger.info(f"Resizing image from {width}x{height} to {new_width}x{new_height}")
        return image.resize((new_width, new_height), Image.Resampling.LANCZOS)
    return image


def extract_text_from_image_ocr(file_content: bytes) -> Tuple[str, bool]:
    """
    Extract text from image using OCR (Tesseract).
    Returns: (ocr_text, success)
    """
    if not OCR_ENABLED:
        logger.debug("OCR is disabled, skipping OCR extraction")
        return "", False
    
    try:
        import pytesseract
        from PIL import Image
        
        # Open image
        image = Image.open(BytesIO(file_content))
        image = resize_image_if_needed(image)
        
        # Convert to RGB if needed (Tesseract requires RGB)
        if image.mode != "RGB":
            image = image.convert("RGB")
        
        # Run OCR
        ocr_text = pytesseract.image_to_string(image, lang="tur+eng")
        
        # Clean up text
        ocr_text = ocr_text.strip()
        
        if ocr_text:
            logger.info(f"OCR extracted {len(ocr_text)} characters from image")
            return ocr_text, True
        else:
            logger.warning("OCR returned empty text")
            return "", False
            
    except ImportError:
        logger.warning("pytesseract not installed, OCR disabled")
        return "", False
    except Exception as e:
        logger.error(f"OCR error: {str(e)}", exc_info=True)
        return "", False


def analyze_image_vision(file_content: bytes, filename: str) -> Dict:
    """
    Analyze image using vision model (OpenAI GPT-4 Vision or similar).
    Returns: {caption, tags, created_at}
    """
    if not VISION_ENABLED:
        logger.debug("Vision analysis is disabled, skipping vision analysis")
        return {
            "caption": "",
            "tags": [],
            "created_at": datetime.utcnow().isoformat()
        }
    
    try:
        from openai import OpenAI
        
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        if not client:
            logger.warning("OpenAI API key not found, vision analysis disabled")
            return {
                "caption": "",
                "tags": [],
                "created_at": datetime.utcnow().isoformat()
            }
        
        # Open and prepare image
        image = Image.open(BytesIO(file_content))
        image = resize_image_if_needed(image)
        
        # Convert to base64 for API
        buffered = BytesIO()
        if image.mode != "RGB":
            image = image.convert("RGB")
        image.save(buffered, format="JPEG")
        image_base64 = base64.b64encode(buffered.getvalue()).decode("utf-8")
        
        # Call vision API
        response = client.chat.completions.create(
            model="gpt-4o-mini",  # Use cheaper model for analysis
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "Bu fotoğrafı analiz et. Fotoğrafta ne görüyorsun? Kısa bir açıklama (caption) ve 3-5 etiket (tag) ver. Türkçe cevap ver. Format: CAPTION: [açıklama] TAGS: [etiket1, etiket2, ...]"
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{image_base64}"
                            }
                        }
                    ]
                }
            ],
            max_tokens=200
        )
        
        result_text = response.choices[0].message.content
        
        # Parse response
        caption = ""
        tags = []
        
        if "CAPTION:" in result_text:
            parts = result_text.split("CAPTION:")
            if len(parts) > 1:
                caption_part = parts[1].split("TAGS:")[0].strip()
                caption = caption_part
                
                if "TAGS:" in result_text:
                    tags_part = result_text.split("TAGS:")[1].strip()
                    # Extract tags (comma-separated)
                    tags = [tag.strip() for tag in tags_part.split(",") if tag.strip()]
        
        logger.info(f"Vision analysis completed: caption_length={len(caption)}, tags_count={len(tags)}")
        
        return {
            "caption": caption,
            "tags": tags,
            "created_at": datetime.utcnow().isoformat()
        }
        
    except ImportError:
        logger.warning("OpenAI not installed, vision analysis disabled")
        return {
            "caption": "",
            "tags": [],
            "created_at": datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error(f"Vision analysis error: {str(e)}", exc_info=True)
        return {
            "caption": "",
            "tags": [],
            "created_at": datetime.utcnow().isoformat()
        }


def analyze_image(file_content: bytes, filename: str) -> Dict:
    """
    Complete image analysis: OCR + Vision.
    Returns: {ocr_text, caption, tags, created_at}
    """
    logger.info(f"Starting image analysis for {filename}, size={len(file_content)} bytes")
    
    # Run OCR
    ocr_text, ocr_success = extract_text_from_image_ocr(file_content)
    
    # Run vision analysis
    vision_result = analyze_image_vision(file_content, filename)
    
    result = {
        "ocr_text": ocr_text,
        "caption": vision_result.get("caption", ""),
        "tags": vision_result.get("tags", []),
        "created_at": datetime.utcnow().isoformat(),
        "ocr_success": ocr_success,
        "vision_success": VISION_ENABLED and bool(vision_result.get("caption"))
    }
    
    logger.info(
        f"Image analysis completed: ocr_success={ocr_success}, "
        f"vision_success={result['vision_success']}, "
        f"ocr_text_length={len(ocr_text)}, caption_length={len(result['caption'])}"
    )
    
    return result

