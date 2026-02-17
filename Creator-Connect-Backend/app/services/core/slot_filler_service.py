from __future__ import annotations

import re
import logging
from typing import Dict, Any, List, Optional

from app.services.llm.agent_service import analyze_prompt

logger = logging.getLogger(__name__)


class InfluencerSlotFiller:
    """
    Stateful slot filler that extracts information from user queries.

    SMART DEFAULTS (if not provided):
    - Location: India
    - Followers: 1k-900k
    - Niche: Any

    INTELLIGENT DETECTION:
    - Detects Instagram profile links/usernames and skips Q&A
    - Automatically extracts and processes direct influencer searches
    - Works with partial information - no mandatory Q&A
    """

    # NO REQUIRED SLOTS - everything is optional now
    required_slots = []

    slot_questions = {
        "niche": "Which niche/campaign focus? (e.g., sports clothing, makeup, tech)",
        "location": "Which city or location should the influencer be in?",
        "followers_range": "What's the required followers range? (e.g., 50k-300k)"
    }

    # Smart defaults
    DEFAULT_LOCATION = "India"
    DEFAULT_FOLLOWERS_RANGE = "1k-900k"
    DEFAULT_NICHE = None  # Any niche
    DEFAULT_NUM_RESULTS = 500

    # Mapping from slot names to analyze_prompt extraction keys
    slot_mapping = {
        "niche": "category",
        "location": "location",
        "followers_range": "followers"
    }

    def __init__(self):
        self.filled_slots: Dict[str, Any] = {}
        # last_asked_slot helps to disambiguate answers (optional)
        self.last_asked_slot: Optional[str] = None
        # Store original messages to preserve num_results
        self.original_messages: List[str] = []

    def _parse_range(self, text: str) -> Optional[str]:
        """Parse range from text (e.g., '50k-300k' or 'under 80k')."""
        text = text.replace(" ", "").lower()
        # patterns: 50k-300k  or 50000-300000 or under 80k
        m = re.search(r"(\d+[kKmM]?)\s*-\s*(\d+[kKmM]?)", text)
        if m:
            return f"{m.group(1)}-{m.group(2)}"
        m = re.search(r"under\s*(\d+[kKmM]?)", text)
        if m:
            return f"under {m.group(1)}"
        m = re.search(r"(\d+[kKmM]?)", text)
        if m:
            return m.group(1)
        return None

    def _detect_instagram_links(self, text: str) -> Optional[List[str]]:
        """
        Detect Instagram profile links or usernames in the message.
        Supports MULTIPLE links (up to 10 profiles for batch analysis).

        Patterns detected:
        - https://instagram.com/username
        - https://www.instagram.com/username
        - instagram.com/username
        - @username
        - username (single handle) or comma/space separated handles

        Returns list of detected links/usernames or None if no match.
        Maximum 10 links to prevent abuse.
        """
        text = text.strip()
        detected_links = []

        # Pattern 1: Full Instagram URLs (supports multiple URLs in one message)
        url_pattern = r'(?:https?://)?(?:www\.)?instagram\.com/([a-zA-Z0-9._]{1,30})/?'
        url_matches = re.findall(url_pattern, text, re.IGNORECASE)
        for username in url_matches:
            link = f"https://www.instagram.com/{username}/"
            if link not in detected_links:  # Avoid duplicates
                detected_links.append(link)

        # Pattern 2: @username mentions (supports multiple @mentions)
        mention_pattern = r'@([a-zA-Z0-9._]{1,30})\b'
        mention_matches = re.findall(mention_pattern, text)
        for username in mention_matches:
            # Avoid duplicates
            link = f"https://www.instagram.com/{username}/"
            if link not in detected_links:
                detected_links.append(link)

        # Pattern 3: Single plain username (letters/numbers/._) with no other text
        # CRITICAL: For DIRECT_PROFILE mode, ONLY return single username - no multiple detection
        words = text.split()
        if len(words) == 1:
            username_pattern = r'^[a-zA-Z0-9._]{2,30}$'  # Changed to 2-30 to match requirement
            if re.match(username_pattern, words[0]):
                username = words[0].lstrip('@')
                link = f"https://www.instagram.com/{username}/"
                if link not in detected_links:
                    detected_links.append(link)
                    # CRITICAL FIX: For single username, return immediately - don't check other patterns
                    return detected_links
        elif len(words) <= 3:
            # Allow usernames with 1-2 words before/after (e.g., "check rohitasharma45" or "rohitasharma45 profile")
            # But prioritize if one word looks like a username
            username_pattern = re.compile(r'^[a-zA-Z0-9._]{2,30}$')  # Changed to 2-30
            for word in words:
                cleaned = word.strip().lstrip('@').rstrip('.,!?;:')
                if username_pattern.match(cleaned) and len(cleaned) >= 2:  # At least 2 chars
                    link = f"https://www.instagram.com/{cleaned}/"
                    if link not in detected_links:
                        detected_links.append(link)
                        # CRITICAL FIX: Only take FIRST valid username for DIRECT_PROFILE mode
                        return detected_links
                        break  # Only take first valid username if multiple words

        # Pattern 4: Comma/space separated usernames (ONLY if explicitly comma-separated, not single word)
        # Skip this pattern if we already found a single username (DIRECT_PROFILE mode)
        if not detected_links:
            tokens = [w.strip().lstrip("@") for w in re.split(r"[,\\s]+", text) if w.strip()]
            username_pattern = re.compile(r'^[a-zA-Z0-9._]{2,30}$')  # Changed to 2-30
            # Only apply if there are MULTIPLE tokens AND all are valid usernames
            if len(tokens) > 1 and all(username_pattern.match(tok) for tok in tokens):
                for username in tokens:
                    link = f"https://www.instagram.com/{username}/"
                    if link not in detected_links:
                        detected_links.append(link)

        # Limit to max 10 profiles to prevent abuse
        if len(detected_links) > 10:
            logger.warning(f"⚠️  Detected {len(detected_links)} links, limiting to 10")
            detected_links = detected_links[:10]

        # Return None if no links detected
        return detected_links if detected_links else None

    def _merge_extracted(self, extracted: Dict[str, Any]) -> None:
        """Merge extracted values from analyze_prompt into filled_slots."""
        if not extracted:
            return
        # Prefer current message extraction over existing slot state
        if extracted.get("extracted_category"):
            self.filled_slots["niche"] = extracted.get("extracted_category")
        if extracted.get("extracted_location"):
            self.filled_slots["location"] = extracted.get("extracted_location")
        if extracted.get("extracted_followers"):
            self.filled_slots["followers_range"] = extracted.get("extracted_followers")

    def _is_slot_filled(self, slot_name: str) -> bool:
        """Check if a slot has a valid non-empty value."""
        value = self.filled_slots.get(slot_name)
        if value is None:
            return False
        if isinstance(value, str):
            return value.strip() != ""  # Non-empty after stripping whitespace
        return bool(value)  # For non-string values, check if truthy
    
    def _first_missing_slot(self) -> Optional[str]:
        """Return the first missing slot in required order."""
        for s in self.required_slots:
            if not self._is_slot_filled(s):
                return s
        return None

    def process_turn(self, message: str) -> Dict[str, Any]:
        """
        Processes either the initial prompt or an answer to the last asked question.
        Returns a dict with keys described in ChatPromptResponse.

        INTELLIGENT DETECTION:
        1. First checks if message contains Instagram links/usernames
        2. If yes, returns immediately with direct link search mode
        3. Otherwise, proceeds with normal Q&A slot filling
        """
        # Store original message to preserve num_results
        self.original_messages.append(message)

        # ============================================================
        # INTELLIGENT DETECTION: Check for Instagram links FIRST
        # ============================================================
        instagram_links = self._detect_instagram_links(message)
        if instagram_links:
            logger.info(f"🔗 DETECTED INSTAGRAM LINKS: {instagram_links}")
            logger.info(f"   Bypassing Q&A flow - DIRECT_PROFILE search mode activated")
            logger.info(f"   [DIRECT_PROFILE_MODE_ACTIVATED] - Discovery disabled, SerpAPI search disabled")

            # Return immediately with special marker for direct profile search
            return {
                "complete": True,
                "filled_slots": {
                    "direct_links": instagram_links,
                    "search_mode": "DIRECT_PROFILE"  # Changed to DIRECT_PROFILE
                },
                "final_prompt": "DIRECT_PROFILE_SEARCH",  # Changed marker
                "message": f"Found {len(instagram_links)} Instagram profile(s). Analyzing...",
                "instagram_links": instagram_links
            }
        
        # ============================================================
        # DETECTION: Plain username pattern (2-30 chars, alphanumeric + ._)
        # ============================================================
        text_clean = message.strip()
        username_pattern = re.compile(r'^[a-zA-Z0-9._]{2,30}$')
        if username_pattern.match(text_clean):
            logger.info(f"🔗 DETECTED PLAIN USERNAME: {text_clean}")
            logger.info(f"   [DIRECT_PROFILE_MODE_ACTIVATED] - Discovery disabled, SerpAPI search disabled")
            
            instagram_link = f"https://www.instagram.com/{text_clean}/"
            return {
                "complete": True,
                "filled_slots": {
                    "direct_links": [instagram_link],
                    "search_mode": "DIRECT_PROFILE"
                },
                "final_prompt": "DIRECT_PROFILE_SEARCH",
                "message": f"Analyzing @{text_clean}...",
                "instagram_links": [instagram_link]
            }

        # ============================================================
        # NORMAL Q&A FLOW: No Instagram links detected
        # ============================================================
        # ALWAYS try to analyze the message to extract any information
        # This ensures we can handle both complete prompts and partial answers intelligently
        try:
            validation = analyze_prompt(message)
            logger.info(f"Analyzed message: {message[:100]}")
            logger.info(f"Extracted - category: {validation.get('extracted_category')}, location: {validation.get('extracted_location')}, followers: {validation.get('extracted_followers')}")
        except Exception as e:
            logger.error(f"Error analyzing prompt: {e}")
            validation = {"is_valid": False}
        
        # Extract num_results from message if present - enhanced pattern
        num_match = re.search(r'(?:top|find|get|show|list|give\s+me)\s*(\d+)|(\d+)\s*(?:influencers?|results?|creators?)', message.lower())
        if num_match:
            num_value = num_match.group(1) or num_match.group(2)
            self.filled_slots['num_results'] = int(num_value)
            logger.info(f"Extracted num_results from message: {self.filled_slots['num_results']}")

        # Merge any extracted information
        self._merge_extracted(validation)

        # If we still have a missing slot and user gave a simple answer (no extracted info),
        # treat the message as a direct answer to the last asked question
        if self.last_asked_slot and not validation.get(f"extracted_{self.slot_mapping.get(self.last_asked_slot, '')}"):
            current_missing = self._first_missing_slot()
            if current_missing and not self._is_slot_filled(current_missing):
                answer = message.strip()
                if answer:
                    if current_missing == "followers_range":
                        parsed = self._parse_range(message)
                        self.filled_slots[current_missing] = parsed or answer
                    elif current_missing not in self.filled_slots:
                        # Only fill if not already filled by analyze_prompt
                        self.filled_slots[current_missing] = answer
                    logger.info(f"Directly filled slot '{current_missing}' with value: {self.filled_slots.get(current_missing)}")

        # ============================================================
        # NO MORE MANDATORY Q&A - ALWAYS COMPLETE WITH SMART DEFAULTS
        # ============================================================
        # Apply smart defaults for missing values
        niche = self.filled_slots.get('niche', self.DEFAULT_NICHE)
        location = self.filled_slots.get('location', self.DEFAULT_LOCATION)
        followers = self.filled_slots.get('followers_range', self.DEFAULT_FOLLOWERS_RANGE)
        num_results = self.filled_slots.get('num_results')

        logger.info(f"Search parameters (with defaults applied):")
        logger.info(f"   • Niche: {niche or 'Any'}")
        logger.info(f"   • Location: {location}")
        logger.info(f"   • Followers: {followers}")
        logger.info(f"   • Num results: {num_results or 'Default'}")

        # Build a natural language prompt
        prompt_parts = []

        # Include "top X" if num_results was extracted or use default
        prompt_parts.append(f"top {num_results or self.DEFAULT_NUM_RESULTS}")

        if niche:
            prompt_parts.append(f"{niche} influencer")
        else:
            prompt_parts.append("influencer")

        if location:
            prompt_parts.append(f"in {location}")

        if followers:
            # Avoid duplicate "followers" word
            if "followers" in followers.lower():
                prompt_parts.append(f"with {followers}")
            else:
                prompt_parts.append(f"with {followers} followers")

        final_prompt = " ".join(prompt_parts)
        logger.info(f"Final prompt built: {final_prompt}")

        # Store defaults in filled_slots for pipeline
        if not self.filled_slots.get('location'):
            self.filled_slots['location'] = location
        if not self.filled_slots.get('followers_range'):
            self.filled_slots['followers_range'] = followers

        return {
            "complete": True,
            "filled_slots": self.filled_slots.copy(),
            "final_prompt": final_prompt,
            "message": "Searching for influencers..."
        }

    def reset(self) -> None:
        """Reset the slot filler to start a new conversation."""
        self.filled_slots = {}
        self.last_asked_slot = None
        self.original_messages = []
        logger.info("Slot filler reset for new conversation")
