"""
LGS Error Analyzer.
Classifies student errors into conceptual, calculation, or reading errors.
"""
import logging
import json
import re
from typing import Optional, Dict, Any
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class ErrorClassification:
    """Result of error classification."""
    error_type: str  # "conceptual" | "calculation" | "reading" | "none"
    confidence: float  # 0.0 - 1.0
    explanation: str  # Short explanation for the student
    specific_mistake: Optional[str] = None  # What exactly went wrong


async def classify_error(
    student_response: str,
    problem: str,
    correct_answer: Optional[str],
    chat_history: list,
    llm_call_func
) -> ErrorClassification:
    """
    Classify the type of error in a student's response.
    
    Args:
        student_response: What the student said/answered
        problem: The original problem
        correct_answer: The correct answer (if known)
        chat_history: Recent chat messages for context
        llm_call_func: Function to call LLM
        
    Returns:
        ErrorClassification with error type and explanation
    """
    
    classification_prompt = f"""Sen bir LGS matematik öğretmenisin. Öğrencinin cevabını analiz et.

SORU: {problem}
{f"DOĞRU CEVAP: {correct_answer}" if correct_answer else ""}
ÖĞRENCİ CEVABI: {student_response}

HATA TÜRLERİ:
1. conceptual: Kavram hatası (karekök tanımını bilmiyor, √16=8 diyor, negatif sayının karekökünü almaya çalışıyor)
2. calculation: İşlem hatası (çarpan ayırma yanlış, toplama/çarpma hatası, sadeleştirme yanlış)
3. reading: Soru okuma hatası (ne istendiğini yanlış anlamış, farklı bir şey hesaplamış)
4. none: Doğru cevap veya henüz cevap vermemiş

SADECE JSON formatında cevap ver, başka hiçbir şey yazma:
{{"error_type": "...", "confidence": 0.0-1.0, "explanation": "Öğrenciye gösterilecek kısa açıklama (max 30 kelime)", "specific_mistake": "Tam olarak nerede hata yapıldı"}}"""

    try:
        response = await llm_call_func(
            messages=[{"role": "user", "content": classification_prompt}],
            temperature=0.1,
            max_tokens=200
        )
        
        # Parse JSON response
        json_match = re.search(r'\{[^}]+\}', response, re.DOTALL)
        if json_match:
            data = json.loads(json_match.group())
            return ErrorClassification(
                error_type=data.get("error_type", "none"),
                confidence=float(data.get("confidence", 0.5)),
                explanation=data.get("explanation", ""),
                specific_mistake=data.get("specific_mistake")
            )
        
        # Fallback if parsing fails
        return ErrorClassification(
            error_type="none",
            confidence=0.3,
            explanation="Cevabınız değerlendiriliyor."
        )
        
    except Exception as e:
        logger.error(f"LGS Analyzer: Error classifying: {str(e)}")
        return ErrorClassification(
            error_type="none",
            confidence=0.0,
            explanation=""
        )


def format_error_feedback(classification: ErrorClassification) -> str:
    """
    Format error classification as short feedback for the student.
    
    Returns:
        Markdown-formatted feedback string
    """
    if classification.error_type == "none":
        return ""
    
    error_labels = {
        "conceptual": "Kavram Hatası",
        "calculation": "İşlem Hatası",
        "reading": "Soru Okuma Hatası"
    }
    
    label = error_labels.get(classification.error_type, "Hata")
    
    feedback = f"❌ **{label}**\n"
    if classification.explanation:
        feedback += f"{classification.explanation}\n"
    
    return feedback
