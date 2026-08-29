import streamlit as st
import requests
from bs4 import BeautifulSoup
import pandas as pd
import json
import sqlite3
import time
import logging
from pathlib import Path
from datetime import datetime, timedelta
import re
from urllib.parse import urlparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from firecrawl import FirecrawlApp
import whois

# --- Setup Logging ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("auditor_app.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# --- Constants ---
CACHE_DIR = Path("audit_cache")
WHOIS_CACHE_DIR = Path("whois_cache")
CACHE_CLEANUP_DAYS = 90
BATCH_SIZE = 10
WHOIS_RETRIES = 2

# Ensure directories exist
for directory in [CACHE_DIR, WHOIS_CACHE_DIR]:
    directory.mkdir(exist_ok=True)

# SQLite database files
DB_FILE = CACHE_DIR / "audit_cache.db"
WHOIS_DB_FILE = WHOIS_CACHE_DIR / "whois_cache.db"

# Initialize databases
def init_db():
    for db_file in [DB_FILE, WHOIS_DB_FILE]:
        if not db_file.exists():
            conn = sqlite3.connect(str(db_file))
            cursor = conn.cursor()
            if db_file == DB_FILE:
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS audits (
                        domain TEXT PRIMARY KEY,
                        data TEXT,
                        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                """)
            elif db_file == WHOIS_DB_FILE:
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS whois (
                        domain TEXT PRIMARY KEY,
                        expiration_date TEXT,
                        expiring_soon BOOLEAN,
                        days_until_expiry INTEGER,
                        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                """)
            conn.commit()
            conn.close()

init_db()

# Score deductions
SCORE_DEDUCTIONS = {
    # Technical
    "ssl_invalid": 30,
    "slow_load_time": 10,
    "mobile_unfriendly": 10,
    "flash_elements": 15,
    "broken_links": 5,
    "outdated_plugins": 10,
    "missing_structured_data": 5,
    "missing_security_headers": 10,  # <-- Missing key causing the error

    # Business Info
    "no_products": 20,
    "no_company_info": 15,
    "no_certifications": 15,
    "no_testimonials": 10,
    "outdated_copyright": 5,

    # Functional
    "no_contact_form": 10,
    "no_rfq": 15,
    "no_ecommerce": 10,
    "no_blog": 5,

    # SEO/Visibility
    "no_analytics": 10,
    "no_local_seo": 10,
    "missing_meta_title": 10,      # <-- Used in seo_visibility_audit
    "missing_meta_description": 10, # <-- Used in seo_visibility_audit
    "missing_alt_text": 5,          # <-- Used in seo_visibility_audit
    "deep_url_structure": 5,        # <-- Used in seo_visibility_audit
    "few_internal_links": 5,       # <-- Used in seo_visibility_audit

    # Budget Red Flags
    "no_physical_address": 10,
    "no_employee_photos": 5,
    "no_online_payments": 10,
    "generic_email": 5,
    "diy_website": 10,
    "no_updates": 10,

    # Dead End
    "domain_expiring": 25,
    "parked_domain": 30,
}

# Thresholds
LOAD_TIME_THRESHOLD = 3.0
MIN_CONTENT_WORDS = 300
MAX_URL_DEPTH = 3
MIN_INTERNAL_LINKS = 5
MAX_PARAGRAPH_LENGTH = 150
COPYRIGHT_YEAR_THRESHOLD = 2

# Industry benchmarks
INDUSTRY_BENCHMARKS = {
    "E-commerce": {"technical": 85, "seo": 80, "content": 75, "ux": 90, "business": 85, "functional": 90},
    "Manufacturing": {"technical": 70, "seo": 60, "content": 65, "ux": 60, "business": 70, "functional": 65},
    "Retail": {"technical": 80, "seo": 85, "content": 80, "ux": 85, "business": 80, "functional": 85},
    "Technology": {"technical": 95, "seo": 90, "content": 90, "ux": 90, "business": 85, "functional": 90},
    "Healthcare": {"technical": 75, "seo": 70, "content": 85, "ux": 80, "business": 90, "functional": 75},
    "Education": {"technical": 70, "seo": 75, "content": 90, "ux": 75, "business": 80, "functional": 80},
    "Finance": {"technical": 90, "seo": 75, "content": 80, "ux": 85, "business": 85, "functional": 90},
    "Travel": {"technical": 85, "seo": 85, "content": 80, "ux": 90, "business": 75, "functional": 80},
    "Food & Beverage": {"technical": 75, "seo": 70, "content": 80, "ux": 80, "business": 70, "functional": 75},
    "Automotive": {"technical": 80, "seo": 75, "content": 70, "ux": 75, "business": 80, "functional": 85},
    "Real Estate": {"technical": 75, "seo": 80, "content": 75, "ux": 85, "business": 85, "functional": 70},
    "Fashion": {"technical": 80, "seo": 85, "content": 85, "ux": 90, "business": 75, "functional": 80},
    "Other": {"technical": 70, "seo": 65, "content": 70, "ux": 65, "business": 60, "functional": 60}
}

# Competitor lists
COMPETITOR_LISTS = {
    "E-commerce": ["https://www.amazon.com", "https://www.ebay.com", "https://www.etsy.com", "https://www.shopify.com", "https://www.walmart.com"],
    "Manufacturing": ["https://www.3m.com", "https://www.ge.com", "https://www.siemens.com", "https://www.honeywell.com", "https://www.bosch.com"],
    "Retail": ["https://www.target.com", "https://www.bestbuy.com", "https://www.ikea.com", "https://www.homedepot.com", "https://www.lowes.com"],
    "Technology": ["https://www.microsoft.com", "https://www.apple.com", "https://www.google.com", "https://www.ibm.com", "https://www.oracle.com"],
    "Healthcare": ["https://www.unitedhealthgroup.com", "https://www.kaiserpermanente.org", "https://www.cvshealth.com", "https://www.tenethealth.com", "https://www.hcahealthcare.com"],
    "Education": ["https://www.coursera.org", "https://www.udemy.com", "https://www.khanacademy.org", "https://www.edx.org", "https://www.linkedin.com/learning"],
    "Finance": ["https://www.chase.com", "https://www.bankofamerica.com", "https://www.wellsfargo.com", "https://www.citigroup.com", "https://www.goldmansachs.com"],
    "Travel": ["https://www.booking.com", "https://www.expedia.com", "https://www.airbnb.com", "https://www.tripadvisor.com", "https://www.kayak.com"],
    "Food & Beverage": ["https://www.mcdonalds.com", "https://www.starbucks.com", "https://www.chipotle.com", "https://www.papajohns.com", "https://www.dominos.com"],
    "Automotive": ["https://www.toyota.com", "https://www.ford.com", "https://www.honda.com", "https://www.gm.com", "https://www.tesla.com"],
    "Real Estate": ["https://www.zillow.com", "https://www.realtor.com", "https://www.redfin.com", "https://www.trulia.com", "https://www.remax.com"],
    "Fashion": ["https://www.zara.com", "https://www.hm.com", "https://www.gucci.com", "https://www.louisvuitton.com", "https://www.chanel.com"]
}

# --- Database Helper Functions ---
def save_to_db(db_file, table, key, data):
    """Save data to SQLite database."""
    conn = sqlite3.connect(str(db_file))
    cursor = conn.cursor()
    if table == "audits":
        cursor.execute(
            "INSERT OR REPLACE INTO audits (domain, data, timestamp) VALUES (?, ?, CURRENT_TIMESTAMP)",
            (key, json.dumps(data))
        )
    elif table == "whois":
        cursor.execute(
            "INSERT OR REPLACE INTO whois (domain, expiration_date, expiring_soon, days_until_expiry, timestamp) VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)",
            (key, data.get("expiration_date", ""), data.get("expiring_soon", False), data.get("days_until_expiry", 0))
        )
    conn.commit()
    conn.close()

def load_from_db(db_file, table, key=None):
    """Load data from SQLite database."""
    if not db_file.exists():
        return {} if table == "audits" else None
    conn = sqlite3.connect(str(db_file))
    cursor = conn.cursor()
    try:
        if key:
            if table == "audits":
                cursor.execute("SELECT data FROM audits WHERE domain = ?", (key,))
                result = cursor.fetchone()
                return json.loads(result[0]) if result else None
        else:
            if table == "audits":
                cursor.execute("SELECT domain, data FROM audits")
                return {row[0]: json.loads(row[1]) for row in cursor.fetchall()}
    except sqlite3.OperationalError as e:
        st.error(f"Database error: {str(e)}. Run the auditor app first to create the database.")
        return {} if table == "audits" else None
    finally:
        conn.close()

def load_cache():
    """Load audit cache from SQLite."""
    return load_from_db(DB_FILE, "audits") or {}

def save_cache(cache):
    """Save audit cache to SQLite."""
    for domain, data in cache.items():
        save_to_db(DB_FILE, "audits", domain, data)

def load_whois_cache():
    """Load WHOIS cache from SQLite."""
    return load_from_db(WHOIS_DB_FILE, "whois") or {}

def save_whois_cache(cache):
    """Save WHOIS cache to SQLite."""
    for domain, data in cache.items():
        save_to_db(WHOIS_DB_FILE, "whois", domain, data)

def cleanup_old_cache_entries(days=90):
    """Remove cache entries older than `days` days."""
    cutoff_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
    deleted_counts = {}

    for db_file, table in [(DB_FILE, "audits"), (WHOIS_DB_FILE, "whois")]:
        conn = sqlite3.connect(str(db_file))
        cursor = conn.cursor()
        cursor.execute(f"DELETE FROM {table} WHERE timestamp < ?", (cutoff_date,))
        deleted_counts[table] = cursor.rowcount
        conn.commit()
        conn.close()

    total_deleted = sum(deleted_counts.values())
    logger.info(f"Cleaned up {total_deleted} cache entries older than {days} days: {deleted_counts}")
    return deleted_counts

# --- Helper Functions ---
def normalize_url(url):
    if not url:
        return ""
    url = str(url).strip()
    if not re.match(r'^https?://', url, re.IGNORECASE):
        url = f"https://{url}"
    return url

def validate_url(url):
    try:
        result = urlparse(url)
        if not all([result.scheme, result.netloc]):
            return False
        if any(x in result.netloc.lower() for x in ["localhost", "127.0.0.1", "192.168.", "10.0."]):
            return False
        return True
    except:
        return False

def get_firecrawl_app():
    try:
        api_key = st.secrets["FIRECRAWL_API_KEY"]
        if not api_key:
            raise ValueError("Firecrawl API key not configured.")
        return FirecrawlApp(api_key=api_key)
    except Exception as e:
        logger.warning(f"Firecrawl initialization failed: {str(e)}. Falling back to requests.")
        st.warning(f"Firecrawl initialization failed: {str(e)}. Falling back to requests.")
        return None

def crawl_page(url, max_retries=2):
    """Crawl a page using requests first, Firecrawl as fallback."""
    if not validate_url(url):
        logger.error(f"Invalid or unsafe URL: {url}")
        st.error(f"Invalid or unsafe URL: {url}")
        return {"url": url, "html": "", "ssl_valid": False, "status_code": None, "load_time": None, "headers": {}}

    for attempt in range(max_retries):
        try:
            response = requests.get(url, timeout=15, verify=True, headers={'User-Agent': 'Mozilla/5.0'})
            html = response.text
            ssl_valid = True
            load_time = response.elapsed.total_seconds()
            headers = dict(response.headers)
            return {
                "url": url,
                "html": html,
                "status_code": response.status_code,
                "ssl_valid": ssl_valid,
                "load_time": load_time,
                "headers": headers
            }
        except requests.exceptions.SSLError:
            logger.warning(f"SSL error for {url}")
            return {"url": url, "html": "", "ssl_valid": False, "status_code": None, "load_time": None, "headers": {}}
        except Exception as e:
            logger.warning(f"Request attempt {attempt + 1} failed for {url}: {str(e)}")
            if attempt == max_retries - 1:
                fc = get_firecrawl_app()
                if fc:
                    try:
                        scrape_result = fc.scrape_url(url, timeout=15)
                        html = scrape_result.get("markdown", "") if scrape_result else ""
                        if html:
                            return {
                                "url": url,
                                "html": html,
                                "status_code": 200,
                                "ssl_valid": True,
                                "load_time": None,
                                "headers": {}
                            }
                    except Exception as e:
                        logger.error(f"Firecrawl failed for {url}: {str(e)}")
                logger.error(f"Crawl failed for {url} after {max_retries} attempts: {str(e)}")
                st.error(f"Crawl failed for {url} after {max_retries} attempts: {str(e)}")
                return {"url": url, "html": "", "ssl_valid": False, "status_code": None, "load_time": None, "headers": {}}
            continue
    return {"url": url, "html": "", "ssl_valid": False, "status_code": None, "load_time": None, "headers": {}}

def check_domain_expiration(url, whois_cache):
    """Check if domain is expiring soon (cached with retries)."""
    domain = urlparse(url).netloc
    if domain in whois_cache:
        return whois_cache[domain].get("expiring_soon", False)

    for attempt in range(WHOIS_RETRIES):
        try:
            w = whois.whois(domain)
            if isinstance(w.expiration_date, list):
                expiration_date = w.expiration_date[0]
            else:
                expiration_date = w.expiration_date

            if expiration_date:
                days_until_expiry = (expiration_date - datetime.now()).days
                expiring_soon = days_until_expiry < 30
                whois_cache[domain] = {
                    "expiration_date": expiration_date.isoformat(),
                    "expiring_soon": expiring_soon,
                    "days_until_expiry": days_until_expiry
                }
                save_whois_cache(whois_cache)
                return expiring_soon
            return False
        except Exception as e:
            logger.warning(f"WHOIS attempt {attempt + 1} failed for {domain}: {str(e)}")
            if attempt == WHOIS_RETRIES - 1:
                logger.error(f"WHOIS lookup failed for {domain} after {WHOIS_RETRIES} attempts")
                whois_cache[domain] = {"expiring_soon": False, "error": str(e)}
                save_whois_cache(whois_cache)
                return False
            time.sleep(1)
    return False

def is_parked_domain(url):
    """Check if domain is parked (basic heuristics)."""
    try:
        response = requests.get(url, timeout=5)
        soup = BeautifulSoup(response.text, 'html.parser')
        parked_indicators = [
            "this domain is for sale", "parked free", "domain parking",
            "under construction", "coming soon", "placeholder", "default webpage",
            "godaddy", "sedo", "namecheap parking"
        ]
        text = soup.get_text().lower()
        return any(indicator in text for indicator in parked_indicators)
    except Exception as e:
        logger.warning(f"Parked domain check failed for {url}: {str(e)}")
        return False

def crawl_competitors_parallel(competitor_urls, max_workers=3, progress_bar=None):
    """Crawl multiple competitor URLs in parallel."""
    results = {}
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_url = {executor.submit(crawl_page, url): url for url in competitor_urls}
        for i, future in enumerate(as_completed(future_to_url)):
            url = future_to_url[future]
            try:
                results[url] = future.result()
            except Exception as e:
                logger.error(f"Failed to crawl {url}: {str(e)}")
                st.warning(f"Failed to crawl {url}: {str(e)}")
                results[url] = {"url": url, "html": "", "ssl_valid": False, "status_code": None, "load_time": None, "headers": {}}
            if progress_bar:
                progress_bar.progress((i + 1) / len(future_to_url))
    return results

def fetch_competitors(industry_keyword):
    """Return predefined competitors for the selected industry."""
    return COMPETITOR_LISTS.get(industry_keyword, [])

def process_batch(urls, cache, whois_cache, industry_keyword, progress_bar, status_text, batch_num, total_batches):
    """Process a batch of URLs."""
    results = []
    for i, url in enumerate(urls):
        status_text.text(f"Processing batch {batch_num}/{total_batches} - URL {i+1}/{len(urls)}: {url}")
        progress_bar.progress((batch_num - 1 + (i + 1) / len(urls)) / total_batches)

        domain_key = urlparse(url).netloc
        if domain_key in cache:
            st.info(f"Using cached data for {url}")
            results.append({**cache[domain_key], "industry_keyword": industry_keyword})
            continue

        st.info(f"Auditing {url}...")
        crawl_result = crawl_page(url)
        if not crawl_result["html"]:
            st.warning(f"Skipping {url} (crawl failed)")
            continue

        tech_audit = technical_audit(crawl_result)
        business_audit = business_info_audit(crawl_result, url)
        functional_audit = functional_gaps_audit(crawl_result, url)
        seo_audit_result = seo_visibility_audit(crawl_result, url)
        budget_audit = budget_red_flags_audit(crawl_result, url)
        dead_end = dead_end_detection(url, crawl_result, whois_cache)
        growth_audit = growth_signals_audit(crawl_result, url)

        benchmarks = get_competitor_benchmarks(url, industry_keyword, cache, whois_cache)

        result = {
            "url": url,
            "audit_date": datetime.now().strftime("%Y-%m-%d"),
            "industry_keyword": industry_keyword,
            "crawl": crawl_result,
            "technical": tech_audit,
            "business": business_audit,
            "functional": functional_audit,
            "seo": seo_audit_result,
            "budget": budget_audit,
            "dead_end": dead_end,
            "growth": growth_audit,
            "benchmarks": benchmarks
        }
        results.append(result)
        cache[domain_key] = result
    return results

# --- Audit Functions ---
def technical_audit(crawl_result):
    if not crawl_result["html"]:
        return {"score": 0, "issues": ["No HTML content"], "checks": {}}
    soup = BeautifulSoup(crawl_result["html"], 'html.parser')
    score = 100
    issues = []
    checks = {}

    # SSL/TLS
    ssl_status = "Good" if crawl_result["ssl_valid"] else "Critical"
    checks["ssl_tls"] = {"status": ssl_status, "issue": "SSL invalid" if not crawl_result["ssl_valid"] else None}
    if not crawl_result["ssl_valid"]:
        score -= SCORE_DEDUCTIONS["ssl_invalid"]
        issues.append("SSL/TLS certificate is invalid or expired")

    # Load time
    load_time = crawl_result["load_time"]
    if load_time:
        load_status = "Good" if load_time < LOAD_TIME_THRESHOLD else "Needs improvement"
        checks["load_time"] = {"status": load_status, "issue": f"Load time: {load_time:.2f}s"}
        if load_time > LOAD_TIME_THRESHOLD:
            score -= SCORE_DEDUCTIONS["slow_load_time"]
            issues.append(f"Page load time is slow ({load_time:.2f}s)")

    # Mobile-friendliness
    viewport = soup.find("meta", attrs={"name": "viewport"})
    viewport_status = "Good" if viewport else "Needs improvement"
    checks["mobile_friendly"] = {"status": viewport_status, "issue": "Missing viewport meta tag"}
    if not viewport:
        score -= SCORE_DEDUCTIONS["mobile_unfriendly"]
        issues.append("Missing viewport meta tag for mobile responsiveness")

    # Flash elements
    flash_elements = soup.find_all("object", type=lambda x: x and "flash" in x.lower())
    flash_elements += soup.find_all("embed", type=lambda x: x and "flash" in x.lower())
    flash_status = "Good" if not flash_elements else "Critical"
    checks["flash_elements"] = {"status": flash_status, "issue": "Outdated Flash elements detected"}
    if flash_elements:
        score -= SCORE_DEDUCTIONS["flash_elements"]
        issues.append("Outdated Flash elements detected")

    # Outdated plugins
    outdated_plugins = soup.find_all("applet") + soup.find_all("object", type=lambda x: x and ("java" in x.lower() or "silverlight" in x.lower()))
    plugin_status = "Good" if not outdated_plugins else "Needs improvement"
    checks["outdated_plugins"] = {"status": plugin_status, "issue": "Outdated plugins detected"}
    if outdated_plugins:
        score -= SCORE_DEDUCTIONS["outdated_plugins"]
        issues.append("Outdated plugins (Java/Silverlight) detected")

    # Broken links (sample first 10)
    internal_links = [a.get("href") for a in soup.find_all("a", href=True) if a.get("href") and a.get("href").startswith(("/", "https://", "http://"))][:10]
    broken_links = []
    for link in internal_links:
        try:
            full_url = f"{crawl_result['url'].rstrip('/')}{link}" if link.startswith("/") else link
            response = requests.head(full_url, timeout=5, allow_redirects=True)
            if response.status_code >= 400:
                broken_links.append(full_url)
        except Exception:
            broken_links.append(full_url)
    broken_status = "Good" if not broken_links else "Needs improvement"
    checks["broken_links"] = {"status": broken_status, "issue": f"{len(broken_links)} broken links found"}
    if broken_links:
        score -= SCORE_DEDUCTIONS["broken_links"] * len(broken_links)
        issues.append(f"{len(broken_links)} broken links detected")

    # Structured data
    structured_data = soup.find("script", type="application/ld+json")
    structured_status = "Good" if structured_data else "Needs improvement"
    checks["structured_data"] = {"status": structured_status, "issue": "Missing structured data"}
    if not structured_data:
        score -= SCORE_DEDUCTIONS["missing_structured_data"]
        issues.append("Missing structured data (JSON-LD)")

    # HTTP headers
    security_headers = ["Strict-Transport-Security", "X-Content-Type-Options", "X-Frame-Options"]
    missing_headers = [h for h in security_headers if h not in crawl_result["headers"]]
    header_status = "Good" if not missing_headers else "Needs improvement"
    checks["security_headers"] = {"status": header_status, "issue": f"Missing security headers: {', '.join(missing_headers)}"}
    if missing_headers:
        score -= SCORE_DEDUCTIONS["missing_security_headers"]
        issues.append(f"Missing security headers: {', '.join(missing_headers)}")
    return {"score": max(0, score), "issues": issues, "checks": checks}

def business_info_audit(crawl_result, url):
    """Check for business information presentation issues."""
    if not crawl_result["html"]:
        return {"score": 100, "issues": [], "checks": {}}
    soup = BeautifulSoup(crawl_result["html"], 'html.parser')
    score = 100
    issues = []
    checks = {}

    # Products/services listed
    product_links = [a for a in soup.find_all("a") if "product" in a.get("href", "").lower() or "service" in a.get("href", "").lower()]
    product_pages = [a for a in soup.find_all("a") if re.search(r"/(products?|services?)/", a.get("href", ""), re.I)]
    has_products = bool(product_links or product_pages or soup.find(string=re.compile("our products?|our services?", re.I)))
    product_status = "Good" if has_products else "Critical"
    checks["products_services"] = {"status": product_status, "issue": "No products/services pages detected"}
    if not has_products:
        score -= SCORE_DEDUCTIONS["no_products"]
        issues.append("No products or services clearly listed")

    # Company story/team/certifications
    about_page = soup.find("a", href=lambda x: x and re.search(r"/(about|company|team|who-we-are)/", x, re.I))
    has_about = bool(about_page or soup.find(string=re.compile("about us|our story|our team|company history", re.I)))
    about_status = "Good" if has_about else "Needs improvement"
    checks["company_info"] = {"status": about_status, "issue": "No company story, team, or history detected"}
    if not has_about:
        score -= SCORE_DEDUCTIONS["no_company_info"]
        issues.append("No company story, team, or history page detected")

    # Certifications (ISO, REACH, RoHS, SDS)
    cert_keywords = ["iso 9001", "iso 14001", "reach", "rohs", "safety data sheet", "sds", "ce marking", "fda", "ul listed"]
    cert_content = soup.get_text().lower()
    has_certifications = any(keyword in cert_content for keyword in cert_keywords)
    cert_status = "Good" if has_certifications else "Needs improvement"
    checks["certifications"] = {"status": cert_status, "issue": "No certifications (ISO, REACH, RoHS, SDS) detected"}
    if not has_certifications:
        score -= SCORE_DEDUCTIONS["no_certifications"]
        issues.append("No certifications (ISO, REACH, RoHS, SDS) detected")

    # Case studies/testimonials
    testimonial_keywords = ["testimonial", "case study", "client success", "customer story"]
    has_testimonials = any(keyword in cert_content for keyword in testimonial_keywords)
    testimonial_status = "Good" if has_testimonials else "Needs improvement"
    checks["testimonials"] = {"status": testimonial_status, "issue": "No case studies or testimonials detected"}
    if not has_testimonials:
        score -= SCORE_DEDUCTIONS["no_testimonials"]
        issues.append("No case studies or testimonials detected")

    # Copyright year
    copyright_match = re.search(r'©\s*(\d{4})', soup.get_text())
    current_year = datetime.now().year
    if copyright_match:
        copyright_year = int(copyright_match.group(1))
        copyright_status = "Good" if (current_year - copyright_year) <= COPYRIGHT_YEAR_THRESHOLD else "Needs improvement"
        checks["copyright_year"] = {"status": copyright_status, "issue": f"Copyright year is {current_year - copyright_year} years outdated"}
        if (current_year - copyright_year) > COPYRIGHT_YEAR_THRESHOLD:
            score -= SCORE_DEDUCTIONS["outdated_copyright"]
            issues.append(f"Copyright year is outdated (last updated: {copyright_year})")
    else:
        checks["copyright_year"] = {"status": "Needs improvement", "issue": "No copyright year detected"}

    return {"score": max(0, score), "issues": issues, "checks": checks}

def functional_gaps_audit(crawl_result, url):
    """Check for functional gaps."""
    if not crawl_result["html"]:
        return {"score": 100, "issues": [], "checks": {}}
    soup = BeautifulSoup(crawl_result["html"], 'html.parser')
    score = 100
    issues = []
    checks = {}

    # Contact form
    contact_forms = soup.find_all("form", action=lambda x: x and ("contact" in x.lower() or "email" in x.lower()))
    contact_form_keywords = ["contact us", "get in touch", "send a message", "request information"]
    has_contact_form = bool(contact_forms or any(keyword in soup.get_text().lower() for keyword in contact_form_keywords))
    contact_status = "Good" if has_contact_form else "Needs improvement"
    checks["contact_form"] = {"status": contact_status, "issue": "No contact form detected"}
    if not has_contact_form:
        score -= SCORE_DEDUCTIONS["no_contact_form"]
        issues.append("No contact form detected")

    # RFQ system
    rfq_keywords = ["request for quote", "get a quote", "rfq", "quote request", "request pricing"]
    has_rfq = any(keyword in soup.get_text().lower() for keyword in rfq_keywords)
    rfq_status = "Good" if has_rfq else "Needs improvement"
    checks["rfq_system"] = {"status": rfq_status, "issue": "No RFQ (Request for Quote) system detected"}
    if not has_rfq:
        score -= SCORE_DEDUCTIONS["no_rfq"]
        issues.append("No RFQ (Request for Quote) system detected")

    # E-commerce
    ecommerce_keywords = ["add to cart", "buy now", "shop now", "checkout", "add to basket", "purchase"]
    has_ecommerce = any(keyword in soup.get_text().lower() for keyword in ecommerce_keywords)
    ecommerce_status = "Good" if has_ecommerce else "Needs improvement"
    checks["ecommerce"] = {"status": ecommerce_status, "issue": "No e-commerce functionality detected"}
    if not has_ecommerce:
        score -= SCORE_DEDUCTIONS["no_ecommerce"]
        issues.append("No e-commerce or online ordering detected")

    # Blog/resource section
    blog_keywords = ["blog", "news", "resources", "articles", "insights"]
    has_blog = any(keyword in soup.get_text().lower() for keyword in blog_keywords)
    blog_status = "Good" if has_blog else "Needs improvement"
    checks["blog"] = {"status": blog_status, "issue": "No blog or resource section detected"}
    if not has_blog:
        score -= SCORE_DEDUCTIONS["no_blog"]
        issues.append("No blog or resource section detected")

    return {"score": max(0, score), "issues": issues, "checks": checks}

def seo_visibility_audit(crawl_result, url):
    """Check for SEO and visibility issues."""
    if not crawl_result["html"]:
        return {"score": 100, "issues": [], "checks": {}}
    soup = BeautifulSoup(crawl_result["html"], 'html.parser')
    score = 100
    issues = []
    checks = {}

    # Meta title
    title = soup.title.string if soup.title else ""
    title_status = "Good" if title and len(title) <= 60 else "Needs improvement"
    checks["meta_title"] = {"status": title_status, "issue": "Missing or long meta title"}
    if not title or len(title) > 60:
        score -= SCORE_DEDUCTIONS["missing_meta_title"]
        issues.append("Meta title is missing or too long (>60 chars)")

    # Meta description
    meta_desc = soup.find("meta", attrs={"name": "description"})
    desc = meta_desc["content"] if meta_desc else ""
    desc_status = "Good" if desc and 50 <= len(desc) <= 160 else "Needs improvement"
    checks["meta_description"] = {"status": desc_status, "issue": "Missing or non-optimal meta description"}
    if not desc or len(desc) > 160 or len(desc) < 50:
        score -= SCORE_DEDUCTIONS["missing_meta_description"]
        issues.append("Meta description is missing or not optimal (50-160 chars)")

    # Alt text for images
    images = soup.find_all("img")
    images_without_alt = [img for img in images if not img.get("alt")]
    alt_status = "Good" if not images_without_alt else "Needs improvement"
    checks["alt_text"] = {"status": alt_status, "issue": f"{len(images_without_alt)} images missing alt text"}
    if images_without_alt:
        score -= SCORE_DEDUCTIONS["missing_alt_text"]
        issues.append(f"{len(images_without_alt)} images are missing alt text")

    # URL structure
    parsed = urlparse(crawl_result["url"])
    path_parts = [p for p in parsed.path.split('/') if p]
    url_status = "Good" if len(path_parts) <= MAX_URL_DEPTH else "Needs improvement"
    checks["url_structure"] = {"status": url_status, "issue": "URL path is too deep"}
    if len(path_parts) > MAX_URL_DEPTH:
        score -= SCORE_DEDUCTIONS["deep_url_structure"]
        issues.append(f"URL path is too deep (>{MAX_URL_DEPTH} levels)")

    # Internal links
    internal_links = [a.get("href") for a in soup.find_all("a", href=True) if a.get("href") and a.get("href").startswith(("/", "https://", "http://"))]
    link_status = "Good" if len(internal_links) >= MIN_INTERNAL_LINKS else "Needs improvement"
    checks["internal_links"] = {"status": link_status, "issue": f"Only {len(internal_links)} internal links found"}
    if len(internal_links) < MIN_INTERNAL_LINKS:
        score -= SCORE_DEDUCTIONS["few_internal_links"]
        issues.append(f"Few internal links found ({len(internal_links)})")

    # Local SEO (Google My Business)
    gmb_script = soup.find("script", src=lambda x: x and "google.com/maps" in x)
    gmb_link = soup.find("a", href=lambda x: x and "google.com/maps" in x)
    has_gmb = bool(gmb_script or gmb_link)
    gmb_status = "Good" if has_gmb else "Needs improvement"
    checks["local_seo"] = {"status": gmb_status, "issue": "No Google My Business integration detected"}
    if not has_gmb:
        score -= SCORE_DEDUCTIONS["no_local_seo"]
        issues.append("No Google My Business integration detected")

    # Analytics tools
    ga_script = soup.find("script", string=re.compile("UA-\d+|G-\w+|gtag\('config'"))
    has_analytics = bool(ga_script)
    analytics_status = "Good" if has_analytics else "Needs improvement"
    checks["analytics"] = {"status": analytics_status, "issue": "No analytics tools detected"}
    if not has_analytics:
        score -= SCORE_DEDUCTIONS["no_analytics"]
        issues.append("No analytics tools detected")

    return {"score": max(0, score), "issues": issues, "checks": checks}

def budget_red_flags_audit(crawl_result, url):
    """Check for budget red flags."""
    if not crawl_result["html"]:
        return {"score": 100, "issues": [], "checks": {}}
    soup = BeautifulSoup(crawl_result["html"], 'html.parser')
    score = 100
    issues = []
    checks = {}
    content = soup.get_text().lower()

    # Physical address
    address_pattern = re.compile(r'\d+\s[\w\s]+,\s[\w\s]+,\s[A-Z]{2}\s\d{5}')
    has_address = bool(address_pattern.search(content))
    address_status = "Good" if has_address else "Needs improvement"
    checks["physical_address"] = {"status": address_status, "issue": "No physical address detected"}
    if not has_address:
        score -= SCORE_DEDUCTIONS["no_physical_address"]
        issues.append("No physical address detected")

    # Employee photos/About Us
    about_page = soup.find("a", href=lambda x: x and re.search(r"/(about|team|employees?)/", x, re.I))
    has_about = bool(about_page)
    about_status = "Good" if has_about else "Needs improvement"
    checks["about_us"] = {"status": about_status, "issue": "No About Us or team page detected"}
    if not has_about:
        score -= SCORE_DEDUCTIONS["no_employee_photos"]
        issues.append("No About Us or team page detected")

    # Online payments
    payment_keywords = ["stripe", "paypal", "square", "checkout.com", "payment gateway"]
    has_payments = any(keyword in content for keyword in payment_keywords)
    payment_status = "Good" if has_payments else "Needs improvement"
    checks["online_payments"] = {"status": payment_status, "issue": "No online payment options detected"}
    if not has_payments:
        score -= SCORE_DEDUCTIONS["no_online_payments"]
        issues.append("No online payment options detected")

    # Generic email addresses
    email_pattern = re.compile(r'[\w\.-]+@(gmail|yahoo|hotmail|outlook|aol)\.com')
    has_generic_email = bool(email_pattern.search(content))
    email_status = "Good" if not has_generic_email else "Needs improvement"
    checks["generic_email"] = {"status": email_status, "issue": "Generic email address detected"}
    if has_generic_email:
        score -= SCORE_DEDUCTIONS["generic_email"]
        issues.append("Generic email address detected")

    # No updates
    recent_dates = re.findall(r'\b(202[3-5]|202[3-5]-\d{2})\b', content)
    has_recent_updates = bool(recent_dates)
    update_status = "Good" if has_recent_updates else "Needs improvement"
    checks["recent_updates"] = {"status": update_status, "issue": "No recent updates (2023-2025) detected"}
    if not has_recent_updates:
        score -= SCORE_DEDUCTIONS["no_updates"]
        issues.append("No recent updates detected")

    # DIY website
    diy_indicators = ["welcome to my site", "under construction", "lorem ipsum", "this is a placeholder", "default template", "just another wordpress site"]
    is_diy = any(indicator in content for indicator in diy_indicators)
    diy_status = "Good" if not is_diy else "Needs improvement"
    checks["diy_website"] = {"status": diy_status, "issue": "DIY website with placeholder content detected"}
    if is_diy:
        score -= SCORE_DEDUCTIONS["diy_website"]
        issues.append("DIY website with placeholder content detected")

    return {"score": max(0, score), "issues": issues, "checks": checks}

def dead_end_detection(url, crawl_result, whois_cache):
    """Check for dead end signals."""
    score = 100
    issues = []
    checks = {}

    # Domain expiration
    expiring_soon = check_domain_expiration(url, whois_cache)
    expiration_status = "Good" if not expiring_soon else "Critical"
    checks["domain_expiration"] = {"status": expiration_status, "issue": "Domain expiring soon"}
    if expiring_soon:
        score -= SCORE_DEDUCTIONS["domain_expiring"]
        issues.append("Domain is expiring soon")

    # Parked domain
    is_parked = is_parked_domain(url)
    parked_status = "Good" if not is_parked else "Critical"
    checks["parked_domain"] = {"status": parked_status, "issue": "Domain appears to be parked"}
    if is_parked:
        score -= SCORE_DEDUCTIONS["parked_domain"]
        issues.append("Domain appears to be parked")

    return {"score": max(0, score), "issues": issues, "checks": checks}

def growth_signals_audit(crawl_result, url):
    """Check for growth signals."""
    if not crawl_result["html"]:
        return {"score": 0, "issues": [], "checks": {}, "growth_signals": []}
    soup = BeautifulSoup(crawl_result["html"], 'html.parser')
    score = 100
    issues = []
    checks = {}
    growth_signals = []
    content = soup.get_text().lower()

    # Job postings
    job_keywords = ["careers", "jobs", "we're hiring", "join our team", "employment"]
    has_jobs = any(keyword in content for keyword in job_keywords)
    if has_jobs:
        growth_signals.append("Job postings detected")
    job_status = "Good" if has_jobs else "Needs improvement"
    checks["job_postings"] = {"status": job_status, "issue": "No job postings detected"}

    # Press releases/news
    press_keywords = ["press release", "newsroom", "media center", "latest news"]
    has_press = any(keyword in content for keyword in press_keywords)
    if has_press:
        growth_signals.append("Press releases/news detected")
    press_status = "Good" if has_press else "Needs improvement"
    checks["press_releases"] = {"status": press_status, "issue": "No press releases or news detected"}

    # Facility expansion
    expansion_keywords = ["new facility", "expanding", "grand opening", "new location"]
    has_expansion = any(keyword in content for keyword in expansion_keywords)
    if has_expansion:
        growth_signals.append("Facility expansion detected")
    expansion_status = "Good" if has_expansion else "Needs improvement"
    checks["facility_expansion"] = {"status": expansion_status, "issue": "No facility expansion detected"}

    # LinkedIn presence
    linkedin_links = [a.get("href", "") for a in soup.find_all("a") if "linkedin.com" in a.get("href", "").lower()]
    linkedin_icons = [img.get("src", "") for img in soup.find_all("img") if "linkedin" in img.get("src", "").lower() or "linkedin" in img.get("alt", "").lower()]
    has_linkedin = bool(linkedin_links or linkedin_icons)
    if has_linkedin:
        growth_signals.append("LinkedIn presence detected")
    linkedin_status = "Good" if has_linkedin else "Needs improvement"
    checks["linkedin_presence"] = {"status": linkedin_status, "issue": "No LinkedIn presence detected"}

    # Google My Business
    gmb_links = [a.get("href", "") for a in soup.find_all("a") if "google.com/maps" in a.get("href", "").lower()]
    gmb_iframes = [iframe.get("src", "") for iframe in soup.find_all("iframe") if "google.com/maps" in iframe.get("src", "").lower()]
    has_gmb = bool(gmb_links or gmb_iframes)
    if has_gmb:
        growth_signals.append("Google My Business detected")
    gmb_status = "Good" if has_gmb else "Needs improvement"
    checks["google_my_business"] = {"status": gmb_status, "issue": "No Google My Business detected"}

    return {"score": max(0, score), "issues": issues, "checks": checks, "growth_signals": growth_signals}

def get_competitor_benchmarks(url, industry_keyword, cache, whois_cache):
    """Fetch competitor benchmarks from predefined lists or fall back to industry benchmarks."""
    domain = urlparse(url).netloc
    competitors = []

    if industry_keyword != "Other":
        competitors = fetch_competitors(industry_keyword)

    uncrawled_competitors = [
        url for url in competitors
        if urlparse(url).netloc not in cache
    ]
    if uncrawled_competitors:
        st.info(f"Crawling {len(uncrawled_competitors)} competitors for {industry_keyword}...")
        progress_bar = st.progress(0)
        competitor_results = crawl_competitors_parallel(uncrawled_competitors, progress_bar=progress_bar)
        for url, crawl_result in competitor_results.items():
            if crawl_result["html"]:
                tech_audit = technical_audit(crawl_result)
                business_audit = business_info_audit(crawl_result, url)
                functional_audit = functional_gaps_audit(crawl_result, url)
                seo_audit_result = seo_visibility_audit(crawl_result, url)
                budget_audit = budget_red_flags_audit(crawl_result, url)
                dead_end = dead_end_detection(url, crawl_result, whois_cache)
                growth_audit = growth_signals_audit(crawl_result, url)

                cache[urlparse(url).netloc] = {
                    "url": url,
                    "technical": tech_audit,
                    "business": business_audit,
                    "functional": functional_audit,
                    "seo": seo_audit_result,
                    "budget": budget_audit,
                    "dead_end": dead_end,
                    "growth": growth_audit,
                    "industry_keyword": industry_keyword
                }
            else:
                st.warning(f"Could not crawl competitor: {url}")

    industry_competitors = [
        data for domain, data in cache.items()
        if data.get("industry_keyword") == industry_keyword
    ]

    if industry_competitors:
        avg_scores = {
            "technical": sum(c["technical"]["score"] for c in industry_competitors) / len(industry_competitors),
            "business": sum(c["business"]["score"] for c in industry_competitors) / len(industry_competitors),
            "functional": sum(c["functional"]["score"] for c in industry_competitors) / len(industry_competitors),
            "seo": sum(c["seo"]["score"] for c in industry_competitors) / len(industry_competitors),
            "budget": sum(c["budget"]["score"] for c in industry_competitors) / len(industry_competitors),
            "dead_end": sum(c["dead_end"]["score"] for c in industry_competitors) / len(industry_competitors),
            "growth": len([c for c in industry_competitors if c["growth"]["growth_signals"]]) / len(industry_competitors) * 100
        }
        return avg_scores
    else:
        return INDUSTRY_BENCHMARKS.get(industry_keyword, INDUSTRY_BENCHMARKS["Other"])
    
    

# --- Main App ---
def main():
    st.set_page_config(
        page_title="Paw a Peau Website Audit",
        layout="wide",
        page_icon="pawapeaufavicon.png"
    )

    # --- HEADER (Logo + Title) ---
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.image("pawapeaufavicon.png", width=64)
        st.title("Website Audit Tool")
        st.markdown("""
        1. Enter **one** of the following:
           - A **single website URL** (left)
           - **OR** a **CSV file** for bulk audits (right)
        2. Select an **industry** from the dropdown.
        3. Click **Run Audit**.
        The tool will analyze the site(s) and display a **scorecard**.
        """)

    # --- MAIN FORM (Side-by-Side) ---
    form_col1, form_col2 = st.columns(2)

    # Left column: URL + Industry
    with form_col1:
        website_url = st.text_input(
            "Enter Website URL",
            key="url_input",
            placeholder="https://example.com"
        )
        industry_options = list(INDUSTRY_BENCHMARKS.keys())
        industry_keyword = st.selectbox(
            "Select Industry",
            industry_options,
            index=len(industry_options)-1,
            key="industry_dropdown"
        )

    # Right column: CSV + Run Audit Button
    with form_col2:
        csv_file = st.file_uploader(
            "Upload CSV for bulk audits",
            type=["csv"],
            key="csv_input"
        )
        # Define the button and capture its state
        run_audit_clicked = st.button("🚀 Run Audit")

    # --- SEPARATOR ---
    st.markdown("---")

    # --- CACHE CLEANUP (Bottom Section) ---
    cache_col1, cache_col2, cache_col3 = st.columns([1, 2, 1])
    with cache_col2:
        if st.button("🧹 Clean Up Old Cache Entries"):
            deleted_counts = cleanup_old_cache_entries(CACHE_CLEANUP_DAYS)
            total_deleted = sum(deleted_counts.values())
            st.success(f"Cleaned up {total_deleted} cache entries older than {CACHE_CLEANUP_DAYS} days: {deleted_counts}")

    # --- AUDIT LOGIC (Triggered by Run Audit Button) ---
    # Check if the button was clicked
    if 'run_audit_clicked' in locals() and run_audit_clicked:
        # Load caches
        cache = load_cache()
        whois_cache = load_whois_cache()

        if website_url and csv_file:
            st.error("❌ **Error:** Please provide **either** a URL **or** a CSV file, not both.")
            st.stop()
        elif not website_url and not csv_file:
            st.error("❌ **Error:** Please provide a URL **or** a CSV file.")
            st.stop()
        else:
            urls = []
            if website_url:
                normalized_url = normalize_url(website_url)
                if not validate_url(normalized_url):
                    st.error("❌ Invalid URL. Please enter a valid website address.")
                    st.stop()
                urls.append(normalized_url)
            if csv_file:
                try:
                    df = pd.read_csv(csv_file)
                    if "website_url" not in df.columns:
                        st.error("❌ CSV must contain a 'website_url' column.")
                        st.stop()
                    urls = df["website_url"].apply(normalize_url).tolist()
                    urls = list(set(urls))
                    invalid_urls = [url for url in urls if not validate_url(url)]
                    if invalid_urls:
                        st.error(f"❌ Invalid URLs detected: {', '.join(invalid_urls)}")
                        st.stop()
                except Exception as e:
                    logger.error(f"Error reading CSV: {str(e)}")
                    st.error(f"❌ Error reading CSV: {str(e)}")
                    st.stop()

            # Process in batches
            total_urls = len(urls)
            total_batches = (total_urls + BATCH_SIZE - 1) // BATCH_SIZE
            progress_bar = st.progress(0)
            status_text = st.empty()

            all_results = []
            for batch_num in range(1, total_batches + 1):
                batch_urls = urls[(batch_num - 1) * BATCH_SIZE : batch_num * BATCH_SIZE]
                batch_results = process_batch(
                    batch_urls, cache, whois_cache, industry_keyword,
                    progress_bar, status_text, batch_num, total_batches
                )
                all_results.extend(batch_results)
                save_cache(cache)
                save_whois_cache(whois_cache)
                time.sleep(1)

            progress_bar.empty()
            status_text.empty()

            if not all_results:
                st.error("No valid results to display.")
                st.stop()

            # Display scorecard
            st.subheader("🏆 Human-Friendly Scorecard")
            for result in all_results:
                # ... (your existing scorecard display code)
                pass

            # Display scorecard
            st.subheader("🏆 Scorecard Results")
            for result in all_results:
                st.markdown(f"### {result['url']}")
                st.markdown(f"**Industry:** {result['industry_keyword']} | **Date:** {result['audit_date']}")
                pass
        
            # Overall scores
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("🔧 Technical", f"{result['technical']['score']}/100",
                         delta=f"{result['technical']['score'] - result['benchmarks'].get('technical', 70):+.0f}")
                if result["technical"]["issues"]:
                    with st.expander("⚠️ Technical Issues"):
                        for issue in result["technical"]["issues"]:
                            st.write(f"- {issue}")
            with col2:
                st.metric("🏢 Business Info", f"{result['business']['score']}/100",
                         delta=f"{result['business']['score'] - result['benchmarks'].get('business', 70):+.0f}")
                if result["business"]["issues"]:
                    with st.expander("⚠️ Business Info Issues"):
                        for issue in result["business"]["issues"]:
                            st.write(f"- {issue}")
            with col3:
                st.metric("🛠️ Functional", f"{result['functional']['score']}/100",
                         delta=f"{result['functional']['score'] - result['benchmarks'].get('functional', 70):+.0f}")
                if result["functional"]["issues"]:
                    with st.expander("⚠️ Functional Gaps"):
                        for issue in result["functional"]["issues"]:
                            st.write(f"- {issue}")

            col4, col5, col6 = st.columns(3)
            with col4:
                st.metric("🔍 SEO", f"{result['seo']['score']}/100",
                         delta=f"{result['seo']['score'] - result['benchmarks'].get('seo', 70):+.0f}")
                if result["seo"]["issues"]:
                    with st.expander("⚠️ SEO Issues"):
                        for issue in result["seo"]["issues"]:
                            st.write(f"- {issue}")
            with col5:
                st.metric("💰 Budget", f"{result['budget']['score']}/100",
                         delta=f"{result['budget']['score'] - result['benchmarks'].get('budget', 70):+.0f}")
                if result["budget"]["issues"]:
                    with st.expander("⚠️ Budget Red Flags"):
                        for issue in result["budget"]["issues"]:
                            st.write(f"- {issue}")
            with col6:
                st.metric("🚨 Dead End", f"{result['dead_end']['score']}/100",
                         delta=f"{result['dead_end']['score'] - 100:+.0f}")
                if result["dead_end"]["issues"]:
                    with st.expander("⚠️ Dead End Risks"):
                        for issue in result["dead_end"]["issues"]:
                            st.write(f"- {issue}")

            # Growth signals
            if result["growth"]["growth_signals"]:
                st.success("✅ **Growth Signals Detected:** " + ", ".join(result["growth"]["growth_signals"]))
            else:
                st.warning("⚠️ **No Growth Signals Detected**")

            # Benchmark comparison
            st.markdown("#### 📈 Benchmark Comparison")
            benchmark_data = {
                "Category": ["Technical", "Business Info", "Functional", "SEO", "Budget", "Dead End"],
                "Your Score": [
                    result["technical"]["score"],
                    result["business"]["score"],
                    result["functional"]["score"],
                    result["seo"]["score"],
                    result["budget"]["score"],
                    result["dead_end"]["score"]
                ],
                "Benchmark": [
                    result["benchmarks"].get("technical", 70),
                    result["benchmarks"].get("business", 70),
                    result["benchmarks"].get("functional", 70),
                    result["benchmarks"].get("seo", 70),
                    result["benchmarks"].get("budget", 70),
                    100
                ]
            }
            st.dataframe(pd.DataFrame(benchmark_data), hide_index=True)

            # Source of benchmarks
            competitor_count = len([
                domain for domain, data in cache.items()
                if data.get("industry_keyword") == industry_keyword
            ])
            if competitor_count > 0:
                st.success(f"✅ Benchmarks based on **{competitor_count} competitors** in your industry.")
            else:
                st.info("ℹ️ Benchmarks based on **industry standards** (no competitors crawled yet).")

            st.markdown("---")
            st.info("💡 **For detailed CSV reports and pain point shortlists, use the Dashboard App.**")
# User feedback
    st.markdown("[📧 Report an Issue](mailto:technical@pawapeau.com?subject=Audit%20Tool%20Issue&body=URL:%20%0AIssue:%20)")


if __name__ == "__main__":
    main()