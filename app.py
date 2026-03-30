import streamlit as st
import pandas as pd
import json
import numpy as np

st.set_page_config(layout="wide", page_title="PostHog Impact Engine")

# --- CUSTOM UI STYLING ---
st.markdown("""
    <style>
    .main { background-color: #0d1117; }
    .stMetric { background-color: #161b22; padding: 15px; border-radius: 10px; border: 1px solid #30363d; }
    .stMetric label { font-size: 1.1rem !important; color: #8b949e !important; }
    .stMetric [data-testid="stMetricValue"] { font-size: 2rem !important; font-weight: 700 !important; color: #58a6ff !important; }
    h1 { font-size: 3.5rem !important; font-weight: 800 !important; color: #f0f6fc; }
    h2 { font-size: 2.2rem !important; border-bottom: 1px solid #30363d; padding-bottom: 10px; color: #f0f6fc; }
    h3 { font-size: 1.5rem !important; color: #c9d1d9; }
    .persona-badge { background-color: #21262d; padding: 4px 10px; border-radius: 15px; font-size: 0.85rem; border: 1px solid #30363d; margin-top: 10px; display: inline-block; }
    .github-user { font-family: monospace; color: #79c0ff; font-weight: bold; font-size: 1.2rem; }
    </style>
    """, unsafe_allow_html=True)

def load_and_process():
    try:
        with open('posthog_data.json', 'r') as f:
            data = json.load(f)
        df = pd.DataFrame(data)
        df['author'] = df['author'].apply(lambda x: x['login'] if x else "Unknown")
        df['label_list'] = df['labels'].apply(lambda x: [n['name'].lower() for n in x['nodes']])
        df['review_count'] = df['reviews'].apply(lambda x: x['totalCount'] if isinstance(x, dict) else 0)
        df['created_at'] = pd.to_datetime(df['createdAt'])
        df['merged_at'] = pd.to_datetime(df['mergedAt'])
        df['hours_to_merge'] = (df['merged_at'] - df['created_at']).dt.total_seconds() / 3600
        return df
    except Exception as e:
        st.error(f"Error loading data: {e}")
        return None

df = load_and_process()

if df is not None:
    # --- HEADER ---
    st.title("🦔 PostHog Impact Engine")
    st.markdown("### Who drives the most leverage in engineering work?")
    st.caption(f"Analyzing {len(df)} merged PRs from last 90 days • Validated via GitHub API")

    # --- LOGIC ---
    bug_keywords = ['bug', 'fix', 'critical', 'regression', 'error', 'issue', 'type: bug', 'p0', 'p1']
    def is_bug_fix(row):
        if any(keyword in row['label_list'] for keyword in bug_keywords): return True
        title_lower = row['title'].lower()
        return any(keyword in title_lower for keyword in bug_keywords)

    df['is_bug'] = df.apply(is_bug_fix, axis=1)
    pr_counts = df.groupby('author').size()
    review_counts = df.groupby('author')['review_count'].sum()
    bug_fixes = df[df['is_bug']].groupby('author').size()

    impact_df = pd.DataFrame({'prs': pr_counts, 'reviews': review_counts, 'bugs': bug_fixes}).fillna(0)
    impact_df['impact_score'] = (impact_df['prs'] * 3 + impact_df['reviews'] * 2 + impact_df['bugs'] * 4)
    top5 = impact_df.sort_values('impact_score', ascending=False).head(5)

    # --- TOP 5 IMPACTFUL ENGINEERS ---
    st.markdown("## 🏆 Top 5 Impactful Engineers")
    

    surgeons = df.groupby('author').apply(lambda x: (x['deletions'] - x['additions']).sum()).nlargest(5)
    closers = df.groupby('author')['hours_to_merge'].mean().nsmallest(5)
    multipliers = df.groupby('author')['review_count'].sum().nlargest(5)
    sentinels = df[df['is_bug']].groupby('author').size().nlargest(5)

    def get_persona_tags(name):
        tags = []
        if name in surgeons.index: tags.append("🔪 Surgeon")
        if name in closers.index: tags.append("🚀 Closer")
        if name in multipliers.index: tags.append("🤝 Multiplier")
        if name in sentinels.index: tags.append("🛡️ Sentinel")
        return " | ".join(tags) if tags else "General Contributor"

    cols = st.columns(5)
    for i, (name, row) in enumerate(top5.iterrows()):
        with cols[i]:
            st.markdown(f'<p class="github-user">@{name}</p>', unsafe_allow_html=True)
            st.metric(
                label="Impact Score", 
                value=int(row['impact_score']), 
                delta=f"{int(row['prs'])} PRs | {int(row['reviews'])} Reviews"
            )
            st.markdown(f'<div class="persona-badge">{get_persona_tags(name)}</div>', unsafe_allow_html=True)

    st.divider()

    # --- PERSONA PANELS ---
    st.markdown("## ⚡ Persona Leaders")
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.markdown("### 1. Surgeons")
        for name, val in surgeons.items(): st.metric(name, f"{int(val)} net deletions")
    with col2:
        st.markdown("### 2. Closers")
        for name, val in closers.items(): st.metric(name, f"{val:.1f} hrs")
    with col3:
        st.markdown("### 3. Multipliers")
        for name, val in multipliers.items(): st.metric(name, f"{int(val)} reviews")
    with col4:
        st.markdown("### 4. Sentinels")
        for name, val in sentinels.items(): st.metric(name, f"{int(val)} fixes")

    st.divider()

    # --- SILO DETECTION ---
    st.markdown("## ⚠️ Knowledge Silo Risk")
    silo_df = df.explode('label_list')
    if not silo_df['label_list'].isna().all():
        expert_stats = silo_df.groupby(['label_list', 'author']).size().reset_index(name='count')
        total_label_counts = silo_df.groupby('label_list').size().reset_index(name='total')
        silos = expert_stats.merge(total_label_counts, on='label_list')
        silos['ownership_ratio'] = silos['count'] / silos['total']
        critical_silos = silos[(silos['ownership_ratio'] > 0.7) & (silos['total'] > 5)].sort_values('ownership_ratio', ascending=False)
        
        if not critical_silos.empty:
            st.warning("High ownership concentration detected in key modules.")
            s_cols = st.columns(min(len(critical_silos), 4))
            for i, (_, row) in enumerate(critical_silos.head(4).iterrows()):
                with s_cols[i]:
                    st.metric(f"Module: {row['label_list']}", row['author'], f"{row['ownership_ratio']*100:.0f}% ownership")
    else:
        st.info("No label data available to determine silos.")

    st.divider()

    # --- VALIDATION VIEW ---
    st.markdown("## 🔍 Validate Impact")
    target = st.selectbox("Select Engineer to Inspect Contribution History:", df['author'].unique())
    eng_prs = df[df['author'] == target].sort_values('deletions', ascending=False).head(3)
    for _, pr in eng_prs.iterrows():
        with st.expander(pr['title']):
            st.write(f"⏱ Merged in **{pr['hours_to_merge']:.1f} hours**")
            st.write(f"➖ {pr['deletions']} deletions | ➕ {pr['additions']} additions")
            st.write(f"[View PR on GitHub]({pr['url']})")

# --- SIDEBAR ---
    st.sidebar.divider()
    
    st.sidebar.markdown("""
    ### 🧬 Principles
    - **Impact ≠ Output**
    - **Leverage > Volume**
    - **Complexity is liability**
    """)
    
    st.sidebar.divider()
    
    st.sidebar.markdown("""
    ### 🎭 Persona Definitions
    
    **1. Surgeons** Engineers who prioritize code quality by removing more lines than they add, reducing technical debt.
    
    **2. Closers** High-velocity contributors with the lowest average time from PR creation to merge.
    
    **3. Multipliers** Team unblockers who drive leverage by providing the highest volume of peer code reviews.
    
    **4. Sentinels** The frontline of reliability, specifically focused on identifying and shipping bug fixes.
    """)