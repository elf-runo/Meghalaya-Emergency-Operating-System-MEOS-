import streamlit as st
import pandas as pd
import numpy as np
import sqlite3
import json
import time
import random
import math
import requests
import altair as alt
from datetime import datetime
from streamlit_js_eval import streamlit_js_eval, get_geolocation

# ==========================================
# MODULE 1: CORE ARCHITECTURE & DB SPINE
# ==========================================

# 1. Page Configuration
st.set_page_config(
    page_title="MEOS: Meghalaya Emergency Operating System", 
    page_icon="🚑", 
    layout="wide", 
    initial_sidebar_state="expanded"
)

# 2. High-End Modern UI CSS Injection (Glassmorphism & Dashboard styling)
st.markdown("""
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
    /* Modern Health-Tech Theme */
    html, body, [class*="css"] {font-family: 'Inter', sans-serif;}
    .card { background: #ffffff; border: 1px solid #e2e8f0; border-radius: 12px; padding: 20px; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05); margin-bottom: 16px; transition: transform 0.2s ease; }
    .card:hover { transform: translateY(-2px); box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.1); }
    .kpi { background: #f8fafc; border-left: 4px solid #3b82f6; border-radius: 8px; padding: 16px; }
    .kpi .label { color: #64748b; font-size: 0.85rem; font-weight: 600; text-transform: uppercase; }
    .kpi .value { font-size: 2rem; font-weight: 700; color: #0f172a; margin-top: 4px; }
    .badge { padding: 6px 12px; border-radius: 20px; font-size: 0.8rem; font-weight: 600; }
    .stMetric { background: white; padding: 15px; border-radius: 8px; border: 1px solid #eee; }
    .stTabs [data-baseweb="tab-list"] { gap: 8px; }
    .stTabs [data-baseweb="tab"] { border-radius: 8px 8px 0 0; padding: 10px 20px; }
</style>
""", unsafe_allow_html=True)

# 3. Robust Database Initialization & Functions
DB_NAME = 'meos_persistence.db'

def init_db():
    """Initializes the SQLite database to store state-wide referral data permanently."""
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS cases (
            id TEXT PRIMARY KEY, 
            data TEXT, 
            triage TEXT, 
            cost REAL, 
            status TEXT, 
            dest TEXT, 
            is_private INTEGER, 
            ts REAL
        )
    ''')
    conn.commit()
    conn.close()

def save_case(obj):
    """Saves or updates a case dict in the SQLite database."""
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    case_id = obj.get('id', f"SYS-{int(time.time())}")
    data_json = json.dumps(obj)
    triage = obj.get('triage', 'UNRATED')
    cost = obj.get('cost', obj.get('fare', 0.0))
    status = obj.get('status', 'Pending')
    dest = obj.get('dest', 'Unassigned')
    is_private = int(obj.get('is_private', False))
    ts = obj.get('ts', time.time())
    
    c.execute('''
        INSERT OR REPLACE INTO cases (id, data, triage, cost, status, dest, is_private, ts)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (case_id, data_json, triage, cost, status, dest, is_private, ts))
    conn.commit()
    conn.close()

def get_cases(filter_status=None, filter_dest=None):
    """Retrieves cases from the database with optional filtering."""
    conn = sqlite3.connect(DB_NAME)
    query = "SELECT data FROM cases WHERE 1=1"
    params = []
    if filter_status:
        if isinstance(filter_status, list):
            placeholders = ','.join(['?'] * len(filter_status))
            query += f" AND status IN ({placeholders})"
            params.extend(filter_status)
        else:
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
    return [json.loads(row[0]) for row in rows]

init_db()

# 4. Data Caching Layer (Performance Optimization)
@st.cache_data
def load_datasets():
    """Loads CSV files robustly, stopping the app with clear errors if missing."""
    try:
        fac_df = pd.read_csv('data/meghalaya_facilities.csv')
        icd_df = pd.read_csv('data/icd_catalogue.csv')
        icd_df['icd10'] = icd_df['icd10'].astype(str).str.strip()
        return fac_df, icd_df
    except FileNotFoundError as e:
        st.error(f"🚨 Data File Missing: {str(e)}")
        st.warning("Please ensure 'meghalaya_facilities.csv' and 'icd_catalogue.csv' are placed in a folder named 'data' in your repository root.")
        st.stop()

facilities_df, icd_catalogue_df = load_datasets()

# 5. Live Geolocation Integration
def fetch_user_location():
    """Uses streamlit_js_eval to ping the browser's GPS for the Citizen SOS tab."""
    try:
        loc = get_geolocation()
        if loc and 'coords' in loc:
            return loc['coords']['latitude'], loc['coords']['longitude']
    except:
        pass
# ==========================================
# MODULE 2: THE CLINICAL BRAIN (DUAL-VECTOR TRIAGE)
# ==========================================

def _num(x):
    """Helper to safely convert inputs to floats."""
    if x is None or str(x).strip() == "": 
        return None
    try: 
        return float(x)
    except: 
        return None

# --- 1. Physiological Scoring Systems ---

def calc_NEWS2(rr, spo2, sbp, hr, temp, avpu="A"):
    """Calculates Adult National Early Warning Score 2."""
    rr, spo2, sbp, hr, temp = _num(rr), _num(spo2), _num(sbp), _num(hr), _num(temp)
    score = 0
    
    if sbp:
        if sbp <= 90 or sbp >= 220: score += 3
        elif sbp <= 100: score += 2
        elif sbp <= 110: score += 1
    if hr:
        if hr <= 40 or hr >= 131: score += 3
        elif hr <= 50 or hr >= 111: score += 1
    if spo2:
        if spo2 <= 91: score += 3
        elif spo2 <= 93: score += 2
        elif spo2 <= 95: score += 1
    if rr:
        if rr <= 8 or rr >= 25: score += 3
        elif rr >= 21: score += 2
        elif rr <= 11: score += 1
    if temp:
        if temp <= 35.0: score += 3
        elif temp >= 39.1: score += 2
        elif temp <= 36.0 or temp >= 38.1: score += 1
        
    if avpu != "A": 
        score += 3
        
    is_urgent = (score >= 7) or (avpu != "A")
    return score, is_urgent

def calc_MEOWS(hr, rr, sbp, temp, spo2):
    """Calculates Maternal Early Obstetric Warning Score."""
    hr, rr, sbp, temp, spo2 = _num(hr), _num(rr), _num(sbp), _num(temp), _num(spo2)
    red = []
    yellow = []
    
    if sbp:
        if sbp < 90 or sbp > 160: red.append("SBP critical")
        elif sbp > 140 or sbp < 100: yellow.append("SBP warning")
    if hr:
        if hr > 120 or hr < 50: red.append("HR critical")
        elif hr > 100 or hr < 60: yellow.append("HR warning")
    if spo2:
        if spo2 < 94: red.append("SpO2 <94%")
    
    return {"red": red, "yellow": yellow}

def calc_PEWS(age, rr, hr, spo2):
    """Calculates simplified Pediatric Early Warning Score."""
    sc = 0
    if hr and hr > 160: sc += 2
    if rr and rr > 50: sc += 2
    if spo2 and spo2 < 92: sc += 2
    return sc, (sc >= 6)

# --- 2. Master Triage Logic ---

def validated_triage_decision(vitals, icd_df_row, context):
    """
    Dual-Vector Triage Matrix: 
    Integrates Pathological Overrides with dynamically selected Physiological Safety Nets.
    """
    # ==========================================
    # VECTOR 1: PATHOLOGICAL OVERRIDE (Auto-Red)
    # ==========================================
    
    # Exhaustive Tier 1 Activation List mapped to the 100-row catalog
    complete_auto_red_codes = {
        'O72.0', 'O72.1', 'O14.1', 'O15.0', 'O71.1', 'O85', 'O44.1', 'O00.1', 'O88.2',  # Maternal
        'S06.5', 'S06.4', 'S36.1', 'S36.0', 'S27.3', 'S12.9', 'S32.1', 'S02.1', 'T07', 'T31.2', 'T17.9', # Trauma
        'I21.9', 'I46.9', 'I44.2', 'I47.2', 'I26.9', 'I33.0', # Cardiac
        'I63.9', 'I61.9', 'I60.9', 'G46.3', 'I62.9', 'G00.9', 'G04.9', 'G06.0', # Stroke/Neuro
        'A41.9', 'R57.1', 'A41.0', 'A41.5', 'A39.2', 'R57.2', 'K65.0', # Sepsis/Shock
        'P07.3', 'P22.0', 'P36.9', 'P21.9', 'P10.2', 'P52.9', # Neonatal
        'J96.0', 'T65.9', 'T63.0', 'N17.9', 'E10.1', 'K56.6', 'K92.2', 'A82.9' # Other Critical
    }
    
    critical_interventions = ["Defibrillation", "Surfactant", "Thrombolysis", "Neuro checks", "Cardioversion", "Chest tube", "Crossmatch"]
    required_interventions = str(icd_df_row.get('default_interventions', ""))
    
    # Trigger Auto-Red if condition or required interventions are time-critical
    if any(c in required_interventions for c in critical_interventions) or icd_df_row.get('icd10') in complete_auto_red_codes:
        return "RED", {
            "driver": "Pathology", 
            "reason": f"Level 1 Critical Diagnosis: {icd_df_row.get('label')}", 
            "ews": "Bypassed - Immediate Transport Required"
        }

    # ==========================================
    # VECTOR 2: PHYSIOLOGICAL SAFETY NET
    # ==========================================
    age = context.get('age', 30)
    is_pregnant = (icd_df_row.get('bundle') == 'Maternal') or context.get('pregnant', False)
    
    urgent = False
    score = 0
    ews_type = ""

    # Route to the correct scoring system based on patient context
    if age < 18:
        score, urgent = calc_PEWS(age, vitals.get('rr'), vitals.get('hr'), vitals.get('spo2'))
        ews_type = "PEWS"
    elif is_pregnant:
        meows_res = calc_MEOWS(vitals.get('hr'), vitals.get('rr'), vitals.get('sbp'), vitals.get('temp'), vitals.get('spo2'))
        urgent = len(meows_res['red']) > 0
        score = len(meows_res['red']) + len(meows_res['yellow'])
        ews_type = "MEOWS"
    else:
        score, urgent = calc_NEWS2(vitals.get('rr'), vitals.get('spo2'), vitals.get('sbp'), vitals.get('hr'), vitals.get('temp'), vitals.get('avpu', 'A'))
        ews_type = "NEWS2"

    # Final logic evaluation
    if urgent: 
        return "RED", {"driver": "Physiology", "reason": f"Clinical Instability ({ews_type} triggers met)", "ews": score}
    elif score >= 5: 
        return "YELLOW", {"driver": "Physiology", "reason": f"Elevated Risk ({ews_type}: {score})", "ews": score}
    
    return "GREEN", {"driver": "Physiology", "reason": f"Hemodynamically Stable ({ews_type}: {score})", "ews": score}
    
# ==========================================
# MODULE 3: THE LOGISTICAL ENGINE
# ==========================================

# --- 1. Routing & Topography ---

def dist_km(lat1, lon1, lat2, lon2):
    """Haversine formula to calculate straight-line distance (Offline Fallback)."""
    R = 6371  # Earth radius in km
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    return R * c

def get_ors_route(lat1, lon1, lat2, lon2, api_key=""):
    """
    Fetches live routing from OpenRouteService. 
    If internet drops, falls back to Haversine Topographical estimation.
    """
    try:
        if api_key:
            res = requests.post(
                "https://api.openrouteservice.org/v2/directions/driving-car", 
                json={"coordinates": [[lon1, lat1], [lon2, lat2]]}, 
                headers={'Authorization': api_key}, 
                timeout=3 # Strict timeout to ensure app doesn't hang in bad network areas
            ).json()
            
            dist_m = res['features'][0]['properties']['segments'][0]['distance']
            dur_s = res['features'][0]['properties']['segments'][0]['duration']
            
            return {
                'km': dist_m / 1000.0, 
                'min': dur_s / 60.0, 
                'offline': False
            }
    except Exception:
        pass
    
    # OFFLINE FALLBACK: Straight line distance adjusted for Meghalaya hills (approx 30km/h)
    km = dist_km(lat1, lon1, lat2, lon2)
    return {
        'km': km, 
        'min': (km / 30.0) * 60.0, 
        'offline': True
    }

# --- 2. Dynamic Pricing & Fleet Allocation ---

def calculate_transit_fare(vehicle_type, distance_km, duration_min, is_offline_fallback=False):
    """Pre-Locked Topographical Pricing Matrix for Guaranteed Driver Payouts."""
    base_fares = {"ALS": 1500.0, "BLS": 500.0, "TAXI": 100.0}
    per_km_rates = {"ALS": 40.0, "BLS": 20.0, "TAXI": 15.0}
    
    base_fare = base_fares.get(vehicle_type, 100.0)
    km_rate = per_km_rates.get(vehicle_type, 15.0)
    
    terrain_multiplier = 1.0
    
    # Adjust multiplier based on data source and terrain difficulty
    if is_offline_fallback:
        terrain_multiplier = 1.8 # Haversine undercalculates winding hill roads
    else:
        if distance_km > 0:
            mins_per_km = duration_min / distance_km
            if mins_per_km > 3.0:    # < 20 km/h avg (Steep/Bad Road)
                terrain_multiplier = 1.5
            elif mins_per_km > 2.0:  # < 30 km/h avg (Winding Road)
                terrain_multiplier = 1.25

    calculated_fare = base_fare + (distance_km * km_rate * terrain_multiplier)
    final_fare = round(calculated_fare / 50) * 50 # Clean payout rounding
    
    return final_fare

def allocate_ambulance_type(triage_color, required_interventions, eta_minutes):
    """3-Tier Fleet Allocation: Protects ALS units and subsidizes Green cases via Taxi."""
    als_mandated_interventions = [
        "Defibrillation", "Cardioversion", "IV fluids", "IV Antibiotics", 
        "Magnesium sulfate", "Uterotonics", "Insulin infusion", "Vasopressors"
    ]
    
    needs_als_intervention = any(req in str(required_interventions) for req in als_mandated_interventions)
    
    # Gate 1: Pathological Requirement
    if needs_als_intervention:
        return "ALS", f"Required intervention mandates Paramedic unit."
        
    # Gate 2: Physiological Instability
    if triage_color == "RED":
        return "ALS", "Critical instability mandates ALS monitoring."
        
    # Gate 3: Topographical Degradation Risk
    if triage_color == "YELLOW" and eta_minutes > 45
# ==========================================
# MODULE 4: ROLE-BASED UI (Part 1)
# ==========================================

# --- Sidebar: Role-Based Access Control (RBAC) ---
st.sidebar.title("🔐 MEOS Login")
st.sidebar.markdown("Select your operational profile:")
role = st.sidebar.radio("Active Profile:", [
    "1. Citizen (SOS)", 
    "2. PHC (Doctor)", 
    "3. Ambulance (EMT)", 
    "4. Receiving Hub", 
    "5. State Command", 
    "6. Health Cab (Taxi Partner)"
])

st.sidebar.markdown("---")
st.sidebar.info("Data Backbone: Connected to SQLite Persistence & ORS Topography Engine.")

# ==========================================
# INTERFACE 1: CITIZEN (SOS)
# ==========================================
if role == "1. Citizen (SOS)":
    st.title("🆘 Emergency Request Portal")
    st.markdown("Request immediate medical assistance. Your location will be fetched automatically.")
    
    # Attempt to fetch live GPS via JavaScript (defined in Module 1)
    live_lat, live_lon = fetch_user_location()
    
    with st.form("citizen_sos_form"):
        st.subheader("Patient Details")
        c_name = st.text_input("Patient Name", placeholder="e.g., John Doe")
        c_age = st.number_input("Age", min_value=0, max_value=120, value=30)
        c_symp = st.text_area("What is the emergency?", placeholder="e.g., Severe chest pain, bleeding...")
        
        st.subheader("Location Data")
        col_lat, col_lon = st.columns(2)
        # Fallback to Shillong coordinates if GPS fetch fails
        with col_lat: lat = st.number_input("Latitude", value=live_lat if live_lat else 25.5788, format="%.6f")
        with col_lon: lon = st.number_input("Longitude", value=live_lon if live_lon else 91.8933, format="%.6f")
        
        submitted = st.form_submit_button("🚨 Request Emergency Dispatch", type="primary", use_container_width=True)
        
        if submitted:
            if not c_name or not c_symp:
                st.error("Please provide both name and emergency details.")
            else:
                case_id = f"SOS-{random.randint(10000, 99999)}"
                new_case = {
                    "id": case_id,
                    "patient": c_name,
                    "age": c_age,
                    "complaint": c_symp,
                    "lat": lat,
                    "lon": lon,
                    "status": "Awaiting Triage"
                }
                save_case(new_case)
                st.success(f"✅ Emergency signal transmitted. ID: {case_id}. Awaiting clinical triage.")

# ==========================================
# INTERFACE 2: PHC (DOCTOR)
# ==========================================
elif role == "2. PHC (Doctor)":
    st.title("🏥 PHC Clinical Triage Desk")
    
    pending_cases = get_cases(filter_status="Awaiting Triage")
    
    if not pending_cases:
        st.success("✅ No pending emergencies. All clear.")
    else:
        # Load the oldest pending case first
        active_case = pending_cases[-1] 
        
        st.markdown(f"""
        <div class="card" style="border-left: 5px solid #f59e0b;">
            <h3 style="margin-top:0;">Incoming SOS: {active_case['patient']} (Age: {active_case.get('age', 'N/A')})</h3>
            <p><strong>Complaint:</strong> {active_case['complaint']}</p>
        </div>
        """, unsafe_allow_html=True)
        
        with st.form("phc_triage_form"):
            st.subheader("1. Patient Vitals")
            v1, v2, v3, v4 = st.columns(4)
            with v1: hr = st.number_input("Heart Rate", 0, 250, 80)
            with v2: sbp = st.number_input("Systolic BP", 0, 300, 120)
            with v3: spo2 = st.number_input("SpO2 %", 50, 100, 98)
            with v4: rr = st.number_input("Resp Rate", 0, 60, 18)
            
            st.subheader("2. Clinical Diagnosis")
            # Dropdown populated by the CSV catalog
            dx_options = icd_catalogue_df['label'].tolist()
            selected_dx_label = st.selectbox("Suspected Pathology", dx_options)
            
            is_pregnant = st.checkbox("Patient is pregnant / postpartum")
            
            submit_triage = st.form_submit_button("⚡ Run Algorithm & Route Patient", type="primary", use_container_width=True)
            
            if submit_triage:
                # 1. Fetch complete ICD row
                icd_row = icd_catalogue_df[icd_catalogue_df['label'] == selected_dx_label].iloc[0]
                
                # 2. Run Dual-Vector Triage
                vitals = {'hr': hr, 'sbp': sbp, 'spo2': spo2, 'rr': rr, 'temp': 37.0, 'avpu': 'A'}
                context = {'age': active_case.get('age', 30), 'pregnant': is_pregnant}
                t_color, t_reason = validated_triage_decision(vitals, icd_row, context)
                
                # 3. Required Capabilities
                req_caps_str = str(icd_row.get('default_caps', ''))
                req_caps = [c.strip() for c in req_caps_str.split(';')] if req_caps_str and req_caps_str != 'nan' else []
                
                # 4. Find Best Facility (Gated Matrix)
                best_fac, best_score, best_det, best_route = None, -1, {}, {}
                
                for _, f in facilities_df.iterrows():
                    route = get_ors_route(active_case['lat'], active_case['lon'], float(f['lat']), float(f['lon']))
                    score, det = calculate_enhanced_facility_score_free(f.to_dict(), req_caps, route, t_color)
                    
                    if score > best_score: 
                        best_score, best_fac, best_det, best_route = score, f, det, route
                
                if best_fac is not None and best_score > 0:
                    # 5. Allocate Fleet & Calculate Fare
                    veh_type, veh_reason = allocate_ambulance_type(t_color, icd_row.get('default_interventions',''), best_route['min'])
                    fare = calculate_transit_fare(veh_type, best_route['km'], best_route['min'], best_route['offline'])
                    
                    # 6. Save Updated Case
                    is_pvt = best_fac['ownership'] == 'Private'
                    updated_case = active_case.copy()
                    updated_case.update({
                        "triage": t_color,
                        "dest": best_fac['name'],
                        "is_private": is_pvt,
                        "status": "Dispatched",
                        "veh": veh_type,
                        "fare": fare,
                        "dx": selected_dx_label,
                        "triage_reason": t_reason,
                        "route_offline": best_route['offline']
                    })
                    save_case(updated_case)
                    
                    st.success(f"✅ Patient successfully routed to {best_fac['name']}.")
                    
                    # --- EXPLAINABLE AI DROPDOWN ---
                    with st.expander("📊 Why was this facility & vehicle recommended? (Algorithm Logic)"):
                        st.markdown(f"**Triage Priority:** <span class='badge' style='background:{t_color.lower()}; color:white;'>{t_color}</span>", unsafe_allow_html=True)
                        st.markdown(f"**Clinical Driver:** {t_reason['driver']} - {t_reason['reason']}")
                        st.markdown("---")
                        st.markdown("#### Facility Match (Gated Matrix)")
                        st.markdown(f"✅ **Infrastructure Gate:** Passed. Facility possesses requested core capabilities.")
                        st.markdown(f"✅ **Capacity Gate:** Passed. Minimum required critical care beds are open.")
                        
                        traffic_txt = "Offline Estimation" if best_route['offline'] else "Live Traffic"
                        st.markdown(f"🚑 **Time-to-Definitive-Care:** {best_det.get('eta', 'N/A')} mins ({traffic_txt}). *(Score: {best_det.get('prox',0)}/50)*")
                        st.markdown(f"🛏️ **Surge Buffer:** {best_det.get('beds', 0)} open beds reduces diversion risk. *(Score: {best_det.get('bed_sc',0)}/15)*")
                        
                        if best_det.get('fisc', 0) > 0:
                            st.markdown(f"🏛️ **Fiscal Guardrail:** State-owned facility prioritized to prevent MHIS fund leakage. *(Score: {best_det.get('fisc',0)}/20)*")
                        else:
                            st.markdown(f"🏥 **Fiscal Guardrail:** Private facility. Utilized because state assets were out of range/capacity. *(Score: 0/20)*")
                        
                        st.markdown("---")
                        st.markdown("#### Logistics & Pricing")
                        st.markdown(f"**Vehicle Dispatched:** {veh_type} - {veh_reason}")
                        st.markdown(f"**Pre-Locked Driver Payout:** ₹{fare} (Topography multiplier applied: {best_route['offline']})")
                else:
                    st.error("❌ CRITICAL: No facility in the state matches the clinical safety gates for this patient.")

# ==========================================
# INTERFACE 6: HEALTH CAB (TAXI PARTNER)
# ==========================================
elif role == "6. Health Cab (Taxi Partner)":
    st.title("🚖 Health Cab Driver App")
    st.info("Authorized Non-Emergency Medical Transport")
    
    # Filter for GREEN cases allocated to TAXI that are waiting to be picked up
    taxi_jobs = [c for c in get_cases(filter_status="Dispatched") if c.get('veh') == 'TAXI' and c.get('triage') == 'GREEN']
    
    c1, c2, c3 = st.columns(3)
    c1.metric("Today's Rides", "4")
    c2.metric("State Subsidy Earned", "₹1,200")
    c3.metric("Fleet Status", "Available", "Online")
    
    st.markdown("---")
    st.subheader("📍 Nearby Ride Requests")
    
    if taxi_jobs:
        for job in taxi_jobs:
            # Privacy Shield: We do not display the diagnosis or vitals here!
            with st.container():
                st.markdown(f"""
                <div class="card" style="border-left: 5px solid #10b981;">
                    <h4>Passenger: {job['patient']}</h4>
                    <p><strong>Pickup:</strong> {job.get('lat', '25.57')}, {job.get('lon', '91.88')} <br>
                    <strong>Dropoff:</strong> {job['dest']} (Hospital Entrance)</p>
                    <p style="color: #64748b; font-size: 0.9rem;">Pre-Authorized State Payout: <strong>₹{job.get('fare', 250)}</strong></p>
                </div>
                """, unsafe_allow_html=True)
                
                col1, col2 = st.columns(2)
                with col1:
                    if st.button("Accept Ride & Pick Up", key=f"accept_{job['id']}", type="primary", use_container_width=True):
                        job['status'] = 'Taxi_Enroute'
                        save_case(job)
                        st.rerun()
                with col2:
                    st.button("Navigate (Maps)", key=f"nav_{job['id']}", use_container_width=True)
    else:
        st.success("No pending ride requests in your zone. Keep the app open.")
        
    # Show active rides the driver has accepted
    active_my_rides = [c for c in get_cases(filter_status="Taxi_Enroute")]
    if active_my_rides:
        st.markdown("### 🚗 Current Active Ride")
        for ride in active_my_rides:
            st.warning(f"Transporting {ride['patient']} to {ride['dest']}")
            if st.button("End Ride (Dropoff Complete)", key=f"drop_{ride['id']}", use_container_width=True):
                ride['status'] = 'Arrived'
                save_case(ride)
                st.success(f"Ride complete. ₹{ride.get('fare', 250)} queued for state payout.")
                time.sleep(2)
                st.rerun()

# ==========================================
# INTERFACE 3: AMBULANCE (EMT)
# ==========================================
elif role == "3. Ambulance (EMT)":
    st.title("🚑 EMT Transit Command Board")
    
    # Exclude TAXI jobs from the medical fleet board
    active_missions = [c for c in get_cases(["Dispatched", "EnRoute_Scene", "Arrive_Scene", "EnRoute_Dest"]) if c.get('veh') != 'TAXI']
    
    if not active_missions:
        st.success("✅ All units standing by. No active medical dispatches.")
    else:
        for r in active_missions:
            case_key = r['id']
            with st.container():
                st.markdown(f"""
                <div class="card" style="border-left: 5px solid {'#ef4444' if r.get('triage') == 'RED' else '#f59e0b'};">
                    <h3 style="margin-top:0;">{r.get('patient', 'Unknown')} | Priority: {r.get('triage', 'UNRATED')}</h3>
                    <p><strong>Destination:</strong> {r.get('dest', 'Unknown')} | <strong>Assigned Unit:</strong> {r.get('veh', 'BLS')}</p>
                    <p><strong>Diagnosis / Complaint:</strong> {r.get('dx', r.get('complaint', 'N/A'))}</p>
                </div>
                """, unsafe_allow_html=True)
                
                # Digital Handover & Transit Timeline
                st.markdown("**Transit Timeline:**")
                col1, col2, col3, col4 = st.columns(4)
                
                status = r.get('status')
                with col1:
                    if st.button("📍 En Route to Scene", key=f"enrt_sc_{case_key}", disabled=(status != "Dispatched"), use_container_width=True):
                        r['status'] = "EnRoute_Scene"; save_case(r); st.rerun()
                with col2:
                    if st.button("🛑 Arrived at Scene", key=f"arr_sc_{case_key}", disabled=(status != "EnRoute_Scene"), use_container_width=True):
                        r['status'] = "Arrive_Scene"; save_case(r); st.rerun()
                with col3:
                    if st.button("🚑 En Route to Hospital", key=f"enrt_dst_{case_key}", disabled=(status != "Arrive_Scene"), use_container_width=True):
                        r['status'] = "EnRoute_Dest"; save_case(r); st.rerun()
                with col4:
                    if st.button("🏥 Arrived at Destination", key=f"arr_dst_{case_key}", disabled=(status != "EnRoute_Dest"), type="primary", use_container_width=True):
                        r['status'] = "Arrived"; save_case(r); st.success("Handover complete."); time.sleep(1); st.rerun()

# ==========================================
# INTERFACE 4: RECEIVING HUB (HOSPITAL)
# ==========================================
elif role == "4. Receiving Hub":
    st.title("🛏️ Hospital ER Board")
    
    hosp_options = facilities_df['name'].tolist()
    my_hosp = st.selectbox("Select Your Facility:", hosp_options)
    
    incoming = get_cases(["Dispatched", "EnRoute_Scene", "Arrive_Scene", "EnRoute_Dest"], filter_dest=my_hosp)
    
    if not incoming:
        st.info(f"No incoming ambulances currently routed to {my_hosp}.")
    else:
        st.error(f"🚨 {len(incoming)} Incoming Emergency Transfer(s) Detected!")
        for inc in incoming:
            st.markdown(f"""
            <div class="card" style="border-left: 5px solid #ef4444;">
                <h4>{inc['patient']} - {inc.get('triage', 'UNRATED')} Priority</h4>
                <p><strong>ETA Status:</strong> {inc['status'].replace('_', ' ')} | <strong>Vehicle:</strong> {inc.get('veh', 'Unknown')}</p>
                <p><strong>Suspected Pathology:</strong> {inc.get('dx', inc.get('complaint', 'Unknown'))}</p>
            </div>
            """, unsafe_allow_html=True)

# ==========================================
# INTERFACE 5: STATE COMMAND
# ==========================================
elif role == "5. State Command":
    st.title("🏛️ Ministry of Health Dashboard")
    
    all_cases = get_cases()
    if not all_cases:
        st.info("No system data available yet. Run a stress test or input a case via the PHC tab.")
    else:
        df = pd.DataFrame(all_cases)
        total_refs = len(df)
        pvt_diversions = len(df[df['is_private'] == 1])
        financial_leakage = pvt_diversions * 35000  # ₹35k assumed loss per private referral
        
        # --- High-Level KPIs ---
        c1, c2, c3 = st.columns(3)
        c1.metric("Total State Referrals", f"{total_refs:,}")
        c2.metric("Private Sector Diversions", f"{pvt_diversions:,}")
        c3.metric("MHIS Financial Leakage", f"₹{financial_leakage:,.0f}", delta="Capital Flight", delta_color="inverse")
        
        # --- System Operations & Stress Test ---
        st.markdown("---")
        st.subheader("⚙️ System Stress Test & Telemetry")
        
        col_stress, col_sms = st.columns(2)
        
        with col_stress:
            with st.container(border=True):
                st.markdown("#### 🌪️ Load Simulation")
                st.write("Simulate 1,000 algorithmic referrals to stress-test the Fiscal Guardrail and private network leakage.")
                if st.button("Run 1,000-Case Stress Test", use_container_width=True):
                    with st.spinner("Simulating state-wide load..."):
                        simulated_cases = []
                        for i in range(1000):
                            # Randomly pick a facility
                            f = facilities_df.sample(1).iloc[0]
                            is_pvt = (f['ownership'] == 'Private')
                            triage_val = random.choices(["RED", "YELLOW", "GREEN"], weights=[15, 35, 50])[0]
                            veh_val = "ALS" if triage_val == "RED" else ("TAXI" if triage_val == "GREEN" else "BLS")
                            
                            simulated_cases.append({
                                "id": f"SIM-{random.randint(100000, 999999)}",
                                "triage": triage_val,
                                "is_private": is_pvt,
                                "dest": f['name'],
                                "status": "Arrived",
                                "veh": veh_val,
                                "fare": random.randint(500, 3500),
                                "ts": time.time() - random.randint(100, 100000)
                            })
                        
                        # Batch insert for speed
                        conn = sqlite3.connect(DB_NAME)
                        c = conn.cursor()
                        for obj in simulated_cases:
                            c.execute("INSERT INTO cases (id, data, triage, cost, status, dest, is_private, ts) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                                      (obj['id'], json.dumps(obj), obj['triage'], obj['fare'], obj['status'], obj['dest'], int(obj['is_private']), obj['ts']))
                        conn.commit()
                        conn.close()
                    st.success("Test Complete!")
                    time.sleep(1)
                    st.rerun()
                    
                if st.button("🗑️ Clear Database", type="secondary", use_container_width=True):
                    conn = sqlite3.connect(DB_NAME)
                    conn.execute("DELETE FROM cases")
                    conn.commit()
                    conn.close()
                    st.rerun()

        # --- SMS Gateway Simulator ---
        with col_sms:
            with st.container(border=True):
                st.markdown("#### 📡 Zero-Internet SMS Gateway")
                st.write("Simulate an incoming 2G text from a remote, offline PHC.")
                
                # Default text simulates a ruptured uterus from Williamnagar
                sms_payload = st.text_input("Incoming Text String:", value="SOS F007 O71.1 130 85 96")
                
                if st.button("Process SMS via USSD/Gateway", type="primary", use_container_width=True):
                    try:
                        parts = sms_payload.strip().split()
                        if len(parts) != 6 or parts[0].upper() != "SOS":
                            st.error("❌ Invalid format. Use: SOS [FacID] [ICD] [HR] [SBP] [SpO2]")
                        else:
                            fac_id, icd_code = parts[1], parts[2]
                            hr, sbp, spo2 = float(parts[3]), float(parts[4]), float(parts[5])
                            
                            # Lookup Data
                            referrer = facilities_df[facilities_df['facility_id'] == fac_id].iloc[0]
                            icd_row = icd_catalogue_df[icd_catalogue_df['icd10'] == icd_code].iloc[0]
                            
                            # Run Triage silently
                            vitals = {'hr': hr, 'sbp': sbp, 'spo2': spo2, 'rr': 20, 'temp': 37.0}
                            t_color, _ = validated_triage_decision(vitals, icd_row, {'age': 30})
                            
                            # Output result
                            st.success(f"✅ SMS Parsed. {icd_code} mapped to {t_color} Priority.")
                            st.info(f"📱 Auto-Reply Sent to {referrer['name']}: 'MEOS ALERT: {t_color} Priority logged for {icd_code}. Unit Dispatched. Monitor Vitals.'")
                            
                    except Exception as e:
                        st.error(f"❌ Processing failed. Ensure Facility ID and ICD code exist in your data. ({str(e)})")
                        
        # --- Analytics Chart ---
        st.markdown("### Referral Distribution by Triage & Sector")
        chart_data = df.groupby(['triage', 'is_private']).size().reset_index(name='count')
        chart_data['Sector'] = chart_data['is_private'].apply(lambda x: 'Private' if x == 1 else 'Government')
        
        chart = alt.Chart(chart_data).mark_bar().encode(
            x=alt.X('triage:N', sort=["RED", "YELLOW", "GREEN"], title="Triage Priority"),
            y=alt.Y('count:Q', title="Number of Cases"),
            color=alt.Color('Sector:N', scale=alt.Scale(domain=['Government', 'Private'], range=['#3b82f6', '#ef4444'])),
            tooltip=['triage', 'Sector', 'count']
        ).properties(height=350)
        
        st.altair_chart(chart, use_container_width=True)
