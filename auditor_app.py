import streamlit as st
import requests
from bs4 import BeautifulSoup
import pandas as pd
import json
from pathlib import Path
from datetime import datetime
import re
from urllib.parse import urlparse

# --- Constants ---
CACHE_DIR = Path("audit_cache")
CACHE_DIR.mkdir(exist_ok=True)

# Industry benchmark fallbacks (scores out of 100)
INDUSTRY_BENCHMARKS = {
    "manufacturing": {
        "technical": 75,
        "seo": 60,
        "content": 70,
        "ux": 65
    },
    "retail": {
        "technical": 80,
        "seo": 70,
        "content": 80,
        "ux": 75
    },
    "technology": {
        "technical": 90,
        "seo": 85,
        "content": 85,
        "ux": 80
    },
    "default": {
        "technical": 70,
        "seo": 65,
        "content": 70,
        "ux": 65
    }
}

# --- Helper Functions ---
def normalize_url(url):
    url = str(url).strip()
    return re.sub(r'^http://', 'https://', url) if url.startswith(('http://', 'https://')) else f"https://{url}"

def load_cache():
    cache_file = CACHE_DIR / "audit_cache.json"
    return json.loads(cache_file.read_text()) if cache_file.exists() else {}

def save_cache(cache):
    cache_file = CACHE_DIR / "audit_cache.json"
    cache_file.write_text(json.dumps(cache, indent=2))

def crawl_page(url):
    try:
        response = requests.get(url, timeout=15, verify=True, headers={'User-Agent': 'Mozilla/5.0'})
        return {
            "url": url,
            "html": response.text,
            "status_code": response.status_code,
            "ssl_valid": True,
            "load_time": response.elapsed.total_seconds(),
            "headers": dict(response.headers)
        }
    except requests.exceptions.SSLError:
        return {"url": url, "html": "", "ssl_valid": False, "status_code": None, "load_time": None, "headers": {}}
    except Exception as e:
        st.error(f"⚠️ Crawl failed for {url}: {str(e)}")
        return {"url": url, "html": "", "ssl_valid": False, "status_code": None, "load_time": None, "headers": {}}

# --- Audit Functions ---
def technical_audit(crawl_result):
    soup = BeautifulSoup(crawl_result["html"], 'html.parser')
    score = 100
    issues = []
    checks = {}

    # SSL/TLS
    checks["ssl_tls"] = {"status": "Good" if crawl_result["ssl_valid"] else "Critical", "issue": "SSL invalid" if not crawl_result["ssl_valid"] else None}
    if not crawl_result["ssl_valid"]:
        score -= 30
        issues.append("SSL/TLS certificate is invalid or expired")

    # Load time
    load_time = crawl_result["load_time"]
    checks["load_time"] = {"status": "Good" if load_time and load_time < 3 else "Needs improvement", "issue": f"Load time: {load_time:.2f}s"}
    if load_time and load_time > 3:
        score -= 10
        issues.append(f"Page load time is slow ({load_time:.2f}s)")

    # Mobile-friendliness (viewport meta tag)
    viewport = soup.find("meta", attrs={"name": "viewport"})
    checks["mobile_friendly"] = {"status": "Good" if viewport else "Needs improvement", "issue": "Missing viewport meta tag"}
    if not viewport:
        score -= 5
        issues.append("Missing viewport meta tag for mobile responsiveness")

    # Structured data
    structured_data = soup.find("script", type="application/ld+json")
    checks["structured_data"] = {"status": "Good" if structured_data else "Needs improvement", "issue": "Missing structured data"}
    if not structured_data:
        score -= 5
        issues.append("Missing structured data (JSON-LD)")

    # HTTP headers
    security_headers = ["Strict-Transport-Security", "X-Content-Type-Options", "X-Frame-Options"]
    missing_headers = [h for h in security_headers if h not in crawl_result["headers"]]
    checks["security_headers"] = {"status": "Good" if not missing_headers else "Needs improvement", "issue": f"Missing security headers: {', '.join(missing_headers)}"}
    if missing_headers:
        score -= 10
        issues.append(f"Missing security headers: {', '.join(missing_headers)}")

    return {"score": max(0, score), "issues": issues, "checks": checks}

def seo_audit(crawl_result, industry_keyword=None):
    soup = BeautifulSoup(crawl_result["html"], 'html.parser')
    score = 100
    issues = []
    checks = {}

    # Meta title
    title = soup.title.string if soup.title else ""
    checks["meta_title"] = {"status": "Good" if title and len(title) < 60 else "Needs improvement", "issue": "Missing or long meta title"}
    if not title or len(title) > 60:
        score -= 10
        issues.append("Meta title is missing or too long (>60 chars)")

    # Meta description
    meta_desc = soup.find("meta", attrs={"name": "description"})
    desc = meta_desc["content"] if meta_desc else ""
    checks["meta_description"] = {"status": "Good" if desc and 50 < len(desc) < 160 else "Needs improvement", "issue": "Missing or non-optimal meta description"}
    if not desc or len(desc) > 160 or len(desc) < 50:
        score -= 10
        issues.append("Meta description is missing or not optimal (50-160 chars)")

    # Alt text for images
    images = soup.find_all("img")
    images_without_alt = [img for img in images if not img.get("alt")]
    checks["alt_text"] = {"status": "Good" if not images_without_alt else "Needs improvement", "issue": f"{len(images_without_alt)} images missing alt text"}
    if images_without_alt:
        score -= 5
        issues.append(f"{len(images_without_alt)} images are missing alt text")

    # URL structure
    parsed = urlparse(crawl_result["url"])
    path_parts = [p for p in parsed.path.split('/') if p]
    checks["url_structure"] = {"status": "Good" if len(path_parts) <= 3 else "Needs improvement", "issue": "URL path is too deep"}
    if len(path_parts) > 3:
        score -= 5
        issues.append("URL path is too deep (more than 3 levels)")

    # Internal links
    internal_links = [a.get("href") for a in soup.find_all("a", href=True) if a.get("href") and a.get("href").startswith(("/", "https://", "http://"))]
    checks["internal_links"] = {"status": "Good" if len(internal_links) > 5 else "Needs improvement", "issue": f"Only {len(internal_links)} internal links found"}
    if len(internal_links) < 5:
        score -= 5
        issues.append(f"Few internal links found ({len(internal_links)})")

    # Keyword in content (if industry_keyword provided)
    if industry_keyword:
        content = soup.get_text().lower()
        keyword_count = content.count(industry_keyword.lower())
        checks["keyword_usage"] = {"status": "Good" if keyword_count > 0 else "Needs improvement", "issue": f"Keyword '{industry_keyword}' not found in content"}
        if keyword_count == 0:
            score -= 10
            issues.append(f"Industry keyword '{industry_keyword}' not found in content")

    return {"score": max(0, score), "issues": issues, "checks": checks}

def content_audit(crawl_result, industry_keyword=None):
    soup = BeautifulSoup(crawl_result["html"], 'html.parser')
    score = 100
    issues = []
    checks = {}

    # Content length
    text = soup.get_text()
    word_count = len(text.split())
    checks["content_length"] = {"status": "Good" if word_count > 300 else "Needs improvement", "issue": f"Content has only {word_count} words"}
    if word_count < 300:
        score -= 15
        issues.append(f"Content is too short ({word_count} words)")

    # Headings hierarchy
    headings = {f"h{i}": soup.find_all(f"h{i}") for i in range(1, 7)}
    checks["headings_hierarchy"] = {"status": "Good" if headings["h1"] and headings["h2"] else "Needs improvement", "issue": "Missing h1 or h2 headings"}
    if not headings["h1"] or not headings["h2"]:
        score -= 10
        issues.append