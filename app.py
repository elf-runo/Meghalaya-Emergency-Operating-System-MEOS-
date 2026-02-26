import streamlit as st
import pandas as pd
import numpy as np
import altair as alt
import sqlite3
import json
import time
import random
from streamlit_js_eval import get_geolocation

# === STYLING & CONFIG ===
st.set_page_config(page_title="MEOS: Meghalaya Command", layout="wide")
st.markdown("""<style>.stMetric { background: white; padding: 20px; border-radius: 10px; border: 1px solid #eee; }</style>""", unsafe_allow_value=True)

# === DATABASE PERSISTENCE (The Digital Spine) ===
def init_db():
    conn = sqlite3.connect('meos_persistence.db')
    c = conn.cursor()
    c.execute('CREATE TABLE IF NOT EXISTS cases (id TEXT PRIMARY KEY, data TEXT, triage TEXT, cost REAL, ts REAL)')
    conn.commit()
    conn.close()

def save_case(obj):
    conn = sqlite3.connect('meos_persistence.db')
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO cases VALUES (?, ?, ?, ?, ?)",
              (obj['id'], json.dumps(obj), obj['triage'], obj['cost'], time.time()))
    conn.commit()
    conn.close()

init_db()

# === THE INBUILT ALGORITHM (Decision Engine) ===
def run_triage_algo(hr, sbp, spo2, icd_code):
    # Clinical NEWS2 Logic
    score = 0
    if sbp < 90 or spo2 < 92: score = 7 # RED
    elif sbp < 100 or hr > 110: score = 5 # YELLOW
    color = "RED" if score >= 7 else "YELLOW" if score >= 5 else "GREEN"
    
    # Capability Logic
    icd_df = pd.read_csv('data/icd_catalogue.csv')
    dx = icd_df[icd_df['icd10'] == icd_code].iloc[0]
    return {"color": color, "label": dx['label'], "caps": dx['default_caps'].split(';'), "interventions": dx['default_interventions'].split(';')}

# === UI TABS ===
t1, t2, t3 = st.tabs(["🏛️ Executive Dashboard", "🚑 Dispatch Center", "⚙️ Admin & Scale"])

with t1:
    st.title("Meghalaya Health Ministry: Policy Oversight")
    conn = sqlite3.connect('meos_persistence.db')
    df_raw = pd.read_sql_query("SELECT * FROM cases", conn)
    conn.close()

    if not df_raw.empty:
        df = pd.DataFrame([json.loads(x) for x in df_raw['data']])
        
        m1, m2, m3 = st.columns(3)
        m1.metric("Active Referrals", len(df))
        m2.metric("Private Diversions", len(df[df['is_private'] == True]))
        m3.metric("Financial Leakage", f"₹{df[df['is_private'] == True]['cost'].sum():,.0f}", delta="Action Required")

        
        
        chart = alt.Chart(df).mark_bar().encode(x='triage:N', y='sum(cost):Q', color='is_private:N')
        st.altair_chart(chart, use_container_width=True)

with t2:
    st.subheader("🔴 Live Case Management")
    with st.form("live_entry"):
        c1, c2 = st.columns(2)
        with c1:
            name = st.text_input("Patient Name")
            icd_df = pd.read_csv('data/icd_catalogue.csv')
            dx_label = st.selectbox("Diagnosis", icd_df['label'].tolist())
            code = icd_df[icd_df['label'] == dx_label]['icd10'].values[0]
        with c2:
            sbp = st.number_input("Systolic BP", 120)
            spo2 = st.number_input("SpO2 %", 98)
        
        if st.form_submit_button("Run Algorithm & Match"):
            res = run_triage_algo(80, sbp, spo2, code)
            st.success(f"Algorithm Result: {res['color']} PRIORITY")
            st.write(f"Recommended Interventions: {', '.join(res['interventions'])}")

with t3:
    st.subheader("Stress Test Engine")
    if st.button("🚀 Simulate 1,000 State-Wide Emergencies"):
        with st.spinner("Processing massive load..."):
            for i in range(1000):
                # Simulated diverse cases across Meghalaya
                t_color = random.choice(["RED", "YELLOW", "GREEN"])
                is_pvt = random.choice([True, False])
                case = {
                    "id": f"SIM-{i}", "triage": t_color, "is_private": is_pvt,
                    "cost": (45000 if t_color == "RED" else 5000) * (3.5 if is_pvt else 1.0)
                }
                save_case(case)
        st.rerun()
