"""
LGS Question Generator.
Generates similar but unique practice problems based on LGS patterns.
"""
import logging
import re
import json
from typing import Optional, List, Dict, Any
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class GeneratedQuestion:
    """A generated practice question."""
    question: str
    solution: str
    difficulty: str
    lgs_relevance: str  # Why this is LGS-appropriate
    topic: str = "karekok"


async def generate_similar_question(
    reference_problem: str,
    difficulty: str,
    avoid_patterns: Optional[List[str]],
    llm_call_func
) -> Optional[GeneratedQuestion]:
    """
    Generate a similar but unique question based on a reference.
    
    Args:
        reference_problem: The reference problem to base on
        difficulty: "easy" | "medium" | "hard"
        avoid_patterns: Patterns/numbers to avoid (already used)
        llm_call_func: Function to call LLM
        
    Returns:
        GeneratedQuestion or None
    """
    
    avoid_str = ", ".join(avoid_patterns[:5]) if avoid_patterns else "yok"
    
    prompt = f"""Sen bir LGS matematik soru yazarısın. Aşağıdaki soruya BENZER ama FARKLI bir soru üret.

REFERANS SORU: {reference_problem}
ZORLUK: {difficulty}
KULLANMA (önceden soruldu): {avoid_str}

KURALLAR:
1. Aynı kavramı test etmeli (kareköklü ifadeler)
2. Sayılar farklı olmalı
3. LGS formatına uygun olmalı (çoktan seçmeli değil, açık uçlu)
4. Tam çözümü de yaz

SADECE JSON formatında cevap ver:
{{"question": "Soru metni", "solution": "Adım adım çözüm", "lgs_relevance": "Bu soru LGS'de çıkabilir çünkü..."}}"""

    try:
        response = await llm_call_func(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,  # Some creativity for variety
            max_tokens=600
        )
        
        # Parse JSON
        json_match = re.search(r'\{[^}]+\}', response, re.DOTALL)
        if json_match:
            data = json.loads(json_match.group())
            return GeneratedQuestion(
                question=data.get("question", ""),
                solution=data.get("solution", ""),
                difficulty=difficulty,
                lgs_relevance=data.get("lgs_relevance", "")
            )
        
        return None
        
    except Exception as e:
        logger.error(f"LGS Generator: Error generating question: {str(e)}")
        return None


async def generate_easier_version(
    problem: str,
    current_difficulty: str,
    llm_call_func
) -> Optional[GeneratedQuestion]:
    """
    Generate an easier version of a problem.
    
    Args:
        problem: The problem to simplify
        current_difficulty: Current difficulty level
        llm_call_func: Function to call LLM
        
    Returns:
        Easier version of the problem
    """
    
    target_difficulty = "easy" if current_difficulty != "easy" else "easy"
    
    prompt = f"""Sen bir LGS matematik öğretmenisin. Aşağıdaki sorunun DAHA KOLAY bir versiyonunu üret.

ORİJİNAL SORU: {problem}
MEVCUT ZORLUK: {current_difficulty}
HEDEF ZORLUK: {target_difficulty}

NASIL KOLAYLAŞTIR:
- Daha küçük sayılar kullan
- Daha az adım gerektir
- Aynı kavramı test et ama daha basit

SADECE JSON formatında cevap ver:
{{"question": "Kolay soru", "solution": "Çözüm", "lgs_relevance": "Temel beceri pratiği"}}"""

    try:
        response = await llm_call_func(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.5,
            max_tokens=400
        )
        
        json_match = re.search(r'\{[^}]+\}', response, re.DOTALL)
        if json_match:
            data = json.loads(json_match.group())
            return GeneratedQuestion(
                question=data.get("question", ""),
                solution=data.get("solution", ""),
                difficulty=target_difficulty,
                lgs_relevance=data.get("lgs_relevance", "Temel beceri pratiği")
            )
        
        return None
        
    except Exception as e:
        logger.error(f"LGS Generator: Error generating easier version: {str(e)}")
        return None
