import os
import datetime
import time
import requests
from requests.auth import HTTPBasicAuth
import streamlit as st
from google import genai
from google.genai import types

# 1. Page Config & Interface Setup
st.set_page_config(page_title="Trail Endurance Coach", page_icon="🏔️", layout="centered")

st.title("🏔️ Trail Endurance Coach")
st.subheader("Adaptive Analytics & Training Planner")

# ==========================================
# SECURE ACCESS TO ENVIRONMENT SECRETS
# ==========================================
try:
    os.environ["GEMINI_API_KEY"] = st.secrets["GEMINI_API_KEY"]
except KeyError:
    st.error("Configuration Error: Missing GEMINI_API_KEY in Streamlit Secrets.")
    st.stop()

# ==========================================
# MULTI-USER SIDEBAR AUTHENTICATION & CONTEXT
# ==========================================
with st.sidebar:
    st.header("⚙️ Athlete Setup")
    st.markdown("Connect your Intervals.icu account.")
    
    user_athlete_id = st.text_input("Athlete ID (e.g., i12345)")
    user_api_key = st.text_input("Intervals API Key", type="password")
    
    st.markdown("---")
    st.header("📋 Analysis Mode")
    analysis_mode = st.selectbox(
        "Select Coach Audit Focus:",
        [
            "Post-Workout Compliance (PM)", 
            "Morning Readiness Check (AM)", 
            "Weekly Performance Review"
        ]
    )
    
    st.markdown("---")
    st.header("📊 Training Context")
    microcycle_context = st.selectbox(
        "Current Microcycle:",
        ["Build Phase (Standard Load)", "Peak / Overload Phase", "Recovery / Deload Week", "Taper (Pre-Race)"]
    )
    
    st.markdown("---")
    st.caption("Locate credentials inside your Intervals.icu > Settings page.")

    if user_athlete_id and user_api_key:
        st.session_state.athlete_id = user_athlete_id
        st.session_state.api_key = user_api_key
    else:
        st.warning("Please enter your credentials to unlock the coach.")
       
    # ==========================================
    # NEW: X-RAY DEBUGGER BUTTON
    # ==========================================
    st.markdown("---")
    if st.button("🔍 Debug: Fetch Raw Wellness Data"):
        if st.session_state.get("athlete_id") and st.session_state.get("api_key"):
            now = datetime.datetime.now()
            oldest = (now - datetime.timedelta(days=2)).strftime('%Y-%m-%d')
            newest = now.strftime('%Y-%m-%d')
            url = f"https://intervals.icu/api/v1/athlete/{st.session_state.athlete_id}/wellness?oldest={oldest}&newest={newest}"
            try:
                resp = requests.get(url, auth=HTTPBasicAuth('API_KEY', st.session_state.api_key))
                if resp.status_code == 200:
                    st.json(resp.json())
                else:
                    st.error(f"API Error: {resp.status_code}")
            except Exception as e:
                st.error(f"Failed to connect: {str(e)}")
        else:
            st.warning("Enter your credentials above first.")

if "athlete_id" not in st.session_state or "api_key" not in st.session_state:
    st.info("👈 Please set up your Intervals.icu connection in the sidebar to begin your adaptive coaching session.")
    st.stop()

# ==========================================
# TOOL 1: PHYSIOLOGICAL WELLNESS METRICS
# ==========================================
def get_daily_wellness(days: int = 14) -> dict:
    """Fetches biological wellness markers (CTL, ATL, TSB, HRV, RHR) from Intervals.icu."""
    st.toast(f"📡 Coach is pulling your wellness data for the last {days} days...", icon="❤️")
    
    now = datetime.datetime.now()
    oldest_date = (now - datetime.timedelta(days=days)).strftime('%Y-%m-%d')
    newest_date = now.strftime('%Y-%m-%d')
    
    url = f"https://intervals.icu/api/v1/athlete/{st.session_state.athlete_id}/wellness?oldest={oldest_date}&newest={newest_date}"
    
    try:
        response = requests.get(url, auth=HTTPBasicAuth('API_KEY', st.session_state.api_key))
        if response.status_code == 200:
            recent_days = response.json() 
            
            wellness_log = []
            for d in recent_days:
                ctl = d.get("ctl", 0) or 0
                atl = d.get("atl", 0) or 0
                calculated_tsb = ctl - atl if (ctl or atl) else (d.get("form", 0) or 0)
                wellness_log.append({
                    "date": d.get("id"),
                    "fitness_ctl": ctl,
                    "fatigue_atl": atl,
                    "form_tsb": calculated_tsb,
                    "hrv_rmssd": d.get("hrv"),
                    "resting_hr": d.get("restingHR") or d.get("restingHr") or d.get("resting_hr") or d.get("icu_resting_hr"),
                    "sleep_hours": round(d.get("sleepSecs") / 3600, 1) if d.get("sleepSecs") else None,
                    "muscle_soreness": d.get("soreness"),
                    "fatigue_rating": d.get("fatigue")
                })
                
            return {"status": "success", "wellness_history": wellness_log}
        else:
            return {"status": "error", "message": f"Wellness API failed: {response.status_code}"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

# ==========================================
# TOOL 2: TRAINING ACTIVITIES PERFORMANCE AUDIT
# ==========================================
def get_weekly_activities(days: int = 7) -> dict:
    """Fetches completed raw activity logs from Intervals.icu."""
    st.toast(f"📡 Coach is pulling your activity logs for the last {days} days...", icon="🏃")
    
    now = datetime.datetime.now()
    cutoff_date = (now - datetime.timedelta(days=days)).strftime('%Y-%m-%d')
    newest_date = now.strftime('%Y-%m-%d')
    
    url = f"https://intervals.icu/api/v1/athlete/{st.session_state.athlete_id}/activities?oldest={cutoff_date}&newest={newest_date}"
    
    try:
        response = requests.get(url, auth=HTTPBasicAuth('API_KEY', st.session_state.api_key))
        if response.status_code == 200:
            raw_activities = response.json()
            
            processed_activities = []
            for act in raw_activities:
                moving_sec = act.get("moving_time", 0) or 0
                elev_gain = act.get("total_elevation_gain", 0) or 0
                avg_speed = act.get("average_speed", 0) or 0
                
                dist_km = round(act.get("distance", 0) / 1000, 2) if act.get("distance") else 0
                duration_hms = str(datetime.timedelta(seconds=moving_sec)) if moving_sec else "00:00:00"
                
                pace_str = "0:00"
                if avg_speed > 0:
                    pace_decimal = 16.6667 / avg_speed
                    p_min = int(pace_decimal)
                    p_sec = int((pace_decimal - p_min) * 60)
                    pace_str = f"{p_min}:{p_sec:02d}"
                
                hr_zones = act.get("icu_hr_zone_times", [])
                z1 = hr_zones[0] if len(hr_zones) > 0 else 0
                z2 = hr_zones[1] if len(hr_zones) > 1 else 0
                z3 = hr_zones[2] if len(hr_zones) > 2 else 0
                z4 = hr_zones[3] if len(hr_zones) > 3 else 0
                
                low_intensity_pct = 0.0
                gray_zone_pct = 0.0
                if moving_sec > 0:
                    low_intensity_pct = round(((z1 + z2) / moving_sec) * 100, 1)
                    gray_zone_pct = round(((z3 + z4) / moving_sec) * 100, 1)
                
                vam_m_per_hour = 0
                if moving_sec > 0 and elev_gain > 0:
                    vam_m_per_hour = round((elev_gain / moving_sec) * 3600)

                cardiac_drift = act.get("icu_pm_ftp_decoupling") or act.get("icu_hr_pw_decoupling") or act.get("decoupling") or 0
                
                processed_activities.append({
                    "id": act.get("id"),
                    "date": act.get("start_date_local", "")[:10],
                    "name": act.get("name"),
                    "type": act.get("type"),
                    "distance_km": dist_km,
                    "duration": duration_hms,
                    "pace_min_km": pace_str,
                    "training_load_tss": act.get("icu_training_load"),
                    "low_intensity_percentage": low_intensity_pct,
                    "gray_zone_percentage": gray_zone_pct,
                    "climbing_vam_m_hr": vam_m_per_hour,
                    "efficiency_factor": act.get("icu_efficiency"),
                    "cardiac_drift_decoupling_pct": cardiac_drift
                })
            return {"status": "success", "processed_completed_workouts": processed_activities}
        return {"status": "error", "message": f"Activities API failed: {response.status_code}"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

# ==========================================
# TOOL 3: UPCOMING TRAINING SCHEDULE
# ==========================================
def get_scheduled_workouts(days_ahead: int = 7) -> dict:
    """Fetches scheduled training calendar events directly from Intervals.icu."""
    st.toast(f"📅 Coach is downloading your upcoming calendar plan for the next {days_ahead} days...", icon="📅")
    
    now = datetime.datetime.now()
    today_str = now.strftime('%Y-%m-%d')
    future_str = (now + datetime.timedelta(days=days_ahead)).strftime('%Y-%m-%d')
    
    url = f"https://intervals.icu/api/v1/athlete/{st.session_state.athlete_id}/events?oldest={today_str}&newest={future_str}"
    
    try:
        response = requests.get(url, auth=HTTPBasicAuth('API_KEY', st.session_state.api_key))
        if response.status_code == 200:
            raw_events = response.json()
            scheduled = []
            
            for ev in raw_events:
                if ev.get("type") in ["Run", "Ride", "Swim", "Strength", "Gym"] or ev.get("category") == "WORKOUT":
                    scheduled.append({
                        "date": ev.get("start_date_local", "")[:10],
                        "name": ev.get("name"),
                        "type": ev.get("type") or ev.get("activity_type"),
                        "planned_duration": str(datetime.timedelta(seconds=ev.get("moving_time", 0))) if ev.get("moving_time") else "0:00:00",
                        "planned_distance_km": round((ev.get("distance", 0) or 0) / 1000, 2) if ev.get("distance") else 0,
                        "planned_load_tss": ev.get("icu_training_load") or ev.get("load") or 0,
                        "description": ev.get("description", "")
                    })
            return {"status": "success", "upcoming_schedule": scheduled}
        else:
            return {"status": "error", "message": f"Calendar API failed: {response.status_code}"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

# ==========================================
# 3. CHAT ENGINE & PERSISTENT SESSION STATE
# ==========================================
if "messages" not in st.session_state:
    st.session_state.messages = []

@st.cache_resource
def get_genai_client():
    return genai.Client()

client = get_genai_client()

@st.cache_resource
def load_knowledge_base():
    """Uploads the manual and ensures processing is finished before conversation initialization."""
    file_name = "Knowledge feed trail running.pdf" 
    if os.path.exists(file_name):
        uploaded_file = client.files.upload(file=file_name)
        while uploaded_file.state == "PROCESSING":
            time.sleep(2)
            uploaded_file = client.files.get(name=uploaded_file.name)
        return uploaded_file
    return None

knowledge_document = load_knowledge_base()

# Initialize the session ONLY if it doesn't exist OR if mode/microcycle changed
if ("chat_session" not in st.session_state or 
    st.session_state.get("current_mode") != analysis_mode or
    st.session_state.get("current_microcycle") != microcycle_context):
    
    st.session_state.current_mode = analysis_mode
    st.session_state.current_microcycle = microcycle_context
    st.session_state.pdf_attached = False  # Reset so we hand the PDF over cleanly on the first prompt
    
    # Customise system prompts dynamically based on the sidebar selectors
    if analysis_mode == "Morning Readiness Check (AM)":
        system_text = (
            "Purpose & Persona:\n"
            "You are an elite ultra-trail running and mountain endurance coach. Your role is to act as a morning sounding board. "
            "Your athlete is starting their day. You must run a Morning Readiness Check analyzing the last 14 days of wellness. "
            "Determine if they are cleared to train or if today's plan must be adjusted based on recovery metrics.\n\n"
            "Morning Audit Methodology Workflow:\n"
            "1. Autonomic System Drift: Compare today's HRV (rMSSD) and Resting HR against their rolling 7-day average. "
            "Identify deviations. Compare sleep metrics and muscle soreness ratings.\n"
            "2. Current Form (TSB): Check if TSB is entering severe overload zones (below -30) or if they are in optimal windows (-10 to -30).\n"
            "3. Actionable Workout Prescription: Based on these metrics, prescribe an explicit today's training target "
            "(Go-ahead, reduced ceiling, active recovery, or complete rest).\n\n"
            "Response Structure:\n"
            "You MUST strictly format your entire response using the following four headings:\n"
            "## ## The AM Readiness Metrics\n"
            "## ## Autonomic System Analysis\n"
            "## ## Today's Workout Ceiling\n"
            "## ## Recovery/Pivot Protocol\n\n"
        )
    elif analysis_mode == "Post-Workout Compliance (PM)":
        system_text = (
            "Purpose & Persona:\n"
            "You are an elite, unyielding ultra-trail and mountain endurance coach. Your focus is to evaluate the athlete's "
            "most recent completed workout for aerobic compliance, then cross-reference upcoming scheduled "
            "workouts from their Intervals.icu calendar to dynamically plan their next session.\n\n"
            "Coaching Audit & Adaptive Planning Steps:\n"
            "1. Past Workout Audit: Examine the most recent workout. Check pacing compliance (Zones 1 & 2 time must be >= 80%). "
            "Flag Zone 3 & 4 'Gray Zone' intrusion. Analyze Cardiac Drift (decoupling %): if > 5%, the aerobic cap is compromised.\n"
            "2. Scheduled Plan Integration: Pull upcoming calendar workouts. Find the next scheduled workout. "
            "DO NOT suggest a make-up session if yesterday was missed. DO NOT create a workout on an empty rest day.\n"
            "3. Predictive Adjustments: Synthesize past workout performance and current recovery markers (HRV/TSB).\n"
            "   - GREEN PATH (Decoupling < 5%, compliance > 80%): Approve the next scheduled session as written.\n"
            "   - AMBER PATH (Decoupling 5-10%, or gray zone): Drop the next session's target duration by 10-20% and lower HR ceiling by 5-10 bpm.\n"
            "   - RED PATH (Decoupling > 10%, or TSB < -30): Suggest scrapping the scheduled high-intensity session for active recovery or rest.\n\n"
            "Response Structure:\n"
            "You MUST strictly structure your output using exactly the following four headings:\n"
            "## ## The Workout Numbers\n"
            "## ## Pacing Discipline Score\n"
            "## ## Cardiovascular Aerobic Drift\n"
            "## ## Adaptive Next Move Plan\n\n"
            "Your 'Adaptive Next Move Plan' must explicitly compare what was scheduled versus what you recommend.\n\n"
        )
    else:  # Weekly Performance Review
        system_text = (
            "Purpose & Persona:\n"
            "You are an elite ultra-trail running and mountain endurance coach. Your role is to act as a weekly sounding board, "
            "an analytical engine, and an unyielding accountability partner.\n\n"
            "Core Methodology Workflow:\n"
            "1. The Holy Trinity Analysis: Always state and interpret current Fitness (CTL), Fatigue (ATL), and Form (TSB).\n"
            "2. 80/20 Rule Check: Ensure easy and long runs are strictly in Zone 1/Zone 2.\n"
            "3. Aerobic Decoupling: Analyze long weekend efforts to check for cardiac drift.\n"
            "4. Muscular Endurance (ME): Verify execution of sport-specific strength progressions.\n\n"
            "Weekly Feedback Structure:\n"
            "You MUST strictly format your entire response using the following four headings:\n"
            "## ## The Numbers\n"
            "## ## The Bright Spots\n"
            "## ## The Brutal Truth\n"
            "## ## The Next Move\n\n"
        )

    # Inject Microcycle Context and Escape Hatch into System Text
    system_text += f"CRITICAL CONTEXT: The athlete is currently in a '{microcycle_context}' phase. Adjust your physiological assessments, toughness, and recovery expectations to match this periodization cycle strictly.\n\n"
    system_text += "CRITICAL ESCAPE HATCH:\nIf tool calls return an error, OR if no data is found, output plain text explaining what failed instead of the required headings."

    # Create the session with PURE TEXT system instructions to prevent 400 ClientErrors
    st.session_state.chat_session = client.chats.create(
        model="gemini-2.5-flash",
        config=types.GenerateContentConfig(
            tools=[get_daily_wellness, get_weekly_activities, get_scheduled_workouts],
            temperature=0.2,
            system_instruction=system_text,
            safety_settings=[
                types.SafetySetting(category="HARM_CATEGORY_HARASSMENT", threshold="BLOCK_ONLY_HIGH"),
                types.SafetySetting(category="HARM_CATEGORY_HATE_SPEECH", threshold="BLOCK_ONLY_HIGH")
            ]
        )
    )

# Render chat interface history
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# 4. Interactive Live Conversation Execution
st.info(f"🎯 **Target Mode:** {analysis_mode} | 📊 **Cycle:** {microcycle_context}")

if user_input := st.chat_input("Message your coach..."):
    st.session_state.messages.append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.markdown(user_input)
        
    with st.chat_message("assistant"):
        with st.spinner("Analyzing physiological markers and training logs..."):
            
            # 1. Build the dynamic time context so the AI knows what "tomorrow" is
            today = datetime.datetime.now()
            tomorrow = today + datetime.timedelta(days=1)
            time_context = f"\n\n[SYSTEM CONTEXT: Today is {today.strftime('%A, %B %d, %Y')}. Tomorrow is {tomorrow.strftime('%A, %B %d, %Y')}.]"
            
            # 2. Safely package the user's message as a strongly-typed Part
            message_parts = [
                types.Part.from_text(text=user_input + time_context)
            ]
            
            # 3. If this is the very first message of the session, silently attach the PDF to the user prompt
            if not st.session_state.get("pdf_attached") and knowledge_document:
                message_parts.append(types.Part.from_uri(file_uri=knowledge_document.uri, mime_type=knowledge_document.mime_type))
                message_parts.append(types.Part.from_text(text="CRITICAL: Read the attached manual. Use its frameworks to judge the athlete's data."))
                st.session_state.pdf_attached = True
            
            # 4. Send the perfectly formatted payload
            response = st.session_state.chat_session.send_message(message_parts)
            
            if response.text:
                st.markdown(response.text)
                st.session_state.messages.append({"role": "assistant", "content": response.text})
            else:
                if response.function_calls:
                    tool_name = response.function_calls[0].name
                    error_msg = f"⚠️ The AI tried to trigger Intervals.icu ({tool_name}), but the automatic loop stalled."
                else:
                    finish_reason = response.candidates[0].finish_reason if response.candidates else "Unknown"
                    error_msg = f"⚠️ The AI generated a blank response. Finish Reason: {finish_reason}"
                
                st.error(error_msg)
                st.session_state.messages.append({"role": "assistant", "content": error_msg})
