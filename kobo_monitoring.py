import streamlit as st
from datetime import datetime, timedelta
import pandas as pd
import sqlite3
import uuid
import json
import requests
from pathlib import Path
import time
from carbonfao import calculate_co2_sequestered

# --- Configuration ---
# Path to your external tree database
TREE_DB_PATH = r"E:\CarbonTally-maintool\CarbonTally-main\data\trees.db"
# Path for local monitoring database
MONITORING_DB_PATH = "monitoring.db"

# --- KoBo Toolbox Configuration ---
KOBO_API_URL = "https://kf.kobotoolbox.org/api/v2"
KOBO_API_TOKEN = st.secrets.get("KOBO_API_TOKEN", "your_api_token_here")
KOBO_MONITORING_ASSET_ID = st.secrets.get("KOBO_MONITORING_ASSET_ID", "your_asset_id_here")

# --- Database Functions ---
def get_tree_db_connection():
    """Connect to the external tree database"""
    try:
        conn = sqlite3.connect(TREE_DB_PATH)
        return conn
    except sqlite3.Error as e:
        st.error(f"Tree database connection error: {e}")
        return None

def get_monitoring_db_connection():
    """Connect to the local monitoring database"""
    try:
        conn = sqlite3.connect(MONITORING_DB_PATH)
        return conn
    except sqlite3.Error as e:
        st.error(f"Monitoring database connection error: {e}")
        return None

def initialize_monitoring_db():
    conn = get_monitoring_db_connection()
    if not conn:
        return False

    try:
        conn.execute("""
        CREATE TABLE IF NOT EXISTS processed_submissions (
            submission_id TEXT PRIMARY KEY,
            tree_id TEXT NOT NULL,
            processed_at TEXT NOT NULL
        )
        """)
        
        conn.execute("""
        CREATE TABLE IF NOT EXISTS tree_monitoring (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tree_id TEXT NOT NULL,
            submission_id TEXT NOT NULL,
            dbh_cm REAL,
            height_m REAL,
            co2_kg REAL,
            monitored_at TEXT
        )
        """)
        
        return True
    except sqlite3.Error as e:
        st.error(f"Error initializing monitoring database: {e}")
        return False
    finally:
        conn.commit()
        conn.close()

# --- Helper Functions ---
def try_float(value):
    """Safely convert value to float"""
    try:
        return float(value)
    except (TypeError, ValueError):
        return None

def validate_user_session():
    """Check if user is properly authenticated"""
    if 'authenticated' not in st.session_state or not st.session_state.authenticated:
        st.warning("Please log in to perform this action.")
        return False
    if 'user' not in st.session_state:
        st.warning("User session data missing. Please log in again.")
        return False
    return True

# --- KoBo Integration Functions ---
def get_monitoring_submissions(asset_id, hours=24):
    """Fetch monitoring submissions from KoBoToolbox"""
    headers = {"Authorization": f"Token {KOBO_API_TOKEN}"}
    since_time = datetime.utcnow() - timedelta(hours=hours)
    params = {
        "format": "json",
        "query": json.dumps({
            "_submission_time": {
                "$gte": since_time.isoformat(timespec='seconds') + 'Z'
            }
        })
    }
    
    try:
        response = requests.get(
            f"{KOBO_API_URL}/assets/{asset_id}/data/",
            headers=headers,
            params=params
        )
        response.raise_for_status()
        return response.json().get("results", [])
    except requests.exceptions.RequestException as e:
        st.error(f"Error fetching submissions: {e}")
        return []

def get_tree_data(tree_id):
    """Retrieve species and coordinates from external tree database"""
    conn = get_tree_db_connection()
    if not conn:
        return None
    
    try:
        query = """
        SELECT scientific_name, latitude, longitude 
        FROM trees 
        WHERE tree_id = ?
        """
        cursor = conn.cursor()
        cursor.execute(query, (tree_id,))
        row = cursor.fetchone()
        
        if row:
            return {
                "scientific_name": row[0],
                "latitude": row[1],
                "longitude": row[2]
            }
        return None
    except sqlite3.Error as e:
        st.error(f"Error fetching tree data: {e}")
        return None
    finally:
        conn.close()

def is_submission_processed(submission_id):
    """Check if submission has already been processed"""
    conn = get_monitoring_db_connection()
    if not conn:
        return False
    
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT 1 FROM processed_submissions WHERE submission_id = ?",
            (submission_id,)
        )
        return cursor.fetchone() is not None
    except sqlite3.Error as e:
        st.error(f"Error checking submission status: {e}")
        return False
    finally:
        conn.close()
def update_tree_inventory(tree_id, dbh_cm, height_m, co2_kg):
    """Update tree record in trees.db"""
    conn = get_tree_db_connection()
    if not conn:
        return False

    try:
        conn.execute("""
            UPDATE trees
            SET dbh_cm = ?, height_m = ?, co2_kg = ?, last_monitored_at = ?
            WHERE tree_id = ?
        """, (dbh_cm, height_m, co2_kg, datetime.utcnow().isoformat(), tree_id))
        conn.commit()
        return True
    except sqlite3.Error as e:
        st.error(f"❌ Error updating tree inventory: {e}")
        return False
    finally:
        conn.close()

def mark_submission_processed(submission_id, tree_id):
    """Record that a submission has been processed"""
    conn = get_monitoring_db_connection()
    if not conn:
        return False
    
    try:
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO processed_submissions 
               (submission_id, tree_id, processed_at) 
               VALUES (?, ?, ?)""",
            (submission_id, tree_id, datetime.utcnow().isoformat())
        )
        conn.commit()
        return True
    except sqlite3.Error as e:
        conn.rollback()
        st.error(f"Error marking submission processed: {e}")
        return False
    finally:
        conn.close()
def save_monitoring_record(tree_id, submission_id, dbh_cm, height_m, co2_kg):
    conn = get_monitoring_db_connection()
    if not conn:
        return False
    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO tree_monitoring (tree_id, submission_id, dbh_cm, height_m, co2_kg, monitored_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (tree_id, submission_id, dbh_cm, height_m, co2_kg, datetime.utcnow().isoformat()))
        conn.commit()
        return True
    except sqlite3.Error as e:
        conn.rollback()
        st.error(f"Error saving monitoring record: {e}")
        return False
    finally:
        conn.close()

# --- Data Processing Functions ---
def process_submission(submission):
    """Process a single KoBo submission"""
    tree_id = submission.get("tree_id")
    submission_id = submission.get("_id")
    
    if not tree_id or not submission_id:
        st.warning("Submission missing tree_id or _id")
        return False
    
    if is_submission_processed(submission_id):
        return True
    
    tree_data = get_tree_data(tree_id)
    if not tree_data:
        st.warning(f"Could not find tree {tree_id} in database")
        return False
    
    dbh_cm = try_float(submission.get("dbh_cm"))
    height_m = try_float(submission.get("height_m"))
    
    co2_kg = None
    if dbh_cm and height_m:
        co2_kg = calculate_co2_sequestered(
            dbh_cm,
            height_m,
            tree_data["scientific_name"],
            tree_data["latitude"],
            tree_data["longitude"]
        )

    # Save monitoring data
    save_monitoring_record(tree_id, submission_id, dbh_cm, height_m, co2_kg)
    
    # Update inventory with latest measurements
    update_tree_inventory(tree_id, dbh_cm, height_m, co2_kg)

    # Mark this submission as processed
    mark_submission_processed(submission_id, tree_id)

    st.success(f"""
        ✅ Processed submission for tree {tree_id}:
        - Species: {tree_data['scientific_name']}
        - Location: {tree_data['latitude']}, {tree_data['longitude']}
        - DBH: {dbh_cm} cm
        - Height: {height_m} m
        - CO₂: {co2_kg} kg/year
    """)
    
    return True

def process_new_submissions(hours=24):
    """Process all new submissions"""
    if not validate_user_session():
        return 0
    
    submissions = get_monitoring_submissions(KOBO_MONITORING_ASSET_ID, hours)
    if not submissions:
        st.info("No new submissions found")
        return 0
    
    processed_count = 0
    with st.spinner(f"Processing {len(submissions)} submissions..."):
        for submission in submissions:
            if process_submission(submission):
                processed_count += 1
    
    return processed_count

# --- User Interface ---
def monitoring_section():
    """Main monitoring interface"""
    st.title("🌿 Tree Monitoring System")
    
    # Initialize databases
    if not initialize_monitoring_db():
        st.error("Failed to initialize monitoring database")
        return
    
    tab1, tab2 = st.tabs(["Process Submissions", "View Processed Data"])
    
    with tab1:
        st.header("Process New Submissions")
        hours = st.slider(
            "Look back hours", 
            min_value=1, 
            max_value=168, 
            value=24,
            key="hours_back"
        )
        
        if st.button("Check for New Submissions"):
            processed = process_new_submissions(hours)
            st.success(f"Processed {processed} new submissions")
    with tab2:
        st.header("Previously Processed Submissions")

    # Show processed submission records
    conn = get_monitoring_db_connection()
    if conn:
        try:
            df = pd.read_sql_query(
                "SELECT * FROM processed_submissions ORDER BY processed_at DESC",
                conn
            )
            if not df.empty:
                st.dataframe(df)
            else:
                st.info("No processed submissions yet")
        except sqlite3.Error as e:
            st.error(f"Error loading processed submissions: {e}")
        finally:
            conn.close()

    # Show summary stats from monitoring table
    conn2 = get_monitoring_db_connection()
    if conn2:
        try:
            df_monitor = pd.read_sql_query("SELECT * FROM tree_monitoring", conn2)
            total_co2 = df_monitor["co2_kg"].sum()
            total_trees_monitored = df_monitor["tree_id"].nunique()
            st.metric("Total CO₂ Sequestered", f"{total_co2:.2f} kg")
            st.metric("Trees Monitored", total_trees_monitored)
        except sqlite3.Error as e:
            st.error(f"Error loading monitoring data: {e}")
        finally:
            conn2.close()

# --- Main Application ---
if __name__ == "__main__":
    # Configure Streamlit
    st.set_page_config(
        page_title="Tree Monitoring System",
        page_icon="🌳",
        layout="wide"
    )
    
    # Initialize session state (for demo purposes)
    if 'user' not in st.session_state:
        st.session_state.user = {
            "username": "admin",
            "email": "admin@example.com"
        }
    if 'authenticated' not in st.session_state:
        st.session_state.authenticated = True
    
    # Run the monitoring interface
    monitoring_section()
