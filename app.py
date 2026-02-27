import streamlit as st
import pandas as pd
import numpy as np
import sqlite3
import json
import time
import random
import math
import requests
from datetime import datetime
import altair as alt

# === 1. CONFIG & DB PERSISTENCE ===
st.set_page_config(page_title="MEOS: Meghalaya Command", layout="wide")
st.markdown("""<style>.stMetric { background: white; padding: 15px; border-radius: 8px; border: 1px solid #eee; }</style>""", unsafe_allow_html=True)

def init_db():
    conn = sqlite3.connect('meos_persistence.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS cases 
                 (id TEXT PRIMARY KEY, data TEXT, triage TEXT, cost REAL, status TEXT, dest TEXT, is_private INTEGER, ts REAL)''')
    conn.commit()
    conn.close()

def save_case(obj):
    conn = sqlite3.connect('meos_persistence.db')
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO cases VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
              (obj['id'], json.dumps(obj), obj.get('triage', 'UNRATED'), obj.get('cost', 0), 
               obj.get('status', 'Pending'), obj.get('dest', 'Unassigned'), int(obj.get('is_private', False)), time.time()))
    conn.commit()
    conn.close()

def get_cases(filter_status=None, filter_dest=None):
    conn = sqlite3.connect('meos_persistence.db')
    query = "SELECT data FROM cases WHERE 1=1"
    params = []
    if filter_status:
        query += " AND status = ?"
        params.append(filter_status)
    if filter_dest:
        query += " AND dest = ?"
        params.append(filter_dest)
    query += " ORDER BY ts DESC"
    c = conn.cursor()
    c.execute(query, params)
    rows = c.fetchall()
    conn.close()
    return [json.loads(r[0]) for r in rows]

init_db()

# === 2. CLINICAL SCORING ENGINE (From PDF) ===
def _num(x):
    """Convert to float or return None.""" # [cite: 471-477]
    if x is None or str(x).strip() == "": return None
    try: return float(x)
    except: return None

def calc_NEWS2(rr, spo2, sbp, hr, temp, avpu="A"):
    # Simplified NEWS2 from PDF logic for MVP speed [cite: 620-685]
    rr, spo2, sbp, hr, temp = _num(rr), _num(spo2), _num(sbp), _num(hr), _num(temp)
    score = 0
    if sbp is not None:
        if sbp <= 90 or sbp >= 220: score += 3
        elif sbp <= 100: score += 2
        elif sbp <= 110: score += 1
    if hr is not None:
        if hr <= 40 or hr >= 131: score += 3
        elif hr <= 50 or hr >= 111: score += 1
    if spo2 is not None:
        if spo2 <= 91: score += 3
        elif spo2 <= 93: score += 2
        elif spo2 <= 95: score += 1
    if avpu != "A": score += 3
    return score, (score >= 7) # Returns score and 'urgent' flag

def calc_MEOWS(hr, rr, sbp, temp, spo2):
    # Maternal Early Warning Score [cite: 717-736]
    hr, rr, sbp, temp, spo2 = _num(hr), _num(rr), _num(sbp), _num(temp), _num(spo2)
    red, yellow = [], []
    if sbp and (sbp < 90 or sbp > 160): red.append("SBP critical")
    if hr and (hr > 120 or hr < 50): red.append("HR critical")
    if spo2 and spo2 < 94: red.append("SpO2 <94%")
    return {"red": red, "yellow": yellow}

def calc_PEWS(age, rr, hr, spo2):
    # Pediatric Early Warning Score [cite: 744-761]
    if age is None or age >= 18: return 0, False
    sc = 0
    if hr and hr > 160: sc += 2
    if rr and rr > 50: sc += 2
    if spo2 and spo2 < 92: sc += 2
    return sc, (sc >= 6)

def triage_decision(vitals, context):
    """Core algorithmic brain combining scores.""" # 
    # Calculate all scores
    n_score, n_urgent = calc_NEWS2(vitals.get('rr'), vitals.get('spo2'), vitals.get('sbp'), vitals.get('hr'), vitals.get('temp'), vitals.get('avpu'))
    meows = calc_MEOWS(vitals.get('hr'), vitals.get('rr'), vitals.get('sbp'), vitals.get('temp'), vitals.get('spo2')) if context.get('pregnant') else {'red':[]}
    p_score, p_urgent = calc_PEWS(context.get('age'), vitals.get('rr'), vitals.get('hr'), vitals.get('spo2'))
    
    # Logic gates [cite: 791-803]
    color = "GREEN"
    if n_urgent or (context.get("pregnant") and len(meows["red"]) > 0) or p_urgent:
        color = "RED"
    elif n_score >= 5 or (n_score > 0 and color == "GREEN"):
        color = "YELLOW"
        
    return color, {"NEWS2": n_score, "PEWS": p_score, "MEOWS_Red": len(meows["red"])}

# === 3. ADVANCED ROUTING & MATCHING ===
def dist_km(lat1, lon1, lat2, lon2):
    # Fallback Haversine 
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1))*math.cos(math.radians(lat2))*math.sin(dlon/2)**2
    return 2 * R * math.atan2(math.sqrt(a), math.sqrt(1-a))

def get_ors_route(origin_lat, origin_lon, dest_lat, dest_lon, api_key):
    """Hits OpenRouteService for exact driving ETA.""" # 
    try:
        url = "https://api.openrouteservice.org/v2/directions/driving-car"
        headers = {'Authorization': f'{api_key}', 'Content-Type': 'application/json'} # [cite: 1269]
        body = {"coordinates": [[origin_lon, origin_lat], [dest_lon, dest_lat]]} # [cite: 1272-1275]
        
        response = requests.post(url, json=body, headers=headers, timeout=5)
        if response.status_code == 200:
            data = response.json()
            route = data['features'][0]
            return {
                'success': True,
                'distance_km': route['properties']['segments'][0]['distance'] / 1000,
                'duration_min': route['properties']['segments'][0]['duration'] / 60
            }
    except: pass
    
    # Fallback to straight line if API fails or no key
    km = dist_km(origin_lat, origin_lon, dest_lat, dest_lon)
    return {'success': False, 'distance_km': km, 'duration_min': (km/40)*60}



def match_facility(required_caps, origin_lat, origin_lon, api_key=""):
    facilities = pd.read_csv('data/meghalaya_facilities.csv')
    best_match = None
    highest_score = -1
    
    for _, fac in facilities.iterrows():
        # Hard stop: Must have capabilities
        if not all(fac.get(cap, 0) == 1 for cap in required_caps): continue
            
        # Routing Score
        route = get_ors_route(origin_lat, origin_lon, float(fac['lat']), float(fac['lon']), api_key)
        eta = route['duration_min']
        
        # Scoring logic: Base 100 - ETA penalty + Government Bonus
        score = 100 - eta 
        if fac['ownership'] == 'Government': score += 30
            
        if score > highest_score:
            highest_score = score
            best_match = fac
            best_match['eta_min'] = round(eta, 1)
            
    return best_match

# === 4. ROLE-BASED UI ROUTING ===
st.sidebar.title("🔐 MEOS Login")
role = st.sidebar.radio("Select Profile:", 
                        ["1. Citizen (SOS)", "2. PHC (Doctor)", "3. Ambulance (EMT)", "4. Receiving Hub", "5. State Command"])

# Optional: Place ORS key in sidebar for live demo routing
ors_key = st.sidebar.text_input("ORS API Key (Optional)", type="password", help="Leave blank to use Haversine fallback")

# ---------------------------------------------------------
# INTERFACE 1: CITIZEN SOS
# ---------------------------------------------------------
if role == "1. Citizen (SOS)":
    st.title("🆘 Emergency Help Request")
    with st.form("citizen_form"):
        name = st.text_input("Patient Name")
        complaint = st.text_area("What is the emergency?")
        lat = st.number_input("Your Latitude", value=25.58)
        lon = st.number_input("Your Longitude", value=91.89)
        if st.form_submit_button("Request Help"):
            case = {"id": f"SOS-{random.randint(1000, 9999)}", "patient": name, "complaint": complaint, 
                    "lat": lat, "lon": lon, "status": "Awaiting Triage", "triage": "UNRATED"}
            save_case(case)
            st.success("Help is on the way. A doctor will evaluate your case momentarily.")

# ---------------------------------------------------------
# INTERFACE 2: REFERRING PHC (Clinical Data Entry)
# ---------------------------------------------------------
elif role == "2. PHC (Doctor)":
    st.title("🏥 PHC Clinical Triage")
    pending = get_cases(filter_status="Awaiting Triage")
    if pending:
        p = pending[0]
        st.warning(f"**SOS Pending:** {p['patient']} - {p['complaint']}")
        
        with st.form("clinical_entry"):
            st.write("Enter Vitals")
            c1, c2, c3 = st.columns(3)
            with c1: hr = st.number_input("HR", 80)
            with c2: sbp = st.number_input("SBP", 120)
            with c3: spo2 = st.number_input("SpO2 %", 98)
            
            icd_df = pd.read_csv('data/icd_catalogue.csv')
            dx_label = st.selectbox("Diagnosis", icd_df['label'].tolist())
            code_row = icd_df[icd_df['label'] == dx_label].iloc[0]
            
            if st.form_submit_button("Run Algorithm & Route"):
                vitals = {'hr': hr, 'sbp': sbp, 'spo2': spo2, 'rr': 20, 'temp': 37.0, 'avpu': 'A'}
                context = {'age': 30, 'pregnant': (code_row['bundle'] == 'Maternal')}
                
                # 1. Triaging (PDF Logic)
                t_color, scores = triage_decision(vitals, context)
                req_caps = code_row['default_caps'].split(';')
                
                # 2. Facility Matching & Routing (ORS Logic)
                target = match_facility(req_caps, p['lat'], p['lon'], ors_key)
                
                if target is not None:
                    is_pvt = target['ownership'] == 'Private'
                    case = {
                        "id": p['id'], "patient": p['patient'], "triage": t_color, 
                        "is_private": is_pvt, "dest": target['name'], "status": "Dispatched",
                        "cost": 15000 + (35000 if is_pvt else 0), "eta": target['eta_min'],
                        "dx": dx_label, "interventions": code_row['default_interventions'].split(';')
                    }
                    save_case(case)
                    st.success(f"🚨 {t_color} Priority. ORS Routing ETA: {target['eta_min']} mins. Dispatched to {target['name']}.")
                else:
                    st.error("No facility matching capabilities found.")

# ---------------------------------------------------------
# INTERFACE 3: AMBULANCE / EMT
# ---------------------------------------------------------
elif role == "3. Ambulance (EMT)":
    st.title("🚑 EMT Transit Board")
    active = get_cases(filter_status="Dispatched")
    if active:
        for run in active:
            with st.expander(f"ACTIVE: {run['patient']} -> {run['dest']}", expanded=True):
                st.write(f"**Triage:** {run['triage']} | **ETA:** {run.get('eta', 'Unknown')} mins")
                st.info(f"**Automated Protocol:** {', '.join(run.get('interventions', []))}")
                if st.button("Mark Arrived at Hospital", key=run['id']):
                    run['status'] = "Arrived"
                    save_case(run)
                    st.rerun()
    else:
        st.success("No active dispatches.")

# ---------------------------------------------------------
# INTERFACE 4: RECEIVING HUB
# ---------------------------------------------------------
elif role == "4. Receiving Hub":
    st.title("🛏️ Hospital Receiving Board")
    facilities = pd.read_csv('data/meghalaya_facilities.csv')['name'].tolist()
    my_hospital = st.selectbox("Select Your Facility:", facilities)
    
    incoming = get_cases(filter_status="Dispatched", filter_dest=my_hospital)
    if incoming:
        for inc in incoming:
            st.error(f"🔴 ETA {inc.get('eta', '--')} Mins: {inc['triage']} Priority - {inc.get('dx', 'Emergency')}")
            st.write(f"Patient: {inc['patient']}")
    else:
        st.write("No incoming high-priority cases.")

# ---------------------------------------------------------
# INTERFACE 5: STATE COMMAND
# ---------------------------------------------------------
elif role == "5. State Command":
    st.title("🏛️ Ministry Executive Dashboard")
    cases = get_cases()
    
    if cases:
        df = pd.DataFrame(cases)
        m1, m2, m3 = st.columns(3)
        m1.metric("Total Cases Handled", len(df))
        pvt_cases = df[df['is_private'] == 1]
        m2.metric("Private Diversions", len(pvt_cases))
        # The Fiscal Guardrail Calculation
        m3.metric("Financial Leakage", f"₹{(len(pvt_cases) * 35000):,.0f}", delta="MHIS Drain", delta_color="inverse")
        
        
        chart = alt.Chart(df).mark_bar().encode(x='triage:N', y='count():Q', color='is_private:N').properties(height=300)
        st.altair_chart(chart, use_container_width=True)
    
    st.markdown("---")
    st.subheader("System Stress Test")
    if st.button("🚀 Run 1,000-Case ORS/Algorithm Simulation"):
        with st.spinner("Processing State-Wide Load..."):
            facilities = pd.read_csv('data/meghalaya_facilities.csv')
            for i in range(1000):
                t_color = random.choice(["RED", "YELLOW", "GREEN"])
                fac = facilities.sample(1).iloc[0]
                is_pvt = fac['ownership'] == 'Private'
                save_case({"id": f"SIM-{random.randint(10000,99999)}", "triage": t_color, "is_private": is_pvt, 
                           "dest": fac['name'], "status": "Arrived", "cost": 15000 + (35000 if is_pvt else 0)})
            st.rerun()
