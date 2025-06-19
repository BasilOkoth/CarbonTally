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

        # Create trees table
        c.execute('''
            CREATE TABLE IF NOT EXISTS trees (
                tree_id TEXT PRIMARY KEY,
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
                tree_tracking_number TEXT UNIQUE
            )
        ''')
        conn.commit()

        # Create species table
        c.execute('''
            CREATE TABLE IF NOT EXISTS species (
                scientific_name TEXT PRIMARY KEY,
                local_name TEXT,
                wood_density REAL,
                benefits TEXT
            )
        ''')
        conn.commit()

        # Create monitoring history table
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
                kobo_submission_id TEXT UNIQUE,
                FOREIGN KEY (tree_id) REFERENCES trees (tree_id)
            )
        ''')
        conn.commit()

    finally:
        conn.close()

def validate_user_session():
    """Validate that the user session has required fields"""
    if "user" not in st.session_state:
        st.error("Please log in to continue.")
        return False
    
    if not isinstance(st.session_state.user, dict):
        st.error("Invalid session format. Please log in again.")
        st.session_state.user = {}
        return False
        
    if "username" not in st.session_state.user:
        st.error("Missing username in session.")
        return False
        
    return True

def get_kobo_form_url():
    """Get the public URL for the KoBo tree planting form"""
    short_code = st.secrets.get("KOBO_ASSET_FORM_CODE")  # use short code, e.g. 's8ntxUM5'
    if not short_code:
        st.error("Form configuration missing. Please contact support.")
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
    """Retrieve submissions from KoBo Toolbox API"""
    kobo_api_token = st.secrets.get("KOBO_API_TOKEN")
    kobo_asset_id = st.secrets.get("KOBO_ASSET_ID")

    if not kobo_api_token or not kobo_asset_id:
        st.error("System configuration error. Please contact support.")
        return None

    headers = {
        "Authorization": f"Token {kobo_api_token}",
        "Accept": "application/json"
    }

    time_filter = datetime.now() - timedelta(hours=hours)
    params = {
        "query": json.dumps({"_submission_time": {"$gte": time_filter.isoformat()}})
    }

    url = f"{KOBO_API_URL}/assets/{kobo_asset_id}/data/"

    try:
        response = requests.get(url, headers=headers, params=params, timeout=30)
        response.raise_for_status()
        return response.json().get("results", [])
    except Exception as e:
        st.error(f"Error fetching submissions: {str(e)}")
        return None

def validate_tracking_number(tracking_number):
    """Validate the Tree Tracking Number format"""
    if not tracking_number or not isinstance(tracking_number, str):
        return False
    return len(tracking_number.strip()) >= 3

def map_kobo_to_database(kobo_data):
    """Map KoBo form fields to database columns"""
    try:
        # DEBUG: Show the tracking number received from KoBo
        st.write("Tracking number from KoBo:", kobo_data.get("tree_tracking_number"))
        # Get and validate Tree Tracking Number
        tracking_number = kobo_data.get("tree_tracking_number", "").strip()
        if not validate_tracking_number(tracking_number):
            st.warning("Invalid Tree Tracking Number - must be at least 3 characters")
            return None

        # Handle geolocation
        lat, lon = 0.0, 0.0
        if "_geolocation" in kobo_data and kobo_data["_geolocation"]:
            if isinstance(kobo_data["_geolocation"], list) and len(kobo_data["_geolocation"]) >= 2:
                try:
                    lat = float(kobo_data["_geolocation"][0])
                    lon = float(kobo_data["_geolocation"][1])
                except (ValueError, TypeError):
                    st.warning("Could not parse GPS coordinates")

        mapped = {
            "local_name": kobo_data.get("Local_Name", "").strip(),
            "scientific_name": kobo_data.get("Scientific_Name", "Unknown").strip(),
            "student_name": kobo_data.get("Student_Name", "").strip(),
            "date_planted": kobo_data.get("Date_Planted", datetime.now().date().isoformat()),
            "tree_stage": kobo_data.get("Tree_Stage", "Seedling"),
            "rcd_cm": float(kobo_data.get("RCD_cm", 0)) if kobo_data.get("RCD_cm") not in [None, ''] else 0.0,
            "dbh_cm": float(kobo_data.get("DBH_cm", 0)) if kobo_data.get("DBH_cm") not in [None, ''] else 0.0,
            "height_m": float(kobo_data.get("Height_m", 0.5)) if kobo_data.get("Height_m") not in [None, ''] else 0.5,
            "latitude": lat,
            "longitude": lon,
            "country": kobo_data.get("Country", "Kenya"),
            "county": kobo_data.get("County", ""),
            "sub_county": kobo_data.get("Sub_County", ""),
            "ward": kobo_data.get("Ward", ""),
            "status": "Alive",
            "kobo_submission_id": kobo_data.get("_id", ""),
            "monitor_notes": kobo_data.get("Notes", ""),
            "tree_tracking_number": tracking_number
        }

        # Calculate CO2
        mapped["co2_kg"] = calculate_co2_sequestration(
            mapped["scientific_name"],
            rcd=mapped["rcd_cm"],
            dbh=mapped["dbh_cm"]
        )

        return mapped
    except Exception as e:
        st.error(f"Error processing submission: {str(e)}")
        return None

def generate_tree_id(tracking_number):
    """Generate a unique tree ID using Tree Tracking Number"""
    if not validate_tracking_number(tracking_number):
        prefix = "TRE"
    else:
        # Use first 3 alphanumeric characters of tracking number
        clean_tracking = re.sub(r'[^A-Z0-9]', '', tracking_number.upper())
        prefix = clean_tracking[:3] if clean_tracking else "TRE"

    conn = sqlite3.connect(SQLITE_DB)
    try:
        # Find highest sequence number for this prefix
        existing_ids = pd.read_sql(
            f"SELECT tree_id FROM trees WHERE tree_id LIKE '{prefix}%'",
            conn
        )["tree_id"].tolist()

        sequence_numbers = []
        for id_str in existing_ids:
            match = re.search(r'\d+$', id_str)
            if match:
                try:
                    sequence_numbers.append(int(match.group()))
                except ValueError:
                    continue

        next_num = max(sequence_numbers) + 1 if sequence_numbers else 1
        return f"{prefix}{next_num:03d}"
    except Exception as e:
        st.error(f"Error generating tree ID: {str(e)}")
        return f"{prefix}{int(time.time()) % 1000:03d}"
    finally:
        conn.close()

def generate_qr_code(tree_id):
    """Generate and save QR code for a tree"""
    try:
        kobo_monitoring_asset_id = st.secrets.get("KOBO_MONITORING_ASSET_ID")
        if not kobo_monitoring_asset_id:
            st.error("QR code generation not configured.")
            return None, None

        form_url = f"https://ee.kobotoolbox.org/single/dXdb36aV?tree_id={tree_id}".strip()
        
        qr = qrcode.QRCode(version=1, box_size=10, border=4)
        qr.add_data(form_url)
        qr.make(fit=True)

        img = qr.make_image(fill_color="#2e8b57", back_color="white")
        QR_CODE_DIR.mkdir(exist_ok=True, parents=True)
        file_path = QR_CODE_DIR / f"{tree_id}.png"
        img.save(file_path)

        buffered = BytesIO()
        img.save(buffered, format="PNG")
        img_str = base64.b64encode(buffered.getvalue()).decode()

        return img_str, str(file_path)
    except Exception as e:
        st.error(f"Error generating QR code: {str(e)}")
        return None, None

def save_tree_submission(submission_data):
    """Save a processed KoBo submission to the database"""
    if not submission_data:
        return False, None, None

    tree_id = generate_tree_id(submission_data["tree_tracking_number"])
    qr_img, qr_path = generate_qr_code(tree_id)

    if not qr_img:
        return False, None, None

    submission_data["tree_id"] = tree_id
    submission_data["qr_code"] = qr_img
    submission_data["last_monitored"] = submission_data["date_planted"]

    conn = sqlite3.connect(SQLITE_DB)
    try:
        # Insert into trees table
        trees_cols = [k for k in submission_data.keys() 
                     if k in ["tree_id", "local_name", "scientific_name", "student_name",
                             "date_planted", "tree_stage", "rcd_cm", "dbh_cm", "height_m",
                             "latitude", "longitude", "co2_kg", "status", "country", "county",
                             "sub_county", "ward", "adopter_name", "last_monitored", 
                             "monitor_notes", "qr_code", "kobo_submission_id", "tree_tracking_number"]]
        
        trees_values = [submission_data[k] for k in trees_cols]
        c = conn.cursor()
        c.execute(f"""
            INSERT INTO trees ({', '.join(trees_cols)})
            VALUES ({', '.join(['?']*len(trees_cols))})
        """, trees_values)

        # Insert into monitoring_history
        monitor_data = {
            "tree_id": tree_id,
            "monitor_date": submission_data["date_planted"],
            "monitor_status": "Alive",
            "monitor_stage": submission_data["tree_stage"],
            "rcd_cm": submission_data["rcd_cm"],
            "dbh_cm": submission_data["dbh_cm"],
            "height_m": submission_data["height_m"],
            "co2_kg": submission_data["co2_kg"],
            "notes": submission_data["monitor_notes"],
            "monitor_by": submission_data["student_name"],
            "kobo_submission_id": submission_data["kobo_submission_id"]
        }

        history_cols = [k for k in monitor_data.keys() 
                       if k in ["tree_id", "monitor_date", "monitor_status", "monitor_stage",
                               "rcd_cm", "dbh_cm", "height_m", "co2_kg", "notes", "monitor_by",
                               "kobo_submission_id"]]
        
        history_values = [monitor_data[k] for k in history_cols]
        c.execute(f"""
            INSERT INTO monitoring_history ({', '.join(history_cols)})
            VALUES ({', '.join(['?']*len(history_cols))})
        """, history_values)

        conn.commit()
        return True, tree_id, qr_path
    except sqlite3.IntegrityError as e:
        conn.rollback()
        st.error(f"Duplicate entry: This Tree Tracking Number may already exist")
        return False, None, None
    except Exception as e:
        conn.rollback()
        st.error(f"Database error: {str(e)}")
        return False, None, None
    finally:
        conn.close()

def calculate_co2_sequestration(species, rcd=None, dbh=None):
    """Calculate estimated CO2 sequestration"""
    conn = sqlite3.connect(SQLITE_DB)
    try:
        species_data = pd.read_sql(
            "SELECT wood_density FROM species WHERE scientific_name = ?",
            conn,
            params=(species,)
        )

        density = species_data["wood_density"].iloc[0] if not species_data.empty else 0.6

        if dbh and dbh > 0:
            agb = 0.0509 * density * (dbh ** 2.5)
        elif rcd and rcd > 0:
            agb = 0.042 * (rcd ** 2.5)
        else:
            return 0.0

        co2_sequestration = 0.47 * (agb + (0.2 * agb)) * 3.67
        return round(co2_sequestration, 2)
    except Exception as e:
        st.error(f"Calculation error: {str(e)}")
        return 0.0
    finally:
        conn.close()

def is_submission_processed(submission_id):
    """Check if a submission has already been processed"""
    if not submission_id:
        return False

    conn = sqlite3.connect(SQLITE_DB)
    try:
        c = conn.cursor()
        c.execute("SELECT 1 FROM trees WHERE kobo_submission_id = ?", (submission_id,))
        return c.fetchone() is not None
    except Exception:
        return False
    finally:
        conn.close()

def check_for_new_submissions():
    """Check for and process new submissions"""
    submissions = get_kobo_submissions()
    if not submissions:
        st.info("No new submissions found.")
        return []

    results = []
    for sub in submissions:
        if is_submission_processed(sub.get("_id")):
            continue

        mapped_data = map_kobo_to_database(sub)
        if not mapped_data:
            continue

        success, tree_id, qr_path = save_tree_submission(mapped_data)
        if success:
            results.append({
                "tree_id": tree_id,
                "qr_path": qr_path,
                "species": mapped_data["local_name"],
                "date": mapped_data["date_planted"],
                "co2": mapped_data["co2_kg"],
                "tree_tracking_number": mapped_data["tree_tracking_number"]
            })

    return results
def display_tree_results(results):
    """Display processed tree planting results"""
    if not results:
        st.info("No new trees processed.")
        return

    st.success(f"Processed {len(results)} new tree(s)!")
    
    for result in results:
        with st.expander(f"Tree {result['tree_id']} ({result['species']})"):
            col1, col2 = st.columns(2)
            
            with col1:
                st.metric("Tree Tracking Number", result["tree_tracking_number"])
                st.metric("Date Planted", result["date"])
                st.metric("CO₂ Sequestered", f"{result['co2']} kg")
            
            with col2:
                if os.path.exists(result["qr_path"]):
                    st.image(result["qr_path"], caption="Tree QR Code")
                    with open(result["qr_path"], "rb") as f:
                        st.download_button(
                            "Download QR Code",
                            f.read(),
                            file_name=f"tree_{result['tree_id']}_qr.png",
                            mime="image/png"
                        )
            
            # Updated share link with actual KoBo URL
            kobo_url = f"https://ee.kobotoolbox.org/single/dXdb36aV?tree_id={result['tree_id']}"
            st.markdown(f"""
            **Share or monitor this tree:** [{kobo_url}]({kobo_url})
            """)
def plant_a_tree_section():
    """Main workflow for planting trees"""
    st.title("Plant a Tree")

    if not validate_user_session():
        return

    if not st.session_state.get("kobo_form_launched"):
        st.markdown("""
        ### Tree Planting Instructions:
        1. Click the button below to open the planting form
        2. Complete all fields including the **Tree Tracking Number**
        3. Submit the form and return here
        """)
        
        if st.button("Open Planting Form"):
            launch_kobo_form()
            st.rerun()
        return

    if not st.session_state.get("submission_checked"):
        st.info("Please complete the planting form and return here.")
        
        if st.button("Check for New Submissions"):
            with st.spinner("Processing..."):
                results = check_for_new_submissions()
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
        st.info("No submissions processed.")
        if st.button("Try Again"):
            st.session_state.submission_checked = False
            st.rerun()

# Initialize database
initialize_database()

# For local testing
if __name__ == "__main__":
    st.set_page_config(page_title="Tree Planting", layout="wide")
    
    if "user" not in st.session_state:
        st.session_state.user = {
            "username": "test_user"
        }
    
    plant_a_tree_section()
