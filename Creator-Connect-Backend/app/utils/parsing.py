"""
Unified Parsing Utility
=======================
Central location for all number and string parsing logic.
Replaces duplicate logic in results.py, report.py, and search_filters.py.
"""
from typing import Optional, Union

def parse_number(value: Union[str, int, float, None]) -> int:
    """
    Parse a number from various formats (int, float, shorthand string).
    Examples: 
      - 1500 -> 1500
      - "1.5k" -> 1500
      - "1.2M" -> 1200000
      - "N/A" -> 0
    """
    if value is None:
        return 0
    if isinstance(value, (int, float)):
        return int(value)
        
    value_str = str(value).upper().replace(',', '').replace('+', '').strip()
    if not value_str or value_str == "N/A" or value_str == "-":
        return 0
        
    try:
        if 'M' in value_str:
            return int(float(value_str.replace('M', '')) * 1_000_000)
        elif 'K' in value_str:
            return int(float(value_str.replace('K', '')) * 1_000)
        else:
            # Handle standard float strings "123.45" -> 123
            return int(float(value_str))
    except (ValueError, TypeError):
        return 0

def parse_percentage(value: Union[str, int, float, None]) -> float:
    """
    Parse a percentage string to a float.
    Examples:
      - "15%" -> 15.0
      - 0.15 -> 0.15
      - "N/A" -> 0.0
    """
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
        
    value_str = str(value).replace('%', '').strip()
    if not value_str or value_str.upper() == "N/A" or value_str == "-":
        return 0.0
        
    try:
        return float(value_str)
    except (ValueError, TypeError):
        return 0.0

def clean_text(text: Optional[str]) -> str:
    """Clean extra whitespace from text."""
    if not text:
        return ""
    return " ".join(str(text).split())
