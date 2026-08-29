import streamlit as st
import requests
from bs4 import BeautifulSoup
import pandas as pd
import json
from pathlib import Path
from datetime import datetime
import re

# Configure cache directory
CACHE_DIR = Path("audit_cache")
CACHE_DIR.mkdir(exist_ok=True)

# --- Helper Functions ---
def normalize_url(url):
    """Normalize URL (force https://, trim whitespace)."""
    url = str(url).strip()
    return re.sub(r'^http://', 'https://', url) if url.startswith(('http://', 'https://')) else f"https://{url}"

def load_cache():
    """Load audit cache from JSON file."""
    cache_file = CACHE_DIR / "audit_cache.json"
    return json.loads(cache_file.read_text()) if cache_file.exists() else {}

def save_cache(cache):
    """Save audit cache to JSON file."""
    cache_file = CACHE_DIR / "audit_cache.json"
    cache_file.write_text(json.dumps(cache, indent=2))

def crawl_page(url):
    """Crawl a page using requests and check SSL/TLS."""
    try:
        response = requests.get(url, timeout=10, verify=True)
        ssl_valid = True
        html = response.text
    except requests.exceptions.SSLError:
        ssl_valid = False
        html = ""
        st.warning(f"SSL/TLS error for {url}")
    except Exception as e:
        ssl_valid = False
        html = ""
        st.error(f"Connection error for {url}: {str(e)}")
    return {"url": url, "html": html, "ssl_valid": ssl_valid}

def technical_audit(html, url):
    """Run technical checks on the HTML."""
    soup = BeautifulSoup(html, 'html.parser')
    score = 100
    issues = []

    # Check for <title>
    if not soup.title:
        score -= 10
        issues.append("Missing <title> tag")

    # Check for meta description
    meta_desc = soup.find("meta", attrs={"name": "description"})
    if not meta_desc:
        score -= 5
        issues.append("Missing meta description")

    # Check for headings (h1)
    if not soup.find("h1"):
        score -= 5
        issues.append("Missing <h1> heading")

    return {"score": score, "issues": issues}

def ux_audit(html, url):
    """Run UX checks on the HTML (simplified for demo)."""
    soup = BeautifulSoup(html, 'html.parser')
    page_purpose = "Clear" if soup.find("h1") else "Unclear"
    navigation_clarity = "Good" if soup.find("nav") else "Needs improvement"
    priority = "High" if page_purpose == "Unclear" else "Low"
    return {
        "page_purpose": page_purpose,
        "navigation_clarity": navigation_clarity,
        "priority": priority
    }

# --- Main App ---
def main():
    st.title("🌐 Website Audit Automation")
    st.markdown("Enter a **single URL** or upload a **CSV file** (columns: `website_url`, `industry_keyword`, `country`).")

    # Inputs
    website_url = st.text_input("Website URL (e.g., https://amarell-thermometer.de/)", key="url_input")
    csv_file = st.file_uploader("Upload CSV for bulk audits", type=["csv"])
    industry_keyword = st.text_input("Industry Keyword (optional)", key="industry")
    country = st.text_input("Country (optional)", key="country")

    if st.button("Run Audit"):
        # Load or initialize cache
        cache = load_cache()
        urls = []

        # Process input
        if website_url:
            urls.append(normalize_url(website_url))
        if csv_file:
            df = pd.read_csv(csv_file)
            urls.extend(df["website_url"].apply(normalize_url).tolist())

        if not urls:
            st.error("❌ Please provide a URL or CSV file.")
            return

        # Process each URL
        results = []
        for url in urls:
            domain_key = url.split("//")[-1].split("/")[0]
            if domain_key in cache:
                st.info(f"✅ Using cached data for {url}")
                results.append(cache[domain_key])
                continue

            st.info(f"🔍 Auditing {url}...")
            crawl_result = crawl_page(url)
            if not crawl_result["html"]:
                st.warning(f"⚠️ Skipping {url} (crawl failed)")
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
            # Technical audit rows
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
            csv_data.append({
                "page_url": result["url"],
                "audit_date": result["audit_date"],
                "audit_type": "Technical",
                "section": "SEO",
                "check": "Meta Tags",
                "status": "Good" if not result["technical"]["issues"] else "Needs improvement",
                "what_i_found": "; ".join(result["technical"]["issues"]) if result["technical"]["issues"] else "All checks passed",
                "why_it_matters": "Meta tags improve SEO and accessibility",
                "recommendation": "Add missing meta tags" if result["technical"]["issues"] else "None",
                "priority": "High" if result["technical"]["issues"] else "Low"
            })

            # UX audit rows
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
            csv_data.append({
                "page_url": result["url"],
                "audit_date": result["audit_date"],
                "audit_type": "UX",
                "section": "Navigation",
                "check": "Navigation Clarity",
                "status": result["ux"]["navigation_clarity"],
                "what_i_found": f"Navigation is {result['ux']['navigation_clarity'].lower()}",
                "why_it_matters": "Clear navigation helps users find content",
                "recommendation": "Improve menu labels and structure" if result["ux"]["navigation_clarity"] == "Needs improvement" else "None",
                "priority": "High" if result["ux"]["navigation_clarity"] == "Needs improvement" else "Low"
            })

        # Display and download CSV
        if csv_data:
            df = pd.DataFrame(csv_data)
            st.dataframe(df)
            csv = df.to_csv(index=False)
            st.download_button(
                label="📥 Download Audit CSV",
                data=csv,
                file_name="website_audit.csv",
                mime="text/csv"
            )
        else:
            st.warning("No data to generate CSV.")

        # Display scorecard
        st.subheader("📊 Scorecard")
        for result in results:
            st.markdown(f"### {result['url']}")
            col1, col2 = st.columns(2)
            with col1:
                st.metric("Technical Score", f"{result['technical']['score']}/100")
                if result["technical"]["issues"]:
                    st.error("Issues: " + ", ".join(result["technical"]["issues"]))
                else:
                    st.success("✅ All technical checks passed!")
            with col2:
                st.metric("SSL/TLS", "✅ Valid" if result["ssl_valid"] else "❌ Invalid")
                st.metric("Page Purpose", result["ux"]["page_purpose"])
                st.metric("Navigation", result["ux"]["navigation_clarity"])

if __name__ == "__main__":
    main()