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
                last_updated TEXT,
                planter_email TEXT,
                planter_uid TEXT,
                planter_tracking_id TEXT UNIQUE
            )
        ''')
        conn.commit()

        # Create user_profiles table (if it doesn't exist)
        c.execute('''
            CREATE TABLE IF NOT EXISTS user_profiles (
                email TEXT PRIMARY KEY,
                username TEXT,
                uid TEXT,
                role TEXT,
                institution TEXT,
                total_trees_planted INTEGER DEFAULT 0,
                total_co2_sequestered REAL DEFAULT 0.0,
                last_activity TEXT,
                badges TEXT,
                tree_tracking_number TEXT UNIQUE
            )
        ''')
        conn.commit()

        # Create institutions table
        c.execute('''
            CREATE TABLE IF NOT EXISTS institutions (
                id TEXT PRIMARY KEY,
                name TEXT UNIQUE,
                contact_email TEXT,
                total_trees_planted INTEGER DEFAULT 0,
                total_co2_sequestered REAL DEFAULT 0.0,
                created_at TEXT
            )
        ''')
        conn.commit()

        # Create donations table
        c.execute('''
            CREATE TABLE IF NOT EXISTS donations (
                donation_id TEXT PRIMARY KEY,
                donor_name TEXT,
                donor_email TEXT,
                institution_id TEXT, -- Link to institutions table if applicable
                num_trees INTEGER,
                amount REAL,
                currency TEXT,
                payment_status TEXT,
                donation_date TEXT,
                message TEXT,
                FOREIGN KEY (institution_id) REFERENCES institutions(id)
            )
        ''')
        conn.commit()

    except Exception as e:
        st.error(f"Database initialization error: {e}")
    finally:
        conn.close()

def get_kobo_secrets():
    """Retrieves KoBo API secrets from Streamlit secrets."""
    try:
        kobo_api_token = st.secrets["KOBO_API_TOKEN"]
        kobo_asset_id = st.secrets["KOBO_ASSET_ID"]
        kobo_asset_form_code = st.secrets["KOBO_ASSET_FORM_CODE"]
        return kobo_api_token, kobo_asset_id, kobo_asset_form_code
    except KeyError as e:
        st.error(f"Missing KoBo secret: {e}. Please ensure KOBO_API_TOKEN, KOBO_ASSET_ID, and KOBO_ASSET_FORM_CODE are set in your secrets.toml.")
        st.stop() # Stop execution if essential secrets are missing
        return None, None, None

def launch_kobo_form():
    """Launches the KoBo Collect form URL in a new browser tab."""
    kobo_api_token, kobo_asset_id, kobo_asset_form_code = get_kobo_secrets()
    if kobo_asset_form_code:
        form_url = f"https://ee.kobotoolbox.org/x/{kobo_asset_form_code}"
        st.markdown(f"<a href='{form_url}' target='_blank'>Click here to open the Tree Planting Form</a>", unsafe_allow_html=True)
        st.info("Please complete the form and submit. Then return to this page.")
        st.session_state.kobo_form_launched = True
    else:
        st.error("KoBo form code is not configured. Cannot launch form.")

def get_kobo_submissions(asset_id, last_n_hours=None):
    """Fetches submissions from a specific KoBo asset."""
    kobo_api_token, _, _ = get_kobo_secrets()
    headers = {"Authorization": f"Token {kobo_api_token}"}
    url = f"{KOBO_API_URL}/assets/{asset_id}/data/"
    params = {"format": "json"}

    if last_n_hours:
        # Calculate the datetime `last_n_hours` ago
        time_ago = datetime.utcnow() - timedelta(hours=last_n_hours)
        # Convert to ISO 8601 format, e.g., '2023-10-27T10:00:00Z'
        # Adjust for 'submissionTime' field in KoBo, which is typically ISO format
        params["query"] = json.dumps({"_submission_time": {"$gte": time_ago.isoformat(timespec='seconds') + 'Z'}})

    try:
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()  # Raise an HTTPError for bad responses (4xx or 5xx)
        return response.json()
    except requests.exceptions.HTTPError as http_err:
        st.error(f"HTTP error fetching KoBo submissions: {http_err} - Response: {response.text}")
    except Exception as err:
        st.error(f"Other error fetching KoBo submissions: {err}")
    return []

def map_kobo_to_database(submission_data):
    """Maps KoBo submission data to the database schema."""
    tree_id = submission_data.get('tree_id', str(uuid.uuid4())) # Use existing or generate new
    # Use .get() with default None for robustness
    planters_name = submission_data.get('planters_name') or submission_data.get('student_name', 'N/A') # Prioritize new field, fallback to old
    date_planted = submission_data.get('date_planted')
    tree_stage = submission_data.get('tree_stage')
    rcd_cm = submission_data.get('rcd_cm')
    dbh_cm = submission_data.get('dbh_cm')
    height_m = submission_data.get('height_m')
    latitude = submission_data.get('_geolocation', [None, None])[0]
    longitude = submission_data.get('_geolocation', [None, None])[1]
    local_name = submission_data.get('tree_species/local_name')
    scientific_name = submission_data.get('tree_species/scientific_name')
    status = submission_data.get('tree_status', 'planted')
    country = submission_data.get('location_details/country')
    county = submission_data.get('location_details/county')
    sub_county = submission_data.get('location_details/sub_county')
    ward = submission_data.get('location_details/ward')
    adopter_name = submission_data.get('adopter_name') # New field from form
    planter_email = submission_data.get('planter_email') # New field from form
    planter_uid = submission_data.get('planter_uid') # New field from form
    planter_tracking_id = submission_data.get('tree_tracking_number') # This maps to the QR code ID

    # Calculate CO2 (simplified placeholder)
    co2_kg = calculate_co2_sequestered(dbh_cm, height_m) if dbh_cm and height_m else 0.0

    return {
        "tree_id": tree_id,
        "local_name": local_name,
        "scientific_name": scientific_name,
        "planters_name": planters_name,
        "date_planted": date_planted,
        "tree_stage": tree_stage,
        "rcd_cm": rcd_cm,
        "dbh_cm": dbh_cm,
        "height_m": height_m,
        "latitude": latitude,
        "longitude": longitude,
        "co2_kg": co2_kg,
        "status": status,
        "country": country,
        "county": county,
        "sub_county": sub_county,
        "ward": ward,
        "adopter_name": adopter_name,
        "last_updated": datetime.utcnow().isoformat(),
        "planter_email": planter_email,
        "planter_uid": planter_uid,
        "planter_tracking_id": planter_tracking_id
    }

def calculate_co2_sequestered(dbh_cm, height_m):
    """
    Calculates estimated CO2 sequestered based on DBH and Height.
    This is a simplified placeholder.
    """
    if dbh_cm is None or height_m is None or dbh_cm <= 0 or height_m <= 0:
        return 0.0

    # Very simplified allometric equation (example: for general broadleaf trees)
    # Biomass = a * (DBH^b) * (Height^c)
    # For simplification, let's use a linear relationship to demonstrate
    # This needs to be replaced with actual allometric equations for specific species/regions
    # For now, let's assume 0.5 kg CO2 per cm DBH * meter Height
    co2_per_unit = 0.5 # kg CO2 per (cm DBH * m Height)

    return dbh_cm * height_m * co2_per_unit

def save_tree_data(tree_data):
    """Saves mapped tree data to the SQLite database."""
    conn = sqlite3.connect(SQLITE_DB)
    try:
        c = conn.cursor()
        columns = ', '.join(tree_data.keys())
        placeholders = ':' + ', :'.join(tree_data.keys())
        sql = f"INSERT OR REPLACE INTO trees ({columns}) VALUES ({placeholders})"
        c.execute(sql, tree_data)
        conn.commit()
        st.success(f"Tree {tree_data['tree_id']} saved successfully!")

        # Update user's total_trees_planted and total_co2_sequestered
        if tree_data.get('planter_email'):
            c.execute('''
                UPDATE user_profiles
                SET total_trees_planted = total_trees_planted + 1,
                    total_co2_sequestered = total_co2_sequestered + ?
                WHERE email = ?
            ''', (tree_data['co2_kg'], tree_data['planter_email']))
            conn.commit()

    except sqlite3.IntegrityError as e:
        st.error(f"Database error (Integrity): {e}. Tree ID might already exist or tracking number is duplicated.")
    except Exception as e:
        st.error(f"Error saving tree data: {e}")
    finally:
        conn.close()

def generate_qr_code(data, filename):
    """Generates a QR code and saves it as a PNG file."""
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(data)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")
    filepath = QR_CODE_DIR / filename
    img.save(filepath)
    return filepath

def get_qr_code_as_base64(filepath):
    """Reads a QR code image and returns its base64 string."""
    try:
        with open(filepath, "rb") as image_file:
            encoded_string = base64.b64encode(image_file.read()).decode()
        return f"data:image/png;base64,{encoded_string}"
    except FileNotFoundError:
        st.error(f"QR code file not found: {filepath}")
        return None

def check_for_new_submissions(user_id=None, hours=24):
    """
    Checks for new KoBo submissions and processes them.
    If user_id is provided, it filters submissions by user's tracking ID.
    """
    kobo_api_token, kobo_asset_id, _ = get_kobo_secrets()
    if not kobo_asset_id:
        return []

    st.info(f"Checking for new submissions from KoBo asset ID: {kobo_asset_id} in the last {hours} hours...")
    submissions = get_kobo_submissions(kobo_asset_id, last_n_hours=hours)

    if not submissions:
        st.info("No new submissions found from KoBo Toolbox.")
        return []

    processed_trees = []
    conn = sqlite3.connect(SQLITE_DB)
    c = conn.cursor()

    for submission in submissions:
        tree_tracking_number = submission.get('tree_tracking_number')

        if tree_tracking_number:
            # Check if this tree_tracking_number already exists in our DB
            c.execute("SELECT tree_id FROM trees WHERE planter_tracking_id = ?", (tree_tracking_number,))
            existing_tree = c.fetchone()
            if existing_tree:
                # st.info(f"Tree with tracking number {tree_tracking_number} already exists. Skipping.")
                continue # Skip already processed submissions

            # If user_id is provided, check if this submission belongs to this user
            if user_id:
                submitted_planter_uid = submission.get('planter_uid')
                if submitted_planter_uid != user_id:
                    # st.info(f"Skipping submission {tree_tracking_number}: does not belong to current user.")
                    continue

            try:
                mapped_data = map_kobo_to_database(submission)
                if mapped_data:
                    save_tree_data(mapped_data)
                    qr_filename = f"qr_{mapped_data['tree_id']}.png"
                    qr_filepath = generate_qr_code(mapped_data['tree_id'], qr_filename)
                    mapped_data['qr_code_path'] = str(qr_filepath)
                    mapped_data['qr_code_base64'] = get_qr_code_as_base64(qr_filepath)
                    processed_trees.append(mapped_data)
            except Exception as e:
                st.error(f"Error processing submission {submission.get('_id')}: {e}")
                # Optionally, log the full submission for debugging
        else:
            # st.warning(f"Submission {submission.get('_id')} has no tree_tracking_number. Skipping.")
            pass # Skip submissions without a tracking number

    conn.close()
    if processed_trees:
        st.success(f"Successfully processed {len(processed_trees)} new tree submissions.")
    else:
        st.info("No new, unprocessed tree submissions found for the specified criteria.")
    return processed_trees

def display_tree_results(tree_results):
    """Displays the results of processed tree submissions."""
    st.subheader("Newly Planted Tree(s) Details")
    for tree in tree_results:
        st.write(f"**Tree ID:** {tree.get('tree_id')}")
        st.write(f"**Species:** {tree.get('local_name')} ({tree.get('scientific_name')})")
        st.write(f"**Planter:** {tree.get('planters_name')}")
        st.write(f"**Date Planted:** {tree.get('date_planted')}")
        st.write(f"**Location:** Lat {tree.get('latitude')}, Lon {tree.get('longitude')}")
        st.write(f"**Estimated CO₂ Sequestered:** {tree.get('co2_kg'):.2f} kg/year")

        if tree.get('qr_code_base64'):
            st.image(tree['qr_code_base64'], caption=f"QR Code for Tree ID: {tree['tree_id']}", width=150)
            st.download_button(
                label=f"Download QR Code for {tree['tree_id']}",
                data=base64.b64decode(tree['qr_code_base64'].split(',')[1]),
                file_name=f"qr_code_{tree['tree_id']}.png",
                mime="image/png"
            )
        st.markdown("---")

def plant_a_tree_section():
    """Main function for the 'Plant a Tree' section."""
    st.title("🌳 Plant a Tree")
    st.markdown("""
        To plant a tree and record its details, please use our KoBo Collect form.
        This ensures accurate data collection for monitoring and impact tracking.
    """)

    # Initialize session state for this workflow
    if "kobo_form_launched" not in st.session_state:
        st.session_state.kobo_form_launched = False
    if "submission_checked" not in st.session_state:
        st.session_state.submission_checked = False
    if "tree_results" not in st.session_state:
        st.session_state.tree_results = None

    if not st.session_state.kobo_form_launched:
        st.info("Click the button below to launch the tree planting data collection form in a new tab.")
        if st.button("Launch KoBo Planting Form"):
            launch_kobo_form()
            st.rerun()
        return

    if not st.session_state.get("submission_checked"):
        st.info("Please complete the planting form and return here.")

        if st.button("Check for New Submissions"):
            with st.spinner("Processing..."):
                current_user = st.session_state.get('user', {})
                user_uid = current_user.get('uid') # Pass the user's UID for filtering

                # Check for submissions only for the current user if logged in
                results = check_for_new_submissions(user_id=user_uid)
                if results:
                    st.session_state.tree_results = results
                st.session_state.submission_checked = True
                st.rerun()

        if st.button("Start Over"):
            st.session_state.kobo_form_launched = False
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
        st.info("No submissions processed for your account in the last 24 hours.")
        if st.button("Try Checking Again"):
            st.session_state.submission_checked = False
            st.rerun()
        if st.button("Reset Workflow"):
            st.session_state.kobo_form_launched = False
            st.session_state.submission_checked = False
            st.session_state.tree_results = None
            st.rerun()

# --- Placeholder functions for app.py imports ---
# These functions were listed in app.py's import but not present in your kobo_integration.py
def get_leaderboard_data():
    """Placeholder for fetching leaderboard data. Returns an empty DataFrame."""
    st.info("Leaderboard data fetching not yet implemented in kobo_integration.py.")
    return pd.DataFrame(columns=['Planter Name', 'Trees Planted', 'CO2 Sequestered (kg)'])

def get_user_badges(user_email=None):
    """Placeholder for fetching user badges. Returns an empty dictionary."""
    st.info("User badges fetching not yet implemented in kobo_integration.py.")
    return {}

# Initialize database
initialize_database()

# For local testing
if __name__ == "__main__":
    st.set_page_config(page_title="Tree Planting", layout="wide")

    if "user" not in st.session_state:
        st.session_state.user = {
            "username": "test_user",
            "email": "test@example.com",
            "uid": "test_uid_123",
            "role": "individual"
        }
        st.session_state.authenticated = True

    plant_a_tree_section()
