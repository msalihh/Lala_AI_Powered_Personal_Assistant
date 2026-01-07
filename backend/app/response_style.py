"""
Response style parser and auto-detector for chat responses.
Handles explicit user commands and automatic style selection based on question complexity.
"""
import re
from typing import Literal, Optional, Tuple

ResponseStyle = Literal["short", "medium", "long", "detailed"]


def parse_response_style_command(message: str) -> Optional[ResponseStyle]:
    """
    Parse explicit response style commands from user message.
    
    Commands:
    - /short, /medium, /long, /detailed
    - Turkish: "kısa", "özet", "detaylı", "uzun anlat", "madde madde"
    
    Args:
        message: User message text
        
    Returns:
        ResponseStyle if command found, None otherwise
    """
    message_lower = message.lower().strip()
    
    # English commands
    if re.search(r'\b/short\b', message_lower):
        return "short"
    if re.search(r'\b/medium\b', message_lower):
        return "medium"
    if re.search(r'\b/long\b', message_lower):
        return "long"
    if re.search(r'\b/detailed\b', message_lower):
        return "detailed"
    
    # Turkish commands
    if re.search(r'\b(kısa|kısaca|özet|özetle|özet olarak)\b', message_lower):
        return "short"
    if re.search(r'\b(orta|normal|standart)\b', message_lower):
        return "medium"
    if re.search(r'\b(uzun|uzun anlat|detaylı|detaylı anlat|detaylıca|açıkla|açıklama)\b', message_lower):
        return "detailed"
    if re.search(r'\b(madde madde|liste|listele|adım adım)\b', message_lower):
        return "long"
    
    return None


def remove_style_commands(message: str) -> str:
    """
    Remove style commands from message before sending to LLM.
    
    Args:
        message: User message text
        
    Returns:
        Message with style commands removed
    """
    # Remove English commands
    message = re.sub(r'\b/short\b', '', message, flags=re.IGNORECASE)
    message = re.sub(r'\b/medium\b', '', message, flags=re.IGNORECASE)
    message = re.sub(r'\b/long\b', '', message, flags=re.IGNORECASE)
    message = re.sub(r'\b/detailed\b', '', message, flags=re.IGNORECASE)
    
    # Remove Turkish commands (be careful not to remove words that are part of the question)
    # Only remove if they appear at the start or end of the message
    message = re.sub(r'^(kısa|kısaca|özet|özetle|özet olarak|orta|normal|standart|uzun|uzun anlat|detaylı|detaylı anlat|detaylıca|açıkla|açıklama|madde madde|liste|listele|adım adım)[\s,]+', '', message, flags=re.IGNORECASE)
    message = re.sub(r'[\s,]+(kısa|kısaca|özet|özetle|özet olarak|orta|normal|standart|uzun|uzun anlat|detaylı|detaylı anlat|detaylıca|açıkla|açıklama|madde madde|liste|listele|adım adım)$', '', message, flags=re.IGNORECASE)
    
    return message.strip()


def auto_detect_response_style(message: str) -> ResponseStyle:
    """
    Automatically detect response style based on question complexity.
    
    Heuristics:
    - Short (2-5 sentences): Simple fact questions, greetings, yes/no questions
    - Medium (1-2 paragraphs): How-to questions, comparisons, explanations
    - Long (step-by-step): Multi-step processes, tutorials, code examples
    - Detailed (comprehensive): Architecture, analysis, deep dives
    
    Args:
        message: User message text
        
    Returns:
        Detected ResponseStyle
    """
    message_lower = message.lower().strip()
    word_count = len(message.split())
    
    # Very short messages (greetings, simple questions)
    if word_count <= 5:
        # Check if it's a simple question
        simple_patterns = [
            r'^(adın|ismin|kimsin|nasılsın|merhaba|selam|hey)',
            r'^(evet|hayır|tamam|ok|teşekkür|sağ ol)',
            r'^\w+\?$',  # Single word question
        ]
        if any(re.match(p, message_lower) for p in simple_patterns):
            return "short"
    
    # Check for detailed/complex indicators
    detailed_indicators = [
        r'\b(mimari|architecture|tasarım|design|plan|planla|analiz|analysis|karşılaştır|compare|compare|benchmark)\b',
        r'\b(neden|why|sebep|reason|açıkla|explain|detay|detail)\b',
        r'\b(adım adım|step by step|tutorial|öğretici|rehber|guide)\b',
        r'\b(kod|code|programlama|programming|implement|uygula|implementasyon)\b',
        r'\b(nasıl yapılır|how to|nasıl kurulur|how to install|nasıl kullanılır|how to use)\b',
    ]
    
    detailed_count = sum(1 for pattern in detailed_indicators if re.search(pattern, message_lower))
    
    if detailed_count >= 2:
        return "detailed"
    elif detailed_count >= 1:
        return "long"
    
    # Check for medium complexity indicators
    medium_indicators = [
        r'\b(nasıl|how|nedir|what is|ne demek|what does)\b',
        r'\b(karşılaştır|compare|fark|difference|benzerlik|similarity)\b',
        r'\b(avantaj|advantage|dezavantaj|disadvantage|artı|plus|eksi|minus)\b',
        r'\b(örnek|example|örnek ver|give example)\b',
    ]
    
    medium_count = sum(1 for pattern in medium_indicators if re.search(pattern, message_lower))
    
    if medium_count >= 1:
        return "medium"
    
    # Default to medium for questions, short for statements
    if '?' in message or word_count > 10:
        return "medium"
    
    return "short"


def determine_response_style(
    user_message: str,
    explicit_style: Optional[ResponseStyle] = None
) -> Tuple[ResponseStyle, str]:
    """
    Determine final response style (explicit command takes priority over auto-detection).
    
    Args:
        user_message: User message text
        explicit_style: Explicit style from request (if provided)
        
    Returns:
        Tuple of (ResponseStyle, cleaned_message)
    """
    # Priority 1: Explicit style from request
    if explicit_style:
        cleaned_message = remove_style_commands(user_message)
        return explicit_style, cleaned_message
    
    # Priority 2: Command in message
    command_style = parse_response_style_command(user_message)
    if command_style:
        cleaned_message = remove_style_commands(user_message)
        return command_style, cleaned_message
    
    # Priority 3: Auto-detection
    auto_style = auto_detect_response_style(user_message)
    return auto_style, user_message


def get_max_tokens_for_style(style: ResponseStyle) -> int:
    """
    Get max_tokens value based on response style.
    
    Args:
        style: Response style
        
    Returns:
        Max tokens value
    """
    style_tokens = {
        "short": 300,      # 2-5 sentences, ~80-100 words
        "medium": 800,     # 1-2 paragraphs + bullet points
        "long": 1200,      # Step-by-step + examples
        "detailed": 1500,  # Headers + sub-items + edge cases (reduced for credit limits)
    }
    return style_tokens.get(style, 800)  # Default fallback


def get_style_prompt_instruction(style: ResponseStyle) -> str:
    """
    Get prompt instruction for the given response style.
    
    Args:
        style: Response style
        
    Returns:
        Prompt instruction text
    """
    instructions = {
        "short": """CEVAP UZUNLUĞU: KISA (2-5 cümle, maksimum ~120-180 kelime)
- Kısa ve öz cevap ver, gereksiz detay ekleme.
- Doğrudan soruya odaklan, yan bilgiler verme.
- RAG kaynakları varsa özetle, uzun açıklamalar yapma.""",
        
        "medium": """CEVAP UZUNLUĞU: ORTA (1-2 paragraf + madde işaretleri)
- Dengeli bir cevap ver: yeterli detay ama çok uzun değil.
- Ana noktaları madde işaretleri ile özetle.
- RAG kaynakları varsa önemli bilgileri vurgula.""",
        
        "long": """CEVAP UZUNLUĞU: UZUN (adım adım + örnekler)
- Detaylı, adım adım açıklama yap.
- Örnekler ve uygulamalar ekle.
- RAG kaynakları varsa detaylı analiz yap.""",
        
        "detailed": """CEVAP UZUNLUĞU: ÇOK DETAYLI (başlıklar + alt maddeler + edge-case)
- Kapsamlı, derinlemesine analiz yap.
- Başlıklar ve alt başlıklar kullan.
- Edge case'leri, istisnaları ve alternatif yaklaşımları dahil et.
- RAG kaynakları varsa tam analiz ve karşılaştırma yap.""",
    }
    return instructions.get(style, instructions["medium"])

