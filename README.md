# 🚑 MEOS: Meghalaya Emergency Operating System v2.0

> **A State-Wide, AI-Optimized Clinical Routing & Fiscal Guardrail Platform**

MEOS is a comprehensive health-tech infrastructure designed specifically for the topography and healthcare economics of Meghalaya. It transitions emergency referral management from a fragmented, phone-based system to a unified, data-driven "Command Center."

## 🏛️ Executive Summary

Currently, the state's healthcare system suffers from two critical inefficiencies during emergencies:
1. **Clinical Delays:** Manual routing of trauma and maternal emergencies often results in patients being sent to facilities lacking the necessary capabilities (e.g., Blood Banks, Neurosurgeons), wasting the "Golden Hour."
2. **Financial Leakage (The MHIS Drain):** Due to a lack of real-time visibility into public ICU/Bed capacity, patients are frequently diverted to Private Tertiary Hubs unnecessarily. 

**The MEOS Solution:**
MEOS utilizes an inbuilt algorithm that combines validated clinical scoring (NEWS2, MEOWS, PEWS, qSOFA) with real-time OpenRouteService (ORS) API GPS routing. It matches the patient's ICD-10 diagnosis to the nearest facility *actually capable* of saving their life, prioritizing government assets to protect the state budget.

---

## 💰 The Fiscal Guardrail: ₹35,000 ROI Logic

MEOS is designed to be a revenue-positive asset for the State Health Ministry.

* **The Problem:** When a RED-triaged patient is diverted to a private hospital, the state pays a commercial package rate via the Meghalaya Health Insurance Scheme (MHIS) (Avg. ₹50,000). When treated in a public hospital, the marginal cost to the state is primarily consumables (Avg. ₹15,000).
* **The Savings:** By using algorithmic routing to find available public beds that a human dispatcher might miss, **the state saves approximately ₹35,000 per optimized referral.**
* **The Scale:** The built-in "State-Wide Stress Test" demonstrates how preventing just 15% of unnecessary private diversions across 25,000 annual emergencies can return crores to the state health budget.

---

## ⚙️ Core Technical Features

* **Advanced Clinical Triaging:** Integrates standard emergency early warning scores (NEWS2 for adults, MEOWS for maternal, PEWS for pediatrics) to remove human bias from life-or-death decisions.
* **100-Point ICD-10 Intelligence:** Maps over 100 severe diagnoses directly to the requisite facility capabilities (e.g., automatically knowing a *Ruptured Uterus* requires an `OBGYN_OT` and `BloodBank`).
* **Real-Time GPS Routing:** Uses the OpenRouteService (ORS) API to calculate exact driving times across Meghalaya's winding terrain, falling back to Haversine geographic algorithms if network connectivity drops.
* **Role-Based Access Control (RBAC):** Tailored, low-latency interfaces for Citizens (SOS), PHC Doctors, Ambulance EMTs, Receiving Hospitals, and State Command.
* **Crash-Proof Persistence:** Powered by an embedded SQLite database to ensure no referral is lost during network blips or page refreshes.

---

## 🚀 Quick Start Installation (For Evaluators)

To run the MEOS platform locally on your machine:

**1. Clone the repository**
```bash
git clone [https://github.com/elf-runo/Meghalaya-Emergency-Operating-System-MEOS-.git](https://github.com/elf-runo/Meghalaya-Emergency-Operating-System-MEOS-.git)
cd Meghalaya-Emergency-Operating-System-MEOS-
