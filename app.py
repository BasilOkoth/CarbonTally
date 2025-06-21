import streamlit as st
import pandas as pd
import plotly.express as px
import sqlite3
import datetime
from pathlib import Path

# Third-party imports
import plotly.graph_objects as go
from geopy.geocoders import Nominatim
from geopy.distance import geodesic
import qrcode
from PIL import Image
import base64
import requests
import paypalrestsdk
from paypalrestsdk import Payment

# Custom module imports with error handling
try:
    from branding_footer import add_branding_footer
except ImportError:
    def add_branding_footer(): 
        st.markdown("<p style='text-align:center;font-size:0.8em;color:grey;'>🌱 CarbonTally – Developed by Basil Okoth</p>", 
                   unsafe_allow_html=True)

try:
    from kobo_integration import plant_a_tree_section, check_for_new_submissions
except ImportError:
    def plant_a_tree_section(): st.warning("Tree planting section coming soon!")
    def check_for_new_submissions(user_id, hours): return []

try:
    from kobo_monitoring import monitoring_section, admin_tree_lookup
except ImportError:
    def monitoring_section(): st.warning("Monitoring section coming soon!")
    def admin_tree_lookup(): st.warning("Tree lookup section coming soon!")

try:
    from unified_user_dashboard import unified_user_dashboard_content
except ImportError:
    def unified_user_dashboard_content(): st.warning("User dashboard coming soon!")

try:
    from donor_dashboard import guest_donor_dashboard_ui
except ImportError:
    def guest_donor_dashboard_ui(): st.warning("Donor dashboard coming soon!")

# Firebase and Authentication
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
        show_firebase_setup_guide
    )
    FIREBASE_AUTH_MODULE_AVAILABLE = True
except ImportError as e:
    FIREBASE_AUTH_MODULE_AVAILABLE = False
    st.error(f"Firebase Auth Integration module not found: {e}")

    # Dummy fallback functions
    def initialize_firebase(): st.warning("⚠️ Firebase not loaded."); return False
    def firebase_login_ui(): st.warning("⚠️ Login not available.")
    def firebase_signup_ui(): st.warning("⚠️ Signup not available.")
    def firebase_password_recovery_ui(): st.warning("⚠️ Password recovery not available.")
    def firebase_admin_approval_ui(): st.warning("⚠️ Admin tools not available.")
    def firebase_logout(): st.warning("⚠️ Logout not available.")
    def get_current_firebase_user(): return None
    def check_firebase_user_role(user, role): return False
    def show_firebase_setup_guide(): st.warning("⚠️ Setup guide not available.")

# Set page config - MUST BE FIRST STREAMLIT COMMAND
st.set_page_config(
    page_title="CarbonTally - Tree Monitoring",
    page_icon="🌳",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# --- Custom CSS Styling ---
def set_custom_css():
    st.markdown("""
    <style>
        /* Landing Page Styles */
        .landing-header {
            background: linear-gradient(135deg, #1D7749 0%, #28a745 100%);
            color: white;
            padding: 3rem 1rem;
            border-radius: 0 0 20px 20px;
            box-shadow: 0 4px 20px rgba(0,0,0,0.1);
            text-align: center;
            margin-bottom: 2rem;
        }
        
        .landing-header h1 {
            font-size: 3.5rem;
            margin-bottom: 0.5rem;
            font-weight: 800;
        }
        
        .landing-header p {
            font-size: 1.2rem;
            max-width: 800px;
            margin: 0 auto 1.5rem auto;
        }
        
        .metric-card {
            background: white;
            border-radius: 10px;
            padding: 1.5rem;
            box-shadow: 0 4px 12px rgba(0,0,0,0.1);
            text-align: center;
            border: 1px solid #e0e0e0;
            transition: all 0.3s ease;
            height: 100%;
        }
        
        .metric-card:hover {
            transform: translateY(-5px);
            box-shadow: 0 8px 20px rgba(0,0,0,0.15);
        }
        
        .metric-value {
            font-size: 2.5rem;
            font-weight: 700;
            color: #1D7749;
            margin: 0.5rem 0;
        }
        
        .metric-label {
            font-size: 1rem;
            color: #555;
            margin-bottom: 0.5rem;
        }
        
        .landing-btn {
            display: inline-block;
            background-color: #1D7749 !important;
            color: white !important;
            border: none !important;
            padding: 0.8rem 2rem !important;
            font-size: 1.1rem !important;
            border-radius: 8px !important;
            margin: 0.5rem !important;
            transition: all 0.3s ease !important;
            text-align: center;
            width: 100%;
        }
        
        .landing-btn:hover {
            background-color: #15613b !important;
            transform: translateY(-2px) !important;
            box-shadow: 0 4px 8px rgba(0,0,0,0.2) !important;
        }
        
        .feature-card {
            background: white;
            border-radius: 10px;
            padding: 1.5rem;
            height: 100%;
            box-shadow: 0 4px 12px rgba(0,0,0,0.1);
            border: 1px solid #e0e0e0;
        }
        
        .feature-card h3 {
            color: #1D7749;
            margin-top: 0;
        }
        
        /* App-wide Styles */
        .header-text {
            color: #1D7749;
            font-weight: 700;
            font-size: 2.2rem;
            margin-bottom: 1rem;
        }
        
        @media (max-width: 768px) {
            .landing-header h1 {
                font-size: 2.5rem;
            }
            
            .metric-value {
                font-size: 2rem;
            }
        }
    </style>
    """, unsafe_allow_html=True)

# --- Configuration ---
BASE_DIR = Path(__file__).parent if "__file__ in locals()" else Path.cwd()
DATA_DIR = BASE_DIR / "data"
SQLITE_DB = DATA_DIR / "trees.db"
QR_CODE_DIR = DATA_DIR / "qr_codes"
QR_CODE_DIR.mkdir(exist_ok=True, parents=True)

# --- Database Initialization ---
def init_db():
    DATA_DIR.mkdir(exist_ok=True, parents=True)
    conn = sqlite3.connect(SQLITE_DB)
    c = conn.cursor()
    
    c.execute("""CREATE TABLE IF NOT EXISTS trees (
        tree_id INTEGER PRIMARY KEY AUTOINCREMENT, 
        institution TEXT, local_name TEXT, scientific_name TEXT,
        planter_id TEXT, date_planted TEXT, tree_stage TEXT, rcd_cm REAL, dbh_cm REAL,
        height_m REAL, latitude REAL, longitude REAL, co2_kg REAL, status TEXT
    )""")
    
    c.execute("""CREATE TABLE IF NOT EXISTS species (
        scientific_name TEXT PRIMARY KEY, local_name TEXT, wood_density REAL, benefits TEXT
    )""")
    
    c.execute("""CREATE TABLE IF NOT EXISTS institutions (
        id TEXT PRIMARY KEY, 
        name TEXT, 
        join_date TEXT
    )""")

    if c.execute("SELECT COUNT(*) FROM species").fetchone()[0] == 0:
        default_species = [
            ("Acacia spp.", "Acacia", 0.65, "Drought-resistant, nitrogen-fixing, provides shade"),
            ("Eucalyptus spp.", "Eucalyptus", 0.55, "Fast-growing, timber production, medicinal uses"),
            ("Mangifera indica", "Mango", 0.50, "Fruit production, shade tree, ornamental"),
            ("Azadirachta indica", "Neem", 0.60, "Medicinal properties, insect repellent, drought-resistant")
        ]
        c.executemany("INSERT INTO species VALUES (?, ?, ?, ?)", default_species)

    conn.commit()
    conn.close()

def add_institution_to_db(firebase_uid: str, institution_name: str):
    conn = sqlite3.connect(SQLITE_DB)
    c = conn.cursor()
    try:
        join_date = datetime.date.today().isoformat()
        c.execute("INSERT INTO institutions (id, name, join_date) VALUES (?, ?, ?)",
                  (firebase_uid, institution_name, join_date))
        conn.commit()
    except Exception as e:
        st.error(f"Error adding to database: {e}")
    finally:
        conn.close()

def load_tree_data():
    conn = sqlite3.connect(SQLITE_DB)
    try:        
        df = pd.read_sql_query("SELECT * FROM trees", conn)
    except pd.io.sql.DatabaseError:    
        df = pd.DataFrame()
    conn.close()
    return df

# --- Landing Page ---
def get_landing_metrics():
    metrics = {
        "institutions": 0,
        "total_trees": 0,
        "alive_trees": 0,
        "survival_rate": 0,
        "co2_sequestered": 0,
        "map_data": pd.DataFrame(columns=['latitude', 'longitude'])
    }
    
    try:
        init_db()
        conn = sqlite3.connect(SQLITE_DB)
        institutions_count = conn.execute("SELECT COUNT(*) FROM institutions").fetchone()[0]
        trees_df = pd.read_sql_query("SELECT * FROM trees", conn)
        
        if not trees_df.empty:
            total_trees = len(trees_df)
            alive_trees = len(trees_df[trees_df["status"] == "Alive"]) if "status" in trees_df.columns else 0
            survival_rate = round((alive_trees / total_trees) * 100, 1) if total_trees > 0 else 0
            co2_sequestered = round(trees_df['co2_kg'].sum(), 2) if 'co2_kg' in trees_df.columns else 0
            map_df = trees_df[['latitude', 'longitude']].dropna()
            
            metrics.update({
                "institutions": institutions_count,
                "total_trees": total_trees,
                "alive_trees": alive_trees,
                "survival_rate": survival_rate,
                "co2_sequestered": co2_sequestered,
                "map_data": map_df
            })
    except Exception as e:
        st.error(f"Error loading metrics: {str(e)}")
    finally:
        if 'conn' in locals():
            conn.close()
    
    return metrics

def show_landing_page():
    set_custom_css()
    metrics = get_landing_metrics()
    
    st.markdown("""
    <div class="landing-header">
        <h1>🌱 CarbonTally</h1>
        <p style="font-size: 1.3rem;">Track, monitor, and contribute to reforestation efforts worldwide</p>
        <p>Join our mission to combat climate change one tree at a time.</p>
    </div>
    """, unsafe_allow_html=True)
    
    st.markdown("## Our Impact at a Glance")
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">Participating Entities</div>
            <div class="metric-value">{metrics['institutions']}</div>
            <div>Individuals & Organizations</div>
        </div>
        """, unsafe_allow_html=True)
    
    with col2:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">Trees Planted</div>
            <div class="metric-value">{metrics['total_trees']:,}</div>
            <div>And counting...</div>
        </div>
        """, unsafe_allow_html=True)
    
    with col3:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">Survival Rate</div>
            <div class="metric-value">{metrics['survival_rate']}%</div>
            <div>Thriving trees</div>
        </div>
        """, unsafe_allow_html=True)
    
    with col4:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">CO₂ Sequestered</div>
            <div class="metric-value">{metrics['co2_sequestered']:,}</div>
            <div>kg carbon removed</div>
        </div>
        """, unsafe_allow_html=True)
    
    st.markdown("## 🌍 Our Global Impact")
    if not metrics['map_data'].empty:
        fig = px.scatter_mapbox(
            metrics['map_data'],
            lat='latitude',
            lon='longitude',
            zoom=1,
            height=500,
            color_discrete_sequence=["#1D7749"]
        )
        fig.update_layout(
            mapbox_style="open-street-map",
            margin={"r":0,"t":0,"l":0,"b":0}
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No tree location data available yet.")
    
    st.markdown("""
    <div style="text-align: center; margin: 3rem 0;">
        <h2>Ready to make a difference?</h2>
        <p style="font-size: 1.1rem; margin-bottom: 2rem;">Join our community or support our mission today</p>
    </div>
    """, unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        if st.button("🌱 Login", key="landing_login", use_container_width=True):
            st.session_state.page = "Login"
            st.rerun()
    
    with col2:
        if st.button("📝 Sign Up", key="landing_signup", use_container_width=True):
            st.session_state.page = "Sign Up"
            st.rerun()
    
    with col3:
        if st.button("💚 Donate Now", key="landing_donate", use_container_width=True):
            st.session_state.page = "Donor Dashboard"
            st.rerun()
    
    st.markdown("## ✨ Why Choose CarbonTally?")
    
    feature_cols = st.columns(3)
    
    with feature_cols[0]:
        st.markdown("""
        <div class="feature-card">
            <h3>🌳 Real-time Monitoring</h3>
            <p>Track the growth and health of every tree planted through our comprehensive monitoring system.</p>
        </div>
        """, unsafe_allow_html=True)
    
    with feature_cols[1]:
        st.markdown("""
        <div class="feature-card">
            <h3>📊 Data-Driven Insights</h3>
            <p>Access detailed analytics on carbon sequestration, survival rates, and environmental impact.</p>
        </div>
        """, unsafe_allow_html=True)
    
    with feature_cols[2]:
        st.markdown("""
        <div class="feature-card">
            <h3>🤝 Community Impact</h3>
            <p>Join a network of individuals and organizations committed to sustainable reforestation.</p>
        </div>
        """, unsafe_allow_html=True)

# --- Main Application ---
def main():
    if 'authenticated' not in st.session_state:
        st.session_state.authenticated = False
    if 'page' not in st.session_state:
        st.session_state.page = "Landing"

    if st.session_state.page == "Landing":
        show_landing_page()
    else:
        set_custom_css()
        init_db()
        
        if FIREBASE_AUTH_MODULE_AVAILABLE:
            if not initialize_firebase():
                st.error("Failed to initialize Firebase")
                return

        with st.sidebar:
            st.markdown("<h3 style='color: #1D7749; margin-bottom: 1rem;'>🌱 CarbonTally</h3>", unsafe_allow_html=True)
            
            if st.session_state.authenticated:
                user = get_current_firebase_user()
                if user:
                    st.markdown(f"**Welcome, {user.get('displayName', 'User')}!**")
                    
                    if check_firebase_user_role(user, 'admin'):
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
                        st.session_state.page = "Login"
                        st.rerun()
            else:
                st.session_state.page = st.radio("Choose an option:", 
                    ["Login", "Sign Up", "Password Recovery", "Donor Dashboard"],
                    index=["Login", "Sign Up", "Password Recovery", "Donor Dashboard"].index(st.session_state.page) 
                    if st.session_state.page in ["Login", "Sign Up", "Password Recovery", "Donor Dashboard"] else 0)

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
                st.markdown("<h1 class='header-text'>👑 Admin Dashboard</h1>", unsafe_allow_html=True)
                admin_tree_lookup()
            elif st.session_state.page == "User Dashboard":
                unified_user_dashboard_content()
            elif st.session_state.page == "Plant a Tree":
                plant_a_tree_section()
            elif st.session_state.page == "Monitor Trees":
                monitoring_section()
        else:
            st.warning("Please log in to access this page.")
            firebase_login_ui()

        add_branding_footer()

if __name__ == "__main__":
    main()
