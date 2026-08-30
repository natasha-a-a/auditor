import streamlit as st
import pandas as pd
import json
import requests
from pathlib import Path
from datetime import datetime, timedelta
import plotly.express as px
import io
import numpy as np

# --- Constants ---
GITHUB_REPO = "natasha-a-a/auditor"
GITHUB_BRANCH = "main"
GITHUB_RAW_BASE = f"https://raw.githubusercontent.com/{GITHUB_REPO}/{GITHUB_BRANCH}"
GITHUB_AUDIT_CSV_URL = f"{GITHUB_RAW_BASE}/audit_cache/audits.csv"
GITHUB_BENCHMARK_CSV_URL = f"{GITHUB_RAW_BASE}/benchmark_websites.csv"  # New: Benchmark websites CSV

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

def load_benchmark_websites():
    """Load benchmark websites from GitHub CSV."""
    df = fetch_csv_from_github(GITHUB_BENCHMARK_CSV_URL)
    if df.empty:
        return set()
    return set(df['url'].tolist())

def load_github_cache():
    """Load audit cache from GitHub CSV."""
    df = fetch_csv_from_github(GITHUB_AUDIT_CSV_URL)
    if df.empty:
        return {}
    benchmark_websites = load_benchmark_websites()
    return {
        row["domain"]: {
            **json.loads(row["data"]),
            "timestamp": row["timestamp"],
            "is_benchmark": row["domain"] in benchmark_websites  # Mark benchmark websites
        }
        for _, row in df.iterrows()
    }

# --- Data Processing Functions ---
def filter_user_audits(cache):
    """Filter out benchmark websites, return only user-submitted audits."""
    return {k: v for k, v in cache.items() if not v.get("is_benchmark", False)}

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
                    "why_it_matters": get_why_it_matters(category, check_data.get("status")),
                    "recommendation": get_recommendation(category, check_data.get("status")),
                    "business_impact": get_business_impact(category, check_name),
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
                "business_impact": "Prevents business disruption" if check_data.get("status") == "Critical" else "No immediate impact",
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
                "business_impact": "Competitive advantage through active growth",
                "priority": "Good",
                "score": 100,
                "benchmark": "N/A",
                "vs_benchmark": "N/A"
            })
    return pd.DataFrame(csv_data)

def get_why_it_matters(category, status):
    """Get why it matters text based on category and status."""
    if status == "Critical":
        return {
            "technical": "Critical for security and site stability",
            "business": "Critical for trust and credibility",
            "functional": "Critical for conversions and user experience",
            "seo": "Critical for search visibility and traffic",
            "budget": "Indicates high risk of digital failure"
        }.get(category, "Important for overall performance")
    return {
        "technical": "Improves site robustness and user experience",
        "business": "Enhances credibility and customer trust",
        "functional": "Boosts user engagement and conversions",
        "seo": "Increases organic search visibility",
        "budget": "Supports sustainable digital growth"
    }.get(category, "Contributes to better performance")

def get_recommendation(category, status):
    """Get recommendation text based on category and status."""
    if status == "Critical":
        return {
            "technical": "Fix immediately to prevent security breaches or downtime",
            "business": "Add missing information to build trust",
            "functional": "Implement missing functionality to improve conversions",
            "seo": "Optimize immediately to regain search visibility",
            "budget": "Invest in digital presence to avoid failure"
        }.get(category, "Address this issue urgently")
    return {
        "technical": "Review and improve for better performance",
        "business": "Enhance to strengthen credibility",
        "functional": "Consider adding to improve user experience",
        "seo": "Optimize for better search rankings",
        "budget": "Plan for future digital investments"
    }.get(category, "Consider improvements")

def get_business_impact(category, check_name):
    """Get business impact explanation for each check."""
    impacts = {
        "technical": {
            "slow_load_time": "Faster load times reduce bounce rates by up to 50% and improve conversion rates by 7%",
            "mobile_unfriendly": "Mobile-optimized sites see 2x higher conversion rates from mobile users",
            "broken_links": "Each broken link costs potential customers and harms SEO rankings",
            "no_ssl": "HTTPS sites rank higher in search and build user trust",
            "outdated_tech": "Modern frameworks improve performance, security, and maintainability"
        },
        "business": {
            "no_contact_info": "Clear contact info increases lead generation by 40%",
            "no_about_page": "About pages build trust and improve conversion rates by 30%",
            "no_testimonials": "Testimonials increase conversions by 34% on average",
            "no_case_studies": "Case studies help close 70% more deals",
            "no_team_page": "Team pages humanize your brand and build credibility"
        },
        "functional": {
            "no_contact_form": "Contact forms generate 5-10x more leads than email links",
            "no_rfq": "RFQ forms qualify leads and increase sales by 20%",
            "no_ecommerce": "E-commerce enables 24/7 sales without staff",
            "no_blog": "Blogs generate 55% more website visitors",
            "no_appointment": "Online booking increases appointments by 40%"
        },
        "seo": {
            "no_meta_tags": "Proper meta tags improve click-through rates by 30%",
            "no_alt_text": "Alt text improves accessibility and SEO rankings",
            "no_sitemap": "Sitemaps help search engines index your site 50% faster",
            "poor_keywords": "Targeted keywords increase organic traffic by 100-200%",
            "no_backlinks": "Quality backlinks improve search rankings significantly"
        },
        "budget": {
            "diy_website": "Professional sites convert 2-3x better than DIY solutions",
            "no_updates": "Regular updates prevent security vulnerabilities and improve performance",
            "no_analytics": "Analytics data helps optimize marketing spend by 20-30%",
            "no_seo_investment": "SEO provides the best long-term ROI of any marketing channel",
            "no_paid_ads": "Paid ads can generate immediate traffic while SEO builds"
        }
    }
    return impacts.get(category, {}).get(check_name, "Improving this aspect will enhance your digital presence and business results")

def generate_painpoint_csv(cache):
    """Generate a CSV of websites categorized by primary pain point."""
    user_cache = filter_user_audits(cache)
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
    for domain, data in user_cache.items():
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
    st.title("📊 Paw à Peau Website Audit Dashboard")

    # Debug: Show GitHub URLs
    st.write(f"🔗 Fetching audits from: {GITHUB_AUDIT_CSV_URL}")
    st.write(f"🔗 Fetching benchmarks from: {GITHUB_BENCHMARK_CSV_URL}")

    # Manual refresh button
    if st.button("🔄 Refresh Data from GitHub"):
        st.rerun()

    # Load data
    cache = load_github_cache()
    if not cache:
        st.warning("⚠️ No audit data found. Run the auditor app and commit CSV files to GitHub first.")
        st.stop()

    user_cache = filter_user_audits(cache)
    if not user_cache:
        st.warning("⚠️ No user-submitted audits found. Only benchmark websites exist in the data.")
        st.stop()

    st.markdown("""
    **Overview:**
    - **Benchmarks**: Compare scores across industries.
    - **Trends**: Track changes over the last 7 days.
    - **Recent Entries**: View the last 10 user-submitted audited websites.
    - **In-Depth Analysis**: Detailed scorecard for the last audited website.
    - **Download Reports**: Get detailed CSV files for analysis.
    """)

    # Get last audited website for in-depth analysis
    last_audit_entries = get_last_n_entries(cache, n=1)
    if last_audit_entries:
        last_domain, last_data = next(iter(last_audit_entries.items()))

        # --- In-Depth Scorecard for Last Audited Website ---
        st.subheader(f"🔍 In-Depth Analysis: {last_data.get('url', 'N/A')}")

        st.markdown(f"**Industry:** {last_data.get('industry_keyword', 'Other')} | **Date:** {last_data.get('audit_date', last_data.get('timestamp', 'N/A'))}")

        # Scorecard with explanations
        st.markdown("### 📊 Detailed Scorecard")

        categories = [
            ("technical", "🔧 Technical", "Performance & Security"),
            ("business", "🏢 Business Info", "Business Presentation"),
            ("functional", "🛠️ Functional", "Functional Gaps"),
            ("seo", "🔍 SEO", "SEO & Visibility"),
            ("budget", "💰 Budget", "Budget & Resources"),
            ("dead_end", "🚨 Dead End", "Domain Health")
        ]

        for cat_key, icon, section in categories:
            with st.expander(f"{icon} {section} (Score: {format_score(last_data.get(cat_key, {}).get('score', 0))}/100)"):
                st.markdown(f"**Section Score:** {format_score(last_data.get(cat_key, {}).get('score', 0))}/100")

                checks = last_data.get(cat_key, {}).get("checks", {})
                if checks:
                    for check_name, check_data in checks.items():
                        st.markdown(f"**{check_name.replace('_', ' ').title()}**")
                        st.write(f"- **Status:** {check_data.get('status', 'N/A')}")
                        st.write(f"- **What I Found:** {check_data.get('issue', 'No issues')}")
                        st.write(f"- **Why It Matters:** {get_why_it_matters(cat_key, check_data.get('status'))}")
                        st.write(f"- **Recommendation:** {get_recommendation(cat_key, check_data.get('status'))}")
                        st.write(f"- **Business Impact:** {get_business_impact(cat_key, check_name)}")
                        st.markdown("---")
                else:
                    st.info("No specific checks recorded for this category.")

                # Benchmark comparison
                benchmark = last_data.get("benchmarks", {}).get(cat_key, 70)
                delta = last_data.get(cat_key, {}).get("score", 0) - benchmark
                st.metric(
                    "Benchmark Comparison",
                    f"{format_score(last_data.get(cat_key, {}).get('score', 0))} vs {format_score(benchmark)}",
                    delta=f"{delta:+.1f}",
                    delta_color="normal"
                )

        # Growth signals
        growth_signals = last_data.get("growth", {}).get("growth_signals", [])
        if growth_signals:
            st.success("✅ **Growth Signals Detected:** " + ", ".join(growth_signals))
        else:
            st.warning("⚠️ **No Growth Signals Detected**")

        st.markdown("---")

    # --- Last 10 User-Submitted Audited Websites ---
    st.subheader("📋 Last 10 User-Submitted Audited Websites")
    last_10_entries = get_last_n_entries(cache, n=10)

    if last_10_entries:
        # Download all user audits button
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

        # Display table
        st.dataframe(last_10_df, use_container_width=True)

        # Individual download buttons for each of the last 10
        st.markdown("### 📥 Individual In-Depth Reports")
        for domain, data in last_10_entries.items():
            col1, col2 = st.columns([4, 1])
            with col1:
                st.markdown(f"**{data.get('url', 'N/A')}** - {data.get('audit_date', 'N/A')}")
            with col2:
                individual_df = generate_full_csv({domain: data})
                if not individual_df.empty:
                    csv_individual = individual_df.to_csv(index=False)
                    st.download_button(
                        label=f"Download {data.get('url', 'N/A')[:20]}... Report",
                        data=csv_individual,
                        file_name=f"audit_{data.get('url', 'website').replace('https://', '').replace('/', '_')}_{datetime.now().strftime('%Y%m%d')}.csv",
                        mime="text/csv",
                        key=f"download_{domain}"
                    )

        # --- Statistical Comparison of Last 10 ---
        st.subheader("📊 Statistical Comparison (Last 10 User Audits)")

        # Collect all scores by category
        category_scores = {
            "Technical": [],
            "Business Info": [],
            "Functional": [],
            "SEO": [],
            "Budget": [],
            "Dead End": []
        }

        for domain, data in last_10_entries.items():
            for cat in category_scores.keys():
                score = data.get(cat.lower().replace(" ", "_"), {}).get("score", 0)
                category_scores[cat].append(score)

        # Calculate and display statistics
        stats_df = pd.DataFrame({
            category: calculate_statistics(scores)
            for category, scores in category_scores.items()
        }).T

        st.dataframe(stats_df.style.format("{:.2f}"), use_container_width=True)

        # Visualize comparison
        fig = px.box(category_scores, labels={"value": "Score", "variable": "Category"})
        fig.update_layout(title="Score Distribution Across Last 10 Audits")
        st.plotly_chart(fig, use_container_width=True)

    # --- Benchmarks by Industry (User Audits Only) ---
    st.subheader("📈 Industry Benchmarks (User Audits Only)")
    industry_data = []
    for domain, data in user_cache.items():
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
                     title="Average Scores by Industry (User Audits Only)", barmode="group")
        st.plotly_chart(fig, use_container_width=True)
        st.dataframe(avg_by_industry, use_container_width=True)

    # --- Trends Over Last 7 Days (User Audits Only) ---
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
                "Budget": data.get("budget", {}).get("score", 0),
                "Dead End": data.get("dead_end", {}).get("score", 0)
            })
        trend_df = pd.DataFrame(trend_data)
        if not trend_df.empty:
            fig = px.line(trend_df, x="Date", y=["Technical", "Business Info", "Functional", "SEO", "Budget"],
                          title="Score Trends Over Time (User Audits Only)", markers=True)
            st.plotly_chart(fig, use_container_width=True)
            st.dataframe(trend_df, use_container_width=True)

    # --- Pain Point Shortlists (User Audits Only) ---
    st.subheader("🎯 Websites by Primary Pain Point (User Audits Only)")
    painpoint_csv_df = generate_painpoint_csv(cache)
    if not painpoint_csv_df.empty:
        st.dataframe(painpoint_csv_df, use_container_width=True)

if __name__ == "__main__":
    main()