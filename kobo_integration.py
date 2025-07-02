# kobo_integration.py

# ========== STREAMLIT SETUP ==========
import streamlit as st
from pathlib import Path
import sqlite3

def get_db_connection():
    BASE_DIR = Path(__file__).parent if "__file__" in locals() else Path.cwd()
    SQLITE_DB = BASE_DIR / "data" / "trees.db"
    return sqlite3.connect(SQLITE_DB)

# ========== STANDARD LIBRARY IMPORTS ==========
import os
import sqlite3
import uuid
import base64
import json
from pathlib import Path
from datetime import datetime
from io import BytesIO

# ========== THIRD-PARTY IMPORTS ==========
import pandas as pd
import qrcode
import requests

# ========== CONFIGURATION ==========
KOBO_API_URL = "https://kf.kobotoolbox.org/api/v2"
KOBO_API_TOKEN = None
KOBO_ASSET_ID = None

BASE_DIR = Path(__file__).parent if "__file__" in locals() else Path.cwd()
DATA_DIR = BASE_DIR / "data"
SQLITE_DB = DATA_DIR / "trees.db"
QR_CODE_DIR = DATA_DIR / "qr_codes"

DATA_DIR.mkdir(exist_ok=True, parents=True)
QR_CODE_DIR.mkdir(exist_ok=True, parents=True)

# ========== CORE FUNCTIONS ==========

def initialize_database():
    conn = sqlite3.connect(SQLITE_DB)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS trees (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            form_uuid TEXT UNIQUE NOT NULL,
            tree_id TEXT NOT NULL,
            tree_tracking_number TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()

# Optional: Uncomment to run only when this file is executed directly
# if __name__ == "__main__":
#     initialize_database()
def initialize_kobo_credentials():
    global KOBO_API_TOKEN, KOBO_ASSET_ID
    
    if KOBO_API_TOKEN is None:
        try:
            KOBO_API_TOKEN = st.secrets["KOBO_API_TOKEN"]
            KOBO_ASSET_ID = st.secrets["KOBO_ASSET_ID"]
        except (AttributeError, KeyError):
            KOBO_API_TOKEN = os.getenv('KOBO_API_TOKEN', '')
            KOBO_ASSET_ID = os.getenv('KOBO_ASSET_ID', '')
    
    if not KOBO_API_TOKEN or KOBO_API_TOKEN == 'your_api_token_here':
        st.error("KoBo API credentials not configured!")
        raise ValueError("KoBo API credentials are missing or not configured.")
    
    return KOBO_API_TOKEN, KOBO_ASSET_ID

# path/to/tree_utils.py
import sqlite3
import uuid
import logging

SQLITE_DB = "data/trees.db"  # Ensure this is the consistent path

def get_next_tree_id(user_full_name: str, tree_tracking_number: str, form_uuid: str) -> str:
    """
    Generate a unique tree ID using initials + sequence.
    Raises error if generation fails instead of falling back to UUID.
    """
    conn = sqlite3.connect(SQLITE_DB)
    try:
        c = conn.cursor()

        # ✅ Ensure the sequences table exists
        c.execute("""
            CREATE TABLE IF NOT EXISTS sequences (
                prefix TEXT PRIMARY KEY,
                next_val INTEGER
            )
        """)

        # Check if tree ID already exists for this form UUID
        c.execute("SELECT tree_id FROM trees WHERE form_uuid = ?", (form_uuid,))
        result = c.fetchone()
        if result:
            return result[0]  # Return existing ID

        # Derive initials from name
        parts = user_full_name.strip().upper().split()
        if len(parts) >= 2:
            prefix = parts[0][0] + parts[1][0]
        elif len(parts) == 1:
            prefix = parts[0][:2]
        else:
            raise ValueError("Invalid name format for tree ID generation")

        # Get current sequence number for this prefix
        c.execute("SELECT next_val FROM sequences WHERE prefix = ?", (prefix,))
        row = c.fetchone()
        next_val = row[0] if row else 1

        # Format suffix
        suffix = f"{next_val:03d}"
        tree_id = f"{prefix}{suffix}"

        # Insert into sequences table or update
        if row:
            c.execute("UPDATE sequences SET next_val = ? WHERE prefix = ?", (next_val + 1, prefix))
        else:
            c.execute("INSERT INTO sequences (prefix, next_val) VALUES (?, ?)", (prefix, next_val + 1))

        # Do NOT insert into trees here — that will be handled later

        conn.commit()
        return tree_id

    except Exception as e:
        conn.rollback()
        logging.error(f"Error generating tree ID: {e}")
        raise ValueError("Failed to generate tree ID")

    finally:
        conn.close()


def initialize_database():
    conn = sqlite3.connect(SQLITE_DB)
    try:
        c = conn.cursor()

        # Create tables with all required columns
        c.execute('''
            CREATE TABLE IF NOT EXISTS trees (
                tree_id TEXT PRIMARY KEY,
                local_name TEXT,
                scientific_name TEXT,
                planters_name TEXT,
                date_planted TEXT,
                latitude REAL,
                longitude REAL,
                co2_kg REAL,
                planter_email TEXT,
                planter_uid TEXT,
                tree_tracking_number TEXT UNIQUE,
                dbh_cm REAL,
                height_m REAL,
                tree_stage TEXT,
                status TEXT,
                country TEXT,
                county TEXT,
                sub_county TEXT,
                ward TEXT,
                adopter_name TEXT,
                last_updated TEXT
            )
        ''')
        conn.commit()
    except Exception as e:
        st.error(f"Database initialization error: {e}")
    finally:
        conn.close()
def get_kobo_secrets():
    try:
        initialize_kobo_credentials()
        return KOBO_API_TOKEN, KOBO_ASSET_ID, st.secrets.get("KOBO_ASSET_FORM_CODE", "")
    except:
        return KOBO_API_TOKEN, KOBO_ASSET_ID, ""

def launch_kobo_form():
    _, _, kobo_asset_form_code = get_kobo_secrets()
    if kobo_asset_form_code:
        form_url = f"https://ee.kobotoolbox.org/x/{kobo_asset_form_code}"
        st.markdown(f"<a href='{form_url}' target='_blank'>Open Tree Planting Form</a>", unsafe_allow_html=True)
        st.session_state.kobo_form_launched = True
    else:
        st.error("KoBo form code not configured")

def get_kobo_submissions(asset_id):
    initialize_kobo_credentials()
    headers = {"Authorization": f"Token {KOBO_API_TOKEN}"}
    all_submissions = []
    next_url = f"{KOBO_API_URL}/assets/{asset_id}/data/"
    
    try:
        while next_url:
            response = requests.get(next_url, headers=headers, params={"format": "json"})
            response.raise_for_status()
            data = response.json()
            all_submissions.extend(data.get('results', []))
            next_url = data.get('next')
        return {'results': all_submissions}
    except Exception as e:
        st.error(f"Error fetching submissions: {str(e)}")
        return None
def check_for_new_submissions():
    """Check KoBoToolbox for new tree submissions and process them"""
    try:
        # Initialize KoBo credentials
        initialize_kobo_credentials()
        asset_id = KOBO_ASSET_ID
        
        if not asset_id:
            st.error("KoBo asset ID is not configured.")
            return []

        # Get current user info
        current_user = st.session_state.get('user', {})
        user_tracking_number = current_user.get('treeTrackingNumber')
        
        if not user_tracking_number:
            st.error("User tracking number not found. Please ensure you're logged in.")
            return []

        # Get all submissions from KoBo
        submissions = get_kobo_submissions(asset_id)
        if not submissions or 'results' not in submissions:
            st.info("No submissions found in KoBoToolbox.")
            return []

        # Get already processed form UUIDs from database
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("SELECT form_uuid FROM trees")
        saved_uuids = {row[0] for row in c.fetchall()}
        conn.close()

        # Process new submissions
        processed_trees = []
        for submission in submissions['results']:
            form_uuid = submission.get('_uuid')
            
            # Skip if already processed or missing UUID
            if not form_uuid or form_uuid in saved_uuids:
                continue
                
            # Verify this submission belongs to current user
            submission_tracking = submission.get('tree_tracking_number')
            if submission_tracking != user_tracking_number:
                continue

            try:
                # Map KoBo data to our database format
                tree_data = map_kobo_to_database(submission)
                
                # Save to database
                save_tree_data(tree_data)
                
                # Generate QR code
                qr_path = generate_qr_code(
                    tree_id=tree_data["tree_id"],
                    tree_name=tree_data["local_name"],
                    planter=tree_data["planters_name"],
                    date_planted=tree_data["date_planted"]
                )
                
                processed_trees.append({
                    "data": tree_data,
                    "qr_code_path": qr_path
                })
                
            except Exception as e:
                st.warning(f"Error processing submission {form_uuid}: {str(e)}")
                continue

        return processed_trees

    except Exception as e:
        st.error(f"Failed to check submissions: {str(e)}")
        return []
def map_kobo_to_database(submission):
    current_user = st.session_state.get('user', {})
    geolocation = submission.get('_geolocation', [None, None])

    if isinstance(geolocation, str):
        try:
            geolocation = json.loads(geolocation)
        except:
            geolocation = [None, None]

    # Get user and tracking info
    planters_name = submission.get('planters_name', current_user.get('displayName', 'Unknown'))
    tree_tracking_number = submission.get('tree_tracking_number', current_user.get('treeTrackingNumber', 'UNKNOWN'))

    # Get form UUID (required for uniqueness)
    form_uuid = submission.get('_uuid')
    if not form_uuid:
        raise ValueError("Missing required '_uuid' in submission.")
    tree_id = get_next_tree_id(planters_name, tree_tracking_number, form_uuid)


    # ✅ Generate tree ID based on name + tracking + form UUID
    tree_id = get_next_tree_id(planters_name, tree_tracking_number, form_uuid)

    # Get form values
    local_name = submission.get('local_name', 'Unknown')
    scientific_name = submission.get('scientific_name', 'Unknown')
    date_planted = submission.get('date_planted', datetime.now().isoformat())

    # Format date safely
    try:
        if isinstance(date_planted, str):
            date_obj = datetime.fromisoformat(date_planted.replace('Z', ''))
            date_planted = date_obj.strftime('%Y-%m-%d')
    except:
        date_planted = datetime.now().strftime('%Y-%m-%d')

    # Get measurements
    dbh_cm = float(submission.get('dbh_cm', 0)) if submission.get('dbh_cm') else None
    height_m = float(submission.get('height_m', 0)) if submission.get('height_m') else None

    return {
        'tree_id': tree_id,
        'local_name': local_name,
        'scientific_name': scientific_name,
        'planters_name': planters_name,
        'date_planted': date_planted,
        'latitude': float(geolocation[0]) if geolocation and geolocation[0] else None,
        'longitude': float(geolocation[1]) if geolocation and geolocation[1] else None,
        'co2_kg': calculate_co2_sequestered(dbh_cm, height_m),
        'planter_email': current_user.get('email', ''),
        'planter_uid': current_user.get('uid', ''),
        'tree_tracking_number': tree_tracking_number,
        'dbh_cm': dbh_cm,
        'height_m': height_m,
        'form_uuid': form_uuid  # optionally store in DB too
    }
def calculate_co2_sequestered(dbh_cm, height_m):
    if dbh_cm is None or height_m is None or dbh_cm <= 0 or height_m <= 0:
        return 0.0
    
    # More accurate formula using DBH and height
    return 0.25 * 3.14159 * (dbh_cm/100)**2 * height_m * 600 * 0.5 * 3.67

def save_tree_data(tree_data):
    conn = get_db_connection()  # ✅ Use the consistent DB connector
    try:
        c = conn.cursor()
        columns = ', '.join(tree_data.keys())
        placeholders = ':' + ', :'.join(tree_data.keys())
        sql = f"INSERT OR REPLACE INTO trees ({columns}) VALUES ({placeholders})"
        c.execute(sql, tree_data)
        conn.commit()
    except Exception as e:
        st.error(f"❌ Error saving tree data: {e}")
    finally:
        conn.close()

import qrcode
import streamlit as st
from PIL import Image, ImageDraw, ImageFont
from pathlib import Path

# Directory to save QR codes
QR_CODE_DIR = Path("data/qrcodes")


import qrcode
import streamlit as st
from PIL import Image, ImageDraw, ImageFont
from pathlib import Path

QR_CODE_DIR = Path("data/qrcodes")

import qrcode
import streamlit as st
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

QR_CODE_DIR = Path("data/qr_codes")  # Update as needed


def generate_qr_code(tree_id, tree_tracking_number=None, tree_name=None, planter=None, date_planted=None):
    """Generate QR code with prefilled KoBo URL and labels"""
    try:
        # Use tracking number if provided, else fallback to tree_id
        tracking_param = tree_tracking_number or tree_id

        # Construct KoBo URL with optional prefill parameters
        base_url = "https://ee.kobotoolbox.org/x/dXdb36aV"
        params = f"?tree_id={tracking_param}"
        if tree_name:
            params += f"&name={tree_name.replace(' ', '+')}"
        if planter:
            params += f"&planter={planter.replace(' ', '+')}"
        if date_planted:
            params += f"&date_planted={date_planted}"
        form_url = base_url + params

        # Create green QR code
        qr = qrcode.QRCode(version=1, box_size=10, border=4)
        qr.add_data(form_url)
        qr.make(fit=True)

        # Generate image with labels
        qr_img = qr.make_image(fill_color="#2e8b57", back_color="white").convert('RGB')
        width, qr_height = qr_img.size

        img = Image.new('RGB', (width, qr_height + 60), 'white')
        img.paste(qr_img, (0, 0))
        draw = ImageDraw.Draw(img)

        try:
            font = ImageFont.truetype("arial.ttf", 16)
        except:
            font = ImageFont.load_default()

        draw.text((10, qr_height + 10), f"Tree ID: {tree_id}", fill="black", font=font)
        draw.text((10, qr_height + 35), "Powered by CarbonTally", fill="gray", font=font)

        # Save using Tree ID
        QR_CODE_DIR.mkdir(exist_ok=True, parents=True)
        file_path = QR_CODE_DIR / f"{tree_id}.png"
        img.save(file_path)

        return str(file_path)
    except Exception as e:
        st.error(f"QR generation failed: {e}")
        return None


# ========== STREAMLIT UI COMPONENTS ==========

def display_tree_results(tree_results):
    st.markdown("## 🌿 Newly Planted Trees")

    if not tree_results:
        st.info("No tree submissions found.")
        return

    for idx, tree in enumerate(tree_results):
        data = tree["data"]
        tree_id = data.get("tree_id", "Unknown")
        tree_name = data.get("local_name", "Unknown")
        planter = data.get("planters_name", "Unknown")
        date_planted = data.get("date_planted", "Unknown")
        tracking_number = data.get("tree_tracking_number", "N/A")

        # Generate QR code if not already present
        if not tree.get("qr_code_path"):
            qr_path = generate_qr_code(
                tree_id=tree_id,
                tree_tracking_number=tracking_number,
                tree_name=tree_name,
                planter=planter,
                date_planted=date_planted
            )
            tree["qr_code_path"] = qr_path

        with st.expander(f"🌳 Tree ID: {tree_id} | Tracking #: {tracking_number}"):
            col1, col2 = st.columns([2, 1])

            with col1:
                st.markdown(f"**🧾 Local Name:** {tree_name}")
                st.markdown(f"**🔬 Scientific Name:** {data.get('scientific_name', 'Unknown')}")
                st.markdown(f"**👤 Planted by:** {planter}")
                st.markdown(f"**📅 Date Planted:** {date_planted}")
                st.markdown(f"**🌱 CO₂ Sequestered:** {data.get('co2_kg', 0.0):.2f} kg")
                # Removed the coordinates/map display

            with col2:
                if tree.get("qr_code_path"):
                    st.image(tree["qr_code_path"], caption="Tree QR Code", width=200)
                    with open(tree["qr_code_path"], "rb") as qr_file:
                        qr_data = qr_file.read()
                    st.download_button(
                        label="📥 Download QR Code",
                        data=qr_data,
                        file_name=f"tree_{tracking_number}_qrcode.png",
                        mime="image/png",
                        key=f"qr_download_{idx}"
                    )
                else:
                    st.warning("QR code not available")
# Add to kobo_integration.py
def get_tree_metrics():
    """Return comprehensive tree metrics for dashboards"""
    conn = sqlite3.connect(SQLITE_DB)
    try:
        # Get basic counts
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM trees")
        total_trees = c.fetchone()[0]
        
        c.execute("SELECT COUNT(*) FROM trees WHERE status = 'Alive'")
        alive_trees = c.fetchone()[0]
        
        c.execute("SELECT SUM(co2_kg) FROM trees")
        total_co2 = c.fetchone()[0] or 0
        
        # Get recent trees - now including planters_name
        c.execute("""
            SELECT tree_id, local_name, planters_name, date_planted, latitude, longitude 
            FROM trees 
            ORDER BY date_planted DESC 
            LIMIT 5
        """)
        recent_trees = c.fetchall()
        
        # Get species distribution
        c.execute("""
            SELECT scientific_name, COUNT(*) as count 
            FROM trees 
            GROUP BY scientific_name 
            ORDER BY count DESC
        """)
        species_dist = c.fetchall()
        
        return {
            'total_trees': total_trees,
            'alive_trees': alive_trees,
            'total_co2': round(total_co2, 2),
            'recent_trees': recent_trees,
            'species_dist': species_dist,
            'survival_rate': round((alive_trees / total_trees * 100), 1) if total_trees > 0 else 0
        }
    except Exception as e:
        st.error(f"Error fetching metrics: {e}")
        return None
    finally:
        conn.close()
def plant_a_tree_section():
    st.title("🌳 Plant a Tree")
    
    # Initialize session state variables
    if "kobo_form_launched" not in st.session_state:
        st.session_state.kobo_form_launched = False
    if "tree_results" not in st.session_state:
        st.session_state.tree_results = None
    if "last_checked" not in st.session_state:
        st.session_state.last_checked = None

    # Step 1: Launch KoBo form
    if not st.session_state.kobo_form_launched:
        st.markdown("### Step 1: Fill out the planting form")
        st.write("Click the button below to open the tree planting form in a new tab.")
        if st.button("Launch Planting Form", key="launch_form"):
            launch_kobo_form()
            st.session_state.kobo_form_launched = True
            st.rerun()
        return

    # Step 2: Check for submissions after form is completed
    st.markdown("### Step 2: Check for submitted trees")
    st.write("After completing the form in KoBoToolbox, click below to check for your submission.")
    
    if st.button("Check for New Submissions", key="check_submissions"):
        with st.spinner("Checking for new tree submissions..."):
            st.session_state.tree_results = check_for_new_submissions()
            st.session_state.last_checked = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            st.rerun()

    # Show last checked time if available
    if st.session_state.last_checked:
        st.caption(f"Last checked: {st.session_state.last_checked}")

    # Step 3: Display results if found
    if st.session_state.tree_results:
        if len(st.session_state.tree_results) > 0:
            st.success(f"Found {len(st.session_state.tree_results)} new tree(s)!")
            display_tree_results(st.session_state.tree_results)
        else:
            st.info("No new tree submissions found. Please ensure you've submitted the form in KoBoToolbox.")
        
        # Option to plant another tree
        if st.button("Plant Another Tree", key="plant_another"):
            st.session_state.kobo_form_launched = False
            st.session_state.tree_results = None
            st.rerun()
 # Tree planting form button
    form_url = "https://ee.kobotoolbox.org/x/s8ntxUM5"
    st.markdown(f"""
    <a href="{form_url}" target="_blank">
        <button style='background-color:#1D7749; color:white; padding:0.75rem 1.5rem;
                        border:none; border-radius:8px; font-size:1rem; cursor:pointer;'>
            📋 Open Tree Planting Form
        </button>
    </a>
    """, unsafe_allow_html=True)



# ========== INITIALIZATION & ENTRY POINT ==========

initialize_database()
from kobo_integration import initialize_database

def main():
    initialize_database()
    ...

if __name__ == "__main__":
    if "user" not in st.session_state:
        st.session_state.user = {
            "username": "test_user",
            "email": "test@example.com",
            "uid": "test_uid_123"
        }
    plant_a_tree_section()
