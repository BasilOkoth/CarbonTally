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
import uuid # Import uuid for unique identifiers

# KoBo Toolbox configuration
KOBO_API_URL = "https://kf.kobotoolbox.org/api/v2"

# Database configuration
BASE_DIR = Path(__file__).parent if "__file__" in locals() else Path.cwd()
DATA_DIR = BASE_DIR / "data"
SQLITE_DB = DATA_DIR / "trees.db"
QR_CODE_DIR = DATA_DIR / "qr_codes"

# Ensure directories exist
DATA_DIR.mkdir(exist_ok=True, parents=True)
QR_CODE_DIR.mkdir(exist_ok=True, parents=True)

def initialize_database():
    """Initialize the database with required tables"""
    conn = sqlite3.connect(SQLITE_DB)
    try:
        c = conn.cursor()

        # Create trees table with 'planters_name'
        c.execute('''
            CREATE TABLE IF NOT EXISTS trees (
                tree_id TEXT PRIMARY KEY,
                local_name TEXT,
                scientific_name TEXT,
                planters_name TEXT,  -- Changed from student_name
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
                last_monitored_date TEXT,
                last_monitor_id TEXT,
                kobo_submission_id TEXT UNIQUE,
                tree_tracking_number TEXT,
                planter_tracking_id TEXT, -- To link to Firebase user's tracking ID
                qr_code_path TEXT
            )
        ''')

        # Create monitoring_events table if not exists
        c.execute('''
            CREATE TABLE IF NOT EXISTS monitoring_events (
                event_id TEXT PRIMARY KEY,
                tree_id TEXT,
                monitor_id TEXT,
                monitoring_date TEXT,
                height_m REAL,
                rcd_cm REAL,
                dbh_cm REAL,
                status TEXT,
                monitor_notes TEXT,
                kobo_monitoring_submission_id TEXT UNIQUE,
                FOREIGN KEY (tree_id) REFERENCES trees(tree_id)
            )
        ''')
        conn.commit()
    except Exception as e:
        st.error(f"Database initialization error: {e}")
    finally:
        conn.close()

def get_kobo_form_url():
    """Get the public URL for the KoBo tree planting form"""
    short_code = st.secrets.get("KOBO_ASSET_FORM_CODE") # use short code, e.g. 's8ntxUM5'
    if not short_code:
        st.error("Form configuration missing (KOBO_ASSET_FORM_CODE). Please contact support.")
        return None
    return f"https://ee.kobotoolbox.org/x/{short_code}"

def launch_kobo_form():
    """Launch the KoBo form for tree planting"""
    form_url = get_kobo_form_url()
    if not form_url:
        return

    tracking_url = f"{form_url}"

    st.markdown(f"""
    ### Tree Planting Form

    You'll be redirected to our tree planting form where you can:
    - Enter tree details including the Tree Tracking Number
    - Capture planting location coordinates
    - Submit your tree planting information

    [Open Tree Planting Form]({tracking_url})

    After submission, return here to view your tree details and QR code.
    """)

    st.session_state.kobo_form_launched = True
    return tracking_url

def get_kobo_submissions(hours=24):
    """Retrieve submissions from KoBo Toolbox API within a given time window"""
    kobo_api_token = st.secrets.get("KOBO_API_TOKEN")
    kobo_asset_id = st.secrets.get("KOBO_ASSET_ID")

    # Create an empty placeholder for displaying errors within Streamlit
    error_placeholder = st.empty()

    if not kobo_api_token or not kobo_asset_id:
        error_placeholder.error("System configuration error: KoBo API token or Asset ID missing. Please contact support and check your .streamlit/secrets.toml file.")
        return None

    headers = {
        "Authorization": f"Token {kobo_api_token}",
        "Accept": "application/json"
    }

    # Filter submissions by time (e.g., last 24 hours)
    time_filter = datetime.now() - timedelta(hours=hours)
    params = {
        "query": json.dumps({"_submission_time": {"$gte": time_filter.isoformat()}})
    }

    url = f"{KOBO_API_URL}/assets/{kobo_asset_id}/data/"

    try:
        response = requests.get(url, headers=headers, params=params, timeout=30)
        response.raise_for_status() # Raise an HTTPError for bad responses (4xx or 5xx)

        # Clear any previous error messages if the request was successful
        error_placeholder.empty()
        
        return response.json().get("results", [])
    except requests.exceptions.HTTPError as http_err:
        error_placeholder.error(f"HTTP Error fetching KoBo submissions: {http_err} - Response: {response.text}")
        return None
    except requests.exceptions.ConnectionError as conn_err:
        error_placeholder.error(f"Connection Error fetching KoBo submissions: {conn_err}. Check internet connection or KoBo API URL.")
        return None
    except requests.exceptions.Timeout as timeout_err:
        error_placeholder.error(f"Timeout Error fetching KoBo submissions: {timeout_err}. KoBo server might be slow or unresponsive.")
        return None
    except Exception as e:
        error_placeholder.error(f"General Error fetching KoBo submissions: {str(e)}")
        return None

def validate_tracking_number(tracking_number):
    """Validate the Tree Tracking Number format"""
    if not tracking_number or not isinstance(tracking_number, str):
        return False
    # Example validation: must be at least 3 characters and can contain letters, numbers, and hyphens
    return len(tracking_number.strip()) >= 3 and re.match(r"^[a-zA-Z0-9_-]+$", tracking_number.strip())

def map_kobo_to_database(kobo_data):
    """Map KoBo form fields to database columns"""
    try:
        # Get and validate Tree Tracking Number
        tracking_number = kobo_data.get("tree_tracking_number", "").strip()
        if not validate_tracking_number(tracking_number):
            st.warning(f"Invalid Tree Tracking Number: '{tracking_number}' - must be at least 3 characters and alphanumeric with hyphens/underscores.")
            return None

        # --- IMPORTANT CHANGE HERE ---
        # planter_tracking_id now ALWAYS comes from the KoBo form's tree_tracking_number
        planter_tracking_id = tracking_number
        # --- END IMPORTANT CHANGE ---

        # Handle geolocation
        lat, lon = 0.0, 0.0
        if "_geolocation" in kobo_data and kobo_data["_geolocation"]:
            if isinstance(kobo_data["_geolocation"], list) and len(kobo_data["_geolocation"]) >= 2:
                try:
                    lat = float(kobo_data["_geolocation"][0])
                    lon = float(kobo_data["_geolocation"][1])
                except (ValueError, TypeError):
                    st.warning("Could not parse GPS coordinates from KoBo submission.")


        mapped = {
            "tree_id": str(uuid.uuid4()), # Generate a unique ID for the tree
            "local_name": kobo_data.get("Local_Name", "").strip(),
            "scientific_name": kobo_data.get("Scientific_Name", "Unknown").strip(),
            "planters_name": kobo_data.get("Planters_Name", "").strip(), # Changed from Student_Name
            "date_planted": kobo_data.get("Date_Planted", datetime.now().date().isoformat()),
            "tree_stage": kobo_data.get("Tree_Stage", "Seedling"),
            "rcd_cm": float(kobo_data.get("RCD_cm", 0)) if kobo_data.get("RCD_cm") not in [None, ''] else 0.0,
            "dbh_cm": float(kobo_data.get("DBH_cm", 0)) if kobo_data.get("DBH_cm") not in [None, ''] else 0.0,
            "height_m": float(kobo_data.get("Height_m", 0.5)) if kobo_data.get("Height_m") not in [None, ''] else 0.5,
            "latitude": lat,
            "longitude": lon,
            "co2_kg": 0.0, # Placeholder, calculation can be added later
            "status": "Alive", # Default status for new trees
            "country": kobo_data.get("Country", "Kenya"),
            "county": kobo_data.get("County", "").strip(),
            "sub_county": kobo_data.get("Sub_County", "").strip(),
            "ward": kobo_data.get("Ward", "").strip(),
            "adopter_name": kobo_data.get("Adopter_Name", "").strip(), # Assuming this field exists
            "last_monitored_date": None, # Will be updated on first monitoring event
            "last_monitor_id": None, # Will be updated on first monitoring event
            "kobo_submission_id": kobo_data.get("_id", ""), # KoBo's internal submission ID
            "tree_tracking_number": tracking_number,
            "planter_tracking_id": planter_tracking_id, # Link to the user/planter
            "qr_code_path": None # Path to the generated QR code image
        }
        return mapped
    except Exception as e:
        st.error(f"Error mapping KoBo data to database format: {str(e)}")
        return None

def save_tree_data(tree_data):
    """Save mapped tree data to the database."""
    conn = sqlite3.connect(SQLITE_DB)
    try:
        c = conn.cursor()
        
        # Check if a tree with the same kobo_submission_id already exists to prevent duplicates
        c.execute("SELECT tree_id FROM trees WHERE kobo_submission_id = ?", (tree_data["kobo_submission_id"],))
        existing_tree = c.fetchone()

        if existing_tree:
            st.info(f"Submission with ID {tree_data['kobo_submission_id']} already processed. Updating existing tree.")
            # Update logic if you want to allow updates to existing trees
            # For now, we'll just skip to prevent re-inserting
            return True # Indicate successful handling (no new insert needed)
            
        columns = ', '.join(tree_data.keys())
        placeholders = ':'+', :'.join(tree_data.keys())
        sql = f"INSERT INTO trees ({columns}) VALUES ({placeholders})"
        c.execute(sql, tree_data)
        conn.commit()
        st.success(f"Tree '{tree_data['local_name']}' with tracking number '{tree_data['tree_tracking_number']}' saved successfully!")

        # Generate and save QR code
        qr_code_path = generate_and_save_qr_code(tree_data['tree_id'], tree_data['tree_tracking_number'])
        if qr_code_path:
            c.execute("UPDATE trees SET qr_code_path = ? WHERE tree_id = ?", (str(qr_code_path), tree_data['tree_id']))
            conn.commit()
            return True
        else:
            st.warning("Failed to generate QR code for the tree.")
            return False

    except sqlite3.IntegrityError as ie:
        st.error(f"Integrity error saving tree: {ie}. This might be a duplicate entry or missing required field.")
        return False
    except Exception as e:
        st.error(f"Error saving tree data: {e}")
        return False
    finally:
        conn.close()

def generate_and_save_qr_code(tree_id, tree_tracking_number):
    """Generates a QR code for a tree and saves it."""
    qr_data = f"CarbonTally Tree ID: {tree_id}\nTracking Number: {tree_tracking_number}\nLink: [Your App URL/tree/{tree_id}]" # Customize your link
    
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(qr_data)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")
    
    # Save the QR code to a file
    qr_filename = QR_CODE_DIR / f"tree_{tree_id}_qr.png"
    img.save(qr_filename)
    st.success(f"QR code generated and saved for Tree ID: {tree_id}")
    return qr_filename

def display_tree_results(tree_results):
    """Displays processed tree submission results to the user."""
    st.header("Processed Tree Submissions")
    if not tree_results:
        st.info("No new trees found from recent submissions.")
        return

    for tree in tree_results:
        st.subheader(f"Tree Tracking Number: {tree['tree_tracking_number']}")
        col1, col2 = st.columns([1, 2])
        with col1:
            st.write(f"**Local Name:** {tree['local_name']}")
            st.write(f"**Scientific Name:** {tree['scientific_name']}")
            st.write(f"**Planter Name:** {tree['planters_name']}") # Changed from Student Name
            st.write(f"**Date Planted:** {tree['date_planted']}")
            st.write(f"**Stage:** {tree['tree_stage']}")
            st.write(f"**Height:** {tree['height_m']} m")
            st.write(f"**Location:** ({tree['latitude']:.4f}, {tree['longitude']:.4f})")
            
            if tree.get('qr_code_path') and Path(tree['qr_code_path']).exists():
                st.image(str(tree['qr_code_path']), caption="Tree QR Code", width=150)
                # Option to download QR code
                with open(tree['qr_code_path'], "rb") as file:
                    st.download_button(
                        label="Download QR Code",
                        data=file,
                        file_name=f"tree_{tree['tree_id']}_qr.png",
                        mime="image/png",
                        key=f"download_qr_{tree['tree_id']}"
                    )
            else:
                st.warning("QR Code not available for this tree.")

        with col2:
            st.map(pd.DataFrame([{'lat': tree['latitude'], 'lon': tree['longitude']}]))
        st.markdown("---")


def check_for_new_submissions(user_tracking_id=None, hours=24):
    """
    Fetches new KoBo submissions, maps them, and saves to the database.
    Can optionally filter by a user's tracking ID if needed for individual users.
    """
    st.info(f"Checking for new KoBo submissions from the last {hours} hours...")
    submissions = get_kobo_submissions(hours=hours)

    if not submissions:
        st.info(f"No new KoBo submissions found in the last {hours} hours.")
        return []

    processed_trees = []
    
    # Get all existing kobo_submission_ids from your database to avoid reprocessing
    conn = sqlite3.connect(SQLITE_DB)
    c = conn.cursor()
    c.execute("SELECT kobo_submission_id FROM trees")
    existing_kobo_ids = {row[0] for row in c.fetchall()}
    conn.close()

    for submission in submissions:
        kobo_submission_id = submission.get("_id")
        if kobo_submission_id in existing_kobo_ids:
            # st.info(f"Skipping already processed submission: {kobo_submission_id}") # Too verbose, uncomment for deep debug
            continue

        mapped_data = map_kobo_to_database(submission)
        if mapped_data:
            # If a specific user_tracking_id is provided, filter submissions by it
            # This filter remains, implying that the 'user_tracking_id' from Streamlit session
            # (e.g., from Firebase user profile) MUST match the 'tree_tracking_number'
            # entered in the KoBo form for the tree to be associated with that user/organization
            if user_tracking_id and mapped_data.get('planter_tracking_id') != user_tracking_id:
                # st.info(f"Skipping submission for different planter_tracking_id: {mapped_data.get('planter_tracking_id')}") # Too verbose
                continue
            
            if save_tree_data(mapped_data):
                processed_trees.append(mapped_data)
        else:
            st.warning(f"Could not map data for submission ID: {kobo_submission_id}. Check KoBo form fields.")

    if processed_trees:
        st.success(f"Successfully processed {len(processed_trees)} new tree submissions!")
    else:
        st.info("No new, unprocessed tree submissions found for you in the specified time frame.")
    
    return processed_trees


def plant_a_tree_section():
    """Main section for planting a tree workflow."""
    st.header("Record a New Tree Planting")
    
    # Initialize session state for this section
    if "kobo_form_launched" not in st.session_state:
        st.session_state.kobo_form_launched = False
    if "submission_checked" not in st.session_state:
        st.session_state.submission_checked = False
    if "tree_results" not in st.session_state:
        st.session_state.tree_results = None

    if not st.session_state.kobo_form_launched:
        st.info("To record a tree, please fill out our KoBo Toolbox form.")
        if st.button("Open Tree Planting Form"):
            launch_kobo_form()
            st.rerun() # Rerun to show the markdown link and set state
        return

    st.markdown("""
    **Instructions:**
    1. Click the link above to open the KoBo Toolbox form in a new tab.
    2. Fill out all required details, including the Tree Tracking Number.
    3. Submit the form.
    4. Return to this page and click 'Check for New Submissions' below.
    """)

    if not st.session_state.submission_checked:
        st.info("After submitting the form, click the button below to retrieve your tree details.")
        
        # Get the current authenticated user's tree_tracking_id
        current_user = st.session_state.get('user')
        user_tracking_id = current_user.get('tree_tracking_id') if current_user else None
        
        if not user_tracking_id:
            st.warning("Your user account is not linked with a Tree Tracking ID. Submissions will be retrieved broadly. Please ensure your KoBo form includes the correct tracking ID.")
        else:
            st.info(f"You are logged in with tracking ID: **{user_tracking_id}**. Only trees submitted with this tracking ID in the KoBo form will be displayed here.")


        if st.button("Check for New Submissions"):
            with st.spinner("Searching for your new tree submission..."):
                # Pass the user_tracking_id to filter if available
                results = check_for_new_submissions(user_tracking_id=user_tracking_id)
                if results:
                    st.session_state.tree_results = results
                st.session_state.submission_checked = True
                st.rerun()
        
        if st.button("Start Over (Reset Form Link)"):
            st.session_state.kobo_form_launched = False
            st.session_state.submission_checked = False
            st.session_state.tree_results = None
            st.rerun()
        return

    if st.session_state.get("tree_results"):
        display_tree_results(st.session_state.tree_results)
        
        if st.button("Plant Another Tree"):
            st.session_state.kobo_form_launched = False
            st.session_state.submission_checked = False
            st.session_state.tree_results = None
            st.rerun()
    else:
        st.warning("No new submissions found matching your criteria in the last check. Please ensure you submitted the form and the tracking ID matches your account (if applicable).")
        if st.button("Try Checking Again"):
            st.session_state.submission_checked = False # Allow re-checking
            st.rerun()
        if st.button("Reset Workflow"):
            st.session_state.kobo_form_launched = False
            st.session_state.submission_checked = False
            st.session_state.tree_results = None
            st.rerun()


# Initialize database when this module is imported
initialize_database()

# For local testing if this file is run directly (useful for isolated module testing)
if __name__ == "__main__":
    # Simulate st.secrets for standalone testing
    if "KOBO_ASSET_FORM_CODE" not in st.secrets:
        st.secrets["KOBO_ASSET_FORM_CODE"] = "your_kobo_form_short_code" # e.g., 's8ntxUM5'
        st.secrets["KOBO_API_TOKEN"] = "your_kobo_api_token"
        st.secrets["KOBO_ASSET_ID"] = "your_kobo_asset_id" # e.g., 'aMd8GqUuYvWtXzYyZz1234'
    
    st.set_page_config(page_title="KoBo Integration Test", layout="wide")
    st.title("KoBo Integration Module - Standalone Test")

    # Simulate user session for testing if needed
    if "user" not in st.session_state:
        st.session_state.user = {
            "uid": "test_user_id",
            "email": "test@example.com",
            "role": "individual", # or 'institution'
            "tree_tracking_id": "TEST_PLANTER_001" # Example tracking ID for testing
        }
        st.session_state.authenticated = True
    
    plant_a_tree_section()
