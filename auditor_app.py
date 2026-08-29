import streamlit as st
import pandas as pd
import json
from pathlib import Path
from playwright.sync_api import sync_playwright, TimeoutError
from datetime import datetime
import re

# Configure cache directory
CACHE_DIR = Path("audit_cache")
CACHE_DIR.mkdir(exist_ok=True)

# Normalize URL (force https://, trim whitespace)
def normalize_url(url):
    url = str(url).strip()
    return re.sub(r'^http://', 'https://', url) if url.startswith(('http://', 'https://')) else f"https://{url}"

# Load or create cache
def load_cache():
    cache_file = CACHE_DIR / "audit_cache.json"
    return json.loads(cache_file.read_text()) if cache_file.exists() else {}

# Save cache
def save_cache(cache):
    cache_file = CACHE_DIR / "audit_cache.json"
    cache_file.write_text(json.dumps(cache, indent=2))

# Crawl a page and return HTML + SSL status
def crawl_page(url):
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()
            # Check SSL/TLS (simplified: if page loads, SSL is valid)
            ssl_valid = True
            try:
                page.goto(url, timeout=10000)
            except Exception as e:
                ssl_valid = False
                st.warning(f"SSL/TLS or connection error for {url}: {str(e)}")
            html = page.content()
            browser.close()
            return {"url": url, "html": html, "ssl_valid": ssl_valid}
    except Exception as e:
        st.error(f"Crawl failed for {url}: {str(e)}")
        return {"url": url, "html": "", "ssl_valid": False}

# Technical audit (simplified example)
def technical_audit(html, url):
    score = 100
    issues = []
    # Example: Check for <title> tag
    if "<title>" not in html.lower():
        score -= 10
        issues.append("Missing <title> tag")
    # Example: Check for meta description
    if 'name="description"' not in html.lower():
        score -= 5
        issues.append("Missing meta description")
    return {"score": score, "issues": issues}

# UX audit (placeholder for your checklist)
def ux_audit(html, url):
    # Use your UX checklist logic here
    return {
        "page_purpose": "Clear" if "<h1>" in html else "Unclear",
        "navigation_clarity": "Good" if "<nav>" in html else "Needs improvement",
        "priority": "High" if "<h1>" not in html else "Low"
    }    
def main():
    st.title("Website Audit Automation")
    st.markdown("Enter a **single URL** or upload a **CSV file** (columns: `website_url`, `industry_keyword`, `country`).")

    # Inputs
    website_url = st.text_input("Website URL (e.g., https://amarell-thermometer.de/)", key="url_input")
    csv_file = st.file_uploader("Upload CSV for bulk audits", type=["csv"])
    industry_keyword = st.text_input("Industry Keyword (optional)")
    country = st.text_input("Country (optional)")

    if st.button("Run Audit"):
        # Load or initialize cache
        cache = load_cache()

        # Process input
        urls = []
        if website_url:
            urls.append(normalize_url(website_url))
        if csv_file:
            df = pd.read_csv(csv_file)
            urls.extend(df["website_url"].apply(normalize_url).tolist())

        if not urls:
            st.error("Please provide a URL or CSV file.")
            return

        # Process each URL
        results = []
        for url in urls:
            # Check cache
            domain_key = url.split("//")[-1].split("/")[0]
            if domain_key in cache:
                st.info(f"Using cached data for {url}")
                results.append(cache[domain_key])
                continue

            # Fresh audit
            st.info(f"Auditing {url}...")
            crawl_result = crawl_page(url)
            if not crawl_result["html"]:
                st.warning(f"Skipping {url} (crawl failed)")
                continue

            # Run audits
            tech_audit = technical_audit(crawl_result["html"], url)
            ux_audit_result = ux_audit(crawl_result["html"], url)

            # Combine results
            result = {
                "url": url,
                "audit_date": datetime.now().strftime("%Y-%m-%d"),
                "technical": tech_audit,
                "ux": ux_audit_result,
                "ssl_valid": crawl_result["ssl_valid"],
                "industry_keyword": industry_keyword,
                "country": country
            }
            results.append(result)
            cache[domain_key] = result  # Update cache

        # Save cache
        save_cache(cache)

        # Generate CSV
        csv_data = []
        for result in results:
            csv_data.append({
                "page_url": result["url"],
                "audit_date": result["audit_date"],
                "audit_type": "Technical",
                "section": "Performance",
                "check": "SSL/TLS",
                "status": "Good" if result["ssl_valid"] else "Needs improvement",
                "what_i_found": "SSL valid" if result["ssl_valid"] else "SSL invalid",
                "why_it_matters": "Secure connections are critical for trust",
                "recommendation": "Renew SSL certificate" if not result["ssl_valid"] else "None",
                "priority": "Critical" if not result["ssl_valid"] else "Low"
            })
            # Add UX rows (example)
            csv_data.append({
                "page_url": result["url"],
                "audit_date": result["audit_date"],
                "audit_type": "UX",
                "section": "Information Architecture",
                "check": "Page Purpose",
                "status": result["ux"]["page_purpose"],
                "what_i_found": f"Page purpose is {result['ux']['page_purpose'].lower()}",
                "why_it_matters": "Clear purpose improves user engagement",
                "recommendation": "Add a hero section with a clear headline" if result["ux"]["page_purpose"] == "Unclear" else "None",
                "priority": result["ux"]["priority"]
            })

        # Display and download CSV
        df = pd.DataFrame(csv_data)
        st.dataframe(df)
        csv = df.to_csv(index=False)
        st.download_button(
            label="Download Audit CSV",
            data=csv,
            file_name="website_audit.csv",
            mime="text/csv"
        )

        # Display scorecard
        st.subheader("Scorecard")
        for result in results:
            st.markdown(f"### {result['url']}")
            st.write(f"**Technical Score:** {result['technical']['score']}/100")
            st.write(f"**UX Issues:** {', '.join([i for i in result['technical']['issues']]) or 'None'}")
            st.write(f"**Page Purpose:** {result['ux']['page_purpose']}")
            st.write(f"**Navigation Clarity:** {result['ux']['navigation_clarity']}")

if __name__ == "__main__":
    main()