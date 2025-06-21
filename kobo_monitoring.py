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

# KoBo Toolbox configuration
KOBO_API_URL = "https://kf.kobotoolbox.org/api/v2"
try:
    KOBO_API_TOKEN = st.secrets["KOBO_API_TOKEN"] # Using directly from secrets
    KOBO_ASSET_ID = st.secrets.get("KOBO_ASSET_ID") # For planting forms, might not be needed directly here
    KOBO_MONITORING_ASSET_ID = st.secrets["KOBO_MONITORING_ASSET_ID"]
except KeyError as e:
    st.warning(f"Could not load KoBo monitoring secrets: {e}. Please ensure KOBO_API_TOKEN and KOBO_MONITORING_ASSET_ID are set in your secrets.toml.")
    # Fallback to dummy values if secrets are not configured, for local testing flexibility
    KOBO_API_TOKEN = "dummy_token_for_testing"
    KOBO_ASSET_ID = "dummy_asset_id_for_testing"
    KOBO_MONITORING_ASSET_ID = "aDSNfsXbXygrn8rwKog5Yd" # Placeholder from original file

# Database configuration
BASE_DIR = Path(__file__).parent if "__file__" in locals() else Path.cwd()
DATA_DIR = BASE_DIR / "data"
SQLITE_DB = DATA_DIR / "trees.db"
QR_CODE_DIR = DATA_DIR / "qr_codes"
DATA_DIR.mkdir(exist_ok=True, parents=True)
QR_CODE_DIR.mkdir(exist_ok=True, parents=True)

def initialize_database():
    """Initialize database tables"""
    conn = sqlite3.connect(SQLITE_DB)
    try:
        c = conn.cursor()
        c.execute('''
            CREATE TABLE IF NOT EXISTS trees (
                tree_id TEXT PRIMARY KEY,
                local_name TEXT,
                scientific_name TEXT,
                planters_name TEXT,
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
                last_updated TEXT,
                planter_email TEXT,
                planter_uid TEXT,
                planter_tracking_id TEXT UNIQUE
            )
        ''')
        # Add monitoring_records table
        c.execute('''
            CREATE TABLE IF NOT EXISTS monitoring_records (
                record_id TEXT PRIMARY KEY,
                tree_id TEXT NOT NULL,
                date_recorded TEXT,
                tree_stage TEXT,
                rcd_cm REAL,
                dbh_cm REAL,
                height_m REAL,
                health_status TEXT,
                notes TEXT,
                recorder_email TEXT,
                FOREIGN KEY (tree_id) REFERENCES trees(tree_id)
            )
        ''')
        conn.commit()
    except Exception as e:
        st.error(f"Monitoring Database initialization error: {e}")
    finally:
        conn.close()

def validate_user_session():
    """Ensure user is logged in for certain actions."""
    if 'authenticated' not in st.session_state or not st.session_state.authenticated:
        st.warning("Please log in to perform this action.")
        return False
    if 'user' not in st.session_state:
        st.warning("User session data missing. Please log in again.")
        return False
    return True

def get_monitoring_submissions(asset_id, last_n_hours=None):
    """Fetches monitoring submissions from a specific KoBo asset."""
    headers = {"Authorization": f"Token {KOBO_API_TOKEN}"}
    url = f"{KOBO_API_URL}/assets/{asset_id}/data/"
    params = {"format": "json"}

    if last_n_hours:
        time_ago = datetime.utcnow() - timedelta(hours=last_n_hours)
        params["query"] = json.dumps({"_submission_time": {"$gte": time_ago.isoformat(timespec='seconds') + 'Z'}})

    try:
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.HTTPError as http_err:
        st.error(f"HTTP error fetching monitoring submissions: {http_err} - Response: {response.text}")
    except Exception as err:
        st.error(f"Other error fetching monitoring submissions: {err}")
    return []

def map_kobo_monitoring_to_database(submission_data):
    """Maps KoBo monitoring submission data to the database schema."""
    record_id = str(uuid.uuid4())
    tree_id = submission_data.get('tree_id_monitoring') # The tree ID being monitored
    date_recorded = submission_data.get('date_of_monitoring')
    tree_stage = submission_data.get('tree_status_update/tree_stage_current')
    rcd_cm = submission_data.get('tree_status_update/rcd_cm_current')
    dbh_cm = submission_data.get('tree_status_update/dbh_cm_current')
    height_m = submission_data.get('tree_status_update/height_m_current')
    health_status = submission_data.get('tree_status_update/health_status')
    notes = submission_data.get('additional_notes')
    recorder_email = submission_data.get('monitor_email') # Email of the person doing the monitoring

    return {
        "record_id": record_id,
        "tree_id": tree_id,
        "date_recorded": date_recorded,
        "tree_stage": tree_stage,
        "rcd_cm": rcd_cm,
        "dbh_cm": dbh_cm,
        "height_m": height_m,
        "health_status": health_status,
        "notes": notes,
        "recorder_email": recorder_email
    }

def save_monitoring_record(record_data):
    """Saves mapped monitoring record data to the SQLite database and updates tree."""
    conn = sqlite3.connect(SQLITE_DB)
    try:
        c = conn.cursor()
        columns = ', '.join(record_data.keys())
        placeholders = ':' + ', :'.join(record_data.keys())
        sql = f"INSERT INTO monitoring_records ({columns}) VALUES ({placeholders})"
        c.execute(sql, record_data)

        # Update the main trees table with the latest monitoring data
        update_tree_sql = """
            UPDATE trees
            SET
                tree_stage = ?,
                rcd_cm = ?,
                dbh_cm = ?,
                height_m = ?,
                status = ?, -- Can be derived from health_status or a separate field
                co2_kg = ?, -- Recalculate based on new measurements
                last_updated = ?
            WHERE tree_id = ?
        """
        co2_kg = (
            calculate_co2_sequestered(record_data['dbh_cm'], record_data['height_m'])
            if record_data['dbh_cm'] and record_data['height_m'] else 0.0
        )
        c.execute(update_tree_sql, (
            record_data['tree_stage'],
            record_data['rcd_cm'],
            record_data['dbh_cm'],
            record_data['height_m'],
            record_data['health_status'], # Using health_status as tree status for now
            co2_kg,
            datetime.utcnow().isoformat(),
            record_data['tree_id']
        ))
        conn.commit()
        st.success(f"Monitoring record for Tree ID {record_data['tree_id']} saved and tree data updated!")
    except Exception as e:
        st.error(f"Error saving monitoring record: {e}")
    finally:
        conn.close()

def check_for_new_monitoring_submissions(hours=24):
    """Checks for and processes new monitoring submissions."""
    st.info(f"Checking for new monitoring submissions in the last {hours} hours...")
    submissions = get_monitoring_submissions(KOBO_MONITORING_ASSET_ID, last_n_hours=hours)

    if not submissions:
        st.info("No new monitoring submissions found.")
        return []

    processed_records = []
    for submission in submissions:
        try:
            mapped_data = map_kobo_monitoring_to_database(submission)
            if mapped_data:
                save_monitoring_record(mapped_data)
                processed_records.append(mapped_data)
        except Exception as e:
            st.error(f"Error processing monitoring submission {submission.get('_id')}: {e}")
    if processed_records:
        st.success(f"Successfully processed {len(processed_records)} new monitoring submissions.")
    return processed_records

def get_tree_details(tree_id):
    """Retrieves full details for a given tree_id from the database."""
    conn = sqlite3.connect(SQLITE_DB)
    try:
        df_tree = pd.read_sql_query(f"SELECT * FROM trees WHERE tree_id = '{tree_id}'", conn)
        df_monitoring = pd.read_sql_query(f"SELECT * FROM monitoring_records WHERE tree_id = '{tree_id}' ORDER BY date_recorded DESC", conn)
        if not df_tree.empty:
            tree_data = df_tree.iloc[0].to_dict()
            tree_data['monitoring_history'] = df_monitoring.to_dict(orient='records')
            return tree_data
        return None
    except Exception as e:
        st.error(f"Error fetching tree details: {e}")
        return None
    finally:
        conn.close()

def display_tree_details(tree_data):
    """Displays detailed information about a single tree."""
    st.subheader(f"Details for Tree ID: {tree_data.get('tree_id')}")
    col1, col2 = st.columns(2)
    with col1:
        st.write(f"**Species:** {tree_data.get('local_name')} ({tree_data.get('scientific_name')})")
        st.write(f"**Planter:** {tree_data.get('planters_name')}")
        st.write(f"**Date Planted:** {tree_data.get('date_planted')}")
        st.write(f"**Current Status:** {tree_data.get('status')}")
        st.write(f"**Current Stage:** {tree_data.get('tree_stage')}")
    with col2:
        st.write(f"**Current RCD:** {tree_data.get('rcd_cm'):.2f} cm")
        st.write(f"**Current DBH:** {tree_data.get('dbh_cm'):.2f} cm")
        st.write(f"**Current Height:** {tree_data.get('height_m'):.2f} m")
        st.write(f"**Estimated CO₂:** {tree_data.get('co2_kg'):.2f} kg/year")
        st.write(f"**Location:** Lat {tree_data.get('latitude')}, Lon {tree_data.get('longitude')}")

    # Display monitoring history
    monitoring_history = tree_data.get('monitoring_history', [])
    if monitoring_history:
        st.subheader("Monitoring History")
        df_history = pd.DataFrame(monitoring_history)
        # Convert date_recorded to datetime for sorting and plotting
        df_history['date_recorded'] = pd.to_datetime(df_history['date_recorded'])
        df_history = df_history.sort_values('date_recorded').reset_index(drop=True)

        st.dataframe(df_history[['date_recorded', 'tree_stage', 'rcd_cm', 'dbh_cm', 'height_m', 'health_status', 'notes', 'recorder_email']])

        # Plot growth over time
        if not df_history.empty:
            st.subheader("Growth Timeline")
            fig = plt.figure(figsize=(10, 5))
            if 'dbh_cm' in df_history.columns and df_history['dbh_cm'].notna().any():
                sns.lineplot(data=df_history, x='date_recorded', y='dbh_cm', marker='o', label='DBH (cm)')
            if 'height_m' in df_history.columns and df_history['height_m'].notna().any():
                sns.lineplot(data=df_history, x='date_recorded', y='height_m', marker='x', label='Height (m)')
            plt.title(f"Growth Timeline for Tree ID: {tree_data.get('tree_id')}")
            plt.xlabel("Date")
            plt.ylabel("Measurement")
            plt.legend()
            st.pyplot(fig)
        else:
            st.info("No timeline data")

def display_monitoring_dashboard():
    """Displays an overview dashboard of monitoring data."""
    st.subheader("Monitoring Overview Dashboard")
    conn = sqlite3.connect(SQLITE_DB)
    try:
        df_trees = pd.read_sql_query("SELECT * FROM trees", conn)
        df_monitoring = pd.read_sql_query("SELECT * FROM monitoring_records", conn)

        st.write(f"Total Trees Tracked: {len(df_trees)}")
        st.write(f"Total Monitoring Records: {len(df_monitoring)}")

        if not df_trees.empty:
            st.subheader("Tree Status Distribution")
            fig_status = px.pie(df_trees, names='status', title='Distribution of Tree Status')
            st.plotly_chart(fig_status, use_container_width=True)

            st.subheader("CO2 Sequestration by Species")
            co2_by_species = df_trees.groupby('local_name')['co2_kg'].sum().reset_index()
            fig_co2 = px.bar(co2_by_species, x='local_name', y='co2_kg', title='Total CO2 Sequestered by Species')
            st.plotly_chart(fig_co2, use_container_width=True)

        if not df_monitoring.empty:
            st.subheader("Monitoring Activity Over Time")
            df_monitoring['date_recorded'] = pd.to_datetime(df_monitoring['date_recorded'])
            monitoring_counts = df_monitoring.groupby(df_monitoring['date_recorded'].dt.to_period('M')).size().reset_index(name='count')
            monitoring_counts['date_recorded'] = monitoring_counts['date_recorded'].astype(str)
            fig_activity = px.line(monitoring_counts, x='date_recorded', y='count', title='Number of Monitoring Records per Month')
            st.plotly_chart(fig_activity, use_container_width=True)

    except Exception as e:
        st.error(f"Error loading monitoring dashboard data: {e}")
    finally:
        conn.close()


def monitoring_section():
    """Main monitoring interface"""
    st.title("🌳 Tree Monitoring System")
    initialize_database()

    tabs = st.tabs(["Tree Lookup", "Monitoring Dashboard", "Process Submissions"])

    with tabs[0]:
        tree_id = st.text_input("Enter Tree ID")
        if tree_id:
            tree_data = get_tree_details(tree_id)
            if tree_data:
                display_tree_details(tree_data)
            else:
                st.error("Tree not found")

    with tabs[1]:
        display_monitoring_dashboard()

    with tabs[2]:
        hours = st.slider("Hours to check", 1, 168, 24)
        if st.button("Check for New Submissions"):
            if validate_user_session():
                with st.spinner("Processing..."):
                    results = check_for_new_monitoring_submissions(hours)
                    if results:
                        st.success(f"Processed {len(results)} submissions")
                    else:
                        st.info("No new submissions found")
            else:
                st.warning("Please log in")

# --- Placeholder/Mapping functions for app.py imports ---
# This function was listed in app.py's import.
# Assuming admin_tree_lookup is intended to call admin_dashboard_monitoring.
def admin_tree_lookup(query):
    """
    Placeholder for admin tree lookup.
    Currently, it simply calls display_monitoring_dashboard or can be adapted.
    If it requires a user_type for filtering, that needs to be passed.
    For now, it returns an empty DataFrame to satisfy the import.
    """
    st.info(f"Admin tree lookup for query '{query}' is not fully implemented yet in kobo_monitoring.py. Displaying overall dashboard.")
    display_monitoring_dashboard() # As a fallback, show the general dashboard
    return pd.DataFrame() # Return empty DataFrame to satisfy potential return type expectations

def calculate_co2_sequestered(dbh_cm, height_m):
    """
    Calculates estimated CO2 sequestered based on DBH and Height.
    This is a simplified placeholder, copied from kobo_integration for consistency.
    """
    if dbh_cm is None or height_m is None or dbh_cm <= 0 or height_m <= 0:
        return 0.0
    co2_per_unit = 0.5 # kg CO2 per (cm DBH * m Height)
    return dbh_cm * height_m * co2_per_unit

# Initialize database when this module is imported
initialize_database()

# For local testing
if __name__ == "__main__":
    st.set_page_config(page_title="Tree Monitoring", layout="wide")
    # Simulate st.secrets for standalone testing
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
            "tree_tracking_number": "TRK123" # Example tracking number for testing
        }
        print(f"[DEBUG_MAIN] Initializing mock user session for standalone run: {st.session_state.user}")
    else:
        print(f"[DEBUG_MAIN] User session already exists: {st.session_state.user}")
    
    # Simulate authentication state if running standalone
    if 'authenticated' not in st.session_state:
        st.session_state.authenticated = True

    st.title("Tree Monitoring Module Test (Standalone)")
    st.info("This is a standalone test for the KoBo monitoring functionality. "
            "In a real app, this module is imported into `app.py`.")
    
    monitoring_section()
