"""
LGS Pedagogical State Management.
Tracks student progress, error patterns, and adaptive teaching state.
"""
import logging
from typing import Optional, Dict, List, Any
from datetime import datetime
from dataclasses import dataclass, field, asdict
from bson import ObjectId

from app.database import get_database

logger = logging.getLogger(__name__)


@dataclass
class LGSPedagogicalState:
    """
    LGS Modülüne özel pedagojik durum.
    Öğrenci performansını, hata kalıplarını ve strateji geçmişini takip eder.
    """
    
    # === Öğrenci Profili ===
    mastery_score: float = 0.5          # 0.0 - 1.0 (Konu hakimiyeti)
    current_difficulty: str = "medium"   # "easy" | "medium" | "hard"
    
    # === Hata Takibi ===
    error_counts: Dict[str, int] = field(default_factory=lambda: {
        "conceptual": 0,    # Kavram hatası (√16 = 8 demek gibi)
        "calculation": 0,   # İşlem hatası (çarpan ayırma yanlışı)
        "reading": 0        # Soru okuma hatası (ne istendiğini yanlış anlama)
    })
    last_error_type: Optional[str] = None
    consecutive_same_error: int = 0
    
    # === Strateji Geçmişi ===
    strategy_history: List[str] = field(default_factory=list)
    current_strategy: str = "direct_solve"
    
    # === Bağlam Sürekliliği ===
    last_problem: Optional[str] = None
    last_solution_steps: Optional[List[str]] = None
    struggle_point: Optional[str] = None
    
    # === Test Modu ===
    test_mode_active: bool = False
    test_mode_type: Optional[str] = None
    
    # === İstatistikler ===
    total_problems_attempted: int = 0
    total_correct: int = 0
    session_start: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for MongoDB storage."""
        data = asdict(self)
        if self.session_start is None:
            data["session_start"] = datetime.utcnow().isoformat()
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "LGSPedagogicalState":
        """Create from MongoDB document."""
        # Filter only known fields
        known_fields = cls.__dataclass_fields__.keys()
        filtered = {k: v for k, v in data.items() if k in known_fields}
        return cls(**filtered)
    
    def record_error(self, error_type: str) -> None:
        """Record an error and update consecutive tracking."""
        if error_type in self.error_counts:
            self.error_counts[error_type] += 1
        
        if error_type == self.last_error_type:
            self.consecutive_same_error += 1
        else:
            self.consecutive_same_error = 1
        
        self.last_error_type = error_type
        self.total_problems_attempted += 1
        
        # Update mastery score
        self._update_mastery()
    
    def record_success(self) -> None:
        """Record a successful answer."""
        self.total_correct += 1
        self.total_problems_attempted += 1
        self.consecutive_same_error = 0
        self.last_error_type = None
        self._update_mastery()
    
    def _update_mastery(self) -> None:
        """Update mastery score based on performance."""
        if self.total_problems_attempted > 0:
            success_rate = self.total_correct / self.total_problems_attempted
            # Weighted average with current mastery
            self.mastery_score = 0.7 * success_rate + 0.3 * self.mastery_score
            self.mastery_score = max(0.0, min(1.0, self.mastery_score))
    
    def add_strategy(self, strategy: str) -> None:
        """Add strategy to history and set as current."""
        self.strategy_history.append(strategy)
        self.current_strategy = strategy
        # Keep only last 10 strategies
        if len(self.strategy_history) > 10:
            self.strategy_history = self.strategy_history[-10:]


async def get_lgs_state(user_id: str, chat_id: str) -> LGSPedagogicalState:
    """
    Get LGS pedagogical state for a chat session.
    
    Args:
        user_id: User ID
        chat_id: Chat ID
        
    Returns:
        LGSPedagogicalState object
    """
    try:
        db = get_database()
        if db is None:
            return LGSPedagogicalState()
        
        state_doc = await db.lgs_states.find_one({
            "user_id": user_id,
            "chat_id": chat_id
        })
        
        if state_doc and "state" in state_doc:
            return LGSPedagogicalState.from_dict(state_doc["state"])
        
        return LGSPedagogicalState()
        
    except Exception as e:
        logger.error(f"LGS: Error getting pedagogical state: {str(e)}", exc_info=True)
        return LGSPedagogicalState()


async def update_lgs_state(
    user_id: str,
    chat_id: str,
    state: LGSPedagogicalState
) -> bool:
    """
    Update LGS pedagogical state for a chat session.
    
    Args:
        user_id: User ID
        chat_id: Chat ID
        state: LGSPedagogicalState to save
        
    Returns:
        True if successful
    """
    try:
        db = get_database()
        if db is None:
            return False
        
        await db.lgs_states.update_one(
            {
                "user_id": user_id,
                "chat_id": chat_id
            },
            {
                "$set": {
                    "state": state.to_dict(),
                    "updated_at": datetime.utcnow()
                }
            },
            upsert=True
        )
        
        logger.debug(f"LGS: Updated pedagogical state for chat {chat_id[:8]}...")
        return True
        
    except Exception as e:
        logger.error(f"LGS: Error updating pedagogical state: {str(e)}", exc_info=True)
        return False
