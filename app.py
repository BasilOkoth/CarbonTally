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
    # Ensure these are imported from the correct files
    from kobo_integration import plant_a_tree_section, check_for_new_submissions, get_kobo_submissions, map_kobo_to_database, validate_tracking_number, initialize_database as initialize_kobo_db # Renamed to avoid conflict
except ImportError:
    def plant_a_tree_section(): st.error("Kobo Integration module (plant_a_tree_section) not found.")
    def check_for_new_submissions(user_id, hours): st.error("Kobo Integration module (check_for_new_submissions) not found."); return []
    def get_kobo_submissions(hours): st.error("Kobo Integration module (get_kobo_submissions) not found."); return []
    def map_kobo_to_database(data): st.error("Kobo Integration module (map_kobo_to_database) not found."); return None
    def validate_tracking_number(tn): st.error("Kobo Integration module (validate_tracking_number) not found."); return False
    def initialize_kobo_db(): st.error("Kobo Integration database initialization failed.");

try:
    from kobo_monitoring import monitoring_section, admin_tree_lookup, initialize_database as initialize_monitoring_db # Renamed to avoid conflict
except ImportError:
    def monitoring_section(): st.error("Kobo Monitoring module (monitoring_section) not found.")
    def admin_tree_lookup(tree_id): st.error("Kobo Monitoring module (admin_tree_lookup) not found."); return None
    def initialize_monitoring_db(): st.error("Kobo Monitoring database initialization failed.");

try:
    from firebase_auth_integration import (
        firebase_login_ui, firebase_signup_ui, firebase_password_recovery_ui,
        firebase_logout, get_current_firebase_user, check_firebase_user_role,
        show_firebase_setup_guide, initialize_firebase,
        admin_approval_dashboard
    )
except ImportError:
    st.error("Firebase Auth Integration module not found or missing functions. Please ensure firebase_auth_integration.py is correctly set up.")
    # Placeholder functions to prevent errors
    def firebase_login_ui(): st.info("Firebase login UI placeholder.")
    def firebase_signup_ui(): st.info("Firebase signup UI placeholder.")
    def firebase_password_recovery_ui(): st.info("Firebase password recovery UI placeholder.")
    def firebase_logout(): st.info("Firebase logout placeholder.")
    def get_current_firebase_user(): return None
    def check_firebase_user_role(user, role): return False
    def show_firebase_setup_guide(): st.info("Firebase setup guide placeholder.")
    def initialize_firebase(): st.info("Firebase initialization placeholder."); return None
    def admin_approval_dashboard(): st.info("Admin approval dashboard placeholder.")

try:
    from donor_dashboard import donor_dashboard, initialize_donor_database # Assuming donor_dashboard is in this file
except ImportError:
    def donor_dashboard(): st.error("Donor Dashboard module not found.")
    def initialize_donor_database(): st.error("Donor database initialization failed.")


# Database configuration
BASE_DIR = Path(__file__).parent if "__file__" in locals() else Path.cwd()
DATA_DIR = BASE_DIR / "data"
SQLITE_DB = DATA_DIR / "trees.db" # Centralized database path
CERT_DIR = DATA_DIR / "certificates"

# Ensure directories exist
DATA_DIR.mkdir(exist_ok=True, parents=True)
CERT_DIR.mkdir(exist_ok=True, parents=True)


# Initialize all necessary databases
def initialize_all_databases():
    initialize_kobo_db() # Initializes the 'trees' table (and QR codes dir)
    initialize_monitoring_db() # Initializes 'monitoring_events' table (from kobo_monitoring.py)
    initialize_donor_database() # Initializes 'donations' and 'donated_trees' tables (from donor_dashboard.py)

# Call database initialization once at the start
initialize_all_databases()


# --- Streamlit Page Configuration (MUST be the first Streamlit command) ---
st.set_page_config(
    page_title="CarbonTally Tree Tracking",
    page_icon="🌳",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- Session State Initialization ---
if 'firebase_initialized' not in st.session_state:
    st.session_state.firebase_initialized = False
if 'authenticated' not in st.session_state:
    st.session_state.authenticated = False
if 'user' not in st.session_state:
    st.session_state.user = None
if 'page' not in st.session_state:
    st.session_state.page = "Home" # Default page


# --- Custom CSS Styling ---
def load_enhanced_css():
    st.markdown("""
    <style>
        /* Enhanced Landing Page Styles */
        .landing-header {
            background: linear-gradient(135deg, #1D7749 0%, #28a745 100%);
            color: white;
            padding: 40px 20px;
            text-align: center;
            border-bottom-left-radius: 25px;
            border-bottom-right-radius: 25px;
            box-shadow: 0 4px 8px rgba(0, 0, 0, 0.2);
            margin-bottom: 30px;
        }
        .landing-header h1 {
            font-size: 3.5em;
            margin-bottom: 10px;
            text-shadow: 2px 2px 4px rgba(0,0,0,0.3);
        }
        .landing-header p {
            font-size: 1.2em;
            opacity: 0.9;
        }

        /* Feature Cards */
        .feature-card {
            background-color: #f0f8f0; /* Light green */
            border-left: 5px solid #28a745;
            border-radius: 8px;
            padding: 20px;
            margin-bottom: 20px;
            box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
            transition: transform 0.2s ease-in-out;
        }
        .feature-card:hover {
            transform: translateY(-5px);
        }
        .feature-card h3 {
            color: #1D7749;
            margin-bottom: 10px;
        }
        .feature-card p {
            color: #555;
        }

        /* Metric Cards (for Dashboard) */
        .metric-card {
            background-color: #ffffff;
            border-radius: 8px;
            padding: 20px;
            margin-bottom: 20px;
            box-shadow: 0 2px 5px rgba(0, 0, 0, 0.1);
            text-align: center;
            border: 1px solid #e0e0e0;
        }
        .metric-card h3 {
            color: #1D7749;
            font-size: 1.5em;
            margin-bottom: 5px;
        }
        .metric-card p {
            font-size: 0.9em;
            color: #777;
        }
        .metric-value {
            font-size: 2.5em;
            font-weight: bold;
            color: #28a745;
            margin-top: 10px;
        }

        /* Call to Action Button */
        .stButton button {
            background-color: #28a745;
            color: white;
            border-radius: 5px;
            padding: 10px 20px;
            font-size: 1.1em;
            border: none;
            cursor: pointer;
            transition: background-color 0.2s ease;
        }
        .stButton button:hover {
            background-color: #1D7749;
        }

        /* General Streamlit Overrides */
        .stApp {
            background-color: #f8f9fa; /* Light background */
        }
        .css-1d391kg, .css-1lcbmhc { /* Streamlit main content area and sidebar */
            padding-top: 1rem;
        }
        /* Style for info/success/warning/error alerts */
        .stAlert {
            border-radius: 8px;
            padding: 15px;
            margin-bottom: 15px;
        }

        /* Badges for roles/status */
        .badge {
            display: inline-block;
            padding: 0.3em 0.7em;
            font-size: 75%;
            font-weight: 700;
            line-height: 1;
            text-align: center;
            white-space: nowrap;
            vertical-align: baseline;
            border-radius: 0.25rem;
        }
        .badge-success { background-color: #28a745; color: white; }
        .badge-info { background-color: #17a2b8; color: white; }
        .badge-warning { background-color: #ffc107; color: #333; }
        .badge-danger { background-color: #dc3545; color: white; }
        .badge-primary { background-color: #007bff; color: white; }
        .badge-secondary { background-color: #6c757d; color: white; }

        /* Social Sharing Buttons (placeholders for now) */
        .social-buttons a {
            display: inline-block;
            margin-right: 10px;
            font-size: 1.5em;
            color: #555;
            transition: color 0.2s;
        }
        .social-buttons a:hover {
            color: #28a745;
        }

        /* Table styling */
        .dataframe {
            width: 100%;
            border-collapse: collapse;
            margin-top: 20px;
        }
        .dataframe th {
            background-color: #28a745;
            color: white;
            padding: 10px;
            text-align: left;
        }
        .dataframe td {
            padding: 10px;
            border-bottom: 1px solid #ddd;
        }
        .dataframe tr:nth-child(even) {
            background-color: #f2f2f2;
        }
    </style>
    """, unsafe_allow_html=True)

def show_enhanced_landing_page():
    load_enhanced_css() # Load the CSS
    st.markdown("""
    <div class="landing-header">
        <h1>Welcome to CarbonTally 🌱</h1>
        <p>Track your tree planting impact and contribute to a sustainable future!</p>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("---")

    col1, col2, col3 = st.columns(3)

    with col1:
        st.markdown("""
        <div class="feature-card">
            <h3>Record New Plantings</h3>
            <p>Easily log newly planted trees using our integrated KoBo Toolbox forms, capturing essential details and GPS coordinates.</p>
        </div>
        """, unsafe_allow_html=True)

    with col2:
        st.markdown("""
        <div class="feature-card">
            <h3>Monitor Tree Growth</h3>
            <p>Keep track of your trees' health and growth over time with our intuitive monitoring tools and data visualization.</p>
        </div>
        """, unsafe_allow_html=True)

    with col3:
        st.markdown("""
        <div class="feature-card">
            <h3>Donate & Support</h3>
            <p>Contribute to global reforestation efforts. Your donations directly support tree planting initiatives and community engagement.</p>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("---")

    st.header("Why CarbonTally?")
    st.write("""
    At CarbonTally, we believe in transparency and impact. Our platform provides:
    - **Real-time Tracking:** See where and when trees are planted.
    - **Community Engagement:** Connect with other planters and donors.
    - **Environmental Impact:** Directly contribute to carbon sequestration and biodiversity.
    """)

    st.subheader("Join Our Growing Community!")
    st.markdown("""
    Ready to make a difference?
    - **Plant a Tree:** If you're a planter, register and start logging your trees.
    - **Support a Tree:** Explore our donor dashboard and contribute to our mission.
    """)

    st.markdown("""
    <div style="text-align: center; margin-top: 30px;">
        <p style="font-size: 1.1em; color: #555;">Have questions? Contact us at <a href="mailto:support@carbontally.org">support@carbontally.org</a></p>
        <div class="social-buttons">
            <a href="#" target="_blank" title="Twitter"><i class="fab fa-twitter"></i></a>
            <a href="#" target="_blank" title="Facebook"><i class="fab fa-facebook"></i></a>
            <a href="#" target="_blank" title="LinkedIn"><i class="fab fa-linkedin"></i></a>
        </div>
    </div>
    """, unsafe_allow_html=True)


# --- Firebase Initialization (only once) ---
if not st.session_state.firebase_initialized:
    st.session_state.firebase_initialized = initialize_firebase() is not None

# --- Main Application Logic ---
def main():
    if not st.session_state.get('firebase_initialized'):
        st.error("Firebase initialization failed. Please check your configuration.")
        show_firebase_setup_guide()
        st.stop() # Stop execution if Firebase is not initialized

    # Sidebar Navigation
    # Replace with your logo URL
    st.sidebar.image("https://images.unsplash.com/photo-1517457210-bf26f477c573?q=80&w=1974&auto=format&fit=crop&ixlib=rb-4.0.3&ixid=M3wxMjA3fDB8MHxwaG90by1wYWdlfHx8fGVufDB8fHx8fA%3D%3D", use_column_width=True)
    st.sidebar.title("Navigation")

    # Determine available pages based on authentication and role
    menu_options = ["Home"] # Always available, will show enhanced landing page for non-logged-in
    
    # If not authenticated, show login/signup/recovery. Donor Dashboard is public.
    if not st.session_state.authenticated:
        menu_options.extend(["Login", "Sign Up", "Password Recovery", "Donor Dashboard"])
    else:
        user = st.session_state.user
        if user:
            st.sidebar.write(f"Welcome, {user.get('email', user.get('uid'))}!")
            # Common pages for authenticated users
            menu_options.extend(["User Dashboard", "Plant a Tree", "Monitor Trees", "Donor Dashboard"])

            # Admin-specific pages (assuming 'institution' role can manage users)
            if check_firebase_user_role(user, 'institution'):
                menu_options.append("Admin Dashboard") # For institution role to approve users

            # Logout button
            if st.sidebar.button("Logout"):
                firebase_logout()

    # Selectbox for navigation
    st.session_state.page = st.sidebar.selectbox("Go to", menu_options, index=menu_options.index(st.session_state.page) if st.session_state.page in menu_options else 0)

    # Main content area
    st.title("🌱 CarbonTally Tree Tracking & Donation")

    if st.session_state.page == "Home":
        # Show enhanced landing page for the Home tab
        show_enhanced_landing_page()
    elif st.session_state.page == "Login":
        firebase_login_ui()
    elif st.session_state.page == "Sign Up":
        firebase_signup_ui()
    elif st.session_state.page == "Password Recovery":
        firebase_password_recovery_ui()
    elif st.session_state.page == "Donor Dashboard":
        # Donor Dashboard is accessible to everyone
        donor_dashboard()
    elif st.session_state.authenticated:
        if st.session_state.page == "Admin Dashboard":
            # This dashboard is for 'institution' role to approve 'individual' users
            if check_firebase_user_role(st.session_state.user, 'institution'):
                admin_approval_dashboard()
            else:
                st.error("You do not have permission to access the Admin Dashboard.")
                st.session_state.page = "Home" # Redirect if not authorized
                st.rerun()
        elif st.session_state.page == "User Dashboard":
            unified_user_dashboard_content() # This function will be defined later or in another file
        elif st.session_state.page == "Plant a Tree":
            plant_a_tree_section()
        elif st.session_state.page == "Monitor Trees":
            monitoring_section()
    else:
        st.warning("Please log in to access this page or navigate to the Donor Dashboard.")
        firebase_login_ui() # Redirect to login if somehow on a restricted page unauthenticated

    # Footer
    add_branding_footer()

def unified_user_dashboard_content():
    """Content for authenticated Individual and Institution users."""
    st.header("Your Dashboard")
    user = st.session_state.user
    if user:
        st.write(f"Welcome, {user.get('email', 'User')}! Your role is: {user.get('role', 'N/A').capitalize()}")

        # Example: Show user-specific data or options
        if check_firebase_user_role(user, 'individual'):
            st.info("As an individual, you can manage your planted trees here.")
            # Add features for individual users (e.g., list their trees)
        elif check_firebase_user_role(user, 'institution'):
            st.info("As an institution, you can view your overall planting impact and manage users.")
            # Add features for institution users (e.g., aggregate data, link to admin approval)

        # Placeholder for tree data associated with the user's tree_tracking_id
        st.subheader("Your Planted Trees")
        current_user_tree_tracking_id = user.get('tree_tracking_id')

        if current_user_tree_tracking_id:
            conn = sqlite3.connect(SQLITE_DB)
            # IMPORTANT: Query now based on planter_tracking_id which stores the KoBo tree_tracking_number
            df_user_trees = pd.read_sql_query(f"SELECT * FROM trees WHERE planter_tracking_id = '{current_user_tree_tracking_id}'", conn)
            conn.close()

            if not df_user_trees.empty:
                st.dataframe(df_user_trees)
            else:
                st.info("No trees found associated with your account yet.")
                if st.button("Plant a Tree Now"):
                    st.session_state.page = "Plant a Tree"
                    st.rerun()
        else:
            st.info("Your account is not yet linked to a Tree Tracking ID. Please contact support if this is incorrect.")

    else:
        st.warning("User session not found. Please log in.")
        st.session_state.page = "Login"
        st.rerun()


if __name__ == "__main__":
    main()
