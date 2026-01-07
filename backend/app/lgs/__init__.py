# LGS Adaptive Expert Teacher Module
"""
LGS Karekok Module - LGS math tutor (always active).

Usage:
    from app.lgs import handle
    
    result = await handle(user_id, chat_id, request_id)
"""

from app.lgs.entry import handle, prepare_lgs_turn, finalize_lgs_turn

__all__ = ["handle", "prepare_lgs_turn", "finalize_lgs_turn"]
