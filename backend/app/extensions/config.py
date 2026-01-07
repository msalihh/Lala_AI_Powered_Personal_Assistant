"""
Extension Configuration

Central configuration for all HACE extensions.
All extensions are disabled by default.
"""

import os
from dataclasses import dataclass, field
from typing import Literal
import logging

logger = logging.getLogger(__name__)


@dataclass
class ExtensionConfig:
    """Configuration for HACE extensions. All disabled by default."""
    
    # Observability
    observability_enabled: bool = False
    observability_exporter: Literal["console", "json_file", "otlp"] = "console"
    observability_log_file: str = "logs/llm_traces.jsonl"
    
    # OCR
    ocr_enabled: bool = False
    ocr_backend: Literal["tesseract", "google_vision", "mock"] = "tesseract"
    
    # Vector Store
    vector_store_backend: Literal["chroma", "qdrant", "mock"] = "chroma"
    qdrant_url: str = "http://localhost:6333"
    qdrant_collection: str = "hace_documents"
    
    # Tool Routing
    tool_routing_enabled: bool = False
    
    # Ingestion Versioning
    ingestion_versioning_enabled: bool = False
    ingestion_version: str = "1.0"
    
    # Workflow Engine
    workflow_engine_enabled: bool = False
    default_workflow: str = "default_chat"


# Singleton instance
_config: ExtensionConfig | None = None


def get_extension_config() -> ExtensionConfig:
    """
    Get extension configuration from environment variables.
    Returns singleton instance.
    """
    global _config
    
    if _config is not None:
        return _config
    
    def _bool(key: str, default: bool = False) -> bool:
        val = os.getenv(key, str(default)).lower()
        return val in ("true", "1", "yes", "on")
    
    def _str(key: str, default: str) -> str:
        return os.getenv(key, default)
    
    _config = ExtensionConfig(
        # Observability
        observability_enabled=_bool("ENABLE_OBSERVABILITY", False),
        observability_exporter=_str("OBSERVABILITY_EXPORTER", "console"),
        observability_log_file=_str("OBSERVABILITY_LOG_FILE", "logs/llm_traces.jsonl"),
        
        # OCR
        ocr_enabled=_bool("ENABLE_OCR", False),
        ocr_backend=_str("OCR_BACKEND", "tesseract"),
        
        # Vector Store
        vector_store_backend=_str("VECTOR_STORE_BACKEND", "chroma"),
        qdrant_url=_str("QDRANT_URL", "http://localhost:6333"),
        qdrant_collection=_str("QDRANT_COLLECTION", "hace_documents"),
        
        # Tool Routing
        tool_routing_enabled=_bool("ENABLE_TOOL_ROUTING", False),
        
        # Ingestion Versioning
        ingestion_versioning_enabled=_bool("ENABLE_INGESTION_VERSIONING", False),
        ingestion_version=_str("INGESTION_VERSION", "1.0"),
        
        # Workflow Engine
        workflow_engine_enabled=_bool("ENABLE_WORKFLOW_ENGINE", False),
        default_workflow=_str("DEFAULT_WORKFLOW", "default_chat"),
    )
    
    # Log enabled extensions
    enabled = []
    if _config.observability_enabled:
        enabled.append(f"observability({_config.observability_exporter})")
    if _config.ocr_enabled:
        enabled.append(f"ocr({_config.ocr_backend})")
    if _config.vector_store_backend != "chroma":
        enabled.append(f"vector_store({_config.vector_store_backend})")
    if _config.tool_routing_enabled:
        enabled.append("tool_routing")
    if _config.ingestion_versioning_enabled:
        enabled.append("ingestion_versioning")
    if _config.workflow_engine_enabled:
        enabled.append("workflow_engine")
    
    if enabled:
        logger.info(f"[EXTENSIONS] Enabled: {', '.join(enabled)}")
    else:
        logger.info("[EXTENSIONS] All extensions disabled (default mode)")
    
    return _config


def is_observability_enabled() -> bool:
    """Quick check for observability feature."""
    return get_extension_config().observability_enabled


def is_ocr_enabled() -> bool:
    """Quick check for OCR feature."""
    return get_extension_config().ocr_enabled


def is_tool_routing_enabled() -> bool:
    """Quick check for tool routing feature."""
    return get_extension_config().tool_routing_enabled
