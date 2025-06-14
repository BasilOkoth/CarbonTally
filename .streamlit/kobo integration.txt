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

# Use secrets management properly - avoid hardcoded tokens
KOBO_API_TOKEN = st.secrets["KOBO_API_TOKEN"]
KOBO_ASSET_ID = st.secrets["KOBO_ASSET_ID"]

# Database configuration
BASE_DIR = Path(__file__).parent if "__file__" in locals() else Path.cwd()
DATA_DIR = BASE_DIR / "data"
SQLITE_DB = DATA_DIR / "trees.db"
QR_CODE_DIR = DATA_DIR / "qr_codes"

# Ensure directories exist
DATA_DIR.mkdir(exist_ok=True, parents=True)
QR_CODE_DIR.mkdir(exist_ok=True, parents=True)

def initialize_database():
    """Initialize the database with required tables, handling schema migrations for the 'trees' table."""
    conn = sqlite3.connect(SQLITE_DB)
    try:
        c = conn.cursor()

        # --- STEP 1: ENSURE THE BASE 'trees' TABLE EXISTS (without kobo_submission_id initially) ---
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
                qr_code TEXT
                -- kobo_submission_id is intentionally LEFT OUT here. It's added in migration below.
            )
        ''')
        conn.commit() # Commit the initial CREATE TABLE to ensure it's persisted

        # --- STEP 2: DATABASE MIGRATION LOGIC FOR 'trees' TABLE TO ADD 'kobo_submission_id' ---
        c.execute("PRAGMA table_info(trees)")
        columns = c.fetchall()
        column_names = [col[1] for col in columns]

        if "kobo_submission_id" not in column_names:
            st.warning("Database schema migration needed: 'kobo_submission_id' column missing from 'trees' table.")
            try:
                # 1. Rename the old table
                c.execute("ALTER TABLE trees RENAME TO old_trees")
                conn.commit()
                st.info("Renamed 'trees' table to 'old_trees'.")

                # 2. Define the new, desired schema for the 'trees' table
                new_trees_table_schema = '''
                    CREATE TABLE trees (
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
                        kobo_submission_id TEXT UNIQUE
                    )
                '''
                # 3. Create the new 'trees' table with the correct schema
                c.execute(new_trees_table_schema)
                conn.commit()
                st.info("Created new 'trees' table with 'kobo_submission_id' column.")

                # 4. Copy data from old_trees to new trees
                old_table_columns_to_copy = [col[1] for col in c.execute("PRAGMA table_info(old_trees)").fetchall()]
                if 'rowid' in old_table_columns_to_copy:
                    old_table_columns_to_copy.remove('rowid')

                columns_for_new_insert = ', '.join(old_table_columns_to_copy) + ', kobo_submission_id'
                select_columns_for_copy = ', '.join(old_table_columns_to_copy) + ", 'OLD_SUB_' || tree_id"

                copy_sql = f"""
                    INSERT INTO trees ({columns_for_new_insert})
                    SELECT {select_columns_for_copy}
                    FROM old_trees
                """
                c.execute(copy_sql)
                conn.commit()
                st.info("Copied data from 'old_trees' to 'trees'.")

                # 5. Drop the old table
                c.execute("DROP TABLE old_trees")
                conn.commit()
                st.success("Successfully migrated 'trees' table to include 'kobo_submission_id'.")

            except sqlite3.OperationalError as e:
                st.error(f"Error during 'trees' table migration: {e}")
                conn.rollback()
                st.warning("If you see 'UNIQUE constraint failed' here, it likely means you have duplicate 'tree_id's "
                           "in your 'old_trees' table that are preventing migration. "
                           "Consider cleaning your old data or adjusting the fallback for `kobo_submission_id`.")
                raise
            except Exception as e:
                st.error(f"Unexpected error during 'trees' table migration: {e}")
                conn.rollback()
                raise

        # --- END OF DATABASE MIGRATION LOGIC ---

        # Create species table if not exists
        c.execute('''
            CREATE TABLE IF NOT EXISTS species (
                scientific_name TEXT PRIMARY KEY,
                local_name TEXT,
                wood_density REAL,
                benefits TEXT
            )
        ''')
        conn.commit()

        # Create monitoring history table if not exists
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
                FOREIGN KEY (tree_id) REFERENCES trees (tree_id)
            )
        ''')
        conn.commit()

    finally:
        conn.close()

def validate_user_session():
    """
    Validate that the user session has all required fields
    Returns True if valid, False otherwise
    """
    if "user" not in st.session_state:
        st.error("User session not found. Please log in again.")
        return False
        
    required_fields = ["username", "user_type"]
    missing_fields = [field for field in required_fields if field not in st.session_state.user]
    
    if missing_fields:
        st.error(f"User session missing required fields: {', '.join(missing_fields)}")
        return False
        
    # Institution is handled separately with a fallback option
    return True

def ensure_institution_assigned():
    """
    Ensure that an institution is assigned to the current user
    Returns the institution name if available or selected, None otherwise
    """
    if "user" not in st.session_state:
        return None
        
    user_institution = st.session_state.user.get("institution")
    
    if user_institution:
        return user_institution
        
    # If no institution is assigned, provide a selection interface
    st.warning("No institution assigned to your account. Please select your institution:")
    
    # Get available institutions from database or use a default list
    # In a production environment, you would query this from your database
    conn = sqlite3.connect(SQLITE_DB)
    try:
        institutions_df = pd.read_sql(
            "SELECT DISTINCT institution FROM trees WHERE institution IS NOT NULL AND institution != ''",
            conn
        )
        available_institutions = institutions_df["institution"].tolist()
    except Exception as e:
        st.error(f"Error fetching institutions: {e}")
        available_institutions = []
    finally:
        conn.close()
    
    # Add some default options if none found in database
    if not available_institutions:
        available_institutions = ["School A", "School B", "NGO Partner", "Government Agency"]
    
    # Sort alphabetically for better UX
    available_institutions.sort()
    
    # Add custom option
    available_institutions = ["-- Select an institution --"] + available_institutions + ["Other (specify)"]
    
    selected_institution = st.selectbox(
        "Select your institution",
        available_institutions,
        index=0
    )
    
    # Handle custom institution entry
    if selected_institution == "Other (specify)":
        custom_institution = st.text_input("Enter your institution name")
        if custom_institution and custom_institution.strip():
            selected_institution = custom_institution.strip()
        else:
            selected_institution = None
    elif selected_institution == "-- Select an institution --":
        selected_institution = None
    
    # Save the selected institution to session state if valid
    if selected_institution:
        st.session_state.user["institution"] = selected_institution
        st.success(f"Institution set to: {selected_institution}")
        return selected_institution
    else:
        st.error("Please select or enter a valid institution to continue.")
        return None

def get_kobo_form_url():
    """Get the URL for the KoBo form"""
    return f"https://ee.kobotoolbox.org/x/{KOBO_ASSET_ID}"

def launch_kobo_form():
    """Launch the KoBo form for tree planting with enhanced tracking"""
    form_url = get_kobo_form_url()

    session_ref = f"ref_{int(time.time())}"
    st.session_state.kobo_session_ref = session_ref

    tracking_url = f"{form_url}?ref={session_ref}"

    st.markdown(f"""
    ### 🌱 Plant a Tree with KoBo Toolbox

    You'll be redirected to our tree planting form where you can:
    - Enter tree details
    - Capture planting location coordinates
    - Submit your tree planting information

    [Open Tree Planting Form]({tracking_url})

    After submission, return here to view your tree details and QR code.
    """)

    st.session_state.kobo_form_launched = True
    return tracking_url

def get_kobo_submissions(time_filter_hours=24, submission_id=None):
    """
    Retrieve submissions from KoBo Toolbox API with optional filters
    """
    if not KOBO_API_TOKEN or not KOBO_ASSET_ID:
        st.error("KoBo API credentials (token or asset ID) not configured in `st.secrets`.")
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

    url = f"{KOBO_API_URL}/assets/{KOBO_ASSET_ID}/data/"

    # st.write(f"**KoBo API Request Debug Info:**") # Commented out for less verbose output
    # st.write(f"Request URL: `{url}`")
    # st.write(f"Request Headers (partial): `Authorization: Token ...{KOBO_API_TOKEN[-5:]}`")
    # st.write(f"Request Params: `{params}`")

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
        st.warning("This often means the API returned an error page (HTML) or malformed data instead of JSON.")
        st.warning("Please double-check your KOBO_API_TOKEN and KOBO_ASSET_ID in your `secrets.toml` file.")
        return None
    except requests.exceptions.HTTPError as e:
        st.error(f"HTTP error from KoBo API: {e.response.status_code} - {e.response.reason}")
        st.error(f"Response body: {e.response.text[:500]}...")
        st.warning("Common reasons: Incorrect KOBO_API_TOKEN (401 Unauthorized), incorrect KOBO_ASSET_ID (404 Not Found), or API issues.")
        return None
    except requests.exceptions.ConnectionError as e:
        st.error(f"Network connection error to KoBo API: {e}")
        st.warning("Check your internet connection or firewall settings.")
        return None
    except requests.exceptions.Timeout as e:
        st.error(f"Request to KoBo API timed out: {e}")
        st.warning("The KoBo server might be slow or unreachable.")
        return None
    except Exception as e:
        st.error(f"An unexpected error occurred while fetching KoBo submissions: {str(e)}")
        return None

def map_kobo_to_database(kobo_data):
    """
    Map KoBo form fields to database columns with validation
    """
    try:
        lat, lon = 0.0, 0.0
        if "_geolocation" in kobo_data and kobo_data["_geolocation"]:
            if isinstance(kobo_data["_geolocation"], list) and len(kobo_data["_geolocation"]) >= 2:
                try:
                    lat = float(kobo_data["_geolocation"][0])
                    lon = float(kobo_data["_geolocation"][1])
                except (ValueError, TypeError):
                    st.warning(f"Could not parse geolocation list: {kobo_data['_geolocation']}")
            else:
                st.warning(f"Unexpected _geolocation format: {kobo_data['_geolocation']}")
        if lat == 0.0 and lon == 0.0:
            try:
                lat = float(kobo_data.get("latitude", 0)) if kobo_data.get("latitude") else 0.0
                lon = float(kobo_data.get("longitude", 0)) if kobo_data.get("longitude") else 0.0
            except (ValueError, TypeError):
                st.warning(f"Could not parse separate latitude/longitude fields: lat={kobo_data.get('latitude')}, lon={kobo_data.get('longitude')}")

        mapped = {
            "institution": kobo_data.get("institution", "").strip(),
            "local_name": kobo_data.get("local_name", "").strip(),
            "scientific_name": kobo_data.get("scientific_name", "Unknown").strip(),
            "student_name": kobo_data.get("student_name", "").strip(),
            "date_planted": kobo_data.get("date_planted", datetime.now().date().isoformat()),
            "tree_stage": kobo_data.get("tree_stage", "Seedling"),
            "rcd_cm": float(kobo_data.get("rcd_cm", 0)) if kobo_data.get("rcd_cm") is not None else 0.0,
            "dbh_cm": float(kobo_data.get("dbh_cm", 0)) if kobo_data.get("dbh_cm") is not None else 0.0,
            "height_m": float(kobo_data.get("height_m", 0.5)) if kobo_data.get("height_m") is not None else 0.5,
            "latitude": lat,
            "longitude": lon,
            "country": kobo_data.get("country", "Kenya"),
            "county": kobo_data.get("county", ""),
            "sub_county": kobo_data.get("sub_county", ""),
            "ward": kobo_data.get("ward", ""),
            "status": "Alive",
            "kobo_submission_id": kobo_data.get("_id", ""),
            "monitor_notes": kobo_data.get("notes", "") + f"\nKoBo Submission ID: {kobo_data.get('_id', '')}"
        }

        if not mapped["institution"] or not mapped["local_name"]:
            st.warning(f"Skipping submission {kobo_data.get('_id', 'N/A')} due to missing required fields (institution or local_name).")
            return None

        return mapped
    except Exception as e:
        st.error(f"Error mapping KoBo data for submission {kobo_data.get('_id', 'N/A')}: {str(e)}")
        st.json(kobo_data)
        return None

def generate_tree_id(institution_name):
    """
    Generate a unique tree ID with institution prefix and sequential number
    """
    if not institution_name:
        prefix = "TRE"
    else:
        prefix = re.sub(r'[^A-Z]', '', institution_name.upper())[:3] or "TRE"

    conn = sqlite3.connect(SQLITE_DB)
    try:
        local_ids = pd.read_sql(
            "SELECT tree_id FROM trees WHERE institution = ?",
            conn,
            params=(institution_name,)
        )["tree_id"].tolist()

        # Removed checking Kobo submissions for existing IDs here, as they are now fully managed by the DB
        # and checking a large number of Kobo submissions on each ID generation can be slow.

        prefix_ids = [id for id in local_ids if str(id).startswith(prefix)]

        if not prefix_ids:
            return f"{prefix}001"

        sequence_numbers = []
        for id_str in prefix_ids:
            match = re.search(r'\d+$', id_str)
            if match:
                try:
                    sequence_numbers.append(int(match.group()))
                except ValueError:
                    continue

        if not sequence_numbers:
            return f"{prefix}001"

        max_num = max(sequence_numbers)
        return f"{prefix}{max_num + 1:03d}"
    except Exception as e:
        st.error(f"Error generating tree ID: {str(e)}")
        # Fallback to a time-based ID if other methods fail
        return f"{prefix}{int(time.time()) % 100000:05d}"
    finally:
        conn.close()

def generate_qr_code(tree_id):
    """
    Generate and save QR code for a tree linking to Kobo form with tree_id pre-filled
    """
    try:
        KOBO_FORM_BASE_URL = "https://ee.kobotoolbox.org/single/dXdb36aV?tree_id="
        
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(f"{KOBO_FORM_BASE_URL}{tree_id}")
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
        st.error(f"Error generating QR code for tree ID '{tree_id}': {str(e)}")
        return None, None

def save_tree_submission(submission_data):
    """
    Save a processed KoBo submission to the database
    """
    if not submission_data:
        st.warning("No valid submission data provided to save.")
        return False, None, None

    tree_id = generate_tree_id(submission_data["institution"])
    qr_img, qr_path = generate_qr_code(tree_id)

    if not qr_img:
        st.error(f"Failed to generate QR code for tree ID: {tree_id}")
        return False, None, None

    submission_data.update({
        "tree_id": tree_id,
        "qr_code": qr_img,
        "co2_kg": calculate_co2_sequestration(
            submission_data["scientific_name"],
            submission_data["rcd_cm"],
            submission_data["dbh_cm"]
        )
    })

    conn = sqlite3.connect(SQLITE_DB)
    try:
        c = conn.cursor()

        columns = list(submission_data.keys())
        placeholders = ", ".join(["?"] * len(columns))
        values = [submission_data[column] for column in columns]

        insert_sql = f"INSERT INTO trees ({', '.join(columns)}) VALUES ({placeholders})"
        c.execute(insert_sql, values)

        c.execute('''
            INSERT INTO monitoring_history (
                tree_id, monitor_date, monitor_status, monitor_stage,
                rcd_cm, dbh_cm, height_m, co2_kg, notes, monitor_by
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            tree_id,
            submission_data["date_planted"],
            "Alive",
            submission_data["tree_stage"],
            submission_data["rcd_cm"],
            submission_data["dbh_cm"],
            submission_data["height_m"],
            submission_data["co2_kg"],
            submission_data["monitor_notes"],
            submission_data["student_name"]
        ))

        conn.commit()
        st.success(f"Successfully saved tree {tree_id} to database.")
        return True, tree_id, qr_path
    except sqlite3.IntegrityError as e:
        st.error(f"Duplicate submission detected or integrity error: {str(e)}")
        conn.rollback()
        return False, None, None
    except Exception as e:
        st.error(f"Unexpected database error while saving tree {tree_id}: {str(e)}")
        conn.rollback()
        return False, None, None
    finally:
        conn.close()

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

def check_for_new_submissions(user_identifier, hours=24):
    """
    Check for new submissions matching the current institution and process them.
    Institution is now the primary matching criterion.
    """
    st.info(f"Fetching KoBo submissions from the last {hours} hours...")
    
    # Replace st.debug() with st.text() for debugging output
    if st.session_state.get('debug_mode', False):
        st.text(f"[DEBUG] User Context: {st.session_state.user}")
    
    # Add debug expander to show session state
    with st.expander("Debug Information", expanded=False):
        st.write({
            "User Session": st.session_state.user if "user" in st.session_state else "Not set",
            "Session Keys": list(st.session_state.keys())
        })
    
    submissions = get_kobo_submissions(hours)
    if not submissions:
        st.info("No new submissions found from KoBo Toolbox.")
        return []

    results = []
    st.info(f"Found {len(submissions)} submissions. Checking institution ownership...")

    # Get institution from session with fallback option
    user_institution = ensure_institution_assigned()
    if not user_institution:
        st.error("Institution selection required to check submissions.")
        return []

    for sub in submissions:
        submission_kobo_id = sub.get("_id")
        if not submission_kobo_id:
            st.warning(f"Skipping submission with no ID: {sub}")
            continue

        if is_submission_processed(submission_kobo_id):
            if st.session_state.get('debug_mode', False):
                st.text(f"[DEBUG] Submission {submission_kobo_id} already processed")
            continue

        # --- Institution Matching (Primary Check) ---
        submitted_institution = sub.get("institution", "").strip()
        if not submitted_institution:
            st.warning(f"Submission {submission_kobo_id} has no institution - skipping")
            continue

        # Normalize institution names for comparison
        is_institution_match = (submitted_institution.lower() == user_institution.lower())
        
        # --- Secondary Checks (for debugging) ---
        if st.session_state.get('debug_mode', False):
            secondary_matches = []
            if st.session_state.get("kobo_session_ref"):
                secondary_matches.append(f"Session ref: {sub.get('ref') == st.session_state.kobo_session_ref}")
            if st.session_state.user.get("email"):
                secondary_matches.append(f"Email match: {sub.get('email') == st.session_state.user.get('email')}")
            if st.session_state.user.get("username"):
                secondary_matches.append(f"Username match: {sub.get('student_name') == st.session_state.user.get('username')}")

            st.text(f"""
            [DEBUG] Submission {submission_kobo_id}:
            - Institution Match: {is_institution_match} 
            ({user_institution} vs {submitted_institution})
            - Secondary Checks: {', '.join(secondary_matches)}
            """)

        if is_institution_match:
            st.success(f"Processing submission from {submitted_institution} (matches your institution)")
            mapped_data = map_kobo_to_database(sub)
            
            if mapped_data:
                if st.session_state.get('debug_mode', False):
                    mapped_data["match_info"] = {
                        "matched_by": "institution",
                        "user_institution": user_institution,
                        "submission_institution": submitted_institution
                    }
                
                success, tree_id, qr_path = save_tree_submission(mapped_data)
                
                if success:
                    results.append({
                        "tree_id": tree_id,
                        "qr_path": qr_path,
                        "species": mapped_data["local_name"],
                        "institution": mapped_data["institution"],
                        "date": mapped_data["date_planted"],
                        "co2": mapped_data["co2_kg"]
                    })
            else:
                st.warning(f"Failed to map submission {submission_kobo_id}")

    # Debug summary
    if st.session_state.get('debug_mode', False):
        st.text(f"""
        [DEBUG] Processing complete:
        - Total submissions: {len(submissions)}
        - Institution matches: {len(results)}
        - Your institution: {user_institution}
        """)
    
    return results

def is_submission_processed(submission_id):
    """Check if a KoBo submission (by its _id) has already been processed and saved to the local DB"""
    if not submission_id:
        return False

    conn = sqlite3.connect(SQLITE_DB)
    try:
        c = conn.cursor()
        c.execute("SELECT 1 FROM trees WHERE kobo_submission_id = ?", (submission_id,))
        return c.fetchone() is not None
    except sqlite3.OperationalError as e:
        st.error(f"Database error in is_submission_processed: {e}. "
                 "Ensure 'kobo_submission_id' column exists in 'trees' table.")
        return False
    finally:
        conn.close()

def display_tree_results(results):
    """Display processed tree planting results in Streamlit"""
    if results:
        st.success(f"🎉 Successfully processed {len(results)} new tree planting(s)! 🎉")

        for result in results:
            with st.expander(f"🌳 Tree {result.get('tree_id', 'N/A')} - {result.get('species', 'Unknown Species')}"):
                col1, col2 = st.columns(2)

                with col1:
                    st.metric("Institution", result.get("institution", "N/A"))
                    st.metric("Date Planted", result.get("date", "N/A"))
                    st.metric("CO₂ Sequestered", f"{result.get('co2', 0.0)} kg")

                with col2:
                    qr_path = result.get("qr_path")
                    if qr_path and os.path.isfile(qr_path):
                        st.image(qr_path, caption=f"QR for Tree {result['tree_id']}")
                        with open(qr_path, "rb") as f:
                            st.download_button(
                                "Download QR Code",
                                f.read(),
                                file_name=f"tree_{result['tree_id']}_qr.png",
                                mime="image/png"
                            )
                    else:
                        st.warning(f"QR code file not found for Tree ID: {result.get('tree_id', 'N/A')}")

                st.markdown(f"""
                **Share this tree:** [https://carbontally.app/tree?id={result.get('tree_id', '')}](https://carbontally.app/tree?id={result.get('tree_id', '')})
                """)
    else:
        st.info("No tree planting results to display at this time.")

def plant_a_tree_section():
    """Main Streamlit UI workflow for planting trees via KoBo Toolbox"""
    st.markdown("<h1 class='header-text'>🌱 Plant a Tree</h1>", unsafe_allow_html=True)

    # Validate user session before proceeding
    if not validate_user_session():
        st.warning("Please log in to plant trees.")
        return

    user_type = st.session_state.user.get("user_type")
    if user_type not in ["admin", "school", "field"]:
        st.error("Your account doesn't have permissions to plant trees.")
        return

    if not st.session_state.get("kobo_form_launched"):
        st.markdown("""
        <div class="card">
            <h3>Tree Planting Process</h3>
            <ol>
                <li>Click the button below to open the planting form in a new tab.</li>
                <li>Complete all required fields in the KoBo Toolbox form.</li>
                <li>**IMPORTANT:** Return to this app page after successfully submitting the form.</li>
            </ol>
        </div>
        """, unsafe_allow_html=True)

        if st.button("Open Tree Planting Form"):
            launch_kobo_form()
            st.rerun()
        return

    if not st.session_state.get("submission_checked"):
        st.info("Form launched. Please complete the KoBo Toolbox form in the new tab and return here.")

        # Determine user_identifier: prioritize email, then username, then session ref
        user_id = (st.session_state.user.get("email") or
                   st.session_state.user.get("username") or
                   st.session_state.get("kobo_session_ref"))

        st.markdown("---")
        st.markdown("### Waiting for your submission...")

        if st.button("I've Completed the Form, Check for Submissions"):
            with st.spinner("Checking for your tree planting submissions..."):
                results = check_for_new_submissions(user_id)

                if results:
                    st.session_state.tree_results = results
                    st.session_state.submission_checked = True
                    st.rerun()
                else:
                    st.warning("Still no new submissions found matching your details in the last 24 hours. Please ensure your submission was successful and try again.")

        if st.button("Start Over (Launch Form Again)"):
            reset_planting_workflow()
            st.rerun()
        return

    if st.session_state.get("tree_results"):
        display_tree_results(st.session_state.tree_results)

        st.markdown("---")
        if st.button("Plant Another Tree"):
            reset_planting_workflow()
            st.rerun()
    else:
        st.info("No tree planting results to display from the last check. You can launch the form again.")
        if st.button("Launch Form Again"):
            reset_planting_workflow()
            st.rerun()

def plant_a_tree_workflow():
    """Alias for plant_a_tree_section to maintain backward compatibility"""
    return plant_a_tree_section()

def reset_planting_workflow():
    """Reset the planting workflow state variables in Streamlit's session state"""
    for key in ["kobo_form_launched", "submission_checked", "tree_results", "kobo_session_ref"]:
        if key in st.session_state:
            del st.session_state[key]

# Initialize database on first run of the script.
initialize_database()

# For local testing purposes (if you run kobo_integration.py directly)
if __name__ == "__main__":
    st.set_page_config(page_title="Tree Planting Module Test", layout="wide")

    # Add a debug mode toggle
    st.sidebar.title("Debug Options")
    st.session_state.debug_mode = st.sidebar.checkbox("Enable Debug Mode", value=False)

    # Example of how your login might set the user session for an 'Osep' user
    if "user" not in st.session_state:
        st.session_state.user = {
            "username": "osep_user",
            "user_type": "school", # Or 'field'
            "email": "osep.user@example.com",
            "institution": "osep" # IMPORTANT: Add this institution key to your user object
        }
    st.title("KoBo Integration Test Module")
    st.info("This is a standalone test for the KoBo integration functionality. "
            "In a real app, this module is imported into `app.py`.")

    plant_a_tree_section()
