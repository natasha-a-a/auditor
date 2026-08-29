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
        issues.append("Missing h1 or h2 headings for content structure")

    # Duplicate content (simple check)
    paragraphs = [p.get_text().strip() for p in soup.find_all("p") if p.get_text().strip()]
    unique_paragraphs = set(paragraphs)
    checks["duplicate_content"] = {"status": "Good" if len(paragraphs) == len(unique_paragraphs) else "Needs improvement", "issue": "Potential duplicate content"}
    if len(paragraphs) != len(unique_paragraphs):
        score -= 10
        issues.append("Potential duplicate content detected")

    # Readability (simple check: paragraph length)
    long_paragraphs = [p for p in paragraphs if len(p.split()) > 150]
    checks["readability"] = {"status": "Good" if not long_paragraphs else "Needs improvement", "issue": f"{len(long_paragraphs)} long paragraphs (>150 words)"}
    if long_paragraphs:
        score -= 5
        issues.append(f"{len(long_paragraphs)} paragraphs are too long (>150 words)")

    return {"score": max(0, score), "issues": issues, "checks": checks}

def ux_audit(crawl_result):
    soup = BeautifulSoup(crawl_result["html"], 'html.parser')
    score = 100
    issues = []
    checks = {}

    # Page purpose (h1 or title)
    has_h1 = bool(soup.find("h1"))
    has_title = bool(soup.title)
    checks["page_purpose"] = {"status": "Good" if has_h1 or has_title else "Needs improvement", "issue": "No clear h1 or title"}
    if not has_h1 and not has_title:
        score -= 20
        issues.append("No clear page purpose (missing h1 and title)")

    # Navigation clarity (nav tag or menu-like structure)
    has_nav = bool(soup.find("nav") or soup.find(class_=re.compile("menu|nav", re.I)))
    checks["navigation_clarity"] = {"status": "Good" if has_nav else "Needs improvement", "issue": "No clear navigation structure"}
    if not has_nav:
        score -= 15
        issues.append("Navigation structure is unclear or missing")

    # Hierarchy (heading levels)
    headings = {f"h{i}": len(soup.find_all(f"h{i}")) for i in range(1, 7)}
    checks["hierarchy"] = {"status": "Good" if headings["h1"] and headings["h2"] and headings["h1"] <= headings["h2"] else "Needs improvement", "issue": "Heading hierarchy is unclear"}
    if not headings["h1"] or not headings["h2"] or headings["h1"] > headings["h2"]:
        score -= 10
        issues.append("Heading hierarchy is unclear")

    # Content grouping (sections, divs with classes)
    sections = soup.find_all(["section", "div"], class_=True)
    checks["content_grouping"] = {"status": "Good" if len(sections) > 2 else "Needs improvement", "issue": "Few content sections"}
    if len(sections) < 3:
        score -= 5
        issues.append("Content grouping could be improved (few sections)")

    # Terminology (check for jargon if industry_keyword is provided)
    # This is a placeholder - you can expand with a dictionary of industry terms
    checks["terminology"] = {"status": "Good", "issue": None}

    # Breadcrumbs
    has_breadcrumbs = bool(soup.find(class_=re.compile("breadcrumb", re.I)) or soup.find(id=re.compile("breadcrumb", re.I)))
    checks["breadcrumbs"] = {"status": "Good" if has_breadcrumbs else "Not applicable", "issue": "No breadcrumbs (may not be needed)"}

    return {"score": max(0, score), "issues": issues, "checks": checks}

def get_competitor_benchmarks(url, industry_keyword, cache):
    """Retrieve competitor benchmarks from cache or use industry fallbacks."""
    domain = urlparse(url).netloc
    competitors = []

    # Try to find cached competitor data for the same industry
    for cached_domain, cached_data in cache.items():
        if cached_domain != domain and cached_data.get("industry_keyword") == industry_keyword:
            competitors.append(cached_data)

    if competitors:
        # Calculate average scores from competitors
        avg_scores = {
            "technical": sum(c["technical"]["score"] for c in competitors) / len(competitors),
            "seo": sum(c["seo"]["score"] for c in competitors) / len(competitors),
            "content": sum(c["content"]["score"] for c in competitors) / len(competitors),
            "ux": sum(c["ux"]["score"] for c in competitors) / len(competitors)
        }
        return avg_scores
    else:
        # Fall back to industry benchmarks
        industry = industry_keyword.lower() if industry_keyword else "default"
        return INDUSTRY_BENCHMARKS.get(industry, INDUSTRY_BENCHMARKS["default"])

# --- Main App ---
def main():
    st.set_page_config(page_title="Website Audit Tool", layout="wide")
    st.title("🌐 Comprehensive Website Audit Tool")
    st.markdown("""
    Enter a **website URL** or upload a **CSV file** (columns: `website_url`, `industry_keyword`, `country`).
    The tool will audit the site and compare it against **competitors** or **industry benchmarks**.
    """)

    # Inputs
    col1, col2 = st.columns(2)
    with col1:
        website_url = st.text_input("Website URL (e.g., https://amarell-thermometer.de/)", key="url_input")
        industry_keyword = st.text_input("Industry Keyword (e.g., manufacturing, retail)", key="industry")
    with col2:
        csv_file = st.file_uploader("Upload CSV for bulk audits", type=["csv"])
        country = st.text_input("Country (optional)", key="country")

    if st.button("🚀 Run Comprehensive Audit"):
        # Load or initialize cache
        cache = load_cache()
        urls = []

        # Process input
        if website_url:
            urls.append(normalize_url(website_url))
        if csv_file:
            df = pd.read_csv(csv_file)
            urls.extend(df["website_url"].apply(normalize_url).tolist())
            # Use the first row's industry_keyword if not provided
            if not industry_keyword and "industry_keyword" in df.columns:
                industry_keyword = df["industry_keyword"].iloc[0] if not df["industry_keyword"].empty else None

        if not urls:
            st.error("❌ Please provide a URL or CSV file.")
            return

        if not industry_keyword:
            st.warning("⚠️ No industry keyword provided. Using 'default' benchmarks.")
            industry_keyword = "default"

        # Process each URL
        results = []
        for url in urls:
            domain_key = urlparse(url).netloc
            if domain_key in cache:
                st.info(f"✅ Using cached data for {url}")
                results.append({**cache[domain_key], "industry_keyword": industry_keyword})
                continue

            st.info(f"🔍 Auditing {url}...")
            crawl_result = crawl_page(url)
            if not crawl_result["html"]:
                st.warning(f"⚠️ Skipping {url} (crawl failed)")
                continue

            # Run all audits
            tech_audit = technical_audit(crawl_result)
            seo_audit_result = seo_audit(crawl_result, industry_keyword)
            content_audit_result = content_audit(crawl_result, industry_keyword)
            ux_audit_result = ux_audit(crawl_result)

            # Get benchmarks
            benchmarks = get_competitor_benchmarks(url, industry_keyword, cache)

            # Combine results
            result = {
                "url": url,
                "audit_date": datetime.now().strftime("%Y-%m-%d"),
                "industry_keyword": industry_keyword,
                "country": country,
                "crawl": crawl_result,
                "technical": tech_audit,
                "seo": seo_audit_result,
                "content": content_audit_result,
                "ux": ux_audit_result,
                "benchmarks": benchmarks
            }
            results.append(result)
            cache[domain_key] = result  # Update cache

        # Save cache
        save_cache(cache)

        if not results:
            st.error("❌ No valid results to display.")
            return

        # --- Generate CSV ---
        csv_data = []
        for result in results:
            url = result["url"]
            audit_date = result["audit_date"]
            benchmarks = result["benchmarks"]

            # Technical checks
            for check_name, check_data in result["technical"]["checks"].items():
                csv_data.append({
                    "page_url": url,
                    "audit_date": audit_date,
                    "audit_type": "Technical",
                    "section": "Performance & Security",
                    "check": check_name.replace("_", " ").title(),
                    "status": check_data["status"],
                    "what_i_found": check_data["issue"] or "No issues",
                    "why_it_matters": "Critical for security and performance" if check_data["status"] == "Critical" else "Improves technical robustness",
                    "recommendation": "Fix immediately" if check_data["status"] == "Critical" else "Review and improve",
                    "priority": check_data["status"],
                    "score": result["technical"]["score"],
                    "benchmark": benchmarks["technical"],
                    "vs_benchmark": "Above" if result["technical"]["score"] > benchmarks["technical"] else "Below"
                })

            # SEO checks
            for check_name, check_data in result["seo"]["checks"].items():
                csv_data.append({
                    "page_url": url,
                    "audit_date": audit_date,
                    "audit_type": "SEO",
                    "section": "Search Engine Optimization",
                    "check": check_name.replace("_", " ").title(),
                    "status": check_data["status"],
                    "what_i_found": check_data["issue"] or "No issues",
                    "why_it_matters": "Critical for search rankings" if check_data["status"] == "Critical" else "Improves visibility",
                    "recommendation": "Optimize for search engines",
                    "priority": check_data["status"],
                    "score": result["seo"]["score"],
                    "benchmark": benchmarks["seo"],
                    "vs_benchmark": "Above" if result["seo"]["score"] > benchmarks["seo"] else "Below"
                })

            # Content checks
            for check_name, check_data in result["content"]["checks"].items():
                csv_data.append({
                    "page_url": url,
                    "audit_date": audit_date,
                    "audit_type": "Content",
                    "section": "Content Quality",
                    "check": check_name.replace("_", " ").title(),
                    "status": check_data["status"],
                    "what_i_found": check_data["issue"] or "No issues",
                    "why_it_matters": "Critical for user engagement" if check_data["status"] == "Critical" else "Improves readability",
                    "recommendation": "Improve content structure and quality",
                    "priority": check_data["status"],
                    "score": result["content"]["score"],
                    "benchmark": benchmarks["content"],
                    "vs_benchmark": "Above" if result["content"]["score"] > benchmarks["content"] else "Below"
                })

            # UX checks
            for check_name, check_data in result["ux"]["checks"].items():
                csv_data.append({
                    "page_url": url,
                    "audit_date": audit_date,
                    "audit_type": "UX",
                    "section": "User Experience",
                    "check": check_name.replace("_", " ").title(),
                    "status": check_data["status"],
                    "what_i_found": check_data["issue"] or "No issues",
                    "why_it_matters": "Critical for user satisfaction" if check_data["status"] == "Critical" else "Improves usability",
                    "recommendation": "Enhance user experience design",
                    "priority": check_data["status"],
                    "score": result["ux"]["score"],
                    "benchmark": benchmarks["ux"],
                    "vs_benchmark": "Above" if result["ux"]["score"] > benchmarks["ux"] else "Below"
                })

        # Display and download CSV
        if csv_data:
            df = pd.DataFrame(csv_data)
            st.subheader("📊 Audit Results (CSV)")
            st.dataframe(df)
            csv = df.to_csv(index=False)
            st.download_button(
                label="📥 Download Full Audit CSV",
                data=csv,
                file_name="comprehensive_website_audit.csv",
                mime="text/csv"
            )
        else:
            st.warning("No data to generate CSV.")

        # --- Human-Friendly Scorecard ---
        st.subheader("🏆 Human-Friendly Scorecard")
        for result in results:
            st.markdown(f"### {result['url']}")
            st.markdown(f"**Industry:** {result['industry_keyword']} | **Date:** {result['audit_date']}")

            # Overall scores
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("🔧 Technical Score", f"{result['technical']['score']}/100",
                         delta=f"{result['technical']['score'] - result['benchmarks']['technical']:+d}",
                         delta_color="normal")
                if result["technical"]["issues"]:
                    with st.expander("⚠️ Technical Issues"):
                        for issue in result["technical"]["issues"]:
                            st.write(f"- {issue}")
            with col2:
                st.metric("🔍 SEO Score", f"{result['seo']['score']}/100",
                         delta=f"{result['seo']['score'] - result['benchmarks']['seo']:+d}",
                         delta_color="normal")
                if result["seo"]["issues"]:
                    with st.expander("⚠️ SEO Issues"):
                        for issue in result["seo"]["issues"]:
                            st.write(f"- {issue}")
            with col3:
                st.metric("📝 Content Score", f"{result['content']['score']}/100",
                         delta=f"{result['content']['score'] - result['benchmarks']['content']:+d}",
                         delta_color="normal")
                if result["content"]["issues"]:
                    with st.expander("⚠️ Content Issues"):
                        for issue in result["content"]["issues"]:
                            st.write(f"- {issue}")
            with col4:
                st.metric("🎨 UX Score", f"{result['ux']['score']}/100",
                         delta=f"{result['ux']['score'] - result['benchmarks']['ux']:+d}",
                         delta_color="normal")
                if result["ux"]["issues"]:
                    with st.expander("⚠️ UX Issues"):
                        for issue in result["ux"]["issues"]:
                            st.write(f"- {issue}")

            # Benchmark comparison
            st.markdown("#### 📈 Benchmark Comparison")
            benchmark_df = pd.DataFrame({
                "Category": ["Technical", "SEO", "Content", "UX"],
                "Your Score": [
                    result["technical"]["score"],
                    result["seo"]["score"],
                    result["content"]["score"],
                    result["ux"]["score"]
                ],
                "Benchmark": [
                    result["benchmarks"]["technical"],
                    result["benchmarks"]["seo"],
                    result["benchmarks"]["content"],
                    result["benchmarks"]["ux"]
                ]
            })
            st.dataframe(benchmark_df, hide_index=True)

            # Competitor/Industry note
            if "competitor" in str(result.get("benchmarks", {})):
                st.success("✅ Benchmarks based on **competitor data** for your industry.")
            else:
                st.info("ℹ️ Benchmarks based on **industry standards** (no competitor data found).")

            st.markdown("---")

if __name__ == "__main__":
    main()