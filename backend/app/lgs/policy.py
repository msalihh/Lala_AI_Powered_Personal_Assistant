"""
LGS Adaptive Policy Engine.
Determines teaching strategy based on student performance and error patterns.
"""
import logging
from typing import Optional, List

from app.lgs.state import LGSPedagogicalState

logger = logging.getLogger(__name__)


# Available teaching strategies
STRATEGIES = {
    "direct_solve": "Doğrudan çözüm göster",
    "scaffolding": "Adım adım ipuçlarıyla yönlendir",
    "simplified_explanation": "Önce temel kavramı anlat",
    "socratic": "Sorularla öğrenciyi düşündür",
    "similar_easier": "Benzer ama daha kolay soru üret",
    "test_mode": "Bilerek hata yap, öğrenci bulsun"
}


def select_strategy(state: LGSPedagogicalState) -> str:
    """
    Select the best teaching strategy based on pedagogical state.
    
    Args:
        state: Current LGSPedagogicalState
        
    Returns:
        Strategy name (key from STRATEGIES dict)
    """
    
    # RULE 1: Same error 3+ times → Simplified explanation
    if state.consecutive_same_error >= 3:
        logger.info(f"LGS Policy: Same error {state.consecutive_same_error}x → simplified_explanation")
        return "simplified_explanation"
    
    # RULE 2: Conceptual error 2+ times → Scaffolding (if not already tried)
    if state.error_counts.get("conceptual", 0) >= 2:
        recent_strategies = state.strategy_history[-3:] if state.strategy_history else []
        if "scaffolding" not in recent_strategies:
            logger.info("LGS Policy: Conceptual errors → scaffolding")
            return "scaffolding"
        else:
            logger.info("LGS Policy: Scaffolding didn't work → simplified_explanation")
            return "simplified_explanation"
    
    # RULE 3: Calculation error 2+ times → Similar easier question
    if state.error_counts.get("calculation", 0) >= 2:
        logger.info("LGS Policy: Calculation errors → similar_easier")
        return "similar_easier"
    
    # RULE 4: High mastery (>0.85) and enough attempts → Test mode
    if state.mastery_score > 0.85 and state.total_problems_attempted >= 5:
        if not state.test_mode_active:
            logger.info("LGS Policy: High mastery → test_mode")
            return "test_mode"
    
    # RULE 5: Strategy failed twice in a row → Switch
    if len(state.strategy_history) >= 2:
        last_two = state.strategy_history[-2:]
        if last_two[0] == last_two[1] and state.last_error_type is not None:
            alternative = _get_alternative_strategy(last_two[0])
            logger.info(f"LGS Policy: Strategy {last_two[0]} failed twice → {alternative}")
            return alternative
    
    # DEFAULT: Direct solve
    return "direct_solve"


def _get_alternative_strategy(current: str) -> str:
    """Get an alternative strategy when the current one isn't working."""
    alternatives = {
        "direct_solve": "scaffolding",
        "scaffolding": "simplified_explanation",
        "simplified_explanation": "socratic",
        "socratic": "similar_easier",
        "similar_easier": "simplified_explanation",
        "test_mode": "direct_solve"
    }
    return alternatives.get(current, "scaffolding")


def adapt_difficulty(state: LGSPedagogicalState) -> str:
    """
    Adapt difficulty level based on performance.
    
    Returns:
        "easy" | "medium" | "hard"
    """
    if state.total_problems_attempted == 0:
        return "medium"
    
    success_rate = state.total_correct / state.total_problems_attempted
    
    if success_rate < 0.4:
        return "easy"
    elif success_rate < 0.7:
        return "medium"
    else:
        return "hard"


def get_strategy_prompt_modifier(strategy: str, state: LGSPedagogicalState) -> str:
    """
    Get prompt modifier text for the selected strategy.
    
    Args:
        strategy: Selected strategy name
        state: Current pedagogical state
        
    Returns:
        Additional prompt instructions for the LLM
    """
    
    modifiers = {
        "direct_solve": """
ÇÖZÜM STRATEJİSİ: Doğrudan Çözüm
- ÖNCE: "KULLANICININ BELGELERİNDEN İLGİLİ NOTLAR" bölümünü tara, oradaki soru tiplerini kullan.
- Yanlış anlaşılan noktayı `\( ... \)` formatıyla belirle.
- Adımları "Ne - Neden - Atlanırsa ne olur?" yapısıyla kesinleştir.
- Dökümandaki benzer sayısal değerleri kullanarak örnek ver.
""",
        
        "scaffolding": f"""
ÇÖZÜM STRATEJİSİ: İpuçlu Yönlendirme
- ÖNCE: Dökümanlardan benzer bir soru bul ve onun üzerinden yönlendir.
- Çözümün tamamını verme.
- Kritik bir adım için "Burada hangi kuralı hatırlamalıyız?" gibi doğrudan bir soru sor.
- Öğrencinin takıldığı nokta: {state.struggle_point or 'genel kavramlar'}.
""",
        
        "simplified_explanation": f"""
ÇÖZÜM STRATEJİSİ: Temel Kavram Anlatımı
- Karmaşıklığı gider, en temel kazanımı (Örn: M.8.1.3.1) açıkla.
- Sadece \\( \\sqrt{4}, \\sqrt{9}, \\sqrt{16} \\) gibi tam kare örneklerle kavramı sabitle.
- Öğrenci {state.consecutive_same_error} kez aynı hatayı tekrarladı, temel bir mantık sapması var.
""",
        
        "socratic": f"""
ÇÖZÜM STRATEJİSİ: Sokratik Sorgulama
- Bilgi verme, sadece öğrencinin mevcut bilgisini çürütecek veya doğrulayacak sorular sor.
- "Neden \\( \\sqrt{18} \\) için \\( 9\\sqrt{2} \\) cevabı doğru olamaz?" gibi doğrudan çelişkilere odaklan.
""",
        
        "similar_easier": """
ÇÖZÜM STRATEJİSİ: Benzer Kolay Soru
- ZORUNLUn: "KULLANICININ BELGELERİNDEN İLGİLİ NOTLAR"daki bir soruyu basitleştir.
- Mevcut soruyu askıya al.
- Dökümandaki bir sorunun sayısal değerlerini küçülterek (Örn: 72→18, 50→8) kolay versiyon oluştur.
- Çözümden sonra asıl soruya dönmek üzere not düş.
""",
        
        "test_mode": """
ÇÖZÜM STRATEJİSİ: Öğretmen Test Modu (Uzman Seviyesi)
- Bilerek teknik bir hata yap (Örn: \\( \\sqrt{50} = 2\\sqrt{5} \\) de).
- "Bu işlemdeki hatayı bulabilir misin?" diyerek öğrencinin dikkatini test et.
"""
    }
    
    return modifiers.get(strategy, modifiers["direct_solve"])
