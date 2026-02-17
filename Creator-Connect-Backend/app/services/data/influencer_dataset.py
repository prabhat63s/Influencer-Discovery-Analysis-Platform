from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Optional

import pandas as pd
import chardet

from app.utils.dataset_paths import get_dynamic_dataset_path

logger = logging.getLogger(__name__)

_dataset_lock = threading.Lock()
_DATAFRAME: Optional[pd.DataFrame] = None


def _read_dataset(path: Path) -> pd.DataFrame:
    """Read dataset with automatic encoding detection for CSV files."""
    if path.suffix.lower() in {".xls", ".xlsx"}:
        df = pd.read_excel(path)
    else:
        # Try UTF-8 first (most common)
        try:
            df = pd.read_csv(path, encoding='utf-8')
        except UnicodeDecodeError:
            # Auto-detect encoding if UTF-8 fails
            logger.info("UTF-8 decoding failed, detecting encoding for %s", path)
            with open(path, 'rb') as f:
                raw_data = f.read()
                result = chardet.detect(raw_data)
                detected_encoding = result['encoding']
                confidence = result['confidence']
                logger.info("Detected encoding: %s (confidence: %.1f%%)", detected_encoding, confidence * 100)
            
            # Read with detected encoding
            df = pd.read_csv(path, encoding=detected_encoding)
            logger.info("Successfully loaded dataset with %s encoding", detected_encoding)
    
    if df.empty:
        raise ValueError(f"Influencer dataset at {path} is empty.")
    return df


def _load_dataset() -> pd.DataFrame:
    path = get_dynamic_dataset_path()
    if not path:
        raise ValueError("INFLUENCER_DATA_PATH is not configured.")

    if not path.exists():
        raise FileNotFoundError(f"Influencer dataset not found at {path}")

    logger.info("Loading influencer dataset from %s", path)
    df = _read_dataset(path)
    logger.info("Influencer dataset loaded with %d rows and %d columns.", len(df), len(df.columns))
    return df


def get_dataset(copy: bool = True) -> pd.DataFrame:
    """
    Get the influencer dataset. Returns the dataset if loaded, otherwise attempts to load it.
    
    Raises:
        ValueError: If INFLUENCER_DATA_PATH is not configured
        FileNotFoundError: If the dataset file doesn't exist
    """
    global _DATAFRAME
    if _DATAFRAME is None:
        with _dataset_lock:
            if _DATAFRAME is None:
                try:
                    _DATAFRAME = _load_dataset()
                except ValueError as e:
                    if "not configured" in str(e):
                        logger.warning("INFLUENCER_DATA_PATH is not configured. Influencer search will not be available. Set INFLUENCER_DATA_PATH in your .env file to enable search.")
                    raise
    return _DATAFRAME.copy(deep=True) if copy else _DATAFRAME


def refresh_dataset() -> pd.DataFrame:
    global _DATAFRAME
    with _dataset_lock:
        _DATAFRAME = _load_dataset()
        return _DATAFRAME.copy(deep=True)


def load_dataset_from_path(path: Path) -> pd.DataFrame:
    """
    Load influencer dataset from a specific file path.
    This is useful for loading static databases without affecting the global dataset.
    
    Args:
        path: Path to the CSV/Excel file
        
    Returns:
        DataFrame with the loaded dataset
        
    Raises:
        FileNotFoundError: If the file doesn't exist
        ValueError: If the dataset is empty
    """
    if not path.exists():
        raise FileNotFoundError(f"Influencer dataset not found at {path}")
    
    logger.info("Loading influencer dataset from %s", path)
    df = _read_dataset(path)
    logger.info("Influencer dataset loaded with %d rows and %d columns.", len(df), len(df.columns))
    return df
