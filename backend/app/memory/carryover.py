"""
Follow-up carryover detection and query rewriting.
Detects follow-up triggers and inherits context from previous conversation.
"""
import re
import logging
from typing import Optional, Tuple

from app.memory.state import ConversationState, get_conversation_state, update_conversation_state

logger = logging.getLogger(__name__)

# Follow-up trigger patterns (Turkish and English)
FOLLOWUP_TRIGGERS = [
    r'\b(devam|uzun\s+çöz|uzun\s+soru\s+çöz|1\s+tane\s+daha|bir\s+tane\s+daha|bunu|şunu|aynısı|detaylandır|daha\s+detaylı)\b',
    r'\b(continue|more|another|same|this|that|detail|elaborate)\b',
]

# Strong topic change indicators (if these appear, don't carry over)
TOPIC_CHANGE_INDICATORS = [
    r'\b(yeni|farklı|başka|değiş|switch|new|different|change)\b',
    r'\b(nedir|ne\s+demek|what\s+is|what\s+does)\b',  # Generic questions often indicate topic change
]


def detect_followup_trigger(user_message: str) -> bool:
    """
    Detect if user message is a follow-up trigger.
    
    Args:
        user_message: User message text
        
    Returns:
        True if message is a follow-up trigger
    """
    message_lower = user_message.lower().strip()
    
    # Check for follow-up triggers
    for pattern in FOLLOWUP_TRIGGERS:
        if re.search(pattern, message_lower, re.IGNORECASE):
            return True
    
    # Check if message is very short (likely a follow-up)
    if len(message_lower.split()) <= 3 and len(message_lower) < 20:
        return True
    
    return False


def detect_topic_change(user_message: str, last_topic: Optional[str]) -> bool:
    """
    Detect if user is changing topic (not continuing previous).
    
    Args:
        user_message: Current user message
        last_topic: Last topic from conversation state
        
    Returns:
        True if topic change detected
    """
    if not last_topic:
        return False
    
    message_lower = user_message.lower()
    
    # Check for strong topic change indicators
    for pattern in TOPIC_CHANGE_INDICATORS:
        if re.search(pattern, message_lower, re.IGNORECASE):
            return True
    
    # Check if message contains specific topic keywords that differ from last_topic
    # This is a heuristic - if message has strong domain-specific keywords, it might be a new topic
    math_keywords = ['karekök', 'radikal', 'üslü', 'logaritma', 'türev', 'integral', 'denklem', 'fonksiyon']
    coding_keywords = ['kod', 'program', 'fonksiyon', 'class', 'import', 'def', 'function']
    
    message_has_math = any(kw in message_lower for kw in math_keywords)
    message_has_coding = any(kw in message_lower for kw in coding_keywords)
    
    last_has_math = any(kw in last_topic.lower() for kw in math_keywords) if last_topic else False
    last_has_coding = any(kw in last_topic.lower() for kw in coding_keywords) if last_topic else False
    
    # If message has different domain keywords than last topic, likely a topic change
    if (message_has_math and last_has_coding) or (message_has_coding and last_has_math):
        return True
    
    return False


async def resolve_carryover(
    user_id: str,
    chat_id: str,
    user_message: str,
    document_ids: Optional[list] = None
) -> Tuple[str, bool]:
    """
    Resolve follow-up carryover by rewriting user query if needed.
    
    Args:
        user_id: User ID
        chat_id: Chat ID
        user_message: Current user message
        document_ids: Current document IDs (optional)
        
    Returns:
        Tuple of (rewritten_message, carryover_used)
        - rewritten_message: Original message or rewritten with context
        - carryover_used: True if carryover was applied
    """
    try:
        # Get conversation state
        state = await get_conversation_state(user_id, chat_id)
        
        # Check if this is a follow-up trigger
        is_followup = detect_followup_trigger(user_message)
        
        if not is_followup:
            # Not a follow-up, update state with new topic and return original message
            # Extract topic from message (simple heuristic)
            topic = _extract_topic(user_message)
            domain = _detect_domain(user_message)
            
            new_state = ConversationState(
                last_topic=topic,
                last_user_question=user_message,
                last_domain=domain,
                unresolved_followup=False,
                last_document_ids=document_ids
            )
            await update_conversation_state(user_id, chat_id, new_state)
            return user_message, False
        
        # This is a follow-up trigger
        # Check if topic is changing
        if detect_topic_change(user_message, state.last_topic):
            logger.info(f"Memory: Topic change detected, not carrying over. Message: {user_message[:50]}...")
            # Update state with new topic
            topic = _extract_topic(user_message)
            domain = _detect_domain(user_message)
            new_state = ConversationState(
                last_topic=topic,
                last_user_question=user_message,
                last_domain=domain,
                unresolved_followup=False,
                last_document_ids=document_ids
            )
            await update_conversation_state(user_id, chat_id, new_state)
            return user_message, False
        
        # Apply carryover: rewrite message with last topic context
        if state.last_topic and state.last_user_question:
            # Rewrite message to include last topic
            rewritten = _rewrite_with_context(user_message, state.last_topic, state.last_user_question)
            
            logger.info(
                f"Memory: Carryover applied. Original: '{user_message[:50]}...' "
                f"→ Rewritten: '{rewritten[:100]}...' (topic: {state.last_topic})"
            )
            
            # Update state (keep same topic, update question)
            new_state = ConversationState(
                last_topic=state.last_topic,
                last_user_question=rewritten,  # Store rewritten question
                last_domain=state.last_domain,
                unresolved_followup=False,
                last_document_ids=document_ids or state.last_document_ids
            )
            await update_conversation_state(user_id, chat_id, new_state)
            
            return rewritten, True
        else:
            # No previous context, can't carry over
            logger.debug(f"Memory: Follow-up trigger but no previous context, using original message")
            return user_message, False
        
    except Exception as e:
        logger.error(f"Memory: Error resolving carryover: {str(e)}", exc_info=True)
        return user_message, False


def _extract_topic(message: str) -> Optional[str]:
    """
    Extract topic from message (simple heuristic).
    
    Args:
        message: User message
        
    Returns:
        Extracted topic or None
    """
    message_lower = message.lower()
    
    # Math topics
    math_topics = {
        'karekök': 'karekök',
        'radikal': 'radikaller',
        'üslü': 'üslü sayılar',
        'logaritma': 'logaritma',
        'türev': 'türev',
        'integral': 'integral',
        'denklem': 'denklem',
        'fonksiyon': 'fonksiyon',
    }
    
    for keyword, topic in math_topics.items():
        if keyword in message_lower:
            return topic
    
    # Coding topics
    coding_topics = {
        'kod': 'kodlama',
        'program': 'programlama',
        'python': 'python',
        'javascript': 'javascript',
        'function': 'fonksiyon',
    }
    
    for keyword, topic in coding_topics.items():
        if keyword in message_lower:
            return topic
    
    # If no specific topic found, use first few words
    words = message.split()[:3]
    if words:
        return ' '.join(words)
    
    return None


def _detect_domain(message: str) -> str:
    """
    Detect domain (math, coding, general) from message.
    
    Args:
        message: User message
        
    Returns:
        Domain string: "math", "coding", or "general"
    """
    message_lower = message.lower()
    
    math_keywords = ['karekök', 'radikal', 'üslü', 'logaritma', 'türev', 'integral', 'denklem', 'matematik', 'math']
    coding_keywords = ['kod', 'program', 'python', 'javascript', 'function', 'class', 'import']
    
    if any(kw in message_lower for kw in math_keywords):
        return "math"
    elif any(kw in message_lower for kw in coding_keywords):
        return "coding"
    else:
        return "general"


def _rewrite_with_context(followup_message: str, last_topic: str, last_question: str) -> str:
    """
    Rewrite follow-up message with context from last topic/question.
    
    Args:
        followup_message: Current follow-up message (e.g., "uzun soru çöz")
        last_topic: Last topic (e.g., "karekök")
        last_question: Last full question
        
    Returns:
        Rewritten message with context
    """
    followup_lower = followup_message.lower().strip()
    
    # If message is very generic, replace with topic-specific request
    if followup_lower in ['devam', 'uzun çöz', 'uzun soru çöz', '1 tane daha', 'bir tane daha']:
        # Rewrite as: "{last_topic} hakkında uzun bir soru çöz"
        return f"{last_topic} hakkında uzun bir soru çöz"
    
    # If message contains "bunu", "şunu", "aynısı", replace with topic
    if re.search(r'\b(bunu|şunu|aynısı)\b', followup_lower):
        # Replace pronoun with topic
        rewritten = re.sub(r'\b(bunu|şunu|aynısı)\b', last_topic, followup_message, flags=re.IGNORECASE)
        return rewritten
    
    # If message is "detaylandır" or "daha detaylı", add topic
    if re.search(r'\b(detaylandır|daha\s+detaylı)\b', followup_lower):
        return f"{last_topic} hakkında {followup_message}"
    
    # Default: prepend topic to message
    return f"{last_topic} {followup_message}"

