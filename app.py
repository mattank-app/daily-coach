import os
import datetime
import time
import requests
from requests.auth import HTTPBasicAuth
import streamlit as st
from google import genai
from google.genai import types

# Page Config & Interface Setup
st.set_page_config(page_title="Trail Endurance Coach", page_icon="🏔️", layout="centered")

st.title("🏔️ Trail Endurance Coach")
st.subheader("Post-Workout Audit & Adaptive Scheduler")

# Verify access to secure keys inside Streamlit environment secrets
try:
    os.environ["GEMINI_API_KEY"] = st.secrets["GEMINI_API_KEY"]
except KeyError:
    st.error("Configuration Error: Missing GEMINI_API_KEY in Streamlit Secrets.")
    st.stop()

with st.sidebar:
    st.header("⚙️ Athlete Setup")
    st.markdown("Connect your Intervals.icu account.")
    
    user_athlete_id = st.text_input("Athlete ID (e.g., i12345)")
    user_api_key = st.text_input("Intervals API Key", type="password")
    
    st.markdown("---")
    st.header("📅 Periodization Settings")
    
    # Active Microcycle context dictates the severity of the coach's fatigue penalties
    selected_microcycle = st.selectbox(
        "Current Microcycle Context:",
        [
            "Build/Load Microcycle (Progressive volume focus)",
            "Peak Overload Microcycle (High stress / overload)",
            "Recovery/Deload Microcycle (Fatigue shedding focus)",
            "Taper Microcycle (Freshness & taper activation)"
        ]
    )
    
    st.markdown("---")
    st.caption("Locate credentials inside your Intervals.icu > Settings page.")

    if user_athlete_id and user_api_key:
        st.session_state.athlete_id = user_athlete_id
        st.session_state.api_key = user_api_key
    else:
        st.warning("Please enter your credentials to unlock the coach.")

if "athlete_id" not in st.session_state or "api_key" not in st.session_state:
    st.info("👈 Please set up your Intervals.icu connection in the sidebar to begin your adaptive coaching session.")
    st.stop()

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
                    "resting_hr": d.get("restingHr"),
                    "sleep_score": d.get("sleepScore"),
                    "muscle_soreness": d.get("soreness"),
                    "fatigue_rating": d.get("fatigue")
                })
            return {"status": "success", "wellness_history": wellness_log}
        else:
            print(f"CRITICAL API ERROR: {response.status_code} - {response.text}")
            return {"status": "error", "message": f"Wellness API failed: {response.status_code}"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

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
            print(f"CRITICAL CALENDAR ERROR: {response.status_code} - {response.text}")
            return {"status": "error", "message": f"Calendar API failed: {response.status_code}"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

if "messages" not in st.session_state:
    st.session_state.messages = []

@st.cache_resource
def get_genai_client():
    return genai.Client()

client = get_genai_client()

@st.cache_resource
def load_knowledge_base():
    """Uploads the manual and ensures processing is finished before conversation initialization."""
    file_name = "training_manual.pdf" 
    if os.path.exists(file_name):
        uploaded_file = client.files.upload(file=file_name)
        
        while uploaded_file.state == "PROCESSING":
            time.sleep(2)
            uploaded_file = client.files.get(name=uploaded_file.name)
            
        return uploaded_file
    return None

knowledge_document = load_knowledge_base()

# Initialize or reset the chat session if it doesn't exist OR if microcycle changed
if "chat_session" not in st.session_state or st.session_state.get("current_microcycle") != selected_microcycle:
    st.session_state.current_microcycle = selected_microcycle
    
    # 1. Base persona text with highly targeted predictive adaptive logic
    system_text = (
        "Purpose & Persona:\n"
        "You are an elite, unyielding ultra-trail and mountain endurance running coach. Your focus is to evaluate the athlete's "
        "most recent completed trail/run workout for aerobic compliance, then automatically cross-reference their upcoming scheduled "
        "workout specifically for TOMORROW (the next day) from their Intervals.icu calendar to dynamically plan and adjust their parameters (intensity, duration, and heart rate caps).\n\n"
        "Coaching Audit & Adaptive Planning Steps:\n"
        "1. Past Workout Audit: Pull completed activities. Check pacing compliance (Zones 1 & 2 time must be >= 80%). "
        "Flag Zone 3 & 4 'Gray Zone' intrusion. Analyze Cardiac Drift (decoupling %).\n"
        "2. Scheduled Plan Integration: Pull upcoming calendar events using get_scheduled_workouts. Locate the planned workout scheduled for TOMORROW.\n"
        "3. Predictive Adjustments (CRITICAL ROUTING): Compare what was completed prior against what is scheduled for tomorrow:\n"
        "   - IF TOMORROW HAS NO WORKOUT PLANNED (Rest/Blank): Under no circumstances should you suggest or invent a new session. Simply write: 'Tomorrow is a planned rest day. Keep your feet up. No adjustments needed.'\n"
        "   - IF THE ATHLETE'S PRIOR WORKOUT FELL SHORT OR WAS SKIPPED: Under no circumstances should you propose a 'make-up' session or double-down on the load. Move forward exactly as planned, adjusting only tomorrow's parameters for safety.\n"
        "   - IF TOMORROW HAS A PLANNED WORKOUT: Review the previous run's cardiac decoupling. Apply adjustments:\n"
        "       - GREEN PATH (Decoupling < 5%): Confirm tomorrow's session is approved exactly as written.\n"
        "       - AMBER PATH (Decoupling 5-10%, or gray zone running): Adjust tomorrow's planned session. Drop the target duration by 10-20% and reduce the heart rate ceiling by 5-10 bpm.\n"
        "       - RED PATH (Decoupling > 10%, or TSB < -30): Soften the impact. Propose swapping tomorrow's scheduled high-intensity/vertical effort for a flat, low-intensity recovery walk/run capped at Zone 1, or complete rest.\n\n"
        "Weekly Feedback Structure:\n"
        "You MUST strictly format your output using exactly the following four headings:\n"
        "## ## The Workout Numbers\n"
        "## ## Pacing Discipline Score\n"
        "## ## Cardiovascular Aerobic Drift\n"
        "## ## Adaptive Next Move Plan\n\n"
        "Your 'Adaptive Next Move Plan' must explicitly state what was scheduled for TOMORROW versus what you are recommending (or confirm it stands as a Rest Day if none was scheduled).\n\n"
        "CRITICAL ESCAPE HATCH:\n"
        "If tool calls return an error, output plain text explaining what failed instead of empty headings."
    )
    
    # 2. Inject Dynamic Microcycle Override rules directly into system instructions
    microcycle_rules = "\n\n--- PERIODIZATION BOUNDARIES ---\n"
    if "Build/Load" in selected_microcycle:
        microcycle_rules += (
            "Current Context: BUILD / LOAD MICROCYCLE\n"
            "- A training stress balance (TSB) of -15 to -25 is expected and highly productive.\n"
            "- Cardiac Drift > 8% on easy runs triggers the AMBER PATH: reduce target duration of the next session by 10% to prevent excessive aerobic decay.\n"
            "- Pacing compliance < 75% in Zone 1/2 triggers a stern reprimand for running in the gray zone, but allow upcoming Muscular Endurance (ME) sessions to proceed with strict heart rate caps."
        )
    elif "Peak Overload" in selected_microcycle:
        microcycle_rules += (
            "Current Context: PEAK OVERLOAD MICROCYCLE\n"
            "- Expect and permit a deep TSB drop of -25 to -35 to trigger supercompensation.\n"
            "- Expect slight suppression of HRV and a slight rise in Resting HR (RHR). Do not panic and pull back training prematurely unless autonomic markers plummet."
        )
    elif "Recovery/Deload" in selected_microcycle:
        microcycle_rules += (
            "Current Context: RECOVERY / DELOAD MICROCYCLE (ABSOLUTE REGENERATION)\n"
            "- A negative TSB of -25 is a critical failure. The TSB must climb back toward neutral (0 to +10).\n"
            "- Cardiac Drift > 8% triggers the RED PATH: Hard Override. Immediately cancel any scheduled intensity or mountain volume. Force active recovery or total rest.\n"
            "- Skipping pacing discipline (gray zone running) during recovery completely resets the recovery cycle. Force an immediate active-rest phase and lock upcoming weekend runs to a max of 90 minutes."
        )
    elif "Taper" in selected_microcycle:
        microcycle_rules += (
            "Current Context: TAPER MICROCYCLE\n"
            "- Prioritize autonomic nervous system recovery (HRV must rebound rapidly).\n"
            "- Volume drops significantly (50% to 60% reduction), but keep short, sharp neuromuscular activations to maintain muscle tension."
        )
    
    system_parts = [system_text + microcycle_rules]
    if knowledge_document:
        system_parts.append(types.Part.from_uri(file_uri=knowledge_document.uri, mime_type=knowledge_document.mime_type))
        system_parts.append("CRITICAL: Read the attached manual. Use its frameworks to judge the athlete's data.")

    st.session_state.chat_session = client.chats.create(
        model="gemini-2.5-flash",
        config=types.GenerateContentConfig(
            tools=[get_daily_wellness, get_weekly_activities, get_scheduled_workouts],
            temperature=0.2,
            system_instruction=system_parts,
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

st.info(f"🎯 **Target Mode:** Post-Workout Audit & Adaptive Scheduler (Active Context: {selected_microcycle})")

if user_input := st.chat_input("Message your coach... (e.g., 'Audit my last run and plan my next move')"):
    st.session_state.messages.append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.markdown(user_input)
        
    with st.chat_message("assistant"):
        with st.spinner("Analyzing performance compliance and fetching upcoming training blocks..."):
            # Compute dates dynamically so the LLM has absolute, real-time clock awareness of what "tomorrow" is
            today_dt = datetime.date.today()
            tomorrow_dt = today_dt + datetime.timedelta(days=1)
            
            # Inject dynamic time context into the message stream transparently
            time_context = (
                f"\n\n[SYSTEM CONTEXT - DO NOT ECHO VERBATIM: Today is {today_dt.strftime('%A, %b %d, %Y')}. "
                f"Tomorrow is {tomorrow_dt.strftime('%A, %b %d, %Y')}. Execute your assessment relative to these dates.]"
            )
            
            response = st.session_state.chat_session.send_message(user_input + time_context)
            
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
