import streamlit as st
from datetime import datetime, timedelta
import pandas as pd
import sqlite3
import json
import requests
from pathlib import Path
from carbonfao import calculate_co2_sequestered

# --- Configuration ---
MONITORING_DB_PATH = "monitoring.db"
KOBO_API_URL = "https://kf.kobotoolbox.org/api/v2"
KOBO_API_TOKEN = st.secrets.get("KOBO_API_TOKEN", "your_api_token_here")
KOBO_MONITORING_ASSET_ID = st.secrets.get("KOBO_MONITORING_ASSET_ID", "your_asset_id_here")

# --- Monitoring DB Connection ---
def get_monitoring_db_connection():
    try:
        return sqlite3.connect(MONITORING_DB_PATH)
    except sqlite3.Error as e:
        st.error(f"Monitoring DB error: {e}")
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
        conn.commit()
        return True
    except sqlite3.Error as e:
        st.error(f"Init error: {e}")
        return False
    finally:
        conn.close()

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
def get_db_connection():
    BASE_DIR = Path(__file__).parent if "__file__" in locals() else Path.cwd()
    SQLITE_DB = BASE_DIR / "data" / "trees.db"
    return sqlite3.connect(SQLITE_DB)

def get_tree_data(tree_id):
    conn = get_db_connection()
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
    conn = get_monitoring_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM processed_submissions WHERE submission_id = ?", (submission_id,))
        return cursor.fetchone() is not None
    finally:
        conn.close()

def save_monitoring_record(tree_id, submission_id, dbh_cm, height_m, co2_kg):
    conn = get_monitoring_db_connection()
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
    conn = get_monitoring_db_connection()
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

    tree_data = get_tree_data(tree_id)
    if not tree_data:
        st.warning(f"Tree {tree_id} not found.")
        return False

    # Try DBH first, fallback to RCD if DBH is missing
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

    # Save record
    save_monitoring_record(tree_id, submission_id, diameter_cm, height_m, co2_kg)

    # Update tree inventory
    update_tree_inventory(tree_id, diameter_cm, height_m, co2_kg)

    # Mark as processed
    mark_submission_processed(submission_id, tree_id)

    st.success(f"✅ Processed submission for tree {tree_id}")
    return True

def process_new_submissions(hours=24):
    if not validate_user_session():
        return 0
    submissions = get_monitoring_submissions(KOBO_MONITORING_ASSET_ID, hours)
    count = 0
    for submission in submissions:
        if process_submission(submission):
            count += 1
    return count

def monitoring_section():
    st.title("🌿 Tree Monitoring System")

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

        conn = get_monitoring_db_connection()
        if conn:
            try:
                df = pd.read_sql_query(
                    "SELECT tree_id, submission_id, dbh_cm, rcd_cm, height_m, co2_kg, notes, monitored_at FROM tree_monitoring ORDER BY monitored_at DESC",
                    conn
                )
                if not df.empty:
                    st.dataframe(df)
                else:
                    st.info("No monitoring records yet")
            except sqlite3.Error as e:
                st.error(f"Error loading monitoring data: {e}")
            finally:
                conn.close()

        conn2 = get_monitoring_db_connection()
        if conn2:
            try:
                df_monitor = pd.read_sql_query("SELECT * FROM tree_monitoring", conn2)
                total_co2 = df_monitor["co2_kg"].sum()
                total_trees_monitored = df_monitor["tree_id"].nunique()
                st.metric("Total CO₂ Sequestered", f"{total_co2:.2f} kg")
                st.metric("Trees Monitored", total_trees_monitored)
            except sqlite3.Error as e:
                st.error(f"Error loading monitoring summary: {e}")
            finally:
                conn2.close()
if __name__ == "__main__":
    monitoring_section()
