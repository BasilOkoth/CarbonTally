import streamlit as st
import requests
import json
import time
import pandas as pd
import sqlite3
import qrcode
from io import BytesIO
import base64
import os
from pathlib import Path
import re
from datetime import datetime, timedelta
import matplotlib.pyplot as plt
import seaborn as sns
import uuid # Ensure uuid is imported for generate_monitoring_qr_code

# Import display_tree_details from kobo_integration for tree lookup in monitoring_section
# This is necessary because display_tree_details is a UI function residing in kobo_integration.py
try:
    from kobo_integration import get_tree_details as get_tree_details_from_integration, display_tree_results # Using alias to avoid conflict if any
except ImportError:
    st.error("Could not import get_tree_details or display_tree_results from kobo_integration.py. Please ensure the file exists and is correct.")
    # Define dummy functions to prevent app crash
    def get_tree_details_from_integration(*args, **kwargs): return None
    def display_tree_results(*args, **kwargs): st.error("display_tree_results not available.")


# KoBo Toolbox configuration
KOBO_API_URL = "https://kf.kobotoolbox.org/api/v2"
try:
    KOBO_API_TOKEN = st.secrets["KOBO"]["API_TOKEN"]
    KOBO_ASSET_ID = st.secrets["KOBO"]["ASSET_ID"] # This is for planting forms, not monitoring
    KOBO_MONITORING_ASSET_ID = st.secrets["KOBO"]["MONITORING_ASSET_ID"]
except Exception as e:
    st.warning(f"Could not load KoBo secrets: {e}")
    KOBO_API_TOKEN = "dummy_token"
    KOBO_ASSET_ID = "dummy_asset_id"
    KOBO_MONITORING_ASSET_ID = "aDSNfsXbXygrn8rwKog5Yd" # Keep this as a known test ID


# Database configuration
BASE_DIR = Path(__file__).parent if "__file__" in locals() else Path.cwd()
DATA_DIR = BASE_DIR / "data"
SQLITE_DB = DATA_DIR / "trees.db"
QR_CODE_DIR = DATA_DIR / "qr_codes"

# Ensure directories exist
DATA_DIR.mkdir(exist_ok=True, parents=True)
QR_CODE_DIR.mkdir(exist_ok=True, parents=True)

def initialize_database():
    """
    Initializes the database with required tables and performs schema migrations.
    Ensures 'tree_tracking_number' column in 'trees' and 'kobo_submission_id' in 'monitoring_history'.
    """
    conn = sqlite3.connect(SQLITE_DB)
    try:
        c = conn.cursor()

        # --- CREATE OR ALTER 'trees' TABLE ---
        c.execute('''
            CREATE TABLE IF NOT EXISTS trees (
                tree_id TEXT PRIMARY KEY,
                institution TEXT,
                local_name TEXT,
                scientific_name TEXT,
                student_name TEXT,
                date_planted TEXT,
                tree_stage TEXT,
                rcd_cm REAL,
                dbh_cm REAL,
                height_m REAL,
                latitude REAL,
                longitude REAL,
                co2_kg REAL,
                status TEXT,
                country TEXT,
                county TEXT,
                sub_county TEXT,
                ward TEXT,
                adopter_name TEXT,
                last_monitored TEXT,
                monitor_notes TEXT,
                qr_code TEXT,
                kobo_submission_id TEXT UNIQUE,
                tree_tracking_number TEXT -- Explicitly defined here
            )
        ''')
        conn.commit()

        # Add tree_tracking_number if it doesn't exist (for existing databases)
        c.execute("PRAGMA table_info(trees)")
        columns = [col[1] for col in c.fetchall()]
        if "tree_tracking_number" not in columns:
            print("[DB_MIGRATION] Adding 'tree_tracking_number' to 'trees' table.")
            c.execute("ALTER TABLE trees ADD COLUMN tree_tracking_number TEXT")
            conn.commit()
            st.info("Added 'tree_tracking_number' column to 'trees' table.")
        else:
            print("[DB_MIGRATION] 'tree_tracking_number' already exists in 'trees' table.")


        # --- CREATE OR ALTER 'monitoring_history' TABLE ---
        c.execute('''
            CREATE TABLE IF NOT EXISTS monitoring_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tree_id TEXT,
                monitor_date TEXT,
                monitor_status TEXT,
                monitor_stage TEXT,
                rcd_cm REAL,
                dbh_cm REAL,
                height_m REAL,
                co2_kg REAL,
                notes TEXT,
                monitor_by TEXT,
                kobo_submission_id TEXT UNIQUE, -- Ensure this is unique
                FOREIGN KEY (tree_id) REFERENCES trees (tree_id)
            )
        ''')
        conn.commit()

        # Add kobo_submission_id to monitoring_history if it doesn't exist
        c.execute("PRAGMA table_info(monitoring_history)")
        columns_mh = [col[1] for col in c.fetchall()]
        if "kobo_submission_id" not in columns_mh:
            print("[DB_MIGRATION] Adding 'kobo_submission_id' to 'monitoring_history' table.")
            c.execute("ALTER TABLE monitoring_history ADD COLUMN kobo_submission_id TEXT UNIQUE")
            conn.commit()
            st.info("Added 'kobo_submission_id' column to 'monitoring_history' table.")
        else:
            print("[DB_MIGRATION] 'kobo_submission_id' already exists in 'monitoring_history' table.")

        # Create processed_monitoring_submissions table
        c.execute('''
            CREATE TABLE IF NOT EXISTS processed_monitoring_submissions (
                submission_id TEXT PRIMARY KEY,
                tree_id TEXT,
                processed_date TEXT,
                FOREIGN KEY (tree_id) REFERENCES trees (tree_id)
            )
        ''')
        conn.commit()
        
        print("[DB_MIGRATION] Database initialization/migration complete.")
        
    except Exception as e:
        st.error(f"Database initialization error: {e}")
        print(f"[DB_MIGRATION] Database initialization FAILED: {e}")
    finally:
        conn.close()

def validate_user_session():
    """
    Validate that the user session has all required fields.
    Returns True if valid, False otherwise.
    """
    print(f"[DEBUG_SESSION] validate_user_session called. Current st.session_state.keys(): {st.session_state.keys()}")
    
    if "user" not in st.session_state:
        st.error("User session not found. Please log in again.")
        print("[DEBUG_SESSION] 'user' not in st.session_state. Returning False.")
        return False
        
    # Ensure st.session_state.user is a dictionary
    if not isinstance(st.session_state.user, dict):
        st.error("Invalid user session format. Please log in again.")
        print(f"[DEBUG_SESSION] st.session_state.user is not a dict. Type: {type(st.session_state.user)}. Setting to empty dict.")
        st.session_state.user = {} # Reset to empty dict to prevent further errors
        return False
        
    required_fields = ["username", "user_type"]
    missing_fields = [field for field in required_fields if field not in st.session_state.user]
    
    if missing_fields:
        st.error(f"User session missing required fields: {', '.join(missing_fields)}. Please log in again.")
        print(f"[DEBUG_SESSION] Missing fields: {missing_fields}. Current st.session_state.user: {st.session_state.user}")
        return False
    
    print(f"[DEBUG_SESSION] User session valid. User: {st.session_state.user}")
    return True

def ensure_institution_assigned():
    """
    Ensure that an institution is assigned to the current user
    Returns the institution name if available or selected, None otherwise
    """
    if "user" not in st.session_state:
        print("[DEBUG_INST] ensure_institution_assigned: 'user' not in st.session_state. Returning None.")
        return None
    
    if not isinstance(st.session_state.user, dict):
        print(f"[DEBUG_INST] ensure_institution_assigned: st.session_state.user is not a dict. Type: {type(st.session_state.user)}. Returning None.")
        return None

    user_institution = st.session_state.user.get("institution")
    
    if user_institution:
        print(f"[DEBUG_INST] Found institution '{user_institution}' in session.")
        return user_institution
        
    # If no institution is assigned, prompt for selection (only if not running as a sub-module where app.py handles it)
    # This block is primarily for standalone testing of kobo_monitoring.py
    if st.session_state.user.get('user_type') in ["school", "field", "admin"]: # Only prompt for these roles
        st.warning("No institution assigned to your account. Please select your institution:")
        print("[DEBUG_INST] Institution not found in session, prompting selection.")

        conn = sqlite3.connect(SQLITE_DB)
        try:
            # Fetch all distinct institutions from the 'trees' table that have actual trees
            institutions_df = pd.read_sql(
                "SELECT DISTINCT institution FROM trees WHERE institution IS NOT NULL AND institution != ''", conn
            )
            available_institutions = institutions_df["institution"].tolist()
            print(f"[DEBUG_INST] Available institutions from DB: {available_institutions}")
        except Exception as e:
            st.error(f"Error fetching institutions: {e}")
            available_institutions = []
        finally:
            conn.close()

        if available_institutions:
            selected_institution = st.selectbox("Select your institution", [""] + available_institutions, key="institution_select_monitor")
            if selected_institution:
                st.session_state.user['institution'] = selected_institution
                st.success(f"Institution set to '{selected_institution}'. Please proceed.")
                st.rerun() # Rerun to apply the new institution to session state
                return selected_institution
            else:
                st.info("Please select an institution to continue.")
                return None
        else:
            st.info("No institutions found in the database yet. Plant some trees first!")
            return None
    
    return None # Return None if not applicable for user type or no institution set

def get_kobo_monitoring_form_url(tree_id=None, tree_tracking_number=None, local_name=None, scientific_name=None, date_planted=None, planter=None, institution=None):
    """
    Generates the URL for the KoBo monitoring form, pre-filling known tree data.
    """
    kobo_monitoring_asset_id = st.secrets.get("KOBO_MONITORING_ASSET_ID")
    if not kobo_monitoring_asset_id:
        st.error("Monitoring form configuration missing. Please contact support.")
        return None
    
    base_url = f"https://ee.kobotoolbox.org/x/{kobo_monitoring_asset_id}"
    
    params = {}
    if tree_id: params["tree_id"] = tree_id
    if tree_tracking_number: params["tree_tracking_number"] = tree_tracking_number
    if local_name: params["local_name"] = local_name
    if scientific_name: params["scientific_name"] = scientific_name
    if date_planted: params["date_planted"] = date_planted
    if planter: params["planter"] = planter
    if institution: params["institution"] = institution

    url_params = "&".join([f"{k}={v}" for k, v in params.items() if v])
    return f"{base_url}?{url_params}" if url_params else base_url

def get_kobo_monitoring_submissions(hours=24):
    """Retrieves monitoring submissions from KoBo Toolbox API."""
    kobo_api_token = st.secrets.get("KOBO_API_TOKEN")
    kobo_monitoring_asset_id = st.secrets.get("KOBO_MONITORING_ASSET_ID")
    
    if not kobo_api_token or not kobo_monitoring_asset_id:
        st.error("System configuration error for monitoring. Please contact support.")
        return None

    headers = {
        "Authorization": f"Token {kobo_api_token}"
    }
    url = f"{KOBO_API_URL}/assets/{kobo_monitoring_asset_id}/data/?format=json"

    try:
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()

        content_type = response.headers.get("Content-Type", "")
        if "application/json" not in content_type:
            st.error("Received non-JSON response from KoBo API for monitoring. Expected 'application/json'.")
            st.error(f"Actual Content-Type: {content_type}")
            st.error(f"Response preview: {response.text[:500]}...")
            return None

        submissions = response.json().get("results", [])
        
        # Filter submissions by time (last X hours)
        current_time = datetime.now()
        recent_submissions = []
        for sub in submissions:
            submission_time_str = sub.get("end") or sub.get("start") or sub.get("_submission_time")
            if submission_time_str:
                try:
                    submission_time = datetime.strptime(submission_time_str, "%Y-%m-%dT%H:%M:%S.%f%z")
                except ValueError:
                    try:
                        submission_time = datetime.strptime(submission_time_str, "%Y-%m-%dT%H:%M:%S%z")
                    except ValueError:
                        try:
                            submission_time = datetime.strptime(submission_time_str, "%Y-%m-%dT%H:%M:%S.%f")
                        except ValueError:
                            submission_time = datetime.strptime(submission_time_str.split('.')[0], "%Y-%m-%dT%H:%M:%S")

                if submission_time.tzinfo is not None and submission_time.tzinfo.utcoffset(submission_time) is not None:
                    current_time_tz = current_time.astimezone(submission_time.tzinfo)
                else:
                    current_time_tz = current_time

                if current_time_tz - submission_time <= timedelta(hours=hours):
                    recent_submissions.append(sub)
        
        return recent_submissions

    except json.JSONDecodeError as e:
        st.error(f"JSON decoding error from KoBo API response for monitoring: {e}")
        st.error(f"Problematic response text (first 500 chars): {response.text[:500]}...")
        return None
    except requests.exceptions.HTTPError as e:
        st.error(f"HTTP error from KoBo API for monitoring: {e.response.status_code} - {e.response.reason}")
        st.error(f"Response body: {e.response.text[:500]}...")
        return None
    except requests.exceptions.ConnectionError as e:
        st.error(f"Network connection error to KoBo API. Please check your internet connection: {e}")
        return None
    except requests.exceptions.Timeout:
        st.error("KoBo API request for monitoring timed out. Please try again.")
        return None
    except Exception as e:
        st.error(f"An unexpected error occurred while fetching KoBo monitoring submissions: {e}")
        return None

def calculate_co2_sequestration_monitoring(scientific_name, rcd=None, dbh=None, height=None):
    """
    Calculates CO2 sequestration in kg for monitoring.
    Uses species wood density and tree measurements (RCD or DBH).
    """
    conn = sqlite3.connect(SQLITE_DB)
    try:
        species_data = pd.read_sql(
            "SELECT wood_density FROM species WHERE scientific_name = ?", conn, params=(scientific_name,)
        )
        density = species_data["wood_density"].iloc[0] if not species_data.empty and species_data["wood_density"].iloc[0] is not None else 0.6 # Default
        
        agb = 0.0
        if dbh is not None and dbh > 0:
            agb = 0.0509 * density * (dbh ** 2.5)
        elif rcd is not None and rcd > 0:
            agb = 0.042 * (rcd ** 2.5)
        else:
            return 0.0

        bgb = 0.2 * agb
        co2_sequestration = 0.47 * (agb + bgb) * 3.67

        return round(co2_sequestration, 2)
    except Exception as e:
        st.error(f"CO2 calculation error during monitoring for species '{scientific_name}': {e}")
        return 0.0
    finally:
        conn.close()

def map_monitoring_submission_to_database(submission):
    """Maps KoBo monitoring submission data to the database schema."""
    submission_id = submission.get("_id") # Use KoBo's internal submission ID for uniqueness
    
    # Check if this monitoring submission_id has already been processed
    conn = sqlite3.connect(SQLITE_DB)
    c = conn.cursor()
    c.execute("SELECT 1 FROM processed_monitoring_submissions WHERE submission_id = ?", (submission_id,))
    if c.fetchone():
        print(f"Skipping already processed monitoring submission: {submission_id}")
        return None # Already processed

    tree_id = submission.get("tree_id", "").strip()
    if not tree_id:
        st.warning(f"Monitoring submission {submission_id} missing 'tree_id'. Skipping.")
        return None

    # Get existing tree data for scientific name and initial measurements
    tree_data = get_tree_details_from_integration(tree_id) # Use the imported get_tree_details
    if not tree_data:
        st.error(f"Tree with ID {tree_id} not found in database for monitoring submission {submission_id}. Skipping.")
        return None
    
    scientific_name = tree_data.get("scientific_name") # Get scientific name from original tree data

    monitor_date = submission.get("date_monitor") or datetime.now().strftime("%Y-%m-%d")
    monitor_status = submission.get("status")
    monitor_stage = submission.get("tree_stage")
    rcd_cm = submission.get("rcd_cm")
    dbh_cm = submission.get("dbh_cm")
    height_m = submission.get("height_m")
    notes = submission.get("notes")
    monitor_by = submission.get("user") # The KoBo user who made the submission

    # Convert numeric fields
    try: rcd_cm = float(rcd_cm) if rcd_cm else tree_data.get('rcd_cm') # Use old value if new is missing
    except ValueError: rcd_cm = tree_data.get('rcd_cm')
    try: dbh_cm = float(dbh_cm) if dbh_cm else tree_data.get('dbh_cm')
    except ValueError: dbh_cm = tree_data.get('dbh_cm')
    try: height_m = float(height_m) if height_m else tree_data.get('height_m')
    except ValueError: height_m = tree_data.get('height_m')

    # Recalculate CO2 sequestration with new measurements
    co2_kg = calculate_co2_sequestration_monitoring(scientific_name, rcd=rcd_cm, dbh=dbh_cm, height=height_m)

    mapped_data = {
        "submission_id": submission_id,
        "tree_id": tree_id,
        "monitor_date": monitor_date,
        "monitor_status": monitor_status,
        "monitor_stage": monitor_stage,
        "rcd_cm": rcd_cm,
        "dbh_cm": dbh_cm,
        "height_m": height_m,
        "co2_kg": co2_kg,
        "notes": notes,
        "monitor_by": monitor_by
    }
    return mapped_data

def save_monitoring_submission(monitoring_data):
    """Saves monitoring data to the database and updates tree's last_monitored."""
    conn = sqlite3.connect(SQLITE_DB)
    try:
        c = conn.cursor()
        
        # Insert into monitoring_history
        c.execute('''
            INSERT INTO monitoring_history (
                tree_id, monitor_date, monitor_status, monitor_stage,
                rcd_cm, dbh_cm, height_m, co2_kg, notes, monitor_by, kobo_submission_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            monitoring_data.get('tree_id'),
            monitoring_data.get('monitor_date'),
            monitoring_data.get('monitor_status'),
            monitoring_data.get('monitor_stage'),
            monitoring_data.get('rcd_cm'),
            monitoring_data.get('dbh_cm'),
            monitoring_data.get('height_m'),
            monitoring_data.get('co2_kg'),
            monitoring_data.get('notes'),
            monitoring_data.get('monitor_by'),
            monitoring_data.get('submission_id')
        ))
        
        # Update tree's last_monitored date and current CO2/status/measurements
        c.execute('''
            UPDATE trees SET
                last_monitored = ?,
                status = ?,
                tree_stage = ?,
                rcd_cm = ?,
                dbh_cm = ?,
                height_m = ?,
                co2_kg = ?
            WHERE tree_id = ?
        ''', (
            monitoring_data.get('monitor_date'),
            monitoring_data.get('monitor_status'),
            monitoring_data.get('monitor_stage'),
            monitoring_data.get('rcd_cm'),
            monitoring_data.get('dbh_cm'),
            monitoring_data.get('height_m'),
            monitoring_data.get('co2_kg'),
            monitoring_data.get('tree_id')
        ))

        # Mark submission as processed
        c.execute("INSERT INTO processed_monitoring_submissions (submission_id, tree_id, processed_date) VALUES (?, ?, ?)",
                  (monitoring_data.get('submission_id'), monitoring_data.get('tree_id'), datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        
        conn.commit()
        return True
    except sqlite3.IntegrityError as e:
        if "UNIQUE constraint failed: monitoring_history.kobo_submission_id" in str(e) or \
           "UNIQUE constraint failed: processed_monitoring_submissions.submission_id" in str(e):
            st.warning(f"Monitoring submission {monitoring_data.get('submission_id')} already processed.")
            return False
        else:
            st.error(f"Database error saving monitoring data: {e}")
            return False
    except Exception as e:
        st.error(f"Error saving monitoring data: {e}")
        return False
    finally:
        conn.close()

# This function was the missing one
def fetch_monitoring_data(monitor_uid, hours=24):
    """
    Fetches new monitoring submissions from KoBoToolbox within the last 'hours'
    and updates the database.
    """
    asset_uid = st.secrets.get("KOBO_MONITORING_ASSET_ID")
    if not asset_uid:
        st.error("KOBO_MONITORING_ASSET_ID not found in secrets.toml.")
        return []

    last_checked_time = (datetime.now() - timedelta(hours=hours)).isoformat()
    
    st.info(f"Checking KoBoToolbox for new monitoring submissions since {last_checked_time}...")
    submissions = get_kobo_monitoring_submissions(hours=hours) # Pass hours to the fetching function

    if not submissions:
        st.info("No new monitoring submissions found.")
        return []

    st.success(f"Found {len(submissions)} new monitoring submissions. Processing...")
    processed_count = 0
    results = []
    for sub in submissions:
        # Check if this specific Kobo monitoring submission ID has already been processed
        conn = sqlite3.connect(SQLITE_DB)
        c = conn.cursor()
        c.execute("SELECT 1 FROM processed_monitoring_submissions WHERE submission_id = ?", (sub.get("_id"),))
        already_processed = c.fetchone() is not None
        conn.close()

        if already_processed:
            print(f"Skipping monitoring submission {sub.get('_id')}: Already processed in processed_monitoring_submissions table.")
            continue

        mapped_data = map_monitoring_submission_to_database(sub)
        if mapped_data:
            # You might want to add a check here to ensure the tree belongs to the monitor_uid's institution
            # if that's a requirement for processing (e.g., if monitor_uid is an institution ID)
            # For now, it processes any valid monitoring submission if the tree_id exists.
            
            if save_monitoring_submission(mapped_data):
                processed_count += 1
                results.append(mapped_data) # Append mapped data, not raw sub
    
    st.info(f"Successfully processed {processed_count} monitoring submissions.")
    return results

def get_monitoring_history(tree_id):
    """Retrieves monitoring history for a specific tree."""
    conn = sqlite3.connect(SQLITE_DB)
    try:
        df = pd.read_sql(
            "SELECT * FROM monitoring_history WHERE tree_id = ? ORDER BY monitor_date DESC",
            conn, params=(tree_id,)
        )
        return df
    finally:
        conn.close()

def admin_tree_lookup():
    """Allows admin to lookup a tree by its tracking number or ID."""
    st.subheader("Lookup Tree by ID or Tracking Number")
    lookup_query = st.text_input("Enter Tree ID or Tree Tracking Number:", key="admin_lookup_query")
    
    if lookup_query:
        conn = sqlite3.connect(SQLITE_DB)
        try:
            tree_df = pd.read_sql(
                "SELECT * FROM trees WHERE tree_id = ? OR tree_tracking_number = ?",
                conn, params=(lookup_query, lookup_query)
            )
            if not tree_df.empty:
                tree_data = tree_df.iloc[0].to_dict()
                display_monitoring_summary_and_history(tree_data['tree_id'])
            else:
                st.warning("Tree not found with the provided ID or Tracking Number.")
        except Exception as e:
            st.error(f"Error looking up tree: {e}")
        finally:
            conn.close()

def get_monitoring_stats():
    """Fetches overall monitoring statistics."""
    conn = sqlite3.connect(SQLITE_DB)
    try:
        # Get overall stats for the dashboard
        stats = pd.read_sql("""
            SELECT
                COUNT(DISTINCT tree_id) as monitored_trees,
                COUNT(*) as monitoring_events,
                SUM(CASE WHEN monitor_status = 'Alive' THEN 1 ELSE 0 END) as alive_count,
                SUM(CASE WHEN monitor_status = 'Dead' THEN 1 ELSE 0 END) as dead_count,
                AVG(co2_kg) as avg_co2,
                SUM(co2_kg) as total_co2
            FROM monitoring_history
        """, conn)

        # Get monitoring data by date
        monitoring_by_date = pd.read_sql("""
            SELECT
                strftime('%Y-%m', monitor_date) as monitor_month,
                COUNT(*) as events_count,
                SUM(co2_kg) as month_co2
            FROM monitoring_history
            GROUP BY monitor_month
            ORDER BY monitor_month
        """, conn)

        # Get monitoring data by institution (trees table joined with monitoring history)
        monitoring_by_institution = pd.read_sql("""
            SELECT
                t.institution,
                COUNT(DISTINCT mh.tree_id) as monitored_trees,
                COUNT(mh.id) as monitoring_events
            FROM monitoring_history mh
            JOIN trees t ON mh.tree_id = t.tree_id
            GROUP BY t.institution
            ORDER BY monitored_trees DESC
        """, conn)
        
        # Get count of trees by growth stage
        growth_stages = pd.read_sql("""
            SELECT
                tree_stage,
                COUNT(DISTINCT tree_id) as tree_count
            FROM trees
            WHERE tree_stage IS NOT NULL AND tree_stage != ''
            GROUP BY tree_stage
            ORDER BY tree_count DESC
        """, conn)

        return {
            "stats": stats.iloc[0].to_dict() if not stats.empty else {},
            "monitoring_by_date": monitoring_by_date.to_dict('records') if not monitoring_by_date.empty else [],
            "monitoring_by_institution": monitoring_by_institution.to_dict('records') if not monitoring_by_institution.empty else [],
            "growth_stages": growth_stages.to_dict('records') if not growth_stages.empty else []
        }
    except Exception as e:
        st.error(f"Error getting monitoring stats: {str(e)}")
        return {
            "stats": {},
            "monitoring_by_date": [],
            "monitoring_by_institution": [],
            "growth_stages": []
        }
    finally:
        conn.close()

def display_monitoring_dashboard():
    """Display monitoring dashboard with statistics and charts"""
    st.title("🌳 Tree Monitoring Dashboard")

    # Get monitoring stats
    stats = get_monitoring_stats()

    # Ensure stats['stats'] is a dictionary to prevent TypeError
    if not isinstance(stats.get('stats'), dict):
        st.error("Invalid monitoring statistics data. Displaying limited metrics.")
        stats['stats'] = {} # Default to an empty dictionary to prevent further errors

    # Display overall metrics
    st.subheader("Overall Monitoring Metrics")
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Trees Monitored", stats["stats"].get("monitored_trees", 0))
    with col2:
        st.metric("Monitoring Events", stats["stats"].get("monitoring_events", 0))
    with col3:
        alive = stats["stats"].get("alive_count", 0)
        total_events = stats["stats"].get("monitoring_events", 1) # Use total events from monitoring history
        survival_rate = (alive / total_events) * 100 if total_events > 0 else 0
        st.metric("Survival Rate", f"{survival_rate:.1f}%")
    with col4:
        st.metric("Avg. CO₂ per Tree", f"{stats['stats'].get('avg_co2', 0):.2f} kg")

    st.markdown("---")

    # Monitoring by Date
    st.subheader("Monitoring Events & CO₂ by Month")
    monitoring_by_date_df = pd.DataFrame(stats["monitoring_by_date"])
    if not monitoring_by_date_df.empty:
        fig_date = px.bar(
            monitoring_by_date_df,
            x="monitor_month",
            y="events_count",
            title="Monitoring Events by Month",
            labels={"monitor_month": "Month", "events_count": "Number of Events"}
        )
        st.plotly_chart(fig_date, use_container_width=True)

        fig_co2_date = px.line(
            monitoring_by_date_df,
            x="monitor_month",
            y="month_co2",
            title="Total CO₂ Sequestered by Month",
            labels={"monitor_month": "Month", "month_co2": "Total CO₂ (kg)"}
        )
        st.plotly_chart(fig_co2_date, use_container_width=True)
    else:
        st.info("No monitoring data by date available.")

    st.markdown("---")

    # Monitoring by Institution
    st.subheader("Monitoring Activity by Institution")
    monitoring_by_institution_df = pd.DataFrame(stats["monitoring_by_institution"])
    if not monitoring_by_institution_df.empty:
        fig_inst = px.bar(
            monitoring_by_institution_df,
            x="institution",
            y="monitored_trees",
            title="Monitored Trees by Institution",
            labels={"institution": "Institution", "monitored_trees": "Number of Monitored Trees"}
        )
        st.plotly_chart(fig_inst, use_container_width=True)
    else:
        st.info("No monitoring data by institution available.")

    st.markdown("---")
    
    # Growth Stages Distribution
    st.subheader("Distribution of Tree Growth Stages")
    growth_stages_df = pd.DataFrame(stats["growth_stages"])
    if not growth_stages_df.empty:
        fig_stage = px.pie(
            growth_stages_df,
            values='tree_count',
            names='tree_stage',
            title='Distribution of Tree Growth Stages',
            hole=0.3
        )
        st.plotly_chart(fig_stage, use_container_width=True)
    else:
        st.info("No tree growth stage data available.")


def display_monitoring_summary_and_history(tree_id):
    """Displays a tree's current status and its monitoring history."""
    tree_data = get_tree_details_from_integration(tree_id) # Use the imported get_tree_details_from_integration
    if not tree_data:
        st.error(f"Tree with ID '{tree_id}' not found.")
        return

    st.subheader(f"Monitoring Details for Tree ID: {tree_data.get('tree_id')}")
    st.markdown(f"**Tree Tracking Number:** {tree_data.get('tree_tracking_number')}")
    st.markdown(f"**Local Name:** {tree_data.get('local_name')}")
    st.markdown(f"**Scientific Name:** {tree_data.get('scientific_name')}")
    st.markdown(f"**Institution:** {tree_data.get('institution')}")
    st.markdown(f"**Date Planted:** {tree_data.get('date_planted')}")

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Current Status", tree_data.get('status', 'N/A'))
    with col2:
        st.metric("Current Stage", tree_data.get('tree_stage', 'N/A'))
    with col3:
        st.metric("Current CO₂ Sequestration", f"{tree_data.get('co2_kg', 0):.2f} kg")
    with col4:
        st.metric("Last Monitored", tree_data.get('last_monitored', 'N/A'))

    st.markdown("---")
    st.subheader("Measurements & QR Code")
    col_meas, col_qr = st.columns(2)
    with col_meas:
        st.write(f"**RCD (cm):** {tree_data.get('rcd_cm', 'N/A'):.2f}")
        st.write(f"**DBH (cm):** {tree_data.get('dbh_cm', 'N/A'):.2f}")
        st.write(f"**Height (m):** {tree_data.get('height_m', 'N/A'):.2f}")
    with col_qr:
        st.write("### Monitoring Form QR Code")
        qr_code_base64 = tree_data.get("qr_code")
        # Note: In kobo_integration, the QR code for planting stores the monitoring URL.
        # So we can just display that stored QR code.
        
        if qr_code_base64:
            st.image(f"data:image/png;base64,{qr_code_base64}", caption="Scan to monitor this tree", use_column_width=True)
            st.download_button(
                label="Download QR Code",
                data=base64.b64decode(qr_code_base64),
                file_name=f"tree_{tree_data['tree_id']}_monitoring_qr.png",
                mime="image/png"
            )
        else:
            st.warning("No QR code exists or could be generated for this tree.")

        if st.button("Generate/Regenerate QR Code", key=f"regen_qr_{tree_id}"):
            with st.spinner("Generating QR code..."):
                qr_img_b64, qr_path, qr_monitoring_url = generate_monitoring_qr_code(tree_data['tree_id'], tree_data)
                if qr_img_b64:
                    st.success("QR code generated and updated!")
                    st.rerun() # Rerun to display the new QR code
                else:
                    st.error("Failed to generate QR code.")

    st.markdown("---")
    st.subheader("Monitoring History")
    history_df = get_monitoring_history(tree_id)
    if not history_df.empty:
        st.dataframe(history_df.set_index('id'))
        
        # Plotting history (e.g., CO2 over time)
        st.subheader("CO₂ Sequestration Over Time")
        history_df['monitor_date'] = pd.to_datetime(history_df['monitor_date'])
        history_df = history_df.sort_values('monitor_date')
        
        fig = px.line(history_df, x='monitor_date', y='co2_kg', title='CO₂ Sequestration (kg) Over Time')
        fig.update_xaxes(title_text='Date')
        fig.update_yaxes(title_text='CO₂ (kg)')
        st.plotly_chart(fig, use_container_width=True)

        st.subheader("Tree Growth (RCD/DBH/Height) Over Time")
        growth_fig = go.Figure()
        if 'rcd_cm' in history_df.columns:
            growth_fig.add_trace(go.Scatter(x=history_df['monitor_date'], y=history_df['rcd_cm'], mode='lines+markers', name='RCD (cm)'))
        if 'dbh_cm' in history_df.columns:
            growth_fig.add_trace(go.Scatter(x=history_df['monitor_date'], y=history_df['dbh_cm'], mode='lines+markers', name='DBH (cm)'))
        if 'height_m' in history_df.columns:
            growth_fig.add_trace(go.Scatter(x=history_df['monitor_date'], y=history_df['height_m'], mode='lines+markers', name='Height (m)'))
        
        growth_fig.update_layout(title='Tree Growth Over Time',
                                 xaxis_title='Date',
                                 yaxis_title='Measurement')
        st.plotly_chart(growth_fig, use_container_width=True)

    else:
        st.info("No monitoring history recorded for this tree yet.")

def monitoring_section():
    """Main monitoring interface"""
    st.title("🌳 Tree Monitoring System")
    initialize_database() # Ensure database is initialized for this module

    if not validate_user_session():
        return
    
    user_type = st.session_state.user.get('user_type')
    user_institution = ensure_institution_assigned()

    if user_type == "admin":
        st.info("As an admin, you can view the overall monitoring dashboard or lookup specific trees.")
        dashboard_tab, lookup_tab = st.tabs(["Monitoring Dashboard", "Lookup Tree"])
        
        with dashboard_tab:
            display_monitoring_dashboard()
        with lookup_tab:
            admin_tree_lookup()

    elif user_type in ["field", "school"]:
        st.info(f"Welcome, {st.session_state.user.get('username')}! Here you can find trees to monitor or view your institution's trees.")
        if not user_institution:
            st.warning("Please select your institution to proceed with monitoring your trees.")
            return

        tab1, tab2, tab3 = st.tabs(["Find Tree to Monitor", "My Institution's Trees", "Process New Submissions"])

        with tab1:
            st.subheader("Find Tree by Tracking Number / ID")
            search_query = st.text_input("Enter Tree Tracking Number or Tree ID:", key="monitor_search_query")
            if st.button("Search Tree", key="monitor_search_button"):
                if search_query:
                    conn = sqlite3.connect(SQLITE_DB)
                    try:
                        tree_df = pd.read_sql(
                            "SELECT * FROM trees WHERE (tree_id = ? OR tree_tracking_number = ?) AND institution = ?",
                            conn, params=(search_query, search_query, user_institution)
                        )
                        if not tree_df.empty:
                            tree_data = tree_df.iloc[0].to_dict()
                            display_monitoring_summary_and_history(tree_data['tree_id'])
                        else:
                            st.warning(f"Tree '{search_query}' not found in your institution's records.")
                    except Exception as e:
                        st.error(f"Error searching for tree: {e}")
                    finally:
                        conn.close()
                else:
                    st.info("Please enter a Tree ID or Tracking Number to search.")

        with tab2:
            st.subheader(f"Trees Planted by {user_institution}")
            conn = sqlite3.connect(SQLITE_DB)
            try:
                my_trees_df = pd.read_sql(
                    "SELECT tree_id, local_name, scientific_name, date_planted, tree_tracking_number, last_monitored, status, co2_kg FROM trees WHERE institution = ? ORDER BY date_planted DESC",
                    conn, params=(user_institution,)
                )
                if not my_trees_df.empty:
                    st.dataframe(my_trees_df)

                    st.subheader("Select a Tree to View Details/Monitor")
                    selected_tree_id = st.selectbox("Choose a tree:", [""] + my_trees_df["tree_id"].tolist(), key="select_my_tree")
                    if selected_tree_id:
                        display_monitoring_summary_and_history(selected_tree_id)
                else:
                    st.info(f"No trees found for your institution '{user_institution}' yet.")
            finally:
                conn.close()
        
        with tab3:
            st.subheader("Process New Monitoring Submissions")
            st.info("Check for recent monitoring data submitted via KoBo Toolbox for your institution.")
            if st.button("Process New Monitoring Submissions", key="process_monitor_subs_button"):
                with st.spinner("Fetching and processing new monitoring submissions..."):
                    processed_count = 0
                    submissions = fetch_monitoring_data(monitor_uid=st.session_state.user.get('uid'), hours=24 * 7) # Call the correct function
                    if submissions:
                        st.success(f"Processed {len(submissions)} new monitoring submissions for your institution!")
                        st.rerun() # Rerun to update dashboards with new data
                    else:
                        st.info("No new monitoring submissions found or none matched your institution for processing.")
                    
    else:
        st.warning("Your user type does not have access to this monitoring section.")

# Initialize database (ensure this is called only once per app run)
initialize_database()

# For local testing of this module
if __name__ == "__main__":
    st.set_page_config(page_title="Tree Monitoring Module Test", layout="wide")

    # Set dummy secrets for local testing if not already configured via .streamlit/secrets.toml
    if "KOBO_API_TOKEN" not in st.secrets:
        st.secrets["KOBO_API_TOKEN"] = "dummy_token_for_testing"
        st.secrets["KOBO_ASSET_ID"] = "dummy_asset_id_for_testing"
        st.secrets["KOBO_MONITORING_ASSET_ID"] = "aDSNfsXbXygrn8rwKog5Yd" # Use the provided one

    # Simulate user session for testing this module directly
    # This block is crucial for resolving "User session missing" when running kobo_monitoring.py directly
    if 'user' not in st.session_state:
        st.session_state.user = {
            "username": "test_monitor_user", # Added a more distinct name
            "user_type": "field", # or "admin", "school"
            "email": "test@example.com",
            "institution": "Test Institution",
            "tree_tracking_number": "TRK123", # Example tracking number for testing
            "uid": "test_monitor_uid" # Added UID for fetch_monitoring_data
        }
        print(f"[DEBUG_MAIN] Initializing mock user session for standalone run: {st.session_state.user}")
    else:
        print(f"[DEBUG_MAIN] User session already exists: {st.session_state.user}")

    st.title("Tree Monitoring Module Test (Standalone)")
    st.info("This is a standalone test for the KoBo monitoring functionality. "
            "In a real app, this module is imported into `app.py` and run within the main application flow."
            " Ensure your `.streamlit/secrets.toml` has `KOBO_API_TOKEN`, `KOBO_ASSET_ID` (for planting), "
            "and `KOBO_MONITORING_ASSET_ID` (for monitoring) configured.")

    monitoring_section()
