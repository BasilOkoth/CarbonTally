import streamlit as st
# Set page config - MUST BE THE FIRST STREAMLIT COMMAND
st.set_page_config(
    page_title="CarbonTally - Tree Monitoring",
    page_icon="🌳",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Standard library imports
import datetime
import re
import random
import os
import time
import sqlite3
import json
from pathlib import Path
from io import BytesIO
from typing import Optional, Tuple, Dict, Any

# Third-party imports
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from geopy.geocoders import Nominatim
from geopy.distance import geodesic
import qrcode
from PIL import Image
import base64
import requests # For KoBo API calls
import paypalrestsdk # For PayPal integration
from paypalrestsdk import Payment

# Custom module imports
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
import streamlit as st

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

# --- Custom CSS for Styling ---
def load_css():
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
            box_shadow: 0 2px 4px rgba(0,0,0,0.1);
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
    c.execute("""CREATE TABLE IF NOT EXISTS trees (
        tree_id TEXT PRIMARY KEY, institution TEXT, local_name TEXT, scientific_name TEXT,
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
    
    # MODIFIED: Changed 'institution_id' to 'institution' as per the column name in the 'trees' table
    num_institutions = trees['institution'].nunique() if 'institution' in trees.columns and not trees.empty else 0

    admin_metrics = [
        (total_trees, "Total Trees"),
        (survival_rate, "Overall Survival"),
        (co2_sequestered, "Total CO₂"),
        (len(set(trees["tree_tracking_number"])) if "tree_tracking_number" in trees.columns and not trees.empty else 0, "Active Users")
    ]
    
    for i, (value, label) in enumerate(admin_metrics):
        with admin_metric_cols[i]:
            st.markdown(f'<div class="metric-card"><div class="metric-value">{value}</div><div class="metric-label">{label}</div></div>', unsafe_allow_html=True)

    # Admin tabs
    tab_inst, tab_users, tab_approval = st.tabs(["🏢 Institution Performance", "👥 User Management", "✅ User Approval"])
    
    with tab_inst:
        st.markdown("<h5 style='color: #333; margin-top:1rem; margin-bottom: 0.5rem;'>Institution Performance</h5>", unsafe_allow_html=True)
        
        # MODIFIED: Changed 'institution_id' to 'institution'
        if not trees.empty and "institution" in trees.columns:
            institution_stats = trees.groupby("institution").agg(
                total_trees=pd.NamedAgg(column="tree_id", aggfunc="count"),
                alive_trees=pd.NamedAgg(column="status", aggfunc=lambda x: (x == "Alive").sum()),
                total_co2=pd.NamedAgg(column="co2_kg", aggfunc="sum")
            ).reset_index()
            
            institution_stats["survival_rate"] = round((institution_stats["alive_trees"] / institution_stats["total_trees"]) * 100, 1).fillna(0)
            
            if not institution_stats.empty:
                # MODIFIED: Changed 'institution_id' to 'institution'
                fig_inst = px.bar(
                    institution_stats.sort_values("total_trees", ascending=False),
                    x="institution", y="total_trees", title="Trees Planted by Institution",
                    color="survival_rate", color_continuous_scale=px.colors.sequential.Greens
                )
                fig_inst.update_layout(title_x=0.5)
                st.plotly_chart(fig_inst, use_container_width=True)
                st.dataframe(institution_stats, use_container_width=True)
            else:
                st.info("No institution data available yet.")
        else:
            st.info("No tree data available yet or 'institution' column missing.")
    
    with tab_users:
        st.markdown("<h5 style='color: #333; margin-top:1rem; margin-bottom: 0.5rem;'>User Management</h5>", unsafe_allow_html=True)
        st.info("User management is now handled through Firebase. Use the User Approval tab to manage pending users.")
    
    with tab_approval:
        st.markdown("<h5 style='color: #333; margin-top:1rem; margin-bottom: 0.5rem;'>User Approval</h5>", unsafe_allow_html=True)
        if FIREBASE_AUTH_MODULE_AVAILABLE:
            firebase_admin_approval_ui()
        else:
            st.error("Firebase authentication module is not available. Please check your installation.")

# --- Learn More Page ---
def learn_more_page():
    st.markdown("<h1 class='header-text'>ℹ️ About CarbonTally</h1>", unsafe_allow_html=True)
    
    st.markdown("""
    <div style="background-color: #f0f7f0; border-radius: 8px; padding: 1.5rem; margin-bottom: 1.5rem;">
        <h3 style="margin-top:0; color: #1D7749;">Our Mission</h3>
        <p>CarbonTally is dedicated to combating climate change through tree planting initiatives. 
        We empower individuals and institutions to plant trees, monitor their growth, and track their environmental impact.</p>
    </div>
    
    <div style="background-color: #f0f7f0; border-radius: 8px; padding: 1.5rem; margin-bottom: 1.5rem;">
        <h3 style="margin-top:0; color: #1D7749;">How It Works</h3>
        <p><strong>1. Plant:</strong> Individuals and institutions plant trees and record their details.</p>
        <p><strong>2. Monitor:</strong> Trees are regularly monitored for growth and health using QR codes.</p>
        <p><strong>3. Track:</strong> Our system calculates CO₂ sequestration and environmental impact.</p>
        <p><strong>4. Support:</strong> Donors can fund tree planting initiatives and track their impact.</p>
    </div>
    
    <div style="background-color: #f0f7f0; border-radius: 8px; padding: 1.5rem; margin-bottom: 1.5rem;">
        <h3 style="margin-top:0; color: #1D7749;">Get Involved</h3>
        <p><strong>As an Individual:</strong> Sign up to track your personal tree planting efforts.</p>
        <p><strong>As an Institution:</strong> Register your school, organization, or community group to manage collective tree planting.</p>
        <p><strong>As a Donor:</strong> Support tree planting initiatives and track the impact of your contribution.</p>
    </div>
    
    <div style="background-color: #f0f7f0; border-radius: 8px; padding: 1.5rem; margin-bottom: 1.5rem;">
        <h3 style="margin-top:0; color: #1D7749;">Contact Us</h3>
        <p>For more information or support, please contact us at:</p>
        <p>📧 <a href="mailto:okothbasil45@gmail.com">okothbasil45@gmail.com</a></p>
        <p>🔗 <a href="https://linkedin.com/in/kaudobasil" target="_blank">linkedin.com/in/kaudobasil</a></p>
    </div>
    """, unsafe_allow_html=True)

# --- Landing Page ---
def landing_page():
    st.markdown("<h1 class='header-text' style='text-align: center;'>🌳 Welcome to CarbonTally</h1>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center; font-size: 1.1rem; margin-bottom: 2rem;'>Monitor tree growth, track carbon sequestration, and support environmental action.</p>", unsafe_allow_html=True)

    # Metrics
    trees = load_tree_data()
    total_trees = len(trees)
    co2_sequestered = trees['co2_kg'].sum() if 'co2_kg' in trees.columns and not trees.empty else 0
    survival_rate = (trees[trees['status'] == 'Alive'].shape[0] / total_trees * 100) if total_trees > 0 and 'status' in trees.columns else 0
    
    # MODIFIED: Changed 'institution_id' to 'institution'
    num_institutions = trees['institution'].nunique() if 'institution' in trees.columns and not trees.empty else 0

    cols = st.columns(4)
    metrics_data = [
        (total_trees, "Trees Planted"),
        (f"{num_institutions}", "Institutions Active"),
        (f"{co2_sequestered:.2f} kg", "CO₂ Sequestered"),
        (f"{survival_rate:.1f}%", "Survival Rate")
    ]
    for i, (value, label) in enumerate(metrics_data):
        with cols[i]:
            st.markdown(f'<div class="metric-card"><div class="metric-value">{value}</div><div class="metric-label">{label}</div></div>', unsafe_allow_html=True)
    
    st.markdown("<hr style='margin: 2rem 0;'>", unsafe_allow_html=True)
    
    # Call to Action Buttons
    cta_cols = st.columns([1,1,1])
    with cta_cols[0]:
        if st.button("Login / Sign Up", use_container_width=True, key="landing_auth"):
            st.session_state.page = "Authentication"
            st.rerun()
    with cta_cols[1]:
        if st.button("View Donor Impact", use_container_width=True, key="landing_donor"):
            st.session_state.page = "Donor Dashboard"
            st.rerun()
    with cta_cols[2]:
        if st.button("Learn More", use_container_width=True, key="landing_learn_more"):
            st.session_state.page = "Learn More"
            st.rerun()

    # Display some public data like recent trees map
    if not trees.empty:
        st.markdown("<h4 style='color: #1D7749; margin-top: 2rem; margin-bottom: 0.5rem;'>Recently Planted Trees</h4>", unsafe_allow_html=True)
        recent_trees = trees.sort_values("date_planted", ascending=False).head(50)
        if 'latitude' in recent_trees.columns and 'longitude' in recent_trees.columns:
            # Filter out trees with missing coordinates
            map_trees = recent_trees.dropna(subset=["latitude", "longitude"])
            
            if not map_trees.empty:
                fig = px.scatter_mapbox(
                    map_trees,
                    lat="latitude", lon="longitude",
                    hover_name="tree_id",
                    # MODIFIED: Changed "institution_id" to "institution" to match the actual column name
                    hover_data={
                        "local_name": True, 
                        "institution": True, # CORRECTED from "institution_id"
                        "date_planted": True,
                        "latitude": False, 
                        "longitude": False
                    },
                    color="status",
                    color_discrete_map={"Alive": "#28a745", "Dead": "#dc3545"},
                    zoom=10, height=400
                )
                fig.update_layout(mapbox_style="carto-positron", margin={"r":0,"t":0,"l":0,"b":0})
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("No location data available for recent trees.")
        else:
            st.info("No location data available for trees.")

# --- Authentication Page ---
def authentication_page_content():
    st.markdown("<h1 class='header-text' style='text-align: center;'>Account Access</h1>", unsafe_allow_html=True)
    if not FIREBASE_AUTH_MODULE_AVAILABLE:
        st.error("Authentication services are currently unavailable. Please try again later.")
        if st.button("← Back to Home"):
            st.session_state.page = "Landing"
            st.rerun()
        return

    auth_tab_login, auth_tab_signup, auth_tab_reset = st.tabs(["Login", "Sign Up", "Forgot Password"])
    with auth_tab_login:
        firebase_login_ui()
    with auth_tab_signup:
        firebase_signup_ui()
    with auth_tab_reset:
        firebase_password_recovery_ui()
    
    if st.button("← Back to Home", key="auth_back_home"):
        st.session_state.page = "Landing"
        st.rerun()

# --- Firebase Setup Guide ---
def show_firebase_setup_guide(): # This function now directly uses its name, no alias needed
    st.markdown("<h1 class='header-text'>🔧 Firebase Setup Guide</h1>", unsafe_allow_html=True)
    
    st.markdown("""
    <div style="background-color: #f0f7f0; border-radius: 8px; padding: 1.5rem; margin-bottom: 1.5rem;">
        <h3 style="margin-top:0; color: #1D7749;">Setting Up Firebase for CarbonTally</h3>
        <p>Follow these steps to set up Firebase authentication for your CarbonTally app:</p>
    </div>
    """, unsafe_allow_html=True)
    
    st.markdown("### Step 1: Create a Firebase Project")
    st.markdown("""
    1. Go to the [Firebase Console](https://console.firebase.google.com/)
    2. Click "Add project" and follow the setup wizard
    3. Enable Google Analytics if desired
    4. Click "Create project"
    """)
    
    st.markdown("### Step 2: Set Up Authentication")
    st.markdown("""
    1. In your Firebase project, go to "Authentication" in the left sidebar
    2. Click "Get started"
    3. Enable the "Email/Password" sign-in method
    4. Save your changes
    """)
    
    st.markdown("### Step 3: Create a Firestore Database")
    st.markdown("""
    1. In your Firebase project, go to "Firestore Database" in the left sidebar
    2. Click "Create database"
    3. Start in production mode
    4. Choose a location closest to your users
    5. Click "Enable"
    """)
    
    st.markdown("### Step 4: Generate Service Account Credentials")
    st.markdown("""
    1. In your Firebase project, go to "Project settings" (gear icon)
    2. Go to the "Service accounts" tab
    3. Click "Generate new private key"
    4. Save the JSON file securely
    """)
    
    st.markdown("### Step 5: Add Firebase Configuration to Streamlit Secrets")
    st.markdown("""
    Add the following to your `.streamlit/secrets.toml` file:
    
    ```toml
    [FIREBASE]
    TYPE = "service_account"
    PROJECT_ID = "your-project-id"
    PRIVATE_KEY_ID = "your-private-key-id"
    PRIVATE_KEY = "your-private-key"
    CLIENT_EMAIL = "your-client-email"
    CLIENT_ID = "your-client-id"
    AUTH_URI = "[https://accounts.google.com/o/oauth2/auth](https://accounts.google.com/o/oauth2/auth)"
    TOKEN_URI = "[https://oauth2.googleapis.com/token](https://oauth2.googleapis.com/token)"
    AUTH_PROVIDER_X509_CERT_URL = "[https://www.googleapis.com/oauth2/v1/certs](https://www.googleapis.com/oauth2/v1/certs)"
    CLIENT_X509_CERT_URL = "[https://www.googleapis.com/robot/v1/metadata/x509/firebase-adminsdk-xxxxx%40your-project-id.iam.gserviceaccount.com](https://www.googleapis.com/robot/v1/metadata/x509/firebase-adminsdk-xxxxx%40your-project-id.iam.gserviceaccount.com)"
    UNIVERSE_DOMAIN = "googleapis.com"
    ```
    
    Replace the placeholder values with the actual values from your service account JSON file.
    """)
    
    st.markdown("### Step 6: Test Your Firebase Configuration")
    
    if st.button("Test Firebase Connection", use_container_width=True):
        if FIREBASE_AUTH_MODULE_AVAILABLE:
            success = initialize_firebase()
            if success:
                st.success("Firebase connection successful! Your authentication system is ready to use.")
            else:
                st.error("Firebase connection failed. Please check your configuration.")
        else:
            st.error("Firebase authentication module is not available. Please check your installation.")

# --- Main App Logic ---
def main():
    init_db() # Initialize SQL DB for app data (not users)
    load_css()

    # Initialize Firebase if available
    # The initialize_firebase function already sets st.session_state.firebase_db internally
    if "firebase_initialized" not in st.session_state:
        if FIREBASE_AUTH_MODULE_AVAILABLE:
            st.session_state["firebase_initialized"] = initialize_firebase()
        else:
            st.session_state["firebase_initialized"] = False


    if 'page' not in st.session_state: 
        st.session_state.page = "Landing"
    
    # Get current Firebase user
    current_user = None
    if FIREBASE_AUTH_MODULE_AVAILABLE and st.session_state.get('firebase_initialized'):
        current_user = get_current_firebase_user()
    
    st.session_state.authenticated = bool(current_user)
    if current_user:
        st.session_state.user = current_user
    else:
        # Use .pop() with a default value to safely remove the key if it exists
        st.session_state.pop("user", None)

    # Page routing logic
    page = st.session_state.page
    user_role = st.session_state.user.get("role") if current_user else None

    # Public Pages
    if page == "Landing": landing_page()
    elif page == "Authentication": authentication_page_content()
    elif page == "Donor Dashboard": guest_donor_dashboard_ui() # Accessible by anyone
    elif page == "Learn More": learn_more_page()
    elif page == "Firebase Setup": 
        # Only show setup guide if authenticated and admin, or if it's the default page before login
        if (st.session_state.authenticated and user_role == "admin") or not st.session_state.authenticated:
            if FIREBASE_AUTH_MODULE_AVAILABLE:
                show_firebase_setup_guide() 
            else:
                st.error("Firebase Auth Integration module not found. Setup guide unavailable.")
        else:
            st.error("Access Denied.") # If authenticated but not admin, deny access to Firebase Setup
    
    # Authenticated Pages
    elif st.session_state.authenticated:
        with st.sidebar:
            st.markdown(f"<h3 style='margin-bottom:0.2rem;'>🌳 CarbonTally</h3>", unsafe_allow_html=True)
            st.markdown(f"<p style='font-size:0.9rem; margin-top:0; margin-bottom:1rem;'>Welcome, <strong>{st.session_state.user.get('displayName', 'User')}</strong></p>", unsafe_allow_html=True)
            
            nav_options = []
            default_page_for_user = "User Dashboard" # Default for individual/institution

            if user_role == "admin":
                nav_options = ["Admin Dashboard", "User Management", "Tree Planting", "Tree Monitoring", "Tree Lookup", "Firebase Setup"]
                default_page_for_user = "Admin Dashboard"
            elif user_role in ["individual", "institution"]:
                nav_options = ["User Dashboard", "Tree Planting", "Tree Monitoring"] # Added Tree Planting and Tree Monitoring
            # Donors don't log in, so no sidebar for them
            
            if not nav_options: # If user is authenticated but has no role or unknown role
                st.warning("Your account role is not configured. Please contact support.")
                if st.button("Logout", key="no_role_logout"): 
                    if FIREBASE_AUTH_MODULE_AVAILABLE: firebase_logout()
                    st.session_state.page = "Landing"; st.rerun()
                return

            current_selection_idx = nav_options.index(page) if page in nav_options else 0
            selected_page = st.radio("Navigation", nav_options, index=current_selection_idx, key="navigation_radio", label_visibility="collapsed")
            
            if selected_page != page: st.session_state.page = selected_page; st.rerun()

            st.markdown("<hr style='margin: 1rem 0;'>", unsafe_allow_html=True)
            if st.button("Logout", use_container_width=True, key="logout_button"):
                if FIREBASE_AUTH_MODULE_AVAILABLE: firebase_logout()
                st.session_state.page = "Landing"; st.rerun()

        # Render authenticated page
        if page == "Admin Dashboard": admin_dashboard_content()
        elif page == "User Dashboard": unified_user_dashboard_content()
        elif page == "User Management": 
            if user_role == "admin" and FIREBASE_AUTH_MODULE_AVAILABLE: firebase_admin_approval_ui()
            else: st.error("Access Denied or Firebase module unavailable.")
        elif page == "Tree Planting": 
            # Allow individual, institution, and admin to plant trees
            if user_role in ["individual", "institution", "admin"]:
                plant_a_tree_section()
            else:
                # ADDED DEBUGGING INFO: Display the current user_role
                st.error(f"Your account ({user_role}) doesn't have permissions to plant trees.") 
        elif page == "Tree Monitoring": monitoring_section()
        elif page == "Tree Lookup": 
            if user_role == "admin": admin_tree_lookup()
            else: st.error("Access Denied.")
        elif page == "Firebase Setup":
            if user_role == "admin": show_firebase_setup_guide() # Directly call the function name
            else: st.error("Access Denied.")
        else:
            st.error("Page not found or access denied.")
            st.session_state.page = default_page_for_user; st.rerun()
    else: # Not authenticated, and not a public page they are on
        st.session_state.page = "Landing"
        st.rerun()

    add_branding_footer()

if __name__ == "__main__":
    main()
# Updated: Force redeploy test on June 13, 2025

