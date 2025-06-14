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
# IMPORTANT: These should ideally be loaded from st.secrets in a real application
# For direct execution of this module, ensure you have a .streamlit/secrets.toml
# or directly assign them for testing purposes in this file, though not recommended for production.
try:
    KOBO_API_TOKEN = st.secrets["KOBO_API_TOKEN"]
    KOBO_ASSET_ID = st.secrets["KOBO_ASSET_ID"] # This is for planting forms, not monitoring
    KOBO_MONITORING_ASSET_ID = st.secrets.get("KOBO_MONITORING_ASSET_ID", "aDSNfsXbXygrn8rwKog5Yd")
except Exception as e:
    st.warning(f"Could not load KoBo secrets. Please ensure `secrets.toml` is configured. Error: {e}")
    # Fallback to dummy values if secrets are not configured, for local testing flexibility
    KOBO_API_TOKEN = "dummy_token_for_testing"
    KOBO_ASSET_ID = "dummy_asset_id_for_testing"
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
        # Note: Added 'tree_tracking_number' to the initial CREATE TABLE statement directly.
        # This simplifies future migrations if this is the first time the DB is created.
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
            institutions_df = pd.read_sql(
                "SELECT DISTINCT institution FROM trees WHERE institution IS NOT NULL AND institution != ''",
                conn
            )
            available_institutions = institutions_df["institution"].tolist()
            print(f"[DEBUG_INST] Available institutions from DB: {available_institutions}")
        except Exception as e:
            st.error(f"Error fetching institutions: {e}")
            print(f"[DEBUG_INST] Error fetching institutions from DB: {e}")
            available_institutions = []
        finally:
            conn.close()
        
        if not available_institutions:
            available_institutions = ["School A", "School B", "NGO Partner", "Government Agency", "Other (specify)"]
        else:
            available_institutions = sorted(list(set(available_institutions))) # Remove duplicates and sort
            available_institutions = ["-- Select an institution --"] + available_institutions + ["Other (specify)"]
        
        selected_institution = st.selectbox(
            "Select your institution",
            available_institutions,
            index=0
        )
        
        if selected_institution == "Other (specify)":
            custom_institution = st.text_input("Enter your institution name")
            if custom_institution and custom_institution.strip():
                selected_institution = custom_institution.strip()
                print(f"[DEBUG_INST] Custom institution entered: {selected_institution}")
            else:
                selected_institution = None
                st.error("Please enter a valid custom institution name.")
                print("[DEBUG_INST] Custom institution input empty.")
        elif selected_institution == "-- Select an institution --":
            selected_institution = None
            st.error("Please select a valid institution.")
            print("[DEBUG_INST] Default 'Select an institution' option chosen.")
        
        if selected_institution:
            st.session_state.user["institution"] = selected_institution
            st.success(f"Institution set to: {selected_institution}")
            print(f"[DEBUG_INST] Institution set in session: {selected_institution}")
            st.experimental_rerun() # Rerun to apply institution change
            return selected_institution
        else:
            print("[DEBUG_INST] No valid institution selected/entered.")
            return None
    else:
        # For public users or roles not associated with institutions, no selection needed
        print(f"[DEBUG_INST] User type '{st.session_state.user.get('user_type')}' does not require institution assignment. Skipping.")
        return None


def generate_tree_qr_code(tree_id, tree_data=None):
    """
    Generate and save a single QR code for tree monitoring
    Returns: (base64_image, file_path)
    """
    try:
        if tree_data is None:
            tree_data = get_tree_details(tree_id)
            if tree_data is None:
                st.error(f"Tree with ID {tree_id} not found.")
                return None, None
        
        # Create URL with parameters for monitoring form
        # Use KOBO_MONITORING_ASSET_ID
        base_url = f"https://ee.kobotoolbox.org/x/{KOBO_MONITORING_ASSET_ID}"
        params = {
            "tree_id": tree_id,
            "local_name": tree_data.get("local_name", ""),
            "scientific_name": tree_data.get("scientific_name", ""),
            "date_planted": tree_data.get("date_planted", ""),
            "planter": tree_data.get("student_name", ""),
            "institution": tree_data.get("institution", ""),
            "tree_tracking_number": tree_data.get("tree_tracking_number", "") # Include tracking number
        }
        
        url_params = "&".join([f"{k}={v}" for k, v in params.items() if v])
        monitoring_url = f"{base_url}?{url_params}"
        
        # Generate QR code
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(monitoring_url)
        qr.make(fit=True)

        img = qr.make_image(fill_color="#2e8b57", back_color="white")

        # Save QR code
        QR_CODE_DIR.mkdir(exist_ok=True, parents=True)
        file_path = QR_CODE_DIR / f"{tree_id}.png"
        img.save(file_path)

        # Create base64 encoded version for display
        buffered = BytesIO()
        img.save(buffered, format="PNG")
        img_str = base64.b64encode(buffered.getvalue()).decode()

        return img_str, str(file_path)
    except Exception as e:
        st.error(f"Error generating QR code: {str(e)}")
        return None, None

def get_tree_details(tree_id):
    """Get complete details for a specific tree, including its tracking number."""
    if not tree_id:
        return None
        
    conn = sqlite3.connect(SQLITE_DB)
    try:
        # Include tree_tracking_number in the SELECT *
        tree_data_df = pd.read_sql(
            "SELECT * FROM trees WHERE tree_id = ?",
            conn,
            params=(tree_id,)
        )
        
        if tree_data_df.empty:
            return None
            
        monitoring_history_df = pd.read_sql(
            """
            SELECT * FROM monitoring_history 
            WHERE tree_id = ? 
            ORDER BY monitor_date DESC
            """,
            conn,
            params=(tree_data_df.iloc[0]["tree_id"],)
        )
        
        result = tree_data_df.iloc[0].to_dict()
        result["monitoring_history"] = monitoring_history_df.to_dict('records')
        print(f"[DEBUG] get_tree_details for {tree_id}: {result.get('tree_tracking_number')}")
        return result
    except Exception as e:
        st.error(f"Error getting tree details: {str(e)}")
        print(f"[DEBUG] Error in get_tree_details for {tree_id}: {e}")
        return None
    finally:
        conn.close()

def admin_tree_lookup():
    """Admin interface for looking up tree details and managing QR codes"""
    st.title("🔍 Admin Tree Lookup")
    
    # Validate admin access
    if not validate_user_session() or st.session_state.user.get("user_type") != "admin":
        st.error("Administrator access required")
        return
    
    # Tree ID input
    tree_id = st.text_input("Enter Tree ID")
    
    if tree_id:
        tree_data = get_tree_details(tree_id)
        if not tree_data:
            st.error("Tree not found")
            return
            
        # Display tree information
        st.subheader(f"Tree {tree_data['tree_id']}")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("### Basic Information")
            st.write(f"**Local Name:** {tree_data.get('local_name', 'N/A')}")
            st.write(f"**Scientific Name:** {tree_data.get('scientific_name', 'N/A')}")
            st.write(f"**Institution:** {tree_data.get('institution', 'N/A')}")
            st.write(f"**Planted By:** {tree_data.get('student_name', 'N/A')}")
            st.write(f"**Date Planted:** {tree_data.get('date_planted', 'N/A')}")
            st.write(f"**Tracking Number:** {tree_data.get('tree_tracking_number', 'N/A')}") # Display tracking number
            
        with col2:
            st.markdown("### Status & Measurements")
            st.write(f"**Status:** {tree_data.get('status', 'N/A')}")
            st.write(f"**Growth Stage:** {tree_data.get('tree_stage', 'N/A')}")
            st.write(f"**RCD:** {tree_data.get('rcd_cm', 'N/A')} cm")
            st.write(f"**DBH:** {tree_data.get('dbh_cm', 'N/A')} cm")
            st.write(f"**Height:** {tree_data.get('height_m', 'N/A')} m")
            st.write(f"**CO₂ Sequestered:** {tree_data.get('co2_kg', 'N/A')} kg")
        
        # QR Code Management
        st.subheader("QR Code Management")
        
        # Use generate_monitoring_qr_code which now includes tracking number
        qr_img_b64, qr_file_path, qr_monitoring_url = generate_monitoring_qr_code(tree_data['tree_id'], tree_data)

        if qr_img_b64:
            st.image(f"data:image/png;base64,{qr_img_b64}", 
                    caption=f"Monitoring QR for Tree {tree_data['tree_id']}")
            
            if os.path.exists(qr_file_path):
                with open(qr_file_path, "rb") as f:
                    st.download_button(
                        "Download QR Code",
                        f.read(),
                        file_name=f"tree_{tree_data['tree_id']}_monitoring_qr.png",
                        mime="image/png",
                        key=f"download_{tree_data['tree_id']}"
                    )
            st.markdown(f"**Monitoring Form URL:** [Link]({qr_monitoring_url})")
        else:
            st.warning("No QR code exists or could be generated for this tree.")
        
        if st.button("Generate/Regenerate QR Code"):
            with st.spinner("Generating QR code..."):
                # Call generate_monitoring_qr_code which updates the tree data's qr_code field
                qr_img, qr_path, _ = generate_monitoring_qr_code(tree_data['tree_id'], tree_data)
                if qr_img:
                    # Update database (if qr_code column exists in trees table)
                    conn = sqlite3.connect(SQLITE_DB)
                    try:
                        c = conn.cursor()
                        c.execute("PRAGMA table_info(trees)")
                        if 'qr_code' in [col[1] for col in c.fetchall()]:
                            conn.execute(
                                "UPDATE trees SET qr_code = ? WHERE tree_id = ?",
                                (qr_img, tree_data['tree_id'])
                            )
                            conn.commit()
                            st.success("QR code updated successfully!")
                            st.rerun()
                        else:
                            st.warning("`qr_code` column not found in `trees` table. QR code generated but not saved to DB.")
                    except Exception as e:
                        st.error(f"Error updating QR code in database: {str(e)}")
                    finally:
                        conn.close()
        
        # Monitoring History
        st.subheader("Monitoring History")
        if tree_data.get('monitoring_history'):
            df = pd.DataFrame(tree_data['monitoring_history'])
            st.dataframe(df[['monitor_date', 'monitor_status', 'monitor_stage', 
                            'rcd_cm', 'dbh_cm', 'height_m', 'co2_kg', 'monitor_by']])
        else:
            st.info("No monitoring history available")

def monitoring_section():
    """Main monitoring interface"""
    st.title("🌳 Tree Monitoring System")
    initialize_database()
    
    # Tab interface
    tab1, tab2, tab3 = st.tabs(["Tree Lookup", "Monitoring Dashboard", "Process KoBo Submissions"])
    
    with tab1:
        st.header("Tree Lookup")
        tree_id = st.text_input("Enter Tree ID", key="monitoring_lookup")
        
        if tree_id:
            tree_data = get_tree_details(tree_id)
            if tree_data:
                display_tree_details(tree_data)
            else:
                st.error("Tree not found")
    
    with tab2:
        display_monitoring_dashboard()
    
    with tab3:
        st.header("Process New KoBo Monitoring Submissions")
        
        st.markdown("""
        Click the button below to check for new tree monitoring submissions from KoBo Toolbox.
        """)
        
        # Time filter selection
        hours = st.slider("Hours to look back for new submissions", min_value=1, max_value=168, value=24, key="monitoring_hours_filter")
        
        if st.button("Check for New Monitoring Submissions", key="check_monitoring_submissions_button"):
            # Validate user session here as well before fetching
            if not validate_user_session():
                st.warning("Cannot check for submissions. Please ensure you are logged in correctly.")
                return

            with st.spinner("Checking for new monitoring submissions..."):
                results = check_for_new_monitoring_submissions(hours)
                display_monitoring_results(results)

def get_kobo_monitoring_submissions(time_filter_hours=24, submission_id=None):
    """
    Retrieve monitoring submissions from KoBo Toolbox API with optional filters
    """
    if not KOBO_API_TOKEN or not KOBO_MONITORING_ASSET_ID:
        st.error("KoBo API credentials (token or monitoring asset ID) not configured in `st.secrets`.")
        return None

    headers = {
        "Authorization": f"Token {KOBO_API_TOKEN}",
        "Accept": "application/json",
        "Content-Type": "application/json"
    }

    params = {}
    if time_filter_hours and not submission_id:
        time_filter = datetime.now() - timedelta(hours=time_filter_hours)
        params["query"] = json.dumps({"_submission_time": {"$gte": time_filter.isoformat()}})

    if submission_id:
        params["query"] = json.dumps({"_id": submission_id})

    url = f"{KOBO_API_URL}/assets/{KOBO_MONITORING_ASSET_ID}/data/"

    try:
        response = requests.get(
            url,
            headers=headers,
            params=params,
            timeout=30
        )

        response.raise_for_status()

        content_type = response.headers.get('Content-Type', '').lower()
        if 'application/json' not in content_type:
            st.error("Received non-JSON response from KoBo API. Expected 'application/json'.")
            st.error(f"Actual Content-Type: {content_type}")
            st.error(f"Response preview: {response.text[:500]}...")
            return None

        return response.json().get("results", [])

    except json.JSONDecodeError as e:
        st.error(f"JSON decoding error from KoBo API response: {e}")
        st.error(f"Problematic response text (first 500 chars): {response.text[:500]}...")
        return None
    except requests.exceptions.HTTPError as e:
        st.error(f"HTTP error from KoBo API: {e.response.status_code} - {e.response.reason}")
        st.error(f"Response body: {e.response.text[:500]}...")
        return None
    except requests.exceptions.ConnectionError as e:
        st.error(f"Network connection error to KoBo API: {e}")
        return None
    except requests.exceptions.Timeout as e:
        st.error(f"Request to KoBo API timed out: {e}")
        return None
    except Exception as e:
        st.error(f"An unexpected error occurred while fetching KoBo monitoring submissions: {str(e)}")
        return None

def is_monitoring_submission_processed(submission_id):
    """Check if a KoBo monitoring submission has already been processed"""
    if not submission_id:
        return False

    conn = sqlite3.connect(SQLITE_DB)
    try:
        c = conn.cursor()
        c.execute("SELECT 1 FROM processed_monitoring_submissions WHERE submission_id = ?", (submission_id,))
        return c.fetchone() is not None
    except Exception as e:
        st.error(f"Database error in is_monitoring_submission_processed: {e}")
        return False
    finally:
        conn.close()

def map_monitoring_submission_to_database(kobo_data):
    """
    Map KoBo monitoring form fields to database columns
    Now properly handles the Tree Tracking Number field from the form
    """
    try:
        # Extract tree_id from submission
        tree_id = kobo_data.get("tree_id", "").strip()
        if not tree_id:
            st.warning("Monitoring submission missing tree_id - skipping")
            return None
            
        # Get current tree data
        tree_data = get_tree_details(tree_id)
        if not tree_data:
            st.error(f"Tree {tree_id} not found in database")
            return None

        # Get the Tree Tracking Number from the form submission
        tracking_number = kobo_data.get("Tree_Tracking_Number", "").strip()
        
        # Determine who monitored the tree:
        # 1. Use tracking number if provided
        # 2. Fallback to monitor_name if available
        # 3. Fallback to original planter name
        monitor_by = tracking_number if tracking_number else (
            kobo_data.get("monitor_name", "").strip() or 
            tree_data.get("student_name", "Unknown Monitor")
        )

        mapped = {
            "tree_id": tree_id,
            "monitor_date": kobo_data.get("monitor_date", datetime.now().date().isoformat()),
            "monitor_status": kobo_data.get("tree_status", "Alive"),
            "monitor_stage": kobo_data.get("growth_stage", tree_data.get("tree_stage", "Seedling")),
            "rcd_cm": float(kobo_data.get("rcd_cm", tree_data.get("rcd_cm", 0))),
            "dbh_cm": float(kobo_data.get("dbh_cm", tree_data.get("dbh_cm", 0))),
            "height_m": float(kobo_data.get("height_m", tree_data.get("height_m", 0.5))),
            "notes": kobo_data.get("monitor_notes", ""),
            "monitor_by": monitor_by,
            "kobo_submission_id": kobo_data.get("_id", ""),
            "tree_tracking_number": tracking_number  # Store the tracking number from the form
        }
        
        # Calculate CO2 sequestration
        mapped["co2_kg"] = calculate_co2_sequestration(
            tree_data.get("scientific_name", "Unknown"),
            mapped["rcd_cm"],
            mapped["dbh_cm"]
        )
        
        return mapped
    except Exception as e:
        st.error(f"Error mapping monitoring data: {str(e)}")
        return None

def calculate_co2_sequestration(species, rcd=None, dbh=None):
    """
    Calculate estimated CO2 sequestration based on tree measurements.
    """
    conn = sqlite3.connect(SQLITE_DB)
    try:
        species_data = pd.read_sql(
            "SELECT wood_density FROM species WHERE scientific_name = ?",
            conn,
            params=(species,)
        )

        density = species_data["wood_density"].iloc[0] if not species_data.empty and species_data["wood_density"].iloc[0] is not None else 0.6

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
        st.error(f"CO2 calculation error for species '{species}': {str(e)}")
        return 0.0
    finally:
        conn.close()

def save_monitoring_submission(monitoring_data):
    """
    Save a processed KoBo monitoring submission to the database
    """
    if not monitoring_data:
        st.warning("No valid monitoring data provided to save.")
        return False
        
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
            monitoring_data["tree_id"],
            monitoring_data["monitor_date"],
            monitoring_data["monitor_status"],
            monitoring_data["monitor_stage"],
            monitoring_data["rcd_cm"],
            monitoring_data["dbh_cm"],
            monitoring_data["height_m"],
            monitoring_data["co2_kg"],
            monitoring_data["notes"],
            monitoring_data["monitor_by"],
            monitoring_data["kobo_submission_id"]
        ))
        
        # Update the tree record with latest monitoring data
        c.execute('''
            UPDATE trees SET
                status = ?,
                tree_stage = ?,
                rcd_cm = ?,
                dbh_cm = ?,
                height_m = ?,
                co2_kg = ?,
                last_monitored = ?
            WHERE tree_id = ?
        ''', (
            monitoring_data["monitor_status"],
            monitoring_data["monitor_stage"],
            monitoring_data["rcd_cm"],
            monitoring_data["dbh_cm"],
            monitoring_data["height_m"],
            monitoring_data["co2_kg"],
            monitoring_data["monitor_date"],
            monitoring_data["tree_id"]
        ))
        
        # Mark submission as processed
        c.execute('''
            INSERT INTO processed_monitoring_submissions (
                submission_id, tree_id, processed_date
            ) VALUES (?, ?, ?)
        ''', (
            monitoring_data["kobo_submission_id"],
            monitoring_data["tree_id"],
            datetime.now().isoformat()
        ))
        
        conn.commit()
        st.success(f"Successfully saved monitoring data for tree {monitoring_data['tree_id']}.")
        return True
    except sqlite3.IntegrityError as e:
        st.error(f"Duplicate submission detected or integrity error: {str(e)}")
        conn.rollback()
        return False
    except Exception as e:
        st.error(f"Unexpected database error while saving monitoring data: {str(e)}")
        conn.rollback()
        return False
    finally:
        conn.close()

def check_for_new_monitoring_submissions(hours=24):
    """Check for new monitoring submissions and process them based on Tree ID"""
    st.info(f"Fetching KoBo monitoring submissions from the last {hours} hours...")
    
    submissions = get_kobo_monitoring_submissions(hours)
    if not submissions:
        st.info("No new monitoring submissions found from KoBo Toolbox.")
        return []
        
    results = []
    st.info(f"Found {len(submissions)} monitoring submissions. Processing...")
    
    for sub in submissions:
        submission_kobo_id = sub.get("_id")
        if not submission_kobo_id:
            st.warning(f"Skipping submission with no ID: {sub}")
            continue
            
        if is_monitoring_submission_processed(submission_kobo_id):
            continue
            
        # Extract tree_id from submission (passed via QR code)
        tree_id = sub.get("tree_id", "").strip()
        if not tree_id:
            st.warning(f"Monitoring submission {submission_kobo_id} missing 'tree_id' - skipping.")
            continue
            
        # Get tree details from DB to verify tree exists
        tree_data = get_tree_details(tree_id)
        if not tree_data:
            st.error(f"Tree with ID {tree_id} not found in database. Skipping.")
            continue
            
        print(f"[DEBUG] Processing monitoring submission for tree {tree_id}")
        mapped_data = map_monitoring_submission_to_database(sub)
        
        if mapped_data:
            success = save_monitoring_submission(mapped_data)
            
            if success:
                results.append({
                    "tree_id": tree_id,
                    "status": mapped_data["monitor_status"],
                    "stage": mapped_data["monitor_stage"],
                    "date": mapped_data["monitor_date"],
                    "co2": mapped_data["co2_kg"],
                    "monitor_by": mapped_data["monitor_by"]
                })
            else:
                st.warning(f"Failed to save mapped monitoring submission {submission_kobo_id}.")
        else:
            st.warning(f"Failed to map monitoring submission {submission_kobo_id}.")
            
    return results
def display_monitoring_results(results):
    """Display processed monitoring results in Streamlit"""
    if results:
        st.success(f"🎉 Successfully processed {len(results)} new monitoring submission(s)! 🎉")

        for result in results:
            with st.expander(f"🌳 Tree {result.get('tree_id', 'N/A')} - {result.get('status', 'Unknown Status')}"):
                col1, col2 = st.columns(2)

                with col1:
                    st.metric("Status", result.get("status", "N/A"))
                    st.metric("Growth Stage", result.get("stage", "N/A"))
                    st.metric("Monitoring Date", result.get("date", "N/A"))
                    st.metric("Monitored By", result.get("monitor_by", "N/A")) # Display monitor

                with col2:
                    st.metric("CO₂ Sequestered", f"{result.get('co2', 0.0)} kg")
                    
                    # Get tree details for QR code
                    tree_data = get_tree_details(result.get("tree_id"))
                    if tree_data:
                        # Generate monitoring QR code
                        _, qr_path, qr_url = generate_monitoring_qr_code(result.get("tree_id"), tree_data)
                        
                        if qr_path and os.path.isfile(qr_path):
                            st.image(qr_path, caption=f"Monitoring QR for Tree {result['tree_id']}")
                            with open(qr_path, "rb") as f:
                                st.download_button(
                                    "Download QR Code",
                                    f.read(),
                                    file_name=f"tree_{result['tree_id']}_monitoring_qr.png",
                                    mime="image/png"
                                )
                            st.markdown(f"**Monitoring Form URL:** [Link]({qr_url})")
    else:
        st.info("No monitoring results to display at this time.")

def get_monitoring_stats():
    """Get monitoring statistics for dashboard"""
    conn = sqlite3.connect(SQLITE_DB)
    try:
        # Get overall stats
        stats = pd.read_sql(
            """
            SELECT 
                COUNT(DISTINCT tree_id) as monitored_trees,
                COUNT(*) as monitoring_events,
                AVG(co2_kg) as avg_co2,
                SUM(CASE WHEN monitor_status = 'Alive' THEN 1 ELSE 0 END) as alive_count,
                COUNT(DISTINCT monitor_by) as monitors_count
            FROM monitoring_history
            """,
            conn
        )
        
        # Get monitoring by date
        monitoring_by_date = pd.read_sql(
            """
            SELECT 
                monitor_date,
                COUNT(*) as count
            FROM monitoring_history
            GROUP BY monitor_date
            ORDER BY monitor_date
            """,
            conn
        )
        
        # Get monitoring by institution
        monitoring_by_institution = pd.read_sql(
            """
            SELECT 
                t.institution,
                COUNT(DISTINCT m.tree_id) as monitored_trees,
                COUNT(*) as monitoring_events
            FROM monitoring_history m
            JOIN trees t ON m.tree_id = t.tree_id
            GROUP BY t.institution
            ORDER BY monitored_trees DESC
            """,
            conn
        )
        
        # Get growth stages
        growth_stages = pd.read_sql(
            """
            SELECT 
                monitor_stage,
                COUNT(*) as count
            FROM monitoring_history
            GROUP BY monitor_stage
            ORDER BY count DESC
            """,
            conn
        )
        
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
    
    # Display overall metrics
    st.subheader("Overall Monitoring Metrics")
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Trees Monitored", stats["stats"].get("monitored_trees", 0))
    with col2:
        st.metric("Monitoring Events", stats["stats"].get("monitoring_events", 0))
    with col3:
        survival_rate = (stats["stats"].get("alive_count", 0) / stats["stats"].get("monitoring_events", 1)) * 100 if stats["stats"].get("monitoring_events", 0) > 0 else 0
        st.metric("Survival Rate", f"{survival_rate:.1f}%")
    with col4:
        st.metric("Avg. CO₂ per Tree", f"{stats['stats'].get('avg_co2', 0):.2f} kg")
    
    # Display monitoring by institution
    st.subheader("Monitoring by Institution")
    
    if stats["monitoring_by_institution"]:
        # Create DataFrame for chart
        df = pd.DataFrame(stats["monitoring_by_institution"])
        
        # Display bar chart
        fig, ax = plt.subplots(figsize=(10, 6))
        sns.barplot(x="institution", y="monitored_trees", data=df, ax=ax)
        ax.set_xlabel("Institution")
        ax.set_ylabel("Trees Monitored")
        ax.set_title("Trees Monitored by Institution")
        plt.xticks(rotation=45, ha="right")
        plt.tight_layout()
        st.pyplot(fig)
        
        # Display table
        st.dataframe(df)
    else:
        st.info("No monitoring data by institution available yet.")
    
    # Display growth stages
    st.subheader("Tree Growth Stages")
    
    if stats["growth_stages"]:
        # Create DataFrame for chart
        df = pd.DataFrame(stats["growth_stages"])
        
        # Display pie chart
        fig, ax = plt.subplots(figsize=(8, 8))
        ax.pie(df["count"], labels=df["monitor_stage"], autopct="%1.1f%%", startangle=90)
        ax.axis("equal")
        st.pyplot(fig)
    else:
        st.info("No growth stage data available yet.")
    
    # Display monitoring by date
    st.subheader("Monitoring Activity Over Time")
    
    if stats["monitoring_by_date"]:
        # Create DataFrame for chart
        df = pd.DataFrame(stats["monitoring_by_date"])
        df["monitor_date"] = pd.to_datetime(df["monitor_date"])
        
        # Display line chart
        fig, ax = plt.subplots(figsize=(10, 6))
        sns.lineplot(x="monitor_date", y="count", data=df, ax=ax)
        ax.set_xlabel("Date")
        ax.set_ylabel("Monitoring Events")
        ax.set_title("Monitoring Events Over Time")
        plt.xticks(rotation=45, ha="right")
        plt.tight_layout()
        st.pyplot(fig)
    else:
        st.info("No monitoring date data available yet.")

def display_tree_details(tree_data):
    """Display tree details for regular users"""
    st.subheader(f"Tree {tree_data['tree_id']}")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("### Tree Information")
        st.write(f"**Local Name:** {tree_data.get('local_name', 'N/A')}")
        st.write(f"**Scientific Name:** {tree_data.get('scientific_name', 'N/A')}")
        st.write(f"**Institution:** {tree_data.get('institution', 'N/A')}")
        st.write(f"**Planted By:** {tree_data.get('student_name', 'N/A')}")
        st.write(f"**Tracking Number:** {tree_data.get('tree_tracking_number', 'N/A')}")
    
    with col2:
        st.markdown("### Status")
        st.write(f"**Status:** {tree_data.get('status', 'N/A')}")
        st.write(f"**Growth Stage:** {tree_data.get('tree_stage', 'N/A')}")
        st.write(f"**Last Monitored:** {tree_data.get('last_monitored', 'N/A')}")
    
    # Display QR code if available
    if tree_data.get('qr_code'):
        st.markdown("### Monitoring QR Code")
        # Ensure that the base64 string is correctly prefixed for display
        st.image(f"data:image/png;base64,{tree_data['qr_code']}", 
                width=200, caption=f"Scan to monitor Tree {tree_data['tree_id']}")
        
        # The qr_path for download button should refer to the one saved by generate_monitoring_qr_code
        qr_file_path = QR_CODE_DIR / f"{tree_data['tree_id']}_monitoring.png"
        if os.path.exists(qr_file_path):
            with open(qr_file_path, "rb") as f:
                st.download_button(
                    "Download QR Code",
                    f.read(),
                    file_name=f"tree_{tree_data['tree_id']}_monitoring_qr.png",
                    mime="image/png",
                    key=f"download_display_{tree_data['tree_id']}"
                )

def generate_monitoring_qr_code(tree_id, tree_data=None):
    """
    Generate and save QR code for tree monitoring with pre-filled data.
    Returns base64 image string, image file path, and monitoring form URL.
    """
    try:
        # If tree_data is not provided, fetch it
        if tree_data is None:
            tree_data = get_tree_details(tree_id)
            if tree_data is None:
                st.error(f"Tree with ID {tree_id} not found for QR code generation.")
                return None, None, None

        # Build monitoring URL
        # Use KOBO_MONITORING_ASSET_ID from st.secrets
        kobo_monitoring_asset_id = st.secrets.get("KOBO_MONITORING_ASSET_ID")
        if not kobo_monitoring_asset_id:
            st.error("KOBO_MONITORING_ASSET_ID is not configured in `st.secrets` for QR code generation.")
            return None, None, None

        form_url = f"https://ee.kobotoolbox.org/single/dXdb36aV?tree_id={tree_id}".strip()
        
        params = {
            "tree_id": tree_id,
            "local_name": tree_data.get("local_name", ""),
            "scientific_name": tree_data.get("scientific_name", ""),
            "date_planted": tree_data.get("date_planted", ""),
            "planter": tree_data.get("student_name", ""),
            "institution": tree_data.get("institution", ""),
            "tree_tracking_number": tree_data.get("tree_tracking_number", "") # Include tracking number
        }
        url_params = "&".join([f"{k}={v}" for k, v in params.items() if v])
        monitoring_url = f"{base_url}?{url_params}"

        # Generate QR code
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(monitoring_url)
        qr.make(fit=True)
        img = qr.make_image(fill_color="#2e8b57", back_color="white")

        # Save QR code image
        QR_CODE_DIR.mkdir(parents=True, exist_ok=True)
        file_path = QR_CODE_DIR / f"{tree_id}_monitoring.png" # Consistent filename
        img.save(file_path)

        # Convert image to base64
        buffered = BytesIO()
        img.save(buffered, format="PNG")
        img_str = base64.b64encode(buffered.getvalue()).decode()

        return img_str, str(file_path), monitoring_url

    except Exception as e:
        st.error(f"Error generating monitoring QR code for tree ID '{tree_id}': {str(e)}")
        return None, None, None

# Main app execution (for standalone testing)
if __name__ == "__main__":
    st.set_page_config(page_title="Tree Monitoring", layout="wide")
    
    # Ensure st.secrets are available for standalone testing if not running via main app
    # In a real app, this would be handled by your secrets.toml
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

    st.title("Tree Monitoring Module Test (Standalone)")
    st.info("This is a standalone test for the KoBo monitoring functionality. "
            "In a real app, this module is imported into `app.py`.")
    
    # Enable debug mode for more console output
    if 'debug_mode' not in st.session_state:
        st.session_state.debug_mode = True 
        print("[DEBUG_MAIN] Setting debug_mode to True.")
        
    monitoring_section()
