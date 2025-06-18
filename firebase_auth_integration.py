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

# Custom module imports
# Ensure you have these files in your project directory
try:
    # Corrected import: Removed show_firebase_setup_guide as it's no longer available
    from firebase_auth_integration import (
        initialize_firebase, firebase_login_ui, firebase_signup_ui, 
        firebase_password_recovery_ui, firebase_admin_approval_ui, 
        firebase_logout, get_current_firebase_user, check_firebase_user_role
    )
except ImportError as e:
    st.error(f"Firebase Auth Integration module not found or missing functions: {e}. Please ensure firebase_auth_integration.py is correctly set up.")
    st.stop() # Stop the app if crucial module is missing

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
    def admin_tree_lookup(tree_id): st.error("Kobo Monitoring module (admin_tree_lookup) not found."); return None

# Set page config - MUST BE THE FIRST STREAMLIT COMMAND
st.set_page_config(
    page_title="CarbonTally - Tree Monitoring",
    page_icon="🌳",
    layout="wide",
    initial_sidebar_state="collapsed"  # Collapsed sidebar for landing page initially
)

# --- SQLite Database Setup ---
BASE_DIR = Path(__file__).parent if "__file__" in locals() else Path.cwd()
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True) # Ensure data directory exists
SQLITE_DB = DATA_DIR / "trees.db"

def init_db():
    """Initializes the SQLite database and creates necessary tables."""
    conn = sqlite3.connect(SQLITE_DB)
    c = conn.cursor()

    # Create 'trees' table for planted trees
    c.execute("""
        CREATE TABLE IF NOT EXISTS trees (
            id TEXT PRIMARY KEY,
            user_id TEXT,
            species TEXT,
            quantity INTEGER,
            planting_date TEXT,
            latitude REAL,
            longitude REAL,
            status TEXT,
            form_id TEXT,
            submission_id TEXT,
            qr_code_path TEXT,
            tree_tracking_number TEXT,
            UNIQUE(form_id, submission_id)
        )
    """)

    # Create 'institutions' table for participants (individuals/institutions)
    c.execute("""
        CREATE TABLE IF NOT EXISTS institutions (
            id TEXT PRIMARY KEY,
            name TEXT,
            join_date TEXT
        )
    """)
    conn.commit()
    conn.close()

# Initialize the database when the app starts
init_db()

# --- Utility Functions ---
def get_total_trees():
    """Fetches the total number of trees from the database."""
    conn = sqlite3.connect(SQLITE_DB)
    c = conn.cursor()
    c.execute("SELECT SUM(quantity) FROM trees WHERE status != 'rejected'")
    total_trees = c.fetchone()[0]
    conn.close()
    return int(total_trees) if total_trees else 0

def get_total_participants():
    """Fetches the total number of unique participants from the database."""
    conn = sqlite3.connect(SQLITE_DB)
    c = conn.cursor()
    c.execute("SELECT COUNT(DISTINCT id) FROM institutions")
    total_participants = c.fetchone()[0]
    conn.close()
    return int(total_participants) if total_participants else 0

def get_carbon_sequestered():
    """Estimates total carbon sequestered based on tree count.
    (Placeholder: Replace with more accurate model if available)"""
    # Assuming 21.77 kg (approx 48 lbs) CO2 per tree per year for a typical broadleaf
    # And average tree lifespan contributing over 40 years.
    # This is a very rough estimate and should be replaced with a proper model.
    trees = get_total_trees()
    # Using a simplified average of 1 ton CO2 per tree over its lifetime for quick demo
    # (Highly variable by species, climate, etc. - for real app, use scientific data)
    return trees * 0.048 # In tons, based on 48 lbs per tree per year (0.02177 tons)

# --- KoBoToolbox Integration ---
# These are placeholder functions. Replace with actual API calls in kobo_integration.py
# and kobo_monitoring.py if you intend to use KoBoToolbox.
# KOBO_API_TOKEN = st.secrets.get("KOBO_API_TOKEN")
# KOBO_USERNAME = st.secrets.get("KOBO_USERNAME")
# KOBO_PASSWORD = st.secrets.get("KOBO_PASSWORD")
# KOBO_FORM_ID = st.secrets.get("KOBO_FORM_ID") # e.g., 'your_form_id_number'
# KOBO_URL = "https://kf.kobotoolbox.org/api/v2/assets/" # Adjust if self-hosting

# --- Admin Dashboard Content ---
def admin_dashboard_content():
    st.title("🌳 Admin Dashboard")
    st.write("Manage users, monitor all trees, and overview system health.")

    st.subheader("Pending User Approvals")
    firebase_admin_approval_ui()

    st.subheader("Search Trees by Tracking Number")
    tree_id_input = st.text_input("Enter Tree Tracking Number or Submission ID to search:")
    if st.button("Search Tree"):
        if tree_id_input:
            tree_data = admin_tree_lookup(tree_id_input) # This function should be in kobo_monitoring.py
            if tree_data:
                st.json(tree_data) # Display raw data for now
                # You can format this to display tree details nicely
            else:
                st.warning("No tree found with that Tracking Number or Submission ID.")
        else:
            st.warning("Please enter a Tree Tracking Number or Submission ID.")

    st.subheader("System Overview")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Total Trees Planted", get_total_trees())
    with col2:
        st.metric("Total Participants", get_total_participants())
    with col3:
        st.metric("Estimated CO2 Sequestered (tons)", f"{get_carbon_sequestered():,.2f}")

    st.subheader("Recent Submissions (Admin View)")
    # This would typically fetch all recent submissions, not just for a specific user
    # For now, a placeholder or a simplified view
    st.info("Functionality to view all recent KoBoToolbox submissions will be here.")
    # Example: recent_submissions = check_for_new_submissions(None, 24) # Fetch all in last 24 hrs
    # if recent_submissions:
    #     st.write(pd.DataFrame(recent_submissions))
    # else:
    #     st.info("No new submissions in the last 24 hours.")

# --- Unified User Dashboard Content (for individual and institution users) ---
def unified_user_dashboard_content():
    user = get_current_firebase_user()
    if not user:
        st.warning("Please log in to view your dashboard.")
        st.session_state.page = "Login"
        st.rerun()
        return

    st.title(f"🌳 Welcome, {user.get('displayName', 'User')}!")
    st.write(f"**Role:** {user.get('role').capitalize()}")
    if user.get('role') == 'institution' and user.get('institution'):
        st.write(f"**Institution:** {user.get('institution')}")
    st.write(f"**Your Tree Tracking Number:** `{user.get('treeTrackingNumber', 'N/A')}`")

    st.subheader("Your Planted Trees")
    # This section would display trees planted by the current user
    # For now, display a placeholder or a simple query
    conn = sqlite3.connect(SQLITE_DB)
    df_user_trees = pd.read_sql_query(f"SELECT * FROM trees WHERE user_id = '{user['uid']}'", conn)
    conn.close()

    if not df_user_trees.empty:
        st.dataframe(df_user_trees[['species', 'quantity', 'planting_date', 'status', 'tree_tracking_number']])
        
        total_user_trees = df_user_trees['quantity'].sum()
        st.metric("Total Trees You Planted", total_user_trees)
    else:
        st.info("You haven't recorded any trees yet. Use the 'Plant a Tree' section to add new records!")

    st.subheader("Recent Activity")
    # This could show recent monitoring updates or new submissions related to their trees
    st.info("Recent activity and monitoring updates for your trees will be displayed here.")

# --- Guest Donor Dashboard Content ---
def guest_donor_dashboard_ui():
    st.title("💖 Donor Dashboard")
    st.write("Thank you for your support! Here you can see the collective impact of your contributions.")

    st.subheader("CarbonTally Impact Metrics")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Total Trees Planted", get_total_trees())
    with col2:
        st.metric("Total Participants", get_total_participants())
    with col3:
        st.metric("Estimated CO2 Sequestered (tons)", f"{get_carbon_sequestered():,.2f}")

    st.subheader("Global Tree Map (Placeholder)")
    st.info("A map showing tree planting locations globally will be displayed here.")
    # Example for a simple placeholder map (requires some dummy data or actual tree data)
    # df_map_data = pd.DataFrame({
    #     'lat': [0.2478, -1.2921, 5.0],
    #     'lon': [37.9062, 36.8219, 30.0],
    #     'size': [1000, 500, 700]
    # })
    # st.map(df_map_data)

    st.subheader("Support CarbonTally")
    st.markdown("""
    Your generous donations help us expand our reforestation efforts and maintain our monitoring platform.
    Consider supporting us today!
    """)
    # Add PayPal/Payment integration here
    st.button("Donate Now (Coming Soon!)")

# --- Landing Page Content ---
def show_landing_page():
    # Header Section
    st.markdown("""
    <style>
        /* General Streamlit overrides */
        .stApp {
            background-color: #f0f2f6; /* Light gray background for the whole app */
        }
        
        /* Landing Page Specific Styles */
        .landing-header {
            background: linear-gradient(135deg, #1D7749 0%, #28a745 100%);
            color: white;
            padding: 3rem 1rem;
            margin: -1rem -1rem 2rem -1rem; /* Adjusts for Streamlit's default margins */
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
            padding: 1.5rem;
            border-radius: 10px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.05);
            text-align: center;
            margin-bottom: 1rem;
        }
        .landing-metric h3 {
            color: #1D7749;
            font-size: 2.5rem;
            margin-bottom: 0.5rem;
        }
        .landing-metric p {
            font-size: 1.1rem;
            color: #555;
        }
        
        .landing-section {
            background-color: white;
            padding: 2rem;
            border-radius: 10px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.05);
            margin-bottom: 2rem;
        }
        .landing-section h2 {
            color: #1D7749;
            text-align: center;
            margin-bottom: 1.5rem;
            font-size: 2rem;
        }
        
        .landing-feature {
            background-color: #f9f9f9;
            padding: 1.5rem;
            border-radius: 8px;
            border: 1px solid #e0e0e0;
            text-align: center;
            margin-bottom: 1.5rem;
            min-height: 200px; /* Ensure consistent height */
            display: flex;
            flex-direction: column;
            justify-content: center;
            align-items: center;
        }
        .landing-feature h3 {
            color: #28a745;
            font-size: 1.5rem;
            margin-bottom: 0.75rem;
        }
        .landing-feature p {
            font-size: 0.95rem;
            color: #666;
        }
        
        .stButton>button {
            background-color: #1D7749;
            color: white;
            padding: 0.75rem 1.5rem;
            border-radius: 8px;
            border: none;
            font-size: 1.1rem;
            font-weight: bold;
            transition: background-color 0.3s ease;
        }
        .stButton>button:hover {
            background-color: #28a745;
            color: white;
        }
        
        /* Ensure inputs and selectboxes are full width */
        .stTextInput, .stSelectbox, .stForm {
            width: 100%;
        }

        /* Remove padding around the main content to allow custom header/footer to stretch */
        .st-emotion-cache-z5fcl4 { /* This class might change, requires inspection */
            padding-top: 0rem;
            padding-bottom: 0rem;
        }
        .st-emotion-cache-1jmve6m { /* Another class that might need adjustment */
            padding: 0rem 1rem;
        }
        
    </style>
    """, unsafe_allow_html=True)
    
    # Load custom CSS
    # load_landing_css() # This was an internal function now inlined for simplicity

    st.markdown("""
    <div class="landing-header">
        <h1>CarbonTally 🌳</h1>
        <p>Your ultimate platform for transparent tree monitoring and impactful climate action. Track every tree, understand its impact, and join a global community dedicated to reforestation.</p>
        <div style="display: flex; justify-content: center; gap: 1rem;">
            <button onclick="window.parent.document.querySelector('[data-testid=\"stSidebarUserContent\"]').click();" style="background-color: white; color: #1D7749; padding: 0.75rem 1.5rem; border-radius: 8px; border: none; font-size: 1.1rem; font-weight: bold; cursor: pointer;">
                Get Started
            </button>
        </div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("## Our Impact")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown(f"""
        <div class="landing-metric">
            <h3>{get_total_trees():,}</h3>
            <p>Trees Planted</p>
        </div>
        """, unsafe_allow_html=True)
    with col2:
        st.markdown(f"""
        <div class="landing-metric">
            <h3>{get_total_participants():,}</h3>
            <p>Dedicated Participants</p>
        </div>
        """, unsafe_allow_html=True)
    with col3:
        st.markdown(f"""
        <div class="landing-metric">
            <h3>{get_carbon_sequestered():,.2f}</h3>
            <p>Tons of CO2 Sequestered</p>
        </div>
        """, unsafe_allow_html=True)

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
    # Initialize session state
    if 'page' not in st.session_state:
        st.session_state.page = "Landing"
    
    if 'authenticated' not in st.session_state:
        st.session_state.authenticated = False
    
    if 'user' not in st.session_state:
        st.session_state.user = None

    # Initialize Firebase at the very beginning of the main function
    # If Firebase initialization fails, display an error and stop execution.
    db = initialize_firebase()
    if db is None:
        st.error("Firebase authentication module is not available. Please install/configure it correctly.")
        # The app cannot function without Firebase, so stop execution.
        st.stop()

    # Sidebar for navigation
    with st.sidebar:
        st.title("Navigation")
        if not st.session_state.authenticated:
            st.session_state.page = st.radio("Choose an option:", ["Login", "Sign Up", "Password Recovery", "Donor Dashboard"],
                                             index=["Login", "Sign Up", "Password Recovery", "Donor Dashboard"].index(st.session_state.page) 
                                             if st.session_state.page in ["Login", "Sign Up", "Password Recovery", "Donor Dashboard"] else 0)
        else:
            user_role = get_current_firebase_user().get('role')
            if user_role == 'admin':
                st.session_state.page = st.radio("Admin Options:", ["Admin Dashboard", "Plant a Tree", "Monitor Trees", "Logout"],
                                                 index=["Admin Dashboard", "Plant a Tree", "Monitor Trees", "Logout"].index(st.session_state.page) 
                                                 if st.session_state.page in ["Admin Dashboard", "Plant a Tree", "Monitor Trees", "Logout"] else 0)
            else: # individual or institution user
                st.session_state.page = st.radio("User Options:", ["User Dashboard", "Plant a Tree", "Monitor Trees", "Logout"],
                                                 index=["User Dashboard", "Plant a Tree", "Monitor Trees", "Logout"].index(st.session_state.page)
                                                 if st.session_state.page in ["User Dashboard", "Plant a Tree", "Monitor Trees", "Logout"] else 0)
            
            if st.session_state.page == "Logout":
                firebase_logout()

    # Main content area based on selected page
    if st.session_state.page == "Landing":
        show_landing_page()
    elif st.session_state.page == "Login":
        firebase_login_ui()
    elif st.session_state.page == "Sign Up":
        firebase_signup_ui()
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
