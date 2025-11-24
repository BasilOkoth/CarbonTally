# app.py

# Streamlit page config - MUST BE THE VERY FIRST STREAMLIT COMMAND
import streamlit as st
from PIL import Image
from pathlib import Path
import sqlite3  # Explicitly import for SQLite operations
import pandas as pd  # Explicitly import for DataFrame operations
import plotly.express as px
import qrcode
from datetime import datetime
import re
from firebase_auth_integration import init_sql_tables, initialize_firebase,sync_users_from_firestore
from kobo_monitoring import initialize_monitoring_db, monitoring_section
from admin_dashboard import (
    get_total_trees_planted,
    get_total_users,
    get_total_carbon_sequestered,
    get_survival_rate
)
from admin_dashboard import admin_dashboard
# --- Load your logo from the local assets folder ---
logo_image = Image.open("assets/default_logo.png")

# --- Set page configuration with the image logo ---
st.set_page_config(
    page_title="CarbonTally",
    page_icon=logo_image,  # PIL image works here
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- Global variables for module functions ---
# Initialize with None or a default value
get_db_connection = None
load_tree_data = None
load_tree_data_by_tracking_number = None
initialize_database = None
plant_a_tree_section = None
generate_qr_code = None
get_kobo_secrets = None
calculate_co2_sequestered = None
get_ecological_zone = None
unified_user_dashboard_content = None
manage_field_agent_credentials = None
guest_donor_dashboard_ui = None
monitoring_section = None
initialize_firebase = None
firebase_login_ui = None
firebase_signup_ui = None
firebase_password_recovery_ui = None
firebase_admin_approval_ui = None
firebase_logout = None
get_current_firebase_user = None
check_firebase_user_role = None
show_firebase_setup_guide = None
get_all_users = None
approve_user = None
reject_user = None
delete_user = None
send_approval_email = None
send_rejection_email = None
sync_users = None
init_sql_tables = None
field_agent_portal = None
FIREBASE_AUTH_MODULE_AVAILABLE = False

# --- Import custom modules with robust error handling ---
try:
    from db_utils import (
        get_db_connection as db_utils_get_db_connection,
        load_tree_data,
        load_tree_data_by_tracking_number
    )
    get_db_connection = db_utils_get_db_connection
except ImportError as e:
    st.error(f"Database utilities module not found: {e}")
    def dummy_get_db_connection_util(): return None
    def dummy_load_tree_data(): return pd.DataFrame()
    def dummy_load_tree_data_by_tracking_number(tracking_number): return None
    get_db_connection = dummy_get_db_connection_util
    load_tree_data = dummy_load_tree_data
    load_tree_data_by_tracking_number = dummy_load_tree_data_by_tracking_number

try:
    from kobo_integration import (
        initialize_database,
        plant_a_tree_section,
        generate_qr_code,
        get_kobo_secrets
    )
except ImportError as e:
    st.error(f"Kobo Integration module not found: {e}")
    def dummy_initialize_database(): st.warning("⚠️ Database initialization not available.")
    def dummy_plant_a_tree_section(): st.warning("Tree planting section coming soon!")
    def dummy_generate_qr_code(tree_id, treeTrackingNumber=None, tree_name=None, planter=None, date_planted=None): return None, None
    def dummy_get_kobo_secrets(): return None, None, None, None, None
    initialize_database = dummy_initialize_database
    plant_a_tree_section = dummy_plant_a_tree_section
    generate_qr_code = dummy_generate_qr_code
    get_kobo_secrets = dummy_get_kobo_secrets

try:
    from carbonfao import calculate_co2_sequestered, get_ecological_zone
except ImportError as e:
    st.error(f"Carbon FAO module not found: {e}")
    def dummy_calculate_co2_sequestered(dbh_cm, height_m, species, latitude, longitude): return 0.0
    def dummy_get_ecological_zone(latitude, longitude): return "Unknown"
    calculate_co2_sequestered = dummy_calculate_co2_sequestered
    get_ecological_zone = dummy_get_ecological_zone

try:
    from unified_user_dashboard_FINAL import (
        unified_user_dashboard as unified_user_dashboard_content,
        manage_field_agent_credentials
    )
except ImportError as e:
    st.error(f"Unified User Dashboard module not found: {e}")
    def dummy_unified_user_dashboard_content(): st.warning("User dashboard coming soon!")
    def dummy_manage_field_agent_credentials(tracking_number, user_name): st.warning("Field agent credential management coming soon!")
    unified_user_dashboard_content = dummy_unified_user_dashboard_content
    manage_field_agent_credentials = dummy_manage_field_agent_credentials

try:
    from donor_dashboard import guest_donor_dashboard_ui
except ImportError:
    def dummy_guest_donor_dashboard_ui(): st.warning("Donor dashboard coming soon!")
    guest_donor_dashboard_ui = dummy_guest_donor_dashboard_ui

try:
    from kobo_monitoring import monitoring_section
except ImportError as e:
    st.error(f"Kobo Monitoring module not found: {e}")
    def dummy_monitoring_section(): st.warning("Monitoring section coming soon!")
    monitoring_section = dummy_monitoring_section

try:
    from firebase_auth_integration import (
        initialize_firebase,
        firebase_login_ui,
        firebase_signup_ui,
        firebase_password_recovery_ui,
        firebase_admin_approval_ui,
        firebase_logout,
        get_current_firebase_user,
        check_firebase_user_role,
        show_firebase_setup_guide,
        get_all_users,
        approve_user,
        reject_user,
        delete_user,
        send_approval_email,
        send_rejection_email,
        sync_users,
        init_sql_tables,
        get_db_connection as firebase_get_db_connection
    )
    get_db_connection = firebase_get_db_connection
    FIREBASE_AUTH_MODULE_AVAILABLE = True
except ImportError as e:
    FIREBASE_AUTH_MODULE_AVAILABLE = False
    st.error(f"Firebase Auth Integration module not found: {e}")
    def dummy_initialize_firebase(): st.warning("⚠️ Firebase not loaded."); return False
    def dummy_firebase_login_ui(): st.warning("⚠️ Login not available.")
    def dummy_firebase_signup_ui(): st.warning("⚠️ Signup not available.")
    def dummy_firebase_password_recovery_ui(): st.warning("⚠️ Password recovery not available.")
    def dummy_firebase_admin_approval_ui(): st.warning("⚠️ Admin approval tools not available.")
    def dummy_firebase_logout(): st.warning("⚠️ Logout not available.")
    def dummy_get_current_firebase_user(): return None
    def dummy_check_firebase_user_role(user, role): return False
    def dummy_show_firebase_setup_guide(): st.warning("⚠️ Firebase setup guide not available.")
    def dummy_get_all_users(): return []
    def dummy_approve_user(uid): st.warning("⚠️ User approval not available.")
    def dummy_reject_user(uid): st.warning("⚠️ User rejection not available.")
    def dummy_delete_user(uid): st.warning("⚠️ User deletion not available.")
    def dummy_send_approval_email(user): st.warning("⚠️ Approval emails not available.")
    def dummy_send_rejection_email(user): st.warning("⚠️ Rejection emails not available.")
    def dummy_sync_users(): st.warning("⚠️ User synchronization not available.")
    def dummy_init_sql_tables(): st.warning("⚠️ Database table initialization not available.")
    def dummy_firebase_get_db_connection(): return None
    initialize_firebase = dummy_initialize_firebase
    firebase_login_ui = dummy_firebase_login_ui
    firebase_signup_ui = dummy_firebase_signup_ui
    firebase_password_recovery_ui = dummy_firebase_password_recovery_ui
    firebase_admin_approval_ui = dummy_firebase_admin_approval_ui
    firebase_logout = dummy_firebase_logout
    get_current_firebase_user = dummy_get_current_firebase_user
    check_firebase_user_role = dummy_check_firebase_user_role
    show_firebase_setup_guide = dummy_show_firebase_setup_guide
    get_all_users = dummy_get_all_users
    approve_user = dummy_approve_user
    reject_user = dummy_reject_user
    delete_user = dummy_delete_user
    send_approval_email = dummy_send_approval_email
    send_rejection_email = dummy_send_rejection_email
    sync_users = dummy_sync_users
    init_sql_tables = dummy_init_sql_tables
    get_db_connection = dummy_firebase_get_db_connection

try:
    from field_agent import field_agent_portal
except ImportError as e:
    st.error(f"Field Agent module not found: {e}")
    def dummy_field_agent_portal(): st.warning("Field Agent Portal coming soon!")
    field_agent_portal = dummy_field_agent_portal

# --- Initial Application Setup ---
db = initialize_firebase()
if not db:
    st.stop()

init_sql_tables()
initialize_monitoring_db()
sync_users()
print("✅ Firebase users synced into users table.")

# --- Paths and Constants ---
BASE_DIR = Path(__file__).parent if "__file__" in locals() else Path.cwd()
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True, parents=True)
SQLITE_DB = DATA_DIR / "trees.db"
QR_CODE_DIR = DATA_DIR / "qr_codes"
QR_CODE_DIR.mkdir(exist_ok=True, parents=True)

# --- Custom CSS ---
def set_custom_css():
    st.markdown("""
    <style>
      :root {
        --primary: #1D7749;
        --primary-light: #28a745;
        --secondary: #6c757d;
        --light: #f8f9fa;
      }
      .app-header {
        position: fixed;
        top: 0;
        left: 0;
        width: 100%;
        height: 60px;
        background-color: var(--primary);
        display: flex;
        align-items: center;
        justify-content: center;
        z-index: 9999;
        box-shadow: 0 2px 6px rgba(0,0,0,0.2);
      }
      .app-header img {
        height: 40px;
        object-fit: contain;
      }
      .block-container {
        padding-top: 60px !important;
        padding-bottom: 1rem !important;
        max-width: 1200px;
      }
      .landing-header {
        background: linear-gradient(135deg, var(--primary) 0%, var(--primary-light) 100%);
        color: white;
        padding: 2.5rem 1rem;
        border-radius: 0 0 20px 20px;
        text-align: center;
        margin-bottom: 2rem;
      }
      .landing-header h1 {
        font-size: 3rem;
        margin: 0 0 0.25rem;
        font-weight: 800;
        text-shadow: 1px 1px 3px rgba(0,0,0,0.2);
      }
      .landing-header p {
        margin: 0.25rem 0;
        font-size: 1.1rem;
        opacity: 0.9;
      }
      .section-header {
        color: var(--primary);
        margin: 1.5rem 0 1rem;
        font-weight: 700;
        font-size: 1.6rem;
        position: relative;
        padding-bottom: 0.4rem;
      }
      .section-header:after {
        content: '';
        position: absolute;
        bottom: 0;
        left: 0;
        width: 50px;
        height: 3px;
        background: var(--primary);
        border-radius: 3px;
      }
      .metric-card {
        background: white;
        border-radius: 12px;
        padding: 1rem;
        box-shadow: 0 2px 8px rgba(0,0,0,0.05);
        text-align: center;
        margin-bottom: 0.75rem;
        transition: transform 0.3s;
      }
      .metric-card:hover {
        transform: translateY(-4px);
      }
      .metric-label {
        font-size: 0.85rem;
        color: var(--secondary);
        margin-bottom: 0.3rem;
        text-transform: uppercase;
        font-weight: 600;
      }
      .metric-value {
        font-size: 2rem;
        font-weight: 700;
        color: var(--primary);
        margin-bottom: 0.3rem;
      }
      .stButton > button,
      .stButton button {
        background-color: var(--primary) !important;
        color: white !important;
        padding: 0.6em 1.4em !important;
        font-size: 1rem !important;
        font-weight: 600 !important;
        border-radius: 0.4rem !important;
        box-shadow: 0 2px 6px rgba(0,0,0,0.15) !important;
        transition: background-color 0.2s ease, transform 0.1s ease !important;
      }
      .stButton > button:hover,
      .stButton button:hover {
        background-color: #166534 !important;
        transform: translateY(-1px) !important;
      }
      .feature-card, .activity-item {
        background: white;
        border-radius: 12px;
        padding: 1rem;
        box-shadow: 0 2px 6px rgba(0,0,0,0.05);
        margin-bottom: 1rem;
        transition: transform 0.3s, box-shadow 0.3s;
      }
      .feature-card:hover, .activity-item:hover {
        transform: translateY(-3px);
        box-shadow: 0 4px 12px rgba(0,0,0,0.1);
      }
      @media (max-width: 768px) {
        .landing-header {
          padding: 2rem 1rem;
        }
        .landing-header h1 {
          font-size: 2.5rem;
        }
        .metric-card {
          padding: 0.8rem;
        }
      }
    </style>
    """, unsafe_allow_html=True)

# --- Landing Page Metrics ---
def get_landing_metrics():
    """Get current metrics for the landing page"""
    conn = get_db_connection()
    try:
        institutions_count = conn.execute("SELECT COUNT(*) FROM institutions").fetchone()[0]
        trees_df = pd.read_sql_query("SELECT * FROM trees", conn)
        dead_trees = len(trees_df[trees_df["status"] == "Dead"]) if "status" in trees_df.columns else 0
        total_trees = len(trees_df)
        survival_rate = round(((total_trees - dead_trees) / total_trees * 100), 1) if total_trees > 0 else 0

        metrics = {
            "institutions": institutions_count,
            "total_trees": total_trees,
            "alive_trees": total_trees - dead_trees,
            "survival_rate": survival_rate,
            "co2_sequestered": round(trees_df['co2_kg'].sum(), 2) if 'co2_kg' in trees_df.columns else 0,
            "map_data": trees_df[['latitude', 'longitude']].dropna() if not trees_df.empty else pd.DataFrame()
        }
        return metrics
    except Exception as e:
        st.error(f"Error loading metrics: {str(e)}")
        return {
            "institutions": 0,
            "total_trees": 0,
            "alive_trees": 0,
            "survival_rate": 0,
            "co2_sequestered": 0,
            "map_data": pd.DataFrame()
        }
    finally:
        conn.close()

# --- Field Agent Login UI ---
def field_agent_login_ui():
    st.markdown("""
    <style>
        .field-agent-login-container {
            background-color: #f0f2f6;
            padding: 3rem;
            border-radius: 15px;
            box-shadow: 0 8px 20px rgba(0,0,0,0.1);
            max-width: 500px;
            margin: 3rem auto;
            text-align: center;
        }
        .field-agent-login-container h2 {
            color: #1D7749;
            margin-bottom: 1.5rem;
            font-size: 2.2rem;
            font-weight: 700;
        }
        .field-agent-login-container .stTextInput>div>div>input {
            border-radius: 8px;
            border: 1px solid #ced4da;
            padding: 0.75rem 1rem;
            font-size: 1rem;
        }
        .field-agent-login-container .stButton>button {
            background-color: #1D7749;
            color: white;
            border-radius: 8px;
            padding: 0.8rem 2rem;
            font-size: 1.1rem;
            font-weight: 600;
            transition: all 0.3s ease;
            width: 100%;
            margin-top: 1.5rem;
        }
        .field-agent-login-container .stButton>button:hover {
            background-color: #218838;
            transform: translateY(-2px);
            box-shadow: 0 4px 10px rgba(0,0,0,0.15);
        }
        .field-agent-login-container .stAlert {
            border-radius: 8px;
            margin-top: 1rem;
        }
    </style>
    """, unsafe_allow_html=True)

    st.markdown("""
    <div class="field-agent-login-container">
        <h2>🌍 Field Agent Access</h2>
        <p style="color: #6c757d; margin-bottom: 2rem;">Enter your organization's tree tracking number and field password.</p>
    </div>
    """, unsafe_allow_html=True)

    with st.form("field_agent_login_form"):
        entered_tracking_number = st.text_input("Tree Tracking Number", key="fa_tracking_number")
        entered_password = st.text_input("Field Password", type="password", key="fa_password")

        login_button = st.form_submit_button("Login to Field Portal")

        if login_button:
            if not entered_tracking_number or not entered_password:
                st.error("Please enter both tracking number and password.")
                return

            conn = get_db_connection()
            c = conn.cursor()
            try:
                c.execute("SELECT fullName, field_password, token_created_at FROM users WHERE treeTrackingNumber = ?", (entered_tracking_number,))
                user_record = c.fetchone()

                if user_record:
                    fullName, correct_password, token_created_at = user_record
                    current_time = int(datetime.now().timestamp())

                    if entered_password == correct_password:
                        if token_created_at and (current_time - token_created_at > 86400):
                            st.error("⚠ Your field password has expired. Please ask the associated account holder to generate a new one from their dashboard.")
                        else:
                            st.success(f"Access granted for field agent: {fullName}")
                            st.session_state.field_agent_authenticated = True
                            st.session_state.field_agent_tracking_number = entered_tracking_number
                            st.session_state.field_agent_name = fullName
                            st.session_state.page = "FieldAgentPortal"
                            st.rerun()
                    else:
                        st.error("Invalid password.")
                else:
                    st.error("Invalid tracking number or no field password set for this tracking number.")
            except Exception as e:
                st.error(f"An error occurred during login: {e}")
            finally:
                conn.close()

    if st.button("Back to Home", key="fa_back_to_home"):
        st.session_state.page = "Landing"
        st.rerun()

# --- Landing Page ---
# Add this to your imports at the top of the file
import plotly.express as px

# Update the show_landing_page function with the map visualization
def show_landing_page():
    set_custom_css()
    metrics = get_landing_metrics()

    # Logo & Hero
    logo_path = Path(r"D:\CARBONTALLY\carbontallyfinalized\CarbonTally-main\assets\default_logo.png")
    if logo_path.exists():
        st.image(str(logo_path), width=180, use_container_width=False)

    st.markdown("""
      <div class="landing-header">
        <h1>CarbonTally</h1>
        <p>Track, monitor, and contribute to reforestation efforts worldwide</p>
        <p>Join our mission to combat climate change one tree at a time.</p>
      </div>
    """, unsafe_allow_html=True)

    # System Overview Metrics
    total_trees = get_total_trees_planted()
    total_users = get_total_users()
    carbon_sequestered = get_total_carbon_sequestered()
    survival_rate = get_survival_rate()

    st.markdown("""
    <style>
    .metric-card {
      background-color: #f4f6f8;
      padding: 1rem;
      border-left: 5px solid #27ae60;
      border-radius: 10px;
      box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }
    .metric-title { color: #7f8c8d; font-weight: 600; }
    .metric-value { color: #2c3e50; font-size: 1.8rem; font-weight: 700; }
    </style>
    """, unsafe_allow_html=True)

    st.subheader("🌍 System Overview")
    cols = st.columns(4)

    with cols[0]:
        st.markdown("""
        <div class='metric-card'>
            <div class='metric-title'>🌱 Trees Planted</div>
            <div class='metric-value'>{:,}</div>
        </div>
        """.format(total_trees), unsafe_allow_html=True)

    with cols[1]:
        st.markdown("""
        <div class='metric-card'>
            <div class='metric-title'>👥 Participating Entities</div>
            <div class='metric-value'>{:,}</div>
        </div>
        """.format(total_users), unsafe_allow_html=True)

    with cols[2]:
        st.markdown("""
        <div class='metric-card'>
            <div class='metric-title'>💨 CO₂ Sequestered</div>
            <div class='metric-value'>{:,.2f} kg</div>
        </div>
        """.format(carbon_sequestered), unsafe_allow_html=True)

    with cols[3]:
        st.markdown("""
        <div class='metric-card'>
            <div class='metric-title'>🌿 Survival Rate</div>
            <div class='metric-value'>{:,.2f}%</div>
        </div>
        """.format(survival_rate), unsafe_allow_html=True)

    # Tree Planting Locations Map
    st.markdown('<div class="section-header">🌳 Tree Planting Locations</div>', unsafe_allow_html=True)
    
    try:
        # Get tree data with coordinates
        conn = get_db_connection()
        trees_df = pd.read_sql_query("""
            SELECT latitude, longitude, local_name as species, 
                   strftime('%Y-%m-%d', date_planted) as date_planted,
                   planters_name, co2_kg
            FROM trees 
            WHERE latitude IS NOT NULL AND longitude IS NOT NULL
            ORDER BY date_planted DESC
        """, conn)
        
        if not trees_df.empty:
            # Create the map visualization
            fig = px.scatter_mapbox(
                trees_df,
                lat="latitude",
                lon="longitude",
                hover_name="species",
                hover_data={
                    "latitude": False,
                    "longitude": False,
                    "date_planted": True,
                    "planters_name": True,
                    "co2_kg": ":.2f",
                    "species": True
                },
                color_discrete_sequence=["#1D7749"],
                zoom=1,
                height=500
            )
            
            # Customize the map layout
            fig.update_layout(
                mapbox_style="open-street-map",
                margin={"r":0,"t":0,"l":0,"b":0},
                hoverlabel=dict(
                    bgcolor="white",
                    font_size=12,
                    font_family="Arial"
                )
            )
            
            # Show the map in Streamlit
            st.plotly_chart(fig, use_container_width=True)
            
            # Add some statistics below the map
            st.markdown(f"""
            <div style="background-color: #f8f9fa; padding: 1rem; border-radius: 8px; margin-top: -1rem;">
                <p style="margin: 0; font-size: 0.9rem;">
                    <strong>{len(trees_df):,}</strong> trees plotted from <strong>{trees_df['planters_name'].nunique():,}</strong> different planters.
                    Each green dot represents a tree planted.
                </p>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.info("No tree location data available yet. Check back soon!")
            
    except Exception as e:
        st.error(f"Could not load tree location data: {str(e)}")
    finally:
        if 'conn' in locals():
            conn.close()

    # Login / Signup / Field-Agent / Donate buttons
    col1, col2 = st.columns(2, gap="small")
    with col1:
        if st.button("Log In to Your Account", key="landing_login", use_container_width=True):
            st.session_state.page = "Login"
            st.rerun()
        if st.button("Field Agent Portal", key="landing_field_agent", use_container_width=True):
            st.session_state.page = "FieldAgentLogin"
            st.rerun()

    with col2:
        if st.button("Create New Account", key="landing_signup", use_container_width=True):
            st.session_state.page = "Sign Up"
            st.rerun()
        if st.button("Support Our Mission", key="landing_donate", use_container_width=True):
            st.session_state.page = "Donate"
            st.rerun()

    # Recent Activity
    st.markdown('<div class="section-header">🔔 Recent Activity Feed</div>', unsafe_allow_html=True)

    try:
        with sqlite3.connect(SQLITE_DB) as conn:
            df = pd.read_sql_query("""
                SELECT 
                    planters_name, 
                    local_name, 
                    ROUND(co2_kg, 2) as co2_kg,
                    strftime('%Y-%m-%d', date_planted) as formatted_date
                FROM trees 
                WHERE date_planted IS NOT NULL
                ORDER BY date_planted DESC 
                LIMIT 6
            """, conn)

        if not df.empty:
            col1, col2 = st.columns(2)
            for i, row in df.iterrows():
                activity_html = f"""
                <div class="activity-item">
                    <div class="activity-content">
                        <span class="activity-highlight">{row['planters_name']}</span> planted a 
                        <span class="activity-highlight">{row['local_name']}</span> tree
                    </div>
                    <div class="activity-meta">
                        🌱 {row['co2_kg']} kg CO₂ • 📅 {row['formatted_date']}
                    </div>
                </div>
                """
                if i < 3:
                    with col1:
                        st.markdown(activity_html, unsafe_allow_html=True)
                else:
                    with col2:
                        st.markdown(activity_html, unsafe_allow_html=True)
        else:
            st.info("No recent activity found. Be the first to plant a tree!")

    except sqlite3.Error as e:
        st.error(f"Database error: {str(e)}")
    except Exception as e:
        st.error(f"Couldn't load recent activities: {str(e)}")
# --- Main Application ---
def main():
    # Initialize session state variables
    if 'authenticated' not in st.session_state:
        st.session_state.authenticated = False
    if 'page' not in st.session_state:
        st.session_state.page = "Landing"
    if 'field_agent_authenticated' not in st.session_state:
        st.session_state.field_agent_authenticated = False
    if 'field_agent_tracking_number' not in st.session_state:
        st.session_state.field_agent_tracking_number = None
    if 'user' not in st.session_state:
        st.session_state.user = None

    # Initialize Firebase if the module is available
    if FIREBASE_AUTH_MODULE_AVAILABLE:
        if not initialize_firebase():
            st.error("Failed to initialize Firebase. Please check your Firebase configuration.")
            return

    # Check authentication status
    current_user = get_current_firebase_user()
    if current_user and not st.session_state.authenticated:
        st.session_state.authenticated = True
        st.session_state.user = {
            "username": current_user.get("displayName", current_user.get("email", "guest")),
            "email": current_user.get("email"),
            "uid": current_user.get("uid"),
            "treeTrackingNumber": current_user.get("treeTrackingNumber", "")
        }
        # Redirect authenticated users away from landing page
        if st.session_state.page == "Landing":
            st.session_state.page = "User Dashboard"
            st.rerun()

    # Route to the appropriate page
    if st.session_state.page == "Landing":
        show_landing_page()
    elif st.session_state.page == "FieldAgentLogin":
        field_agent_login_ui()
    elif st.session_state.page == "FieldAgentPortal" and st.session_state.field_agent_authenticated:
        field_agent_portal()
    else:
        set_custom_css()

        # Sidebar navigation
        with st.sidebar:
            st.markdown(
                "<h3 style='color: #1D7749; margin-bottom: 1rem;'>🌱 CarbonTally</h3>",
                unsafe_allow_html=True
            )

            if st.session_state.authenticated and current_user:
                st.markdown(f"**Welcome, {current_user.get('displayName', 'User')}!**")

                if check_firebase_user_role(current_user, 'admin'):
                    page_options = ["Admin Dashboard", "User Dashboard", "Plant a Tree", "Monitor Trees", "Donor Dashboard"]
                else:
                    page_options = ["User Dashboard", "Plant a Tree", "Monitor Trees", "Donor Dashboard"]

                try:
                    current_page_index = page_options.index(st.session_state.page)
                except ValueError:
                    current_page_index = 0

                st.session_state.page = st.radio("Navigate to:", page_options, index=current_page_index)

                if st.button("Logout", use_container_width=True):
                    firebase_logout()
                    st.session_state.authenticated = False
                    st.session_state.user = None
                    st.session_state.page = "Landing"
                    st.rerun()
            else:
                # Options for unauthenticated users
                st.session_state.page = st.radio(
                    "Choose an option:",
                    ["Login", "Sign Up", "Password Recovery", "Donor Dashboard"],
                    index=(["Login", "Sign Up", "Password Recovery", "Donor Dashboard"]
                           .index(st.session_state.page)
                           if st.session_state.page in ["Login", "Sign Up", "Password Recovery", "Donor Dashboard"] else 0)
                )

        # Main content area based on selected page
        if st.session_state.page == "Login":
            firebase_login_ui()
        elif st.session_state.page == "Sign Up":
            firebase_signup_ui()
        elif st.session_state.page == "Password Recovery":
            firebase_password_recovery_ui()
        elif st.session_state.page == "Donor Dashboard":
            guest_donor_dashboard_ui()
        elif st.session_state.authenticated:
            if st.session_state.page == "Admin Dashboard":
                admin_dashboard()
            elif st.session_state.page == "User Dashboard":
                unified_user_dashboard_content()
            elif st.session_state.page == "Plant a Tree":
                plant_a_tree_section()
            elif st.session_state.page == "Monitor Trees":
                monitoring_section()
        else:
            st.warning("Please log in to access this page.")
            firebase_login_ui()

    # Footer
    st.markdown("---")
    st.markdown("""
        <div style='text-align: center; font-size: 0.9rem; color: gray;'>
            <strong>CarbonTally</strong> | Making Every Tree Count 🌱<br>
            Developed by <a href="mailto:okothbasil45@gmail.com">Basil Okoth</a> |
            <a href="https://www.linkedin.com/in/kaudobasil/" target="_blank">LinkedIn</a><br>
            © 2025 CarbonTally. All rights reserved.
        </div>
    """, unsafe_allow_html=True)

# --- Entry Point ---
if __name__ == "__main__":
    main()
