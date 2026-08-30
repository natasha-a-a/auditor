import streamlit as st
import pandas as pd
import json
import requests
from pathlib import Path
from datetime import datetime, timedelta
import plotly.express as px
import io

# --- Constants ---
GITHUB_REPO = "natasha-a-a/auditor"
GITHUB_BRANCH = "main"
GITHUB_RAW_BASE = f"https://raw.githubusercontent.com/{GITHUB_REPO}/{GITHUB_BRANCH}"
GITHUB_AUDIT_CSV_URL = f"{GITHUB_RAW_BASE}/audit_cache/audits.csv"
GITHUB_WHOIS_CSV_URL = f"{GITHUB_RAW_BASE}/whois_cache/whois.csv"

# --- Helper Functions ---
def format_score(score, decimals=3):
    """Format score to maximum `decimals` decimal places."""
    if isinstance(score, (int, float)):
        formatted = f"{score:.{decimals}f}"
        return formatted.rstrip('0').rstrip('.') if '.' in formatted else formatted
    return str(score)

def fetch_csv_from_github(url):
    """Fetch CSV file directly from GitHub raw URL."""
    try:
        response = requests.get(url)
        response.raise_for_status()
        return pd.read_csv(io.StringIO(response.text))
    except requests.exceptions.RequestException as e:
        st.warning(f"⚠️ Could not fetch {url}: {str(e)}")
        return pd.DataFrame()

def load_github_cache():
    """Load audit cache from GitHub CSV."""
    df = fetch_csv_from_github(GITHUB_AUDIT_CSV_URL)
    if df.empty:
        return {}
    return {
        row["domain"]: {
            **json.loads(row["data"]),
            "timestamp": row["timestamp"]
        }
        for _, row in df.iterrows()
    }

# --- Data Processing Functions ---
def filter_recent_entries(cache, days=7):
    """Filter cache entries from the last N days."""
    cutoff_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    return {k: v for k, v in cache.items() if v.get("audit_date", v.get("timestamp", "")) >= cutoff_date}

def get_last_n_entries(cache, n=10):
    """Get the last N entries from the cache."""
    sorted_entries = sorted(
        cache.items(),
        key=lambda x: x[1].get("audit_date", x[1].get("timestamp", "")),
        reverse=True
    )
    return dict(sorted_entries[:n])

def generate_full_csv(cache):
    """Generate a CSV of all audit data in the cache."""
    csv_data = []
    for domain, data in cache.items():
        url = data.get("url", "N/A")
        audit_date = data.get("audit_date", data.get("timestamp", "N/A"))
        benchmarks = data.get("benchmarks", {})

        for category in ["technical", "business", "functional", "seo", "budget"]:
            for check_name, check_data in data.get(category, {}).get("checks", {}).items():
                csv_data.append({
                    "page_url": url,
                    "audit_date": audit_date,
                    "audit_type": category.capitalize(),
                    "section": "Performance & Security" if category == "technical" else
                              "Business Presentation" if category == "business" else
                              "Functional Gaps" if category == "functional" else
                              "SEO & Visibility" if category == "seo" else
                              "Budget & Resources",
                    "check": check_name.replace("_", " ").title(),
                    "status": check_data.get("status", "N/A"),
                    "what_i_found": check_data.get("issue", "No issues"),
                    "why_it_matters": "Critical for security" if check_data.get("status") == "Critical" else
                                    "Critical for trust" if category == "business" and check_data.get("status") == "Critical" else
                                    "Critical for conversions" if category == "functional" and check_data.get("status") == "Critical" else
                                    "Critical for visibility" if category == "seo" and check_data.get("status") == "Critical" else
                                    "Indicates low digital investment" if category == "budget" and check_data.get("status") != "Good" else
                                    "No immediate risk",
                    "recommendation": "Fix immediately" if check_data.get("status") == "Critical" else
                                     "Add missing information" if category == "business" and check_data.get("status") != "Good" else
                                     "Implement missing functionality" if category == "functional" and check_data.get("status") != "Good" else
                                     "Optimize for search engines" if category == "seo" and check_data.get("status") != "Good" else
                                     "Invest in digital presence" if category == "budget" and check_data.get("status") != "Good" else
                                     "Monitor domain status",
                    "priority": check_data.get("status", "N/A"),
                    "score": data.get(category, {}).get("score", 0),
                    "benchmark": benchmarks.get(category, 70),
                    "vs_benchmark": "Above" if data.get(category, {}).get("score", 0) > benchmarks.get(category, 70) else "Below"
                })

        for check_name, check_data in data.get("dead_end", {}).get("checks", {}).items():
            csv_data.append({
                "page_url": url,
                "audit_date": audit_date,
                "audit_type": "Dead End Detection",
                "section": "Domain Health",
                "check": check_name.replace("_", " ").title(),
                "status": check_data.get("status", "N/A"),
                "what_i_found": check_data.get("issue", "No issues"),
                "why_it_matters": "Critical for business continuity" if check_data.get("status") == "Critical" else "No immediate risk",
                "recommendation": "Renew domain immediately" if check_data.get("status") == "Critical" else "Monitor domain status",
                "priority": check_data.get("status", "N/A"),
                "score": data.get("dead_end", {}).get("score", 0),
                "benchmark": 100,
                "vs_benchmark": "Above" if data.get("dead_end", {}).get("score", 0) == 100 else "Below"
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
                "why_it_matters": "Indicates active business growth",
                "recommendation": "Leverage growth momentum",
                "priority": "Good",
                "score": 100,
                "benchmark": "N/A",
                "vs_benchmark": "N/A"
            })
    return pd.DataFrame(csv_data)

def generate_painpoint_csv(cache):
    """Generate a CSV of websites categorized by primary pain point."""
    pain_points = {
        "Technical Issues": [],
        "Business Info Gaps": [],
        "Functional Gaps": [],
        "SEO Weaknesses": [],
        "Budget Constraints": [],
        "Dead End Risks": []
    }
    category_map = {
        "Technical": "Technical Issues",
        "Business Info": "Business Info Gaps",
        "Functional": "Functional Gaps",
        "SEO": "SEO Weaknesses",
        "Budget": "Budget Constraints",
        "Dead End": "Dead End Risks"
    }
    for domain, data in cache.items():
        scores = {
            "Technical": data.get("technical", {}).get("score", 0),
            "Business Info": data.get("business", {}).get("score", 0),
            "Functional": data.get("functional", {}).get("score", 0),
            "SEO": data.get("seo", {}).get("score", 0),
            "Budget": data.get("budget", {}).get("score", 0),
            "Dead End": data.get("dead_end", {}).get("score", 0)
        }
        worst_category = min(scores, key=scores.get)
        pain_points[category_map[worst_category]].append(data.get("url", "N/A"))

    painpoint_data = []
    for category, urls in pain_points.items():
        for url in urls:
            painpoint_data.append({"Pain Point": category, "URL": url, "Count": len(urls)})
    return pd.DataFrame(painpoint_data)

# --- Main Dashboard App ---
def main():
    st.set_page_config(page_title="Paw à Peau Audit Dashboard", layout="wide", page_icon="📊")
    st.title("📊 Paw à Peau Website Audit Dashboard")

    # Debug: Show GitHub URLs
    st.write(f"🔗 Fetching audits from: {GITHUB_AUDIT_CSV_URL}")
    st.write(f"🔗 Fetching WHOIS from: {GITHUB_WHOIS_CSV_URL}")

    # Manual refresh button
    if st.button("🔄 Refresh Data from GitHub"):
        st.rerun()

    # Load cache from GitHub
    cache = load_github_cache()
    if not cache:
        st.warning("⚠️ No audit data found. Run the auditor app and commit CSV files to GitHub first.")
        st.stop()

    st.markdown("""
    **Overview:**
    - **Benchmarks**: Compare scores across industries.
    - **Trends**: Track changes over the last 7 days.
    - **Recent Entries**: View the last 10 audited websites.
    - **Download Reports**: Get detailed CSV files for analysis.
    """)

    # --- Benchmarks by Industry ---
    st.subheader("📈 Industry Benchmarks")
    industry_data = []
    for domain, data in cache.items():
        industry = data.get("industry_keyword", "Other")
        industry_data.append({
            "Industry": industry,
            "Technical": data.get("technical", {}).get("score", 0),
            "Business Info": data.get("business", {}).get("score", 0),
            "Functional": data.get("functional", {}).get("score", 0),
            "SEO": data.get("seo", {}).get("score", 0),
            "Budget": data.get("budget", {}).get("score", 0),
            "Dead End": data.get("dead_end", {}).get("score", 0),
            "Growth Signals": len(data.get("growth", {}).get("growth_signals", []))
        })
    if industry_data:
        industry_df = pd.DataFrame(industry_data)
        avg_by_industry = industry_df.groupby("Industry").mean().reset_index()
        fig = px.bar(avg_by_industry, x="Industry", y=["Technical", "Business Info", "Functional", "SEO", "Budget"],
                     title="Average Scores by Industry", barmode="group")
        st.plotly_chart(fig, use_container_width=True)
        st.dataframe(avg_by_industry, use_container_width=True)

    # --- Trends Over Last 7 Days ---
    st.subheader("📉 Trends (Last 7 Days)")
    recent_entries = filter_recent_entries(cache, days=7)
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
                "Budget": data.get("budget", {}).get("score", 0),
                "Dead End": data.get("dead_end", {}).get("score", 0)
            })
        trend_df = pd.DataFrame(trend_data)
        if not trend_df.empty:
            fig = px.line(trend_df, x="Date", y=["Technical", "Business Info", "Functional", "SEO", "Budget"],
                          title="Score Trends Over Time", markers=True)
            st.plotly_chart(fig, use_container_width=True)
            st.dataframe(trend_df, use_container_width=True)

    # --- Last 10 URL Entries ---
    st.subheader("🔍 Last 10 Audited Websites")
    last_10_entries = get_last_n_entries(cache, n=10)
    if last_10_entries:
        last_10_data = []
        for domain, data in last_10_entries.items():
            last_10_data.append({
                "URL": data.get("url", "N/A"),
                "Date": data.get("audit_date", data.get("timestamp", "N/A")),
                "Industry": data.get("industry_keyword", "Other"),
                "Technical": format_score(data.get("technical", {}).get("score", 0)),
                "Business Info": format_score(data.get("business", {}).get("score", 0)),
                "Functional": format_score(data.get("functional", {}).get("score", 0)),
                "SEO": format_score(data.get("seo", {}).get("score", 0)),
                "Budget": format_score(data.get("budget", {}).get("score", 0)),
                "Dead End": format_score(data.get("dead_end", {}).get("score", 0)),
                "Growth Signals": ", ".join(data.get("growth", {}).get("growth_signals", [])) or "None"
            })
        last_10_df = pd.DataFrame(last_10_data)
        st.dataframe(last_10_df, use_container_width=True)

    # --- Downloadable Reports ---
    st.subheader("📥 Download Reports")

    full_csv_df = generate_full_csv(cache)
    if not full_csv_df.empty:
        csv_full = full_csv_df.to_csv(index=False)
        st.download_button(
            label="📥 Download Full Audit CSV",
            data=csv_full,
            file_name=f"full_audit_report_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
            mime="text/csv"
        )

    painpoint_csv_df = generate_painpoint_csv(cache)
    if not painpoint_csv_df.empty:
        csv_painpoint = painpoint_csv_df.to_csv(index=False)
        st.download_button(
            label="📥 Download Pain Point Shortlists CSV",
            data=csv_painpoint,
            file_name=f"painpoint_shortlists_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
            mime="text/csv"
        )

    # --- Pain Point Shortlists (Expandable) ---
    st.subheader("🎯 Websites by Primary Pain Point")
    pain_points = {
        "Technical Issues": [],
        "Business Info Gaps": [],
        "Functional Gaps": [],
        "SEO Weaknesses": [],
        "Budget Constraints": [],
        "Dead End Risks": []
    }
    category_map = {
        "Technical": "Technical Issues",
        "Business Info": "Business Info Gaps",
        "Functional": "Functional Gaps",
        "SEO": "SEO Weaknesses",
        "Budget": "Budget Constraints",
        "Dead End": "Dead End Risks"
    }
    for domain, data in cache.items():
        scores = {
            "Technical": data.get("technical", {}).get("score", 0),
            "Business Info": data.get("business", {}).get("score", 0),
            "Functional": data.get("functional", {}).get("score", 0),
            "SEO": data.get("seo", {}).get("score", 0),
            "Budget": data.get("budget", {}).get("score", 0),
            "Dead End": data.get("dead_end", {}).get("score", 0)
        }
        worst_category = min(scores, key=scores.get)
        pain_points[category_map[worst_category]].append(data.get("url", "N/A"))

    for category, urls in pain_points.items():
        if urls:
            with st.expander(f"{category} ({len(urls)} websites)"):
                for url in urls:
                    st.write(f"- {url}")

if __name__ == "__main__":
    main()