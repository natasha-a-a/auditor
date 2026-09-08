"""
GitHub CSV cache module for fetching and caching CSV files from GitHub.
Provides a shared cache for CSV files to reduce redundant network requests.
"""

import io
import time
import requests
import pandas as pd
from functools import lru_cache
from datetime import datetime, timedelta

# Default cache TTL in seconds (1 hour)
_DEFAULT_CACHE_TTL = 3600
_cache_ttl = _DEFAULT_CACHE_TTL

# Cache storage
_csv_cache = {}


def set_cache_ttl(seconds):
    """Set the cache TTL in seconds."""
    global _cache_ttl
    _cache_ttl = seconds


def clear_cache():
    """Clear all cached CSV data."""
    global _csv_cache
    _csv_cache = {}


def _is_cache_expired(timestamp):
    """Check if a cache entry has expired."""
    if _cache_ttl <= 0:
        return False  # Cache never expires if TTL is 0 or negative
    return (datetime.now() - timestamp).total_seconds() > _cache_ttl


def get_github_csv(csv_url, force_refresh=False):
    """
    Fetch a CSV file from GitHub with caching.
    
    Args:
        csv_url: URL of the CSV file on GitHub
        force_refresh: If True, bypass cache and fetch fresh data
    
    Returns:
        pandas.DataFrame containing the CSV data, or empty DataFrame if fetch fails
    """
    if not csv_url:
        return pd.DataFrame()
    
    # Check cache
    if not force_refresh and csv_url in _csv_cache:
        entry = _csv_cache[csv_url]
        if not _is_cache_expired(entry['timestamp']):
            return entry['data']
    
    # Fetch from GitHub
    try:
        response = requests.get(csv_url, timeout=10)
        if response.status_code == 200:
            df = pd.read_csv(io.StringIO(response.text))
            # Cache the result
            _csv_cache[csv_url] = {
                'data': df,
                'timestamp': datetime.now()
            }
            return df
    except Exception:
        pass
    
    return pd.DataFrame()
