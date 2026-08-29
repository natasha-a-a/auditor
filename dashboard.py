Here is the **full corrected `dashboard.py`** with all fixes applied:

```python
import streamlit as st
import pandas as pd
import json
import sqlite3
from pathlib import Path
from datetime import datetime, timedelta
import plotly.express as px

# --- Constants ---
CACHE_DIR = Path("audit_cache")
WHOIS_CACHE_DIR = Path("whois_cache")
DB_FILE = CACHE_DIR / "audit_cache.db"
WHOIS_DB_FILE = WHOIS_CACHE_DIR / "whois_cache.db"

# Ensure directories exist
for directory in [CACHE_DIR, WHOIS_CACHE_DIR]:
    directory.mkdir(exist_ok=True)

# --- Database Initialization ---
def init_db():
    """Initialize SQLite databases if they don't exist."""
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

# Initialize databases
init_db()

# --- Database Helper Functions ---
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
        st.warning(f"⚠️ Database error: {str(e)}. Run the auditor app first to create data.")
        return {} if table == "audits" else None
    finally:
        conn.close()

def load_cache():
    """Load audit cache from SQLite."""
    return load_from_db(DB_FILE, "audits") or {}

def filter_recent_entries(cache, days=7):
    """Filter cache entries from the last N days."""
    cutoff_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    return {k: v for k, v in cache.items() if v.get("audit_date", "") >= cutoff_date}

def get_last_n_entries(cache, n=10):
    """Get the last N entries from the cache."""
    sorted_entries = sorted(cache.items(), key=lambda x: x[1].get("audit_date", ""), reverse=True)
    return dict(sorted_entries[:n])

def generate_full_csv(cache):
    """Generate a CSV of all audit data in the cache."""
    csv_data = []
    for domain, data in cache.items():
        url = data["url"]
        audit_date = data["audit_date"]
        benchmarks = data["benchmarks"]

        # Technical checks
        for check_name, check_data in data["technical"]["checks"].items():
            csv_data.append({
                "page_url": url, "audit_date": audit_date, "audit_type": "Technical",
                "section": "Performance & Security", "check": check_name.replace("_", " ").title(),
                "status": check_data["status"], "what_i_found": check_data["issue"] or "No issues",
                "why_it_matters": "Critical for security" if check_data["status"] == "Critical" else "Improves robustness",
                "recommendation": "Fix immediately" if check_data["status"] == "Critical" else "Review and improve",
                "priority": check_data["status"], "score": data["technical"]["score"],
                "benchmark": benchmarks.get("technical", 70), "vs_benchmark": "Above" if data["technical"]["score"] > benchmarks.get("technical", 70) else "Below"
            })

        # Business Info checks
        for check_name, check_data in data["business"]["checks"].items():
            csv_data.append({
                "page_url": url, "audit_date": audit_date, "audit_type": "Business Info",
                "section": "Business Presentation", "check": check_name.replace("_", " ").title(),
                "status": check_data["status"], "what_i_found": check_data["issue"] or "No issues",
                "why_it_matters": "Critical for trust" if check_data["status"] == "Critical" else "Improves credibility",
                "recommendation": "Add missing information" if check_data["status"] != "Good" else "None",
                "priority": check_data["status"], "score": data["business"]["score"],
                "benchmark": benchmarks.get("business", 70), "vs_benchmark": "Above" if data["business"]["score"] > benchmarks.get("business", 70) else "Below"
            })

        # Functional checks
        for check_name, check_data in data["functional"]["checks"].items():
            csv_data.append({
                "page_url": url, "audit_date": audit_date, "audit_type": "Functional",
                "section": "Functional Gaps", "check": check_name.replace("_", " ").title(),
                "status": check_data["status"], "what_i_found": check_data["issue"] or "No issues",
                "why_it_matters": "Critical for conversions" if check_data["status"] == "Critical" else "Improves user experience",
                "recommendation": "Implement missing functionality" if check_data["status"] != "Good" else "None",
                "priority": check_data["status"], "score": data["functional"]["score"],
                "benchmark": benchmarks.get("functional", 70), "vs_benchmark": "Above" if data["functional"]["score"] > benchmarks.get("functional", 70) else "Below"
            })

        # SEO checks
        for check_name, check_data in data["seo"]["checks"].items():
            csv_data.append({
                "page_url": url, "audit_date": audit_date, "audit_type": "SEO",
                "section": "SEO & Visibility", "check": check_name.replace("_", " ").title(),
                "status": check_data["status"], "what_i_found": check_data["issue"] or "No issues",
                "why_it_matters": "Critical for visibility" if check_data["status"] == "Critical" else "Improves rankings",
                "recommendation": "Optimize for search engines" if check_data["status"] != "Good" else "None",
                "priority": check_data["status"], "score": data["seo"]["score"],
                "benchmark": benchmarks.get("seo", 70), "vs_benchmark": "Above" if data["seo"]["score"] > benchmarks.get("seo", 70) else "Below"
            })

        # Budget Red Flags checks
        for check_name, check_data in data["budget"]["checks"].items():
            csv_data.append({
                "page_url": url, "audit_date": audit_date, "audit_type": "Budget Red Flags",
                "section": "Budget & Resources", "check": check_name.replace("_", " ").title(),
                "status": check_data["status"], "what_i_found": check_data["issue"] or "No issues",
                "why_it_matters": "Indicates low digital investment" if check_data["status"] != "Good" else "No concerns",
                "recommendation": "Invest in digital presence" if check_data["status"] != "Good" else "None",
                "priority": check_data["status"], "score": data["budget"]["score"],
                "benchmark": benchmarks.get("budget", 70), "vs_benchmark": "Above" if data["budget"]["score"] > benchmarks.get("budget", 70) else "Below"
            })

        # Dead End checks
        for check_name, check_data in data["dead_end"]["checks"].items():
            csv_data.append({
                "page_url": url, "audit_date": audit_date, "audit_type": "Dead End Detection",
                "section": "Domain Health", "check": check_name.replace("_", " ").title(),
                "status": check_data["status"], "what_i_found": check_data["issue"] or "No issues",
                "why_it_matters": "Critical for business continuity" if check_data["status"] == "Critical" else "No immediate risk",
                "recommendation": "Renew domain immediately" if check_data["status"] == "Critical" else "Monitor domain status",
                "priority": check_data["status"], "score": data["dead_end"]["score"],
                "benchmark": 100, "vs_benchmark": "Above" if data["dead_end"]["score"] == 100 else "Below"
            })

        # Growth Signals
        growth_signals = data["growth"]["growth_signals"]
        if growth_signals:
            csv_data.append({
                "page_url": url, "audit_date": audit_date, "audit_type": "Growth Signals",
                "section": "Growth Indicators", "check": "Growth Signals Detected",
                "status": "Good", "what_i_found": "; ".join(growth_signals),
                "why_it_matters": "Indicates active business growth",
                "recommendation": "Leverage growth momentum",
                "priority": "Good", "score": 100,
                "benchmark": "N/A", "vs_benchmark": "N/A"
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

    for domain, data in cache.items():
        scores = {
            "Technical": data["technical"]["score"],
            "Business Info": data["business"]["score"],
            "Functional": data["functional"]["score"],
            "SEO": data["seo"]["score"],
            "Budget": data["budget"]["score"],
            "Dead End": data["dead_end"]["score"]
        }
        worst_category = min(scores, key=scores.get)
        pain_points[worst_category + " Issues" if worst_category != "Dead End" else "Dead End Risks"].append(data["url"])

    # Convert to DataFrame
    painpoint_data = []
    for category, urls in pain_points.items():
        for url in urls:
            painpoint_data.append({
                "Pain Point": category,
                "URL": url,
                "Count": len(urls)
            })
    return pd.DataFrame(painpoint_data)

# --- Main Dashboard App ---
def main():
    st.set_page_config(page_title="Paw à Peau Audit Dashboard", layout="wide", page_icon="📊")
    st.title("📊 Paw à Peau Website Audit Dashboard")
    st.markdown("""
    **Overview:**
    - **Benchmarks**: Compare scores across industries.
    - **Trends**: Track changes over the last 7 days.
    - **Recent Entries**: View the last 10 audited websites.
    - **Download Reports**: Get detailed CSV files for analysis.
    """)

    # Load cache from SQLite
    cache = load_cache()
    if not cache:
        st.warning("⚠️ No audit data found. Run the auditor app first to generate data.")
        st.stop()

    # --- Benchmarks by Industry ---
    st.subheader("📈 Industry Benchmarks")
    industry_data = []
    for domain, data in cache.items():
        industry = data.get("industry_keyword", "Other")
        industry_data.append({
            "Industry": industry,
            "Technical": data["technical"]["score"],
            "Business Info": data["business"]["score"],
            "Functional": data["functional"]["score"],
            "SEO": data["seo"]["score"],
            "Budget": data["budget"]["score"],
            "Dead End": data["dead_end"]["score"],
            "Growth Signals": len(data["growth"]["growth_signals"])
        })

    if industry_data:
        industry_df = pd.DataFrame(industry_data)
        avg_by_industry = industry_df.groupby("Industry").mean().reset_index()

        # Plot average scores by industry
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
                "Date": data["audit_date"],
                "URL": data["url"],
                "Technical": data["technical"]["score"],
                "Business Info": data["business"]["score"],
                "Functional": data["functional"]["score"],
                "SEO": data["seo"]["score"],
                "Budget": data["budget"]["score"],
                "Dead End": data["dead_end"]["score"]
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
                "URL": data["url"],
                "Date": data["audit_date"],
                "Industry": data["industry_keyword"],
                "Technical": data["technical"]["score"],
                "Business Info": data["business"]["score"],
                "Functional": data["functional"]["score"],
                "SEO": data["seo"]["score"],
                "Budget": data["budget"]["score"],
                "Dead End": data["dead_end"]["score"],
                "Growth Signals": ", ".join(data["growth"]["growth_signals"]) if data["growth"]["growth_signals"] else "None"
            })

        last_10_df = pd.DataFrame(last_10_data)
        st.dataframe(last_10_df, use_container_width=True)

    # --- Downloadable Reports ---
    st.subheader("📥 Download Reports")

    # Full Audit CSV
    full_csv_df = generate_full_csv(cache)
    if not full_csv_df.empty:
        csv_full = full_csv_df.to_csv(index=False)
        st.download_button(
            label="📥 Download Full Audit CSV",
            data=csv_full,
            file_name=f"full_audit_report_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
            mime="text/csv"
        )

    # Pain Point Shortlists CSV
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

    for domain, data in cache.items():
        scores = {
            "Technical": data["technical"]["score"],
            "Business Info": data["business"]["score"],
            "Functional": data["functional"]["score"],
            "SEO": data["seo"]["score"],
            "Budget": data["budget"]["score"],
            "Dead End": data["dead_end"]["score"]
        }
        worst_category = min(scores, key=scores.get)
        if worst_category == "Technical":
            pain_points["Technical Issues"].append(data["url"])
        elif worst_category == "Business Info":
            pain_points["Business Info Gaps"].append(data["url"])
        elif worst_category == "Functional":
            pain_points["Functional Gaps"].append(data["url"])
        elif worst_category == "SEO":
            pain_points["SEO Weaknesses"].append(data["url"])
        elif worst_category == "Budget":
            pain_points["Budget Constraints"].append(data["url"])
        elif worst_category == "Dead End":
            pain_points["Dead End Risks"].append(data["url"])

    for category, urls in pain_points.items():
        if urls:
            with st.expander(f"{category} ({len(urls)} websites)"):
                for url in urls:
                    st.write(f"- {url}")

if __name__ == "__main__":
    main()