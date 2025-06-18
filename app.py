import streamlit as st
import pandas as pd
import plotly.express as px
import sqlite3
import datetime
import re
import random
import os
import time
import json
from pathlib import Path
from io import BytesIO
from typing import Optional, Tuple, Dict, Any

# Third-party imports
import plotly.graph_objects as go
from geopy.geocoders import Nominatim
from geopy.distance import geodesic
import qrcode
from PIL import Image
import base64
import requests # For KoBo API calls
import paypalrestsdk # For PayPal integration
from paypalrestsdk import Payment

# Custom module imports (assuming these files exist in the same directory)
# Placeholder functions if modules are not found
try:
    from branding_footer import add_branding_footer
except ImportError:
    def add_branding_footer(): st.markdown("<p style='text-align:center;font-size:0.8em;color:grey;'>🌱 CarbonTally – Developed by Basil Okoth</p>", unsafe_allow_html=True)

try:
    from kobo_integration import plant_a_tree_section, check_for_new_submissions
except ImportError:
    def plant_a_tree_section(): st.error("Kobo Integration module (plant_a_tree_section) not found.")
    def check_for_new_submissions(user_id, hours): st.error("Kobo Integration module (check_for_new_submissions) not found."); return []

try:
    from kobo_monitoring import monitoring_section, admin_tree_lookup
except ImportError:
    def monitoring_section(): st.error("Kobo Monitoring module (monitoring_section) not found.")
    def admin_tree_lookup(): st.error("Kobo Monitoring module (admin_tree_lookup) not found.")

# Import unified user dashboard
try:
    from unified_user_dashboard import unified_user_dashboard_content
except ImportError:
    def unified_user_dashboard_content(): st.error("Unified User Dashboard module not found.")

# Import donor dashboard
try:
    from donor_dashboard import guest_donor_dashboard_ui
except ImportError:
    def guest_donor_dashboard_ui(): st.error("Donor Dashboard module not found.")

# Firebase and Authentication module imports
try:
    from firebase_admin.exceptions import FirebaseError  # For general Firebase exceptions
    from firebase_admin import credentials, auth, firestore, get_app  # Firebase core modules

    # Custom Firebase authentication integration
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
    st.error(f"Firebase Auth Integration module not found or missing functions: {e}. Please ensure firebase_auth_integration.py is correctly set up.")

    # Define dummy fallback functions to prevent app crash
    def initialize_firebase(): st.warning("⚠️ Firebase: initialize_firebase() not loaded."); return False
    def firebase_login_ui(): st.warning("⚠️ Firebase: firebase_login_ui() not loaded.")
    def firebase_signup_ui(): st.warning("⚠️ Firebase: firebase_signup_ui() not loaded.")
    def firebase_password_recovery_ui(): st.warning("⚠️ Firebase: firebase_password_recovery_ui() not loaded.")
    def firebase_admin_approval_ui(): st.warning("⚠️ Firebase: firebase_admin_approval_ui() not loaded.")
    def firebase_logout(): st.warning("⚠️ Firebase: firebase_logout() not loaded.")
    def get_current_firebase_user(): st.warning("⚠️ Firebase: get_current_firebase_user() not loaded."); return None
    def check_firebase_user_role(user, role): st.warning("⚠️ Firebase: check_firebase_user_role() not loaded."); return False
    def show_firebase_setup_guide(): st.warning("⚠️ Firebase: show_firebase_setup_guide() not loaded.")

# Set page config - MUST BE THE FIRST STREAMLIT COMMAND
st.set_page_config(
    page_title="CarbonTally - Tree Monitoring",
    page_icon="🌳",
    layout="wide",
    initial_sidebar_state="collapsed"  # Collapsed sidebar initially for landing page
)

# --- Custom CSS for Landing Page ---
def load_landing_css():
    st.markdown("""
    <style>
        /* Landing Page Specific Styles */
        .landing-header {
            background: linear-gradient(135deg, #1D7749 0%, #28a745 100%);
            color: white;
            padding: 3rem 1rem;
            margin: -1rem -1rem 2rem -1rem;
            border-radius: 0 0 20px 20px;
            box-shadow: 0 4px 20px rgba(0,0,0,0.1);
            text-align: center;
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
        
        .landing-metric {
            background-color: white;
            border-radius: 12px;
            padding: 1.5rem;
            box-shadow: 0 4px 12px rgba(0,0,0,0.05);
            text-align: center;
            transition: all 0.3s ease;
            border: 1px solid #e0e0e0;
            height: 100%;
        }
        
        .landing-metric:hover {
            transform: translateY(-5px);
            box-shadow: 0 8px 20px rgba(0,0,0,0.1);
        }
        
        .landing-metric-value {
            font-size: 2.8rem;
            font-weight: 700;
            color: #1D7749;
            margin: 0.5rem 0;
            line-height: 1;
        }
        
        .landing-metric-label {
            font-size: 1rem;
            color: #555;
            margin-bottom: 0.5rem;
        }
        
        .landing-cta {
            background-color: #f8f9fa;
            padding: 2rem;
            border-radius: 12px;
            margin: 2rem 0;
            text-align: center;
        }
        
        .landing-map-container {
            border-radius: 12px;
            overflow: hidden;
            box-shadow: 0 4px 12px rgba(0,0,0,0.1);
            margin: 2rem 0;
            border: 1px solid #e0e0e0;
        }
        
        .landing-btn {
            background-color: #1D7749 !important;
            color: white !important;
            border: none !important;
            padding: 0.8rem 2rem !important;
            font-size: 1.1rem !important;
            border-radius: 8px !important;
            margin: 0.5rem !important;
            transition: all 0.3s ease !important;
        }
        
        .landing-btn:hover {
            background-color: #15613b !important;
            transform: translateY(-2px) !important;
        }
        
        .landing-btn-secondary {
            background-color: white !important;
            color: #1D7749 !important;
            border: 2px solid #1D7749 !important;
        }
        
        .landing-btn-secondary:hover {
            background-color: #f0f0f0 !important;
        }
        
        .landing-features {
            display: flex;
            flex-wrap: wrap;
            gap: 1.5rem;
            margin: 2rem 0;
        }
        
        .landing-feature {
            flex: 1;
            min-width: 250px;
            background-color: white;
            border-radius: 12px;
            padding: 1.5rem;
            box-shadow: 0 4px 12px rgba(0,0,0,0.05);
            border: 1px solid #e0e0e0;
        }
        
        .landing-feature h3 {
            color: #1D7749;
            margin-top: 0;
        }
        
        @media (max-width: 768px) {
            .landing-header h1 {
                font-size: 2.5rem;
            }
            
            .landing-metric-value {
                font-size: 2rem;
            }
        }
    </style>
    """, unsafe_allow_html=True)

# --- Custom CSS for Main App Styling ---
def load_app_css():
    st.markdown("""
    <style>
        /* Global Resets & Base Styles */
        html, body {
            margin: 0;
            padding: 0;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif, "Apple Color Emoji", "Segoe UI Emoji";
            background-color: #f0f2f5; /* Lighter, cleaner background */
            color: #333;
            line-height: 1.6;
        }

        /* Main App Container - More Compact */
        .main .block-container {
            padding-top: 1.5rem; /* Reduced top padding */
            padding-bottom: 1.5rem;
            padding-left: 1rem;
            padding-right: 1rem;
            max-width: 1200px; /* Constrain width for better readability on large screens */
            margin: 0 auto;
        }

        /* Header Styling - Modern & Clean */
        .header-text {
            color: #1D7749; /* Deeper, more sophisticated green */
            font-weight: 700;
            font-size: 2.2rem; /* Slightly reduced for compactness */
            margin-bottom: 1rem; /* Consistent spacing */
            text-align: left;
        }

        /* Sidebar Styling - Clean & Functional */
        .sidebar .sidebar-content {
            background-color: #ffffff; /* White sidebar for cleaner look */
            border-right: 1px solid #e0e0e0;
            padding: 1rem;
        }
        .sidebar .sidebar-content h3 {
            color: #1D7749;
            font-size: 1.1rem;
            margin-top: 0;
        }
        .sidebar .sidebar-content p {
            font-size: 0.9rem;
            color: #555;
        }
        .sidebar .stRadio > label {
            font-weight: 600;
            font-size: 1rem;
            color: #333;
        }
        .sidebar .stRadio div[role="radiogroup"] > div {
            margin-bottom: 0.5rem;
        }

        /* Button Styling - Modern & Action-Oriented */
        .stButton>button {
            background-color: #28a745; /* Vibrant green */
            color: white;
            border-radius: 6px; /* Slightly less rounded */
            padding: 0.6rem 1.2rem; /* Adjusted padding */
            border: none;
            font-weight: 600;
            transition: all 0.2s ease-in-out;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        .stButton>button:hover {
            background-color: #218838; /* Darker on hover */
            transform: translateY(-1px);
            box-shadow: 0 4px 8px rgba(0,0,0,0.15);
        }
        .stButton>button:active {
            transform: translateY(0px);
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }

        /* Card Styling - Elevated & Informative */
        .card {
            background-color: white;
            border-radius: 8px; /* Consistent rounding */
            padding: 1.2rem; /* Adjusted padding */
            box-shadow: 0 3px 6px rgba(0,0,0,0.08); /* Softer shadow */
            margin-bottom: 1.2rem;
            border: 1px solid #e0e0e0;
        }
        .card h3 {
            color: #1D7749;
            margin-top: 0;
            margin-bottom: 0.5rem;
            font-size: 1.3rem;
        }
        .card p {
            font-size: 0.95rem;
            color: #444;
            margin-bottom: 0.8rem;
        }

        /* Metric Card Styling - Impactful & Clear */
        .metric-card {
            background-color: #ffffff;
            border-radius: 8px;
            padding: 1rem;
            box-shadow: 0 3px 6px rgba(0,0,0,0.07);
            margin-bottom: 1rem;
            text-align: center;
            border: 1px solid #e8e8e8;
            transition: transform 0.2s ease, box-shadow 0.2s ease;
        }
        .metric-card:hover {
            transform: translateY(-3px);
            box-shadow: 0 5px 10px rgba(0,0,0,0.1);
        }
        .metric-value {
            font-size: 2rem; /* Slightly reduced for compactness */
            font-weight: 700;
            color: #1D7749;
            margin: 0.3rem 0;
        }
        .metric-label {
            font-size: 0.85rem; /* Slightly reduced */
            color: #555;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }

        /* Form Elements - Clean & User-Friendly */
        .stTextInput input, .stDateInput input, .stNumberInput input, .stSelectbox div[data-baseweb="select"] > div {
            border-radius: 6px !important;
            border: 1px solid #ccc !important;
        }
        .stTextArea textarea {
            border-radius: 6px !important;
            border: 1px solid #ccc !important;
            padding: 0.75rem !important;
        }
        .stForm {
            border: 1px solid #e0e0e0;
            border-radius: 8px;
            padding: 1.5rem;
            background-color: #f9f9f9;
        }

        /* Tabs Styling - Modern & Integrated */
        .stTabs [data-baseweb="tab-list"] {
            gap: 8px; /* Reduced gap */
            border-bottom: 2px solid #e0e0e0;
        }
        .stTabs [data-baseweb="tab"] {
            background-color: transparent; /* Cleaner look */
            border-radius: 6px 6px 0 0 !important;
            padding: 0.7rem 1.2rem; /* Adjusted padding */
            color: #555;
            font-weight: 600;
            border: none !important; /* Remove default borders */
            border-bottom: 2px solid transparent !important;
            transition: all 0.2s ease-in-out;
        }
        .stTabs [aria-selected="true"] {
            background-color: transparent !important;
            color: #1D7749 !important;
            border-bottom: 2px solid #1D7749 !important;
        }

        /* Footer Styling - Unobtrusive */
        .footer {
            margin-top: 2rem; /* Reduced margin */
            padding: 1rem 0;
            border-top: 1px solid #e0e0e0;
            text-align: center;
            font-size: 0.85rem;
            color: #777;
        }

        /* Responsive Adjustments */
        @media (max-width: 768px) {
            .main .block-container {
                padding-top: 1rem;
                padding-left: 0.5rem;
                padding-right: 0.5rem;
            }
            .header-text {
                font-size: 1.8rem;
            }
            .metric-card {
                padding: 0.8rem;
                margin-bottom: 0.8rem;
            }
            .metric-value {
                font-size: 1.6rem;
            }
            .metric-label {
                font-size: 0.75rem;
            }
            .stButton>button {
                padding: 0.5rem 1rem;
                width: 100%; /* Full width buttons on mobile */
            }
            .stTabs [data-baseweb="tab"] {
                padding: 0.6rem 1rem;
            }
            .card {
                padding: 1rem;
            }
            .stForm {
                padding: 1rem;
            }
        }
    </style>
    """, unsafe_allow_html=True)


# --- Configuration ---
BASE_DIR = Path(__file__).parent if "__file__" in locals() else Path.cwd()
DATA_DIR = BASE_DIR / "data"
SQLITE_DB = DATA_DIR / "trees.db" # SQLite DB will still be used for app data, not users
QR_CODE_DIR = DATA_DIR / "qr_codes"
QR_CODE_DIR.mkdir(exist_ok=True, parents=True)

# PayPal and KoBo configurations
PAYPAL_MODE = st.secrets.get("PAYPAL_MODE", "sandbox")
PAYPAL_CLIENT_ID = st.secrets.get("PAYPAL_CLIENT_ID", "YOUR_SANDBOX_CLIENT_ID")
PAYPAL_CLIENT_SECRET = st.secrets.get("PAYPAL_CLIENT_SECRET", "YOUR_SANDBOX_CLIENT_SECRET")
KOBO_API_TOKEN = st.secrets.get("KOBO_API_TOKEN", "your_kobo_api_token")
KOBO_ASSET_ID = st.secrets.get("KOBO_ASSET_ID", "your_planting_asset_id")
KOBO_MONITORING_ASSET_ID = st.secrets.get("KOBO_MONITORING_ASSET_ID", "your_monitoring_asset_id")

# --- User Roles ---
USER_ROLES = {
    "individual": "Individual User",
    "institution": "Institution User",
    "donor": "Donor",
    "admin": "Administrator"
}

# --- Database Initialization (SQL parts for app data only) ---
def init_db():
    DATA_DIR.mkdir(exist_ok=True, parents=True)
    conn = sqlite3.connect(SQLITE_DB)
    c = conn.cursor()
    
    # Create tables for app data (not users)
    # Modified 'trees' table to use INTEGER PRIMARY KEY AUTOINCREMENT
    c.execute("""CREATE TABLE IF NOT EXISTS trees (
        tree_id INTEGER PRIMARY KEY AUTOINCREMENT, 
        institution TEXT, local_name TEXT, scientific_name TEXT,
        planter_id TEXT, date_planted TEXT, tree_stage TEXT, rcd_cm REAL, dbh_cm REAL,
        height_m REAL, latitude REAL, longitude REAL, co2_kg REAL, status TEXT, country TEXT,
        county TEXT, sub_county TEXT, ward TEXT, adopter_name TEXT, last_monitored TEXT,
        monitor_notes TEXT, qr_code TEXT, kobo_submission_id TEXT UNIQUE,
        tree_tracking_number TEXT
    )""")
    
    c.execute("""CREATE TABLE IF NOT EXISTS species (
        scientific_name TEXT PRIMARY KEY, local_name TEXT, wood_density REAL, benefits TEXT
    )""")
    
    c.execute("""CREATE TABLE IF NOT EXISTS monitoring_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT, tree_id TEXT, monitor_date TEXT, monitor_status TEXT,
        monitor_stage TEXT, rcd_cm REAL, dbh_cm REAL, height_m REAL, co2_kg REAL, notes TEXT,
        monitor_by TEXT, kobo_submission_id TEXT UNIQUE, FOREIGN KEY (tree_id) REFERENCES trees (tree_id)
    )""")
    
    c.execute("""CREATE TABLE IF NOT EXISTS donations (
        donation_id TEXT PRIMARY KEY, donor_email TEXT, donor_name TEXT, institution_id TEXT,
        num_trees INTEGER, amount REAL, currency TEXT, donation_date TEXT, payment_id TEXT,
        payment_status TEXT, message TEXT
    )""")
    
    c.execute("""CREATE TABLE IF NOT EXISTS donated_trees (
        id INTEGER PRIMARY KEY AUTOINCREMENT, donation_id TEXT, tree_id TEXT,
        FOREIGN KEY (donation_id) REFERENCES donations (donation_id),
        FOREIGN KEY (tree_id) REFERENCES trees (tree_id)
    )""")
            
    c.execute("""CREATE TABLE IF NOT EXISTS processed_monitoring_submissions (
        submission_id TEXT PRIMARY KEY, tree_id TEXT, processed_date TEXT,
        FOREIGN KEY (tree_id) REFERENCES trees (tree_id)
    )""")

    # Create institutions table
    c.execute("""CREATE TABLE IF NOT EXISTS institutions (
        id TEXT PRIMARY KEY, 
        name TEXT, 
        join_date TEXT
    )""")

    # Initialize species data if table is empty
    if c.execute("SELECT COUNT(*) FROM species").fetchone()[0] == 0:
        default_species = [
            ("Acacia spp.", "Acacia", 0.65, "Drought-resistant, nitrogen-fixing, provides shade"),
            ("Eucalyptus spp.", "Eucalyptus", 0.55, "Fast-growing, timber production, medicinal uses"),
            ("Mangifera indica", "Mango", 0.50, "Fruit production, shade tree, ornamental"),
            ("Azadirachta indica", "Neem", 0.60, "Medicinal properties, insect repellent, drought-resistant"),
            ("Quercus spp.", "Oak", 0.75, "Long-term carbon storage, wildlife habitat, durable wood"),
            ("Pinus spp.", "Pine", 0.45, "Reforestation, timber production, resin production")
        ]
        c.executemany("INSERT INTO species VALUES (?, ?, ?, ?)", default_species)

    conn.commit()
    conn.close()

# --- Helper function to add institution to DB ---
def add_institution_to_db(firebase_uid: str, institution_name: str):
    """Adds a new institution record to the SQLite database.
    This function should be called from your firebase_auth_integration.py
    upon successful signup of an 'individual' OR 'institution' user.
    """
    conn = sqlite3.connect(SQLITE_DB)
    c = conn.cursor()
    try:
        join_date = datetime.date.today().isoformat()
        c.execute("INSERT INTO institutions (id, name, join_date) VALUES (?, ?, ?)",
                  (firebase_uid, institution_name, join_date))
        conn.commit()
        st.success(f"Participant '{institution_name}' successfully registered.")
    except sqlite3.IntegrityError:
        st.warning(f"Participant with ID {firebase_uid} already exists.")
    except Exception as e:
        st.error(f"Error adding participant to database: {e}")
    finally:
        if conn: # Ensure conn is defined before closing
            conn.close()


# --- Data Loading (for app data) ---
def load_tree_data():
    conn = sqlite3.connect(SQLITE_DB)
    try:        
        df = pd.read_sql_query("SELECT * FROM trees", conn)
    except pd.io.sql.DatabaseError:    
        df = pd.DataFrame()
    conn.close()
    return df

# --- Admin Dashboard Content ---
def admin_dashboard_content():    
    st.markdown("<h1 class='header-text'>👑 Admin Dashboard</h1>", unsafe_allow_html=True)
    
    # Admin metrics
    trees = load_tree_data()
    
    st.markdown("<h4 style='color: #1D7749; margin-bottom: 0.5rem;'>System Overview</h4>", unsafe_allow_html=True)
    admin_metric_cols = st.columns(4)
    
    # Calculate metrics
    total_trees = len(trees)
    alive_trees = len(trees[trees["status"] == "Alive"]) if "status" in trees.columns and not trees.empty else 0
    survival_rate = f"{round((alive_trees / total_trees) * 100, 1)}%" if total_trees > 0 else "0%"
    co2_sequestered = f"{round(trees['co2_kg'].sum(), 2)} kg" if "co2_kg" in trees.columns and not trees.empty else "0 kg"
    
    with admin_metric_cols[0]:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-value">{total_trees}</div>
            <div class="metric-label">Total Trees</div>
        </div>
        """, unsafe_allow_html=True)
    
    with admin_metric_cols[1]:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-value">{alive_trees}</div>
            <div class="metric-label">Alive Trees</div>
        </div>
        """, unsafe_allow_html=True)
    
    with admin_metric_cols[2]:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-value">{survival_rate}</div>
            <div class="metric-label">Survival Rate</div>
        </div>
        """, unsafe_allow_html=True)
    
    with admin_metric_cols[3]:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-value">{co2_sequestered}</div>
            <div class="metric-label">CO₂ Sequestered</div>
        </div>
        """, unsafe_allow_html=True)

    # Admin tabs
    admin_tabs = st.tabs(["🌳 Tree Management", "👥 User Management", "📊 Analytics", "🔍 Tree Lookup"])
    
    with admin_tabs[0]:
        st.markdown("<h4 style='color: #1D7749;'>Tree Management</h4>", unsafe_allow_html=True)
        
        if not trees.empty:
            # Tree status distribution
            status_counts = trees['status'].value_counts() if 'status' in trees.columns else pd.Series()
            if not status_counts.empty:
                fig = px.pie(values=status_counts.values, names=status_counts.index,    
                             title="Tree Status Distribution")
                st.plotly_chart(fig, use_container_width=True)
            
            # Recent trees
            st.markdown("<h5 style='color: #1D7749;'>Recent Trees</h5>", unsafe_allow_html=True)
            recent_trees = trees.head(10)
            st.dataframe(recent_trees, use_container_width=True)
        else:
            st.info("No tree data available.")
    
    with admin_tabs[1]:
        st.markdown("<h4 style='color: #1D7749;'>User Management</h4>", unsafe_allow_html=True)
        firebase_admin_approval_ui()
    
    with admin_tabs[2]:
        st.markdown("<h4 style='color: #1D7749;'>Analytics</h4>", unsafe_allow_html=True)
        
        if not trees.empty:
            # Trees planted over time
            if 'date_planted' in trees.columns:
                trees['date_planted'] = pd.to_datetime(trees['date_planted'], errors='coerce')
                trees_by_date = trees.groupby(trees['date_planted'].dt.date).size().reset_index()
                trees_by_date.columns = ['Date', 'Trees Planted']
                
                fig = px.line(trees_by_date, x='Date', y='Trees Planted',    
                              title="Trees Planted Over Time")
                st.plotly_chart(fig, use_container_width=True)
            
            # Species distribution
            if 'scientific_name' in trees.columns:
                species_counts = trees['scientific_name'].value_counts().head(10)
                fig = px.bar(x=species_counts.values, y=species_counts.index,    
                             orientation='h', title="Top 10 Tree Species")
                st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No data available for analytics.")
    
    with admin_tabs[3]:
        st.markdown("<h4 style='color: #1D7749;'>Tree Lookup</h4>", unsafe_allow_html=True)
        admin_tree_lookup()

# --- Landing Page ---
def get_landing_metrics():
    # Ensure database is initialized before trying to connect
    init_db() 
    conn = sqlite3.connect(SQLITE_DB)
    
    # Get number of institutions
    # This now counts both "Individual" and "Institution" users added via add_institution_to_db
    institutions_count = conn.execute("SELECT COUNT(*) FROM institutions").fetchone()[0]
    
    # Get tree metrics
    trees_df = pd.read_sql_query("SELECT * FROM trees", conn)
    
    if not trees_df.empty:
        total_trees = len(trees_df)
        alive_trees = len(trees_df[trees_df["status"] == "Alive"]) if "status" in trees_df.columns else 0
        survival_rate = round((alive_trees / total_trees) * 100, 1) if total_trees > 0 else 0
        co2_sequestered = round(trees_df['co2_kg'].sum(), 2) if 'co2_kg' in trees_df.columns else 0
        
        # Get tree locations for map
        map_df = trees_df[['latitude', 'longitude']].dropna()
    else:
        total_trees = 0
        alive_trees = 0
        survival_rate = 0
        co2_sequestered = 0
        map_df = pd.DataFrame(columns=['latitude', 'longitude'])
    
    conn.close()
    
    return {
        "institutions": institutions_count,
        "total_trees": total_trees,
        "alive_trees": alive_trees,
        "survival_rate": survival_rate,
        "co2_sequestered": co2_sequestered,
        "map_data": map_df
    }

def show_landing_page():
    # Load custom CSS
    load_landing_css()
    
    # Get metrics
    metrics = get_landing_metrics()
    
    # Header Section
    st.markdown("""
    <div class="landing-header">
        <h1>🌱 CarbonTally</h1>
        <p>Track, monitor, and contribute to reforestation efforts worldwide. Join our mission to combat climate change one tree at a time.</p>
    </div>
    """, unsafe_allow_html=True)
    
    # Key Metrics
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        # Changed label to reflect that it includes both individuals and organizations
        st.markdown(f"""
        <div class="landing-metric">
            <div class="landing-metric-label">Participating Entities</div>
            <div class="landing-metric-value">{metrics['institutions']}</div>
            <div>Individuals & Organizations</div>
        </div>
        """, unsafe_allow_html=True)
    
    with col2:
        st.markdown(f"""
        <div class="landing-metric">
            <div class="landing-metric-label">Trees Planted</div>
            <div class="landing-metric-value">{metrics['total_trees']:,}</div>
            <div>And counting...</div>
        </div>
        """, unsafe_allow_html=True)
    
    with col3:
        st.markdown(f"""
        <div class="landing-metric">
            <div class="landing-metric-label">Survival Rate</div>
            <div class="landing-metric-value">{metrics['survival_rate']}%</div>
            <div>Thriving trees</div>
        </div>
        """, unsafe_allow_html=True)
    
    with col4:
        st.markdown(f"""
        <div class="landing-metric">
            <div class="landing-metric-label">CO₂ Sequestered</div>
            <div class="landing-metric-value">{metrics['co2_sequestered']:,} kg</div>
            <div>Carbon removed</div>
        </div>
        """, unsafe_allow_html=True)
    
    # Map Visualization
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
    
    # Call to Action
    st.markdown("""
    <div class="landing-cta">
        <h2>Ready to make a difference?</h2>
        <p>Join our community of environmental stewards or support our mission through donations.</p>
    </div>
    """, unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1,1,1])
    
    with col1:
        if st.button("🌱 Login", key="landing_login", use_container_width=True, 
                    help="Access your CarbonTally account"):
            st.session_state.page = "Login"
            st.rerun()
    
    with col2:
        if st.button("📝 Sign Up", key="landing_signup", use_container_width=True, 
                    help="Create a new CarbonTally account"):
            st.session_state.page = "Sign Up"
            st.rerun()
    
    with col3:
        if st.button("💚 Donate Now", key="landing_donate", use_container_width=True, 
                    help="Support our reforestation efforts"):
            st.session_state.page = "Donor Dashboard"
            st.rerun()
    
    # Features Section
    st.markdown("## ✨ Why CarbonTally?")
    
    feature_cols = st.columns(3)
    
    with feature_cols[0]:
        st.markdown("""
        <div class="landing-feature">
            <h3>🌳 Real-time Monitoring</h3>
            <p>Track the growth and health of every tree planted through our comprehensive monitoring system.</p>
        </div>
        """, unsafe_allow_html=True)
    
    with feature_cols[1]:
        st.markdown("""
        <div class="landing-feature">
            <h3>📊 Data-Driven Insights</h3>
            <p>Access detailed analytics on carbon sequestration, survival rates, and environmental impact.</p>
        </div>
        """, unsafe_allow_html=True)
    
    with feature_cols[2]:
        st.markdown("""
        <div class="landing-feature">
            <h3>🤝 Community Impact</h3>
            <p>Join a network of individuals and organizations committed to sustainable reforestation.</p>
        </div>
        """, unsafe_allow_html=True)

# --- Main Application ---
def main():
    # Initialize session state for page and authentication
    if 'authenticated' not in st.session_state:
        st.session_state.authenticated = False
    if 'page' not in st.session_state:
        st.session_state.page = "Landing" # Start on landing page

    # Handle page routing
    if st.session_state.page == "Landing":
        show_landing_page()
    else:
        # If not on landing page, load app specific CSS and initialize Firebase
        load_app_css()
        init_db() # Initialize general app database
        
        if FIREBASE_AUTH_MODULE_AVAILABLE:
            db = initialize_firebase()
            if not db:
                st.error("Failed to initialize Firebase. Please check your configuration.")
                show_firebase_setup_guide()
                return # Exit if Firebase fails to initialize
        else:
            st.error("Firebase authentication module is not available. Please install/configure it.")
            return # Exit if Firebase module is not available

        # Sidebar navigation for authenticated parts of the app
        with st.sidebar:
            st.markdown("<h3 style='color: #1D7749; margin-bottom: 1rem;'>🌱 CarbonTally</h3>", unsafe_allow_html=True)
            
            if st.session_state.authenticated:
                user = get_current_firebase_user()
                if user:
                    st.markdown(f"**Welcome, {user.get('displayName', 'User')}!**")
                    st.markdown(f"*Role: {user.get('role', 'individual').title()}*")
                    
                    # Navigation based on user role
                    if check_firebase_user_role(user, 'admin'):
                        page_options = ["Admin Dashboard", "User Dashboard", "Plant a Tree", "Monitor Trees", "Donor Dashboard"]
                    else:
                        page_options = ["User Dashboard", "Plant a Tree", "Monitor Trees", "Donor Dashboard"]
                    
                    # Set initial radio selection based on current page state
                    try:
                        current_page_index = page_options.index(st.session_state.page)
                    except ValueError:
                        current_page_index = 0 # Default to first option if current page isn't in options
                    
                    st.session_state.page = st.radio("Navigate to:", page_options,    
                                                     index=current_page_index)
                    
                    if st.button("Logout", use_container_width=True):
                        firebase_logout()
                        # After logout, redirect to landing or login page
                        st.session_state.page = "Login"
                        st.rerun() # Rerun to update the UI immediately
            else:
                # Options for non-authenticated users after leaving landing
                st.session_state.page = st.radio("Choose an option:", ["Login", "Sign Up", "Password Recovery", "Donor Dashboard"],
                                                 index=["Login", "Sign Up", "Password Recovery", "Donor Dashboard"].index(st.session_state.page) 
                                                 if st.session_state.page in ["Login", "Sign Up", "Password Recovery", "Donor Dashboard"] else 0)

        # Main content area based on selected page
        if st.session_state.page == "Login":
            firebase_login_ui()
        elif st.session_state.page == "Sign Up":
            firebase_signup_ui()
            # IMPORTANT: To count both 'individual' and 'institution' users as
            # "Participating Entities" on the landing page, you MUST ensure that
            # your `firebase_auth_integration.py` file (specifically, the part
            # that handles successful user signup in `firebase_signup_ui`) calls
            # the `add_institution_to_db(firebase_uid, display_name)` function for
            # *both* individual and institution role signups.
            # You can copy the `add_institution_to_db` function (including its
            # imports and SQLITE_DB path definition) into firebase_auth_integration.py
            # for direct access.
        elif st.session_state.page == "Password Recovery":
            firebase_password_recovery_ui()
        elif st.session_state.page == "Donor Dashboard":
            guest_donor_dashboard_ui()
        elif st.session_state.authenticated:
            if st.session_state.page == "Admin Dashboard":
                admin_dashboard_content()
            elif st.session_state.page == "User Dashboard":
                unified_user_dashboard_content()
            elif st.session_state.page == "Plant a Tree":
                plant_a_tree_section()
            elif st.session_state.page == "Monitor Trees":
                monitoring_section()
        else:
            st.warning("Please log in to access this page.")
            firebase_login_ui() # Redirect to login if somehow on a restricted page unauthenticated

        # Footer
        add_branding_footer()

if __name__ == "__main__":
    main()
