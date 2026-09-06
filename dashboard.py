import streamlit as st
import pandas as pd
import json
import requests
from pathlib import Path
from datetime import datetime, timedelta
import plotly.express as px
import io
import numpy as np
from bs4 import BeautifulSoup
import re

# --- Constants ---
GITHUB_REPO = st.secrets["GITHUB_REPO"]
GITHUB_BRANCH = st.secrets["GITHUB_BRANCH"]

if not GITHUB_REPO or not GITHUB_BRANCH:
    st.error("❌ GitHub repository and branch must be configured in secrets.toml")
    st.stop()

GITHUB_RAW_BASE = f"https://raw.githubusercontent.com/{GITHUB_REPO}/{GITHUB_BRANCH}"
GITHUB_AUDIT_CSV_URL = f"{GITHUB_RAW_BASE}/audit_cache/audits.csv"
GITHUB_BENCHMARK_CSV_URL = f"{GITHUB_RAW_BASE}/benchmark_websites.csv"
GITHUB_RECOMMENDATIONS_CSV_URL = f"{GITHUB_RAW_BASE}/recommendations.csv"

# --- Helper Functions ---
def format_score(score, decimals=3):
    """Format score to maximum `decimals` decimal places."""
    if isinstance(score, (int, float)):
        formatted = f"{score:.{decimals}f}"
        return formatted.rstrip('0').rstrip('.') if '.' in formatted else formatted
    return str(score)

def fetch_csv_from_github(url, sep=';'):
    """Fetch CSV file directly from GitHub raw URL with proper error handling."""
    try:
        response = requests.get(url)
        response.raise_for_status()
        return pd.read_csv(io.StringIO(response.text), sep=sep)
    except requests.exceptions.RequestException as e:
        st.warning(f"⚠️ Could not fetch {url}: {str(e)}")
        return pd.DataFrame()
    except Exception as e:
        st.warning(f"⚠️ CSV parsing error for {url}: {str(e)}")
        return pd.DataFrame()

def load_benchmark_websites():
    """Load benchmark websites from GitHub CSV."""
    df = fetch_csv_from_github(GITHUB_BENCHMARK_CSV_URL, sep=',')
    if df.empty:
        return set()
    if 'url' not in df.columns:
        st.warning("⚠️ Benchmark CSV missing 'url' column")
        return set()
    return set(df['url'].tolist())

def load_recommendations():
    """Load recommendations from CSV with semicolon delimiter and validation."""
    expected_columns = ['industry', 'category', 'check_name', 'business_impact', 'recommendation', 'priority']
    local_path = Path("recommendations.csv")

    if local_path.exists():
        try:
            df = pd.read_csv(local_path, sep=';')
            if not df.empty and all(col in df.columns for col in expected_columns):
                st.info(f"✅ Loaded {len(df)} recommendations from local CSV")
                return df
        except Exception as e:
            st.warning(f"⚠️ Local recommendations CSV error: {str(e)}")

    try:
        df = fetch_csv_from_github(GITHUB_RECOMMENDATIONS_CSV_URL, sep=';')
        if not df.empty and all(col in df.columns for col in expected_columns):
            st.info(f"✅ Loaded {len(df)} recommendations from GitHub CSV")
            return df
    except Exception as e:
        st.warning(f"⚠️ GitHub recommendations CSV error: {str(e)}")

    return pd.DataFrame(columns=expected_columns)

def load_github_cache():
    """Load audit cache from GitHub CSV with error handling."""
    df = fetch_csv_from_github(GITHUB_AUDIT_CSV_URL, sep=',')
    if df.empty:
        return {}
    if not all(col in df.columns for col in ['domain', 'data', 'timestamp']):
        st.warning("⚠️ Audit CSV missing required columns")
        return {}

    benchmark_websites = load_benchmark_websites()
    cache = {}
    for _, row in df.iterrows():
        try:
            cache[row["domain"]] = {
                **json.loads(row["data"]),
                "timestamp": row["timestamp"],
                "is_benchmark": row["domain"] in benchmark_websites
            }
        except json.JSONDecodeError:
            continue
    return cache

def extract_contact_info(html, url):
    """Extract contact email and physical address from HTML."""
    if not html:
        return None, None
    try:
        soup = BeautifulSoup(html, 'html.parser')
        text = soup.get_text()
        email_pattern = r'[\w\.-]+@[\w\.-]+\.\w+'
        emails = re.findall(email_pattern, text)
        contact_email = None
        generic_domains = ['gmail', 'yahoo', 'hotmail', 'outlook', 'aol', 'protonmail']
        for email in emails:
            if not any(domain in email.lower() for domain in generic_domains):
                contact_email = email
                break
        if not contact_email and emails:
            contact_email = emails[0]

        address_pattern = r'\d+\s[\w\s]+,\s[\w\s]+,\s[A-Z]{2}\s\d{5}(?:-\d{4})?'
        address_match = re.search(address_pattern, text)
        physical_address = address_match.group(0) if address_match else None
        return contact_email, physical_address
    except Exception:
        return None, None

# Load recommendations at startup
RECOMMENDATIONS_DF = load_recommendations()

def get_business_impact(category, check_name):
    """Get business impact from CSV data with fallback."""
    if not RECOMMENDATIONS_DF.empty and all(col in RECOMMENDATIONS_DF.columns for col in ['category', 'check_name', 'business_impact']):
        filtered = RECOMMENDATIONS_DF[
            (RECOMMENDATIONS_DF['category'] == category) &
            (RECOMMENDATIONS_DF['check_name'] == check_name)
        ]
        if not filtered.empty:
            return filtered.iloc[0]['business_impact']
    fallbacks = {
        "technical": "Improves security, performance, and user experience leading to higher conversions and better SEO.",
        "business": "Enhances credibility and customer trust resulting in 30-50% higher conversion rates.",
        "functional": "Boosts user engagement and conversions by 20-40% through improved functionality.",
        "seo": "Increases organic traffic and search visibility by 100-200% through better optimization.",
        "ux": "Improves user experience and accessibility, reducing bounce rates by 40-60% and increasing conversions.",
        "budget": "Supports sustainable digital growth and prevents revenue loss from outdated solutions.",
        "growth": "Provides competitive advantage through active business growth and expansion."
    }
    return fallbacks.get(category, "Enhances overall digital presence and business results")

def get_recommendation(category, check_name):
    """Get recommendation text from CSV data with fallback."""
    if not RECOMMENDATIONS_DF.empty and all(col in RECOMMENDATIONS_DF.columns for col in ['category', 'check_name', 'recommendation']):
        filtered = RECOMMENDATIONS_DF[
            (RECOMMENDATIONS_DF['category'] == category) &
            (RECOMMENDATIONS_DF['check_name'] == check_name)
        ]
        if not filtered.empty:
            return filtered.iloc[0]['recommendation']
    fallbacks = {
        "technical": "We will implement technical improvements to address security, performance, and compatibility issues.",
        "business": "We will enhance business information presentation to build trust and credibility with visitors.",
        "functional": "We will add or improve functionality to drive user engagement and conversions.",
        "seo": "We will optimize for better search visibility, rankings, and organic traffic growth.",
        "ux": "We will improve user experience and accessibility to reduce bounce rates and increase conversions.",
        "budget": "We will address budget-related constraints to support sustainable digital growth.",
        "growth": "We will leverage this growth opportunity for competitive advantage and business expansion."
    }
    return fallbacks.get(category, "We will address this to improve digital performance and business results")

# --- Data Processing Functions ---
def filter_user_audits(cache):
    """Filter out benchmark websites, return only user-submitted audits."""
    return {k: v for k, v in cache.items() if not v.get("is_benchmark", False)}

def filter_recent_entries(cache, days=7):
    """Filter cache entries from the last N days."""
    cutoff_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    return {k: v for k, v in cache.items() if v.get("audit_date", v.get("timestamp", "")) >= cutoff_date}

def get_last_n_entries(cache, n=10):
    """Get the last N user-submitted entries from the cache."""
    user_cache = filter_user_audits(cache)
    sorted_entries = sorted(
        user_cache.items(),
        key=lambda x: x[1].get("audit_date", x[1].get("timestamp", "")),
        reverse=True
    )
    return dict(sorted_entries[:n])

def generate_full_csv(cache, include_benchmarks=False):
    """Generate a CSV of all audit data in the cache."""
    user_cache = cache if include_benchmarks else filter_user_audits(cache)
    csv_data = []
    for domain, data in user_cache.items():
        url = data.get("url", "N/A")
        audit_date = data.get("audit_date", data.get("timestamp", "N/A"))
        benchmarks = data.get("benchmarks", {})

        for category in ["technical", "business", "functional", "seo", "ux", "budget"]:
            category_data = data.get(category, {})
            checks = category_data.get("checks", {})
            score = category_data.get("score", 0)

            for check_name, check_data in checks.items():
                status = check_data.get("status", "N/A")
                issue = check_data.get("issue", "No issues")

                if check_name in ['flash_elements', 'outdated_plugins'] and issue and 'detected' in str(issue).lower():
                    status = 'Needs improvement'
                elif check_name == 'ssl_tls' and data.get('crawl', {}).get('ssl_valid') is False:
                    status = 'Critical'

                csv_data.append({
                    "page_url": url,
                    "audit_date": audit_date,
                    "audit_type": category.capitalize(),
                    "section": "Performance & Security" if category == "technical" else
                              "Business Presentation" if category == "business" else
                              "Functional Gaps" if category == "functional" else
                              "SEO & Visibility" if category == "seo" else
                              "UX & Accessibility" if category == "ux" else
                              "Budget & Resources",
                    "check": check_name.replace("_", " ").title(),
                    "status": status,
                    "what_i_found": issue,
                    "business_impact": get_business_impact(category, check_name),
                    "recommendation": get_recommendation(category, check_name) if status != "Good" else "",
                    "priority": status,
                    "score": score,
                    "benchmark": benchmarks.get(category, 70),
                    "vs_benchmark": "Above" if score > benchmarks.get(category, 70) else "Below"
                })

        growth_signals = data.get("growth", {}).get("growth_signals", [])
        if growth_signals:
            csv_data.append({
                "page_url": url,
                "audit_date": audit_date,
                "audit_type": "Growth Signals",
                "section": "Growth Indicators",
                "check": "Growth Signals Detected",
                "status": "Good",
                "what_i_found": "; ".join(growth_signals),
                "business_impact": "",
                "recommendation": "",
                "priority": "Good",
                "score": 100,
                "benchmark": "N/A",
                "vs_benchmark": "N/A"
            })
    return pd.DataFrame(csv_data)

def generate_painpoint_csv_with_contact(cache):
    """Generate a CSV of websites categorized by primary pain point with contact info."""
    user_cache = filter_user_audits(cache)
    category_map = {
        "Technical": "Technical Issues",
        "Business Info": "Business Info Gaps",
        "Functional": "Functional Gaps",
        "SEO": "SEO Weaknesses",
        "UX": "UX & Accessibility Issues",
        "Budget": "Budget Constraints"
    }

    painpoint_data = []
    for domain, data in user_cache.items():
        html = data.get('crawl', {}).get('html', '')
        contact_email, physical_address = extract_contact_info(html, data.get('url', ''))

        scores = {
            "Technical": data.get("technical", {}).get("score", 0),
            "Business Info": data.get("business", {}).get("score", 0),
            "Functional": data.get("functional", {}).get("score", 0),
            "SEO": data.get("seo", {}).get("score", 0),
            "UX": data.get("ux", {}).get("score", 0),
            "Budget": data.get("budget", {}).get("score", 0)
        }
        worst_category = min(scores, key=scores.get)
        category = category_map[worst_category]

        painpoint_data.append({
            "Website": data.get("url", "N/A"),
            "Pain Point": category,
            "Contact Email": contact_email or "Not found",
            "Physical Address": physical_address or "Not found",
            "Industry": data.get("industry_keyword", "Other"),
            "Growth Signals": ", ".join(data.get("growth", {}).get("growth_signals", []))
        })

    return pd.DataFrame(painpoint_data)

def calculate_statistics(scores):
    """Calculate basic statistics for a list of scores."""
    if not scores:
        return {}
    return {
        "Mean": np.mean(scores),
        "Median": np.median(scores),
        "Min": min(scores),
        "Max": max(scores),
        "Std Dev": np.std(scores),
        "Range": max(scores) - min(scores)
    }

# --- Main Dashboard App ---
def main():
    st.set_page_config(page_title="Paw à Peau Audit Dashboard", layout="wide", page_icon="📊")
    st.title("📊 Paw à Peau Audit Dashboard")

    if st.button("🔄 Refresh Data from GitHub"):
        st.rerun()

    cache = load_github_cache()
    if not cache:
        st.warning("⚠️ No audit data found. Run the auditor app first.")
        st.stop()

    user_cache = filter_user_audits(cache)
    if not user_cache:
        st.warning("⚠️ No user-submitted audits found.")
        st.stop()

    st.markdown("""
    **Overview:**
    - **Benchmarks**: Compare scores across industries (includes user audits in same industry).
    - **Trends**: Analyze user audit scores over the last 7 days.
    - **Recent Entries**: View the last 10 user-submitted audited websites.
    - **In-Depth Analysis**: Detailed scorecard for the last audited website.
    - **Download Reports**: Detailed CSV files for analysis.
    """)

    last_audit_entries = get_last_n_entries(cache, n=1)
    if last_audit_entries:
        last_domain, last_data = next(iter(last_audit_entries.items()))

        st.subheader(f"🔍 In-Depth Analysis: {last_data.get('url', 'N/A')}")
        st.markdown(f"**Industry:** {last_data.get('industry_keyword', 'Other')} | **Date:** {last_data.get('audit_date', last_data.get('timestamp', 'N/A'))} | **Language:** {last_data.get('language', 'N/A').upper()}")

        st.markdown("### 📊 Detailed Scorecard")

        categories = [
            ("technical", "🔧", "Technical Performance & Security"),
            ("business", "🏢", "Company Presentation"),
            ("functional", "🛠️", "Functional Gaps"),
            ("seo", "🔍", "SEO & Visibility"),
            ("ux", "🎨", "UX & Accessibility"),
            ("budget", "💰", "Budget & Resources")
        ]

        for cat_key, icon, section in categories:
            with st.expander(f"{icon} {section} (Score: {format_score(last_data.get(cat_key, {}).get('score', 0))}/100)"):
                st.markdown(f"**Section Score:** {format_score(last_data.get(cat_key, {}).get('score', 0))}/100")

                checks = last_data.get(cat_key, {}).get("checks", {})
                if checks:
                    for check_name, check_data in checks.items():
                        st.markdown(f"**{check_name.replace('_', ' ').title()}**")
                        status = check_data.get('status', 'N/A')
                        issue = check_data.get('issue', 'No issues')

                        if check_name in ['flash_elements', 'outdated_plugins'] and issue and 'detected' in str(issue).lower():
                            display_status = 'Needs improvement'
                        elif check_name == 'ssl_tls' and last_data.get('crawl', {}).get('ssl_valid') is False:
                            display_status = 'Critical'
                        else:
                            display_status = status

                        st.write(f"- **Status:** {display_status}")
                        st.write(f"- **What I Found:** {issue}")

                        # FIXED: Always show business impact, only show recommendation for non-Good
                        st.write(f"- **Business Impact:** {get_business_impact(cat_key, check_name)}")
                        if display_status != "Good":
                            st.write(f"- **Recommendation:** {get_recommendation(cat_key, check_name)}")
                        st.markdown("---")
                else:
                    st.info("No specific checks recorded for this category.")

                benchmark = last_data.get("benchmarks", {}).get(cat_key, 70)
                delta = last_data.get(cat_key, {}).get("score", 0) - benchmark
                st.metric(
                    "Benchmark Comparison",
                    f"{format_score(last_data.get(cat_key, {}).get('score', 0))} vs {format_score(benchmark)}",
                    delta=f"{delta:+.1f}",
                    delta_color="normal"
                )

        st.markdown("---")

    st.subheader("📋 Last 10 User-Submitted Audited Websites")
    last_10_entries = get_last_n_entries(cache, n=10)

    if last_10_entries:
        if st.button("📥 Download ALL User Audits CSV"):
            all_user_df = generate_full_csv(cache, include_benchmarks=False)
            if not all_user_df.empty:
                csv_all = all_user_df.to_csv(index=False)
                st.download_button(
                    label="⬇️ Download Complete User Audit Report",
                    data=csv_all,
                    file_name=f"all_user_audits_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                    mime="text/csv"
                )

        st.markdown("### 📥 Individual In-Depth Reports")
        for domain, data in last_10_entries.items():
            col1, col2 = st.columns([4, 1])
            with col1:
                st.write(f"{data.get('url', 'N/A')} - {data.get('audit_date', 'N/A')}")
            with col2:
                individual_df = generate_full_csv({domain: data})
                if not individual_df.empty:
                    csv_individual = individual_df.to_csv(index=False)
                    st.download_button(
                        label="Download",
                        data=csv_individual,
                        file_name=f"audit_{data.get('url', 'website').replace('https://', '').replace('/', '_')}_{datetime.now().strftime('%Y%m%d')}.csv",
                        mime="text/csv",
                        key=f"download_{domain}"
                    )

        st.subheader("📊 Statistical Comparison (Last 10 User Audits)")
        category_scores = {
            "Technical": [],
            "Business Info": [],
            "Functional": [],
            "SEO": [],
            "UX": [],
            "Budget": []
        }

        for domain, data in last_10_entries.items():
            for cat in category_scores.keys():
                cat_key = cat.lower().replace(" ", "_")
                score = data.get(cat_key, {}).get("score", 0)
                category_scores[cat].append(score)

        stats_df = pd.DataFrame({
            category: calculate_statistics(scores)
            for category, scores in category_scores.items()
        }).T

        st.dataframe(stats_df.style.format("{:.2f}"), use_container_width=True)
        fig = px.box(category_scores, labels={"value": "Score", "variable": "Category"})
        fig.update_layout(title="Score Distribution Across Last 10 Audits")
        st.plotly_chart(fig, use_container_width=True)

    st.subheader("📈 Industry Benchmarks (Includes User Audits in Same Industry)")
    industry_data = []
    for domain, data in cache.items():
        if not data.get("is_benchmark", False):
            industry = data.get("industry_keyword", "Other")
            industry_data.append({
                "Industry": industry,
                "Technical": data.get("technical", {}).get("score", 0),
                "Business Info": data.get("business", {}).get("score", 0),
                "Functional": data.get("functional", {}).get("score", 0),
                "SEO": data.get("seo", {}).get("score", 0),
                "UX": data.get("ux", {}).get("score", 0),
                "Budget": data.get("budget", {}).get("score", 0)
            })

    if industry_data:
        industry_df = pd.DataFrame(industry_data)
        avg_by_industry = industry_df.groupby("Industry").mean().reset_index()
        fig = px.bar(avg_by_industry, x="Industry", y=["Technical", "Business Info", "Functional", "SEO", "UX", "Budget"],
                     title="Average Scores by Industry", barmode="group")
        st.plotly_chart(fig, use_container_width=True)
        st.dataframe(avg_by_industry, use_container_width=True)

    st.subheader("📉 Trends (Last 7 Days - User Audits Only)")
    recent_entries = filter_recent_entries(user_cache, days=7)
    if recent_entries:
        trend_data = []
        for domain, data in recent_entries.items():
            trend_data.append({
                "Date": data.get("audit_date", data.get("timestamp", "N/A")),
                "URL": data.get("url", "N/A"),
                "Technical": data.get("technical", {}).get("score", 0),
                "Business Info": data.get("business", {}).get("score", 0),
                "Functional": data.get("functional", {}).get("score", 0),
                "SEO": data.get("seo", {}).get("score", 0),
                "UX": data.get("ux", {}).get("score", 0),
                "Budget": data.get("budget", {}).get("score", 0)
            })
        trend_df = pd.DataFrame(trend_data)
        if not trend_df.empty:
            fig = px.line(trend_df, x="Date", y=["Technical", "Business Info", "Functional", "SEO", "UX", "Budget"],
                          title="Score Trends Over Time", markers=True)
            st.plotly_chart(fig, use_container_width=True)
            st.dataframe(trend_df, use_container_width=True)

    st.subheader("Download Websites by Pain Point")
    painpoint_df = generate_painpoint_csv_with_contact(cache)
    if not painpoint_df.empty:
        pain_points = painpoint_df['Pain Point'].unique()
        cols = st.columns(min(len(pain_points), 3))
        for idx, pain_point in enumerate(pain_points):
            with cols[idx % len(cols)]:
                pain_point_data = painpoint_df[painpoint_df['Pain Point'] == pain_point]
                csv_data = pain_point_data.to_csv(index=False)
                st.download_button(
                    label=f"📥 {pain_point}",
                    data=csv_data,
                    file_name=f"{pain_point.replace(' ', '_').replace('/', '_')}_websites_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                    mime="text/csv",
                    key=f"painpoint_{pain_point.replace(' ', '_')}"
                )

if __name__ == "__main__":
    main()