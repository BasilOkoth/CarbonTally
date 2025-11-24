# --- Updated monitoring.py ---

import streamlit as st
from datetime import datetime, timedelta
import pandas as pd
import sqlite3
import json
import requests
from pathlib import Path
from carbonfao import calculate_co2_sequestered

# --- Configuration ---
# Standardize MONITORING_DB_PATH to be in the 'data' directory
BASE_DIR_MONITORING = Path(__file__).parent # Get the directory of kobo_monitoring.py
MONITORING_DB_PATH = BASE_DIR_MONITORING / 'data' / 'monitoring.db' # Corrected path
KOBO_API_URL = "https://kf.kobotoolbox.org/api/v2"
KOBO_API_TOKEN = st.secrets.get("KOBO_API_TOKEN", "your_api_token_here")
KOBO_MONITORING_ASSET_ID = st.secrets.get("KOBO_MONITORING_ASSET_ID", "your_asset_id_here")

# --- Monitoring DB Connection ---
def get_monitoring_db_connection():
    try:
        # Ensure the directory exists before attempting to connect
        MONITORING_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        print(f"DEBUG: Attempting to connect to Monitoring DB at: {MONITORING_DB_PATH}")
        return sqlite3.connect(str(MONITORING_DB_PATH)) # Use str() for compatibility
    except sqlite3.Error as e:
        st.error(f"Monitoring DB connection error: {e}")
        print(f"ERROR: Monitoring DB connection error: {e}")
        return None

def initialize_monitoring_db():
    conn = get_monitoring_db_connection()
    if not conn:
        print("ERROR: Failed to get monitoring DB connection for initialization.")
        return False
    try:
        c = conn.cursor()
        print("DEBUG: Executing CREATE TABLE IF NOT EXISTS processed_submissions in monitoring.db...")
        c.execute("""
        CREATE TABLE IF NOT EXISTS processed_submissions (
            submission_id TEXT PRIMARY KEY,
            tree_id TEXT NOT NULL,
            processed_at TEXT NOT NULL
        )
        """)
        print("DEBUG: CREATE TABLE processed_submissions executed.")

        print("DEBUG: Executing CREATE TABLE IF NOT EXISTS tree_monitoring in monitoring.db...")
        c.execute("""
        CREATE TABLE IF NOT EXISTS tree_monitoring (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tree_id TEXT NOT NULL,
            submission_id TEXT NOT NULL,
            dbh_cm REAL,
            height_m REAL,
            rcd_cm REAL,
            co2_kg REAL,
            monitored_at TEXT
        )
        """)
        print("DEBUG: CREATE TABLE tree_monitoring executed.")
        conn.commit()
        print("✅ Monitoring.db tables initialized or verified. All commits successful.")
        return True
    except sqlite3.Error as e:
        st.error(f"Monitoring DB initialization error: {e}")
        print(f"ERROR: Monitoring DB initialization error: {e}")
        return False
    finally:
        if conn:
            conn.close()
            print("DEBUG: Monitoring DB connection closed after initialization.")

# --- Helpers ---
def try_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None

def validate_user_session():
    if 'authenticated' not in st.session_state or not st.session_state.authenticated:
        st.warning("Please log in.")
        return False
    if 'user' not in st.session_state:
        st.warning("Session error.")
        return False
    if 'treeTrackingNumber' not in st.session_state.get('user', {}):
        st.warning("No tree tracking number associated with this user.")
        return False
    return True

# --- KoBo ---
def get_monitoring_submissions(asset_id, hours=24):
    headers = {"Authorization": f"Token {KOBO_API_TOKEN}"}
    since_time = datetime.utcnow() - timedelta(hours=hours)
    params = {
        "format": "json",
        "query": json.dumps({
            "_submission_time": {"$gte": since_time.isoformat(timespec='seconds') + 'Z'}
        })
    }
    try:
        response = requests.get(f"{KOBO_API_URL}/assets/{asset_id}/data/", headers=headers, params=params)
        response.raise_for_status()
        return response.json().get("results", [])
    except requests.RequestException as e:
        st.error(f"Submission fetch error: {e}")
        return []

# Ensure get_db_connection in kobo_monitoring also uses an absolute path if it's meant to connect to trees.db
def get_db_connection():
    # This connects to trees.db, ensure its path is also robust
    BASE_DIR_TREES = Path(__file__).parent if "__file__" in locals() else Path.cwd()
    SQLITE_DB_TREES = BASE_DIR_TREES / "data" / "trees.db"
    return sqlite3.connect(str(SQLITE_DB_TREES)) # Use str() for compatibility

def get_tree_data(tree_id):
    conn = get_db_connection() # This connects to trees.db
    try:
        query = "SELECT scientific_name, latitude, longitude FROM trees WHERE tree_id = ?"
        cursor = conn.cursor()
        cursor.execute(query, (tree_id,))
        row = cursor.fetchone()
        if row:
            return {"scientific_name": row[0], "latitude": row[1], "longitude": row[2]}
        return None
    except sqlite3.Error as e:
        st.error(f"Tree fetch error: {e}")
        return None
    finally:
        conn.close()

def is_submission_processed(submission_id):
    conn = get_monitoring_db_connection() # This connects to monitoring.db
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM processed_submissions WHERE submission_id = ?", (submission_id,))
        return cursor.fetchone() is not None
    finally:
        conn.close()

def save_monitoring_record(tree_id, submission_id, dbh_cm, height_m, co2_kg):
    conn = get_monitoring_db_connection() # This connects to monitoring.db
    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO tree_monitoring (tree_id, submission_id, dbh_cm, height_m, co2_kg, monitored_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (tree_id, submission_id, dbh_cm, height_m, co2_kg, datetime.utcnow().isoformat()))
        conn.commit()
    finally:
        conn.close()

def update_tree_inventory(tree_id, dbh_cm, height_m, co2_kg):
    # This function updates the 'trees' table in trees.db, not monitoring.db
    conn = get_db_connection()
    try:
        conn.execute("""
            UPDATE trees SET dbh_cm = ?, height_m = ?, co2_kg = ?, last_monitored_at = ?
            WHERE tree_id = ?
        """, (dbh_cm, height_m, co2_kg, datetime.utcnow().isoformat(), tree_id))
        conn.commit()
    finally:
        conn.close()

def mark_submission_processed(submission_id, tree_id):
    conn = get_monitoring_db_connection() # This connects to monitoring.db
    try:
        conn.execute("""
            INSERT INTO processed_submissions (submission_id, tree_id, processed_at)
            VALUES (?, ?, ?)
        """, (submission_id, tree_id, datetime.utcnow().isoformat()))
        conn.commit()
    finally:
        conn.close()

def process_submission(submission):
    tree_id = submission.get("tree_id")
    submission_id = submission.get("_id")

    if not tree_id or not submission_id:
        return False

    if is_submission_processed(submission_id):
        return True

    tree_data = get_tree_data(tree_id) # This gets data from trees.db
    if not tree_data:
        st.warning(f"Tree {tree_id} not found.")
        return False

    dbh_cm = try_float(submission.get("dbh_cm"))
    rcd_cm = try_float(submission.get("rcd_cm"))
    height_m = try_float(submission.get("height_m"))

    diameter_cm = dbh_cm if dbh_cm else rcd_cm
    co2_kg = None

    if diameter_cm is not None and height_m is not None:
        co2_kg = calculate_co2_sequestered(
            diameter_cm,
            height_m,
            tree_data["scientific_name"],
            tree_data["latitude"],
            tree_data["longitude"]
        )
    else:
        st.warning(f"Missing or invalid DBH/RCD or height for tree {tree_id}. Skipping CO₂ calculation.")

    save_monitoring_record(tree_id, submission_id, diameter_cm, height_m, co2_kg)
    update_tree_inventory(tree_id, diameter_cm, height_m, co2_kg)
    mark_submission_processed(submission_id, tree_id)

    st.success(f"✅ Processed submission for tree {tree_id}")
    return True

def process_new_submissions(hours=24):
    if not validate_user_session():
        st.error("Session validation failed")
        return 0

    user_tracking_number = st.session_state.get('user', {}).get('treeTrackingNumber', '').strip().lower()
    if not user_tracking_number:
        st.error("No tracking number found in user session")
        return 0

    submissions = get_monitoring_submissions(KOBO_MONITORING_ASSET_ID, hours)
    count = 0

    for submission in submissions:
        tree_id = submission.get("tree_id")
        if not tree_id:
            continue

        tree_data = get_tree_data(tree_id) # This gets data from trees.db
        if not tree_data:
            st.warning(f"Tree {tree_id} not found in database")
            continue

        conn = get_db_connection() # This connects to trees.db
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT treeTrackingNumber FROM trees WHERE tree_id = ?", (tree_id,))
            row = cursor.fetchone()
            if not row or not row[0]:
                st.warning(f"No tracking number found for tree {tree_id} in database")
                continue
                
            db_tracking = str(row[0]).strip().lower()
        finally:
            conn.close()

        # REVERTED: Using 'tree_tracking_number' (snake_case) as confirmed by user for Kobo submissions
        submission_tracking = str(submission.get("tree_tracking_number", "")).strip().lower() # This line was updated

        if submission_tracking and submission_tracking != db_tracking:
            st.warning(f"Skipping submission for tree {tree_id}: tracking number mismatch between Kobo data and DB record.")
            continue

        if db_tracking != user_tracking_number:
            st.warning(f"Tree {tree_id} doesn't belong to this user (tracking number mismatch with user session).")
            continue

        if process_submission(submission):
            count += 1

    return count

def monitoring_section():
    st.title("🌿 Tree Monitoring System")

    if not initialize_monitoring_db(): # This initializes monitoring.db
        st.error("Failed to initialize monitoring database")
        return

    # Store the last seen timestamp in session state
    if 'last_view_time' not in st.session_state:
        st.session_state.last_view_time = datetime.utcnow()

    tab1, tab2 = st.tabs(["Process Submissions", "View Processed Data"])

    with tab1:
        st.header("Process New Submissions")
        hours = st.slider("Look back hours", min_value=1, max_value=168, value=24, key="hours_back")

        if st.button("Check for New Submissions"):
            processed = process_new_submissions(hours)
            st.success(f"Processed {processed} new submissions")
            # Update last view time when processing new submissions
            st.session_state.last_view_time = datetime.utcnow()

    with tab2:
        st.header("Previously Processed Submissions")

        monitoring_conn = get_monitoring_db_connection() # Connects to monitoring.db
        main_db_conn = get_db_connection() # Connects to trees.db
        
        if monitoring_conn and main_db_conn:
            try:
                # Get monitoring data with tracking numbers
                monitoring_df = pd.read_sql_query("SELECT * FROM tree_monitoring", monitoring_conn) # Correctly queries monitoring.db
                trees_df = pd.read_sql_query("SELECT tree_id, treeTrackingNumber, local_name FROM trees", main_db_conn) # Correctly queries trees.db
                
                if not monitoring_df.empty and not trees_df.empty:
                    df = pd.merge(
                        monitoring_df,
                        trees_df,
                        on='tree_id',
                        how='left'
                    )
                    
                    # Convert monitored_at to datetime and identify new entries
                    df['monitored_at'] = pd.to_datetime(df['monitored_at'])
                    df['is_new'] = df['monitored_at'] > st.session_state.last_view_time
                    
                    # Rename columns for display
                    df = df.rename(columns={
                        'tree_id': 'Tree ID',
                        'treeTrackingNumber': 'Tracking Number', # Corrected
                        'local_name': 'Tree Name', # Added Tree Name for display
                        'dbh_cm': 'DBH (cm)',
                        'height_m': 'Height (m)',
                        'co2_kg': 'CO₂ (kg)',
                        'monitored_at': 'Monitored At'
                        })
                    
                    # Apply styling to highlight new entries
                    def highlight_new(row):
                        if row['is_new']:
                            return ['background-color: #e6ffe6'] * len(row)
                        else:
                            return [''] * len(row)
                    
                    styled_df = df.style.apply(highlight_new, axis=1)
                    
                    # Display the styled dataframe
                    st.dataframe(styled_df)
                    
                    # Update last view time after displaying
                    st.session_state.last_view_time = datetime.utcnow()
                    
                else:
                    st.info("No monitoring records yet")
                    
            except Exception as e:
                st.error(f"Error loading monitoring data: {e}")
            finally:
                monitoring_conn.close()
                main_db_conn.close()
if __name__ == "__main__":
    monitoring_section()
