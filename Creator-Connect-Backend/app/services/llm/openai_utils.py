"""
OpenAI Utility Service
======================
Centralized handling of OpenAI API interactions.
Provides a singleton client, robust error handling, and shared configuration.

This module replaces scattered OpenAI client initializations across:
- industry_standards.py
- agent_service.py
- brightdata_scraper.py
"""

from __future__ import annotations

import logging
import os
from threading import Lock
from typing import Optional

from app.config.settings import settings

# Attempt to import OpenAI client
try:
    from openai import OpenAI, AzureOpenAI
except ImportError:
    OpenAI = None
    AzureOpenAI = None

logger = logging.getLogger(__name__)

# ==============================================================================
# CONFIGURATION
# ==============================================================================

# API Configuration (OpenAI only; OpenRouter not used – optional keys read via getattr)
OPENAI_API_KEY = settings.OPENAI_API_KEY
OPENAI_MODEL = settings.OPENAI_MODEL or "gpt-4o"
OPENROUTER_API_KEY = getattr(settings, "OPENROUTER_API_KEY", None) or ""
OPENROUTER_MODEL = getattr(settings, "OPENROUTER_MODEL", None) or "openai/gpt-4o-2024-05-13"

# Singleton instance
_openai_client: Optional[OpenAI] = None
_client_lock = Lock()


# ==============================================================================
# CLIENT FACTORY
# ==============================================================================

def get_openai_client() -> Optional[OpenAI]:
    """
    Get or create a thread-safe singleton OpenAI client.
    
    Returns:
        OpenAI: Initialized client instance or None if not available/configured.
    """
    global _openai_client

    if _openai_client:
        return _openai_client

    with _client_lock:
        # Double-checked locking
        if _openai_client:
            return _openai_client
            
        if not OpenAI:
            logger.error("OpenAI library not installed. Please run `pip install openai`.")
            return None

        # 1. Try OpenRouter configuration first (if specified)
        if OPENROUTER_API_KEY:
            try:
                logger.info("Initializing OpenAI client with OpenRouter...")
                _openai_client = OpenAI(
                    base_url="https://openrouter.ai/api/v1",
                    api_key=OPENROUTER_API_KEY,
                )
                logger.debug("✅ OpenRouter client initialized.")
                return _openai_client
            except Exception as e:
                logger.error(f"❌ Failed to initialize OpenRouter client: {e}")

        # 2. Fallback to standard OpenAI configuration
        if OPENAI_API_KEY:
            try:
                logger.info("Initializing standard OpenAI client...")
                _openai_client = OpenAI(
                    api_key=OPENAI_API_KEY
                )
                logger.debug("✅ OpenAI client initialized.")
                return _openai_client
            except Exception as e:
                logger.error(f"❌ Failed to initialize OpenAI client: {e}")
        
        logger.warning("⚠️ No valid OpenAI/OpenRouter API key found.")
        return None


def get_openai_model() -> str:
    """
    Get the configured model name, prioritizing OpenRouter if configured.
    
    Returns:
        str: Model name (e.g. 'gpt-4o', 'openai/gpt-4o...')
    """
    if OPENROUTER_API_KEY:
        return OPENROUTER_MODEL
    return OPENAI_MODEL


# ==============================================================================
# UTILITY FUNCTIONS
# ==============================================================================

def is_openai_configured() -> bool:
    """Check if OpenAI services are properly configured."""
    return bool(OPENAI_API_KEY or OPENROUTER_API_KEY)
