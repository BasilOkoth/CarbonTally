import streamlit as st
import pandas as pd
import plotly.express as px # Added for plotting
import plotly.graph_objects as go # Added for plotting
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

# Third-party imports (ensure these are installed in your environment)
# from geopy.geocoders import Nominatim # Uncomment if you use this
# from geopy.distance import geodesic # Uncomment if you use this
# import qrcode # Already in kobo_integration, but might be needed here if used directly
# from PIL import Image # Already in kobo_integration, but might be needed here if used directly
# import base64 # Already in kobo_integration, but might be needed here if used directly
# import requests # Already in kobo_integration, but might be needed here if used directly
# import paypalrestsdk # Uncomment if you're using PayPal
# from paypalrestsdk import Payment # Uncomment if you're using PayPal

# Custom module imports with error handling
try:
    from firebase_auth_integration import (
        firebase_login_ui, firebase_signup_ui, firebase_password_recovery_ui,
        firebase_logout, check_firebase_user_role, initialize_firebase,
        get_current_firebase_user
    )
    FIREBASE_AVAILABLE = True
except ImportError as e:
    st.error(f"Firebase Auth Integration Error: {str(e)}")
    # Create dummy functions for missing imports
    def firebase_login_ui(): st.warning("Login UI not available")
    def firebase_signup_ui(): st.warning("Signup UI not available")
    def firebase_password_recovery_ui(): st.warning("Password recovery not available")
    def firebase_logout(): st.session_state.authenticated = False
    def check_firebase_user_role(user, role): return False
    def initialize_firebase(): return None
    def get_current_firebase_user(): return None
    FIREBASE_AVAILABLE = False

try:
    from kobo_integration import (
        plant_a_tree_section,
        check_for_new_submissions,
        initialize_database, # Assuming this is the primary initialize for Kobo integration
        get_leaderboard_data as get_kobo_leaderboard, # Now defined in kobo_integration.py
        get_user_badges as get_kobo_badges # Now defined in kobo_integration.py
    )
except ImportError as e:
    st.error(f"Kobo Integration module error: {str(e)}. Tree planting section coming soon!")
    def plant_a_tree_section(): st.warning("Tree planting section coming soon!")
    def check_for_new_submissions(user_id=None, hours=24): return []
    def initialize_database(): pass
    def get_kobo_leaderboard(): return pd.DataFrame()
    def get_kobo_badges(user_email=None): return {}

try:
    from kobo_monitoring import (
        monitoring_section,
        get_tree_details,
        check_for_new_monitoring_submissions,
        admin_tree_lookup as admin_monitoring_lookup, # Now defined in kobo_monitoring.py
        initialize_database as initialize_monitoring_db # Assuming this is the primary initialize for Kobo monitoring
    )
except ImportError as e:
    st.error(f"Kobo Monitoring module error: {str(e)}. Monitoring section coming soon!")
    def monitoring_section(): st.warning("Monitoring section coming soon!")
    def get_tree_details(tree_id): return None
    def check_for_new_monitoring_submissions(hours=24): return []
    def admin_monitoring_lookup(query): return pd.DataFrame()
    def initialize_monitoring_db(): pass

try:
    from donor_dashboard import guest_donor_dashboard_ui
except ImportError as e:
    st.error(f"Donor Dashboard module error: {str(e)}. Donor dashboard coming soon!")
    def guest_donor_dashboard_ui(): st.warning("Donor dashboard coming soon!")

try:
    from branding_footer import add_branding_footer
except ImportError:
    def add_branding_footer(): st.markdown("<p style='text-align:center;font-size:0.8em;color:grey;'>🌱 CarbonTally – Developed by Basil Okoth</p>", unsafe_allow_html=True)

# Database configuration
BASE_DIR = Path(__file__).parent if "__file__" in locals() else Path.cwd()
DATA_DIR = BASE_DIR / "data"
SQLITE_DB = DATA_DIR / "trees.db"

# Initialize directories
DATA_DIR.mkdir(exist_ok=True, parents=True)

# --- Streamlit Configuration ---
st.set_page_config(
    page_title="CarbonTally Tree Tracking",
    page_icon="🌳",
    layout="wide",
    initial_sidebar_state="expanded" # Keep sidebar expanded by default
)

def set_custom_css():
    """Applies custom CSS to the Streamlit app."""
    custom_css = """
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
        .stSidebar {
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
    """
    st.markdown(custom_css, unsafe_allow_html=True)

# --- Firebase Initialization ---
if FIREBASE_AVAILABLE and 'firebase_initialized' not in st.session_state:
    try:
        initialize_firebase()
        st.session_state.firebase_initialized = True
    except Exception as e:
        st.error(f"Firebase initialization failed: {e}")
        st.session_state.firebase_initialized = False

# --- Session State Management ---
if 'authenticated' not in st.session_state:
    st.session_state.authenticated = False
if 'user' not in st.session_state:
    st.session_state.user = None
if 'page' not in st.session_state:
    st.session_state.page = "Home"

# Function to get active user and update session state
def get_active_user_and_update_state():
    if st.session_state.authenticated:
        try:
            current_user = get_current_firebase_user()
            if current_user:
                st.session_state.user = current_user
                return True
            else:
                st.session_state.authenticated = False
                st.session_state.user = None
                return False
        except Exception as e:
            st.error(f"Error fetching current Firebase user: {e}")
            st.session_state.authenticated = False
            st.session_state.user = None
            return False
    return False

# --- UI Components ---
def show_landing_page():
    # Use the landing-header class for styling the welcome section
    st.markdown("<div class='landing-header'>", unsafe_allow_html=True)
    st.markdown("<h1>Welcome to CarbonTally! 🌳</h1>", unsafe_allow_html=True)
    st.markdown("""
        <p><strong>CarbonTally</strong> is a platform dedicated to tracking and monitoring tree planting initiatives.
        We provide tools for individuals, schools, and institutions to record tree data,
        track their growth, estimate CO2 sequestration, and engage in a community committed to a greener future.</p>
    """, unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("<div class='landing-cta'>", unsafe_allow_html=True)
    st.subheader("Get Started")
    st.markdown("""
    * **New Users:** <a href="#sign-up" class='landing-btn'>Sign Up</a> to start planting and monitoring trees!
    * **Existing Users:** <a href="#login" class='landing-btn landing-btn-secondary'>Login</a> to access your dashboard.
    * **Donors:** Explore the <a href="#donor-dashboard" class='landing-btn landing-btn-secondary'>Donor Dashboard</a> to see our impact and support initiatives.
    """, unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

    st.subheader("Key Features")
    st.markdown("<div class='landing-features'>", unsafe_allow_html=True)
    st.markdown("""
    <div class='landing-feature'>
        <h3>🌲 Tree Planting</h3>
        <p>Record new tree data easily via KoBo forms.</p>
    </div>
    <div class='landing-feature'>
        <h3>📈 Tree Monitoring</h3>
        <p>Track the growth and health of planted trees over time.</p>
    </div>
    <div class='landing-feature'>
        <h3>📊 CO₂ Sequestration</h3>
        <p>Estimate the carbon impact of your trees.</p>
    </div>
    <div class='landing-feature'>
        <h3>🏅 Leaderboards & Badges</h3>
        <p>Gamified engagement for planters.</p>
    </div>
    <div class='landing-feature'>
        <h3>🌍 Donor Dashboard</h3>
        <p>Transparent impact tracking for donors.</p>
    </div>
    <div class='landing-feature'>
        <h3>🔒 Secure Authentication</h3>
        <p>Manage user accounts with Firebase.</p>
    </div>
    """, unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("---")
    st.subheader("Participating Entities")
    # You will populate this with data from your database (e.g., institutions)
    st.info("List of participating institutions/schools will appear here.")
    # Example:
    # conn = sqlite3.connect(SQLITE_DB)
    # try:
    #     df_institutions = pd.read_sql_query("SELECT name, total_trees_planted FROM institutions ORDER BY total_trees_planted DESC", conn)
    #     if not df_institutions.empty:
    #         st.dataframe(df_institutions)
    #     else:
    #         st.info("No institutions registered yet.")
    # finally:
    #     conn.close()

def unified_user_dashboard_content():
    """Displays dashboard content based on user role."""
    st.title("My Dashboard")
    user = st.session_state.get('user')

    if user:
        st.subheader(f"Welcome, {user.get('username', user.get('email', 'User'))}!")
        st.write(f"**Email:** {user.get('email')}")
        st.write(f"**Role:** {user.get('role', 'N/A').capitalize()}")

        # Display basic user stats from session state or profile (from firebase_auth_integration.py)
        st.write(f"**Total Trees Planted:** {user.get('total_trees_planted', 0)}")
        st.write(f"**Total CO₂ Sequestered:** {user.get('total_co2_sequestered', 0.0):.2f} kg")

        if check_firebase_user_role(user, 'individual'):
            st.info("As an individual, you can plant trees and monitor their growth.")
            # Add features for individual users (e.g., list their trees)
        elif check_firebase_user_role(user, 'institution'):
            st.info("As an institution, you can view your overall planting impact and manage users.")
            # Add features for institution users (e.g., aggregate data, link to admin approval)

        # Placeholder for tree data associated with the user's tree_tracking_id
        st.subheader("Your Planted Trees")
        current_user_tree_tracking_id = user.get('tree_tracking_number')

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

def admin_dashboard_content():
    st.title("Admin Dashboard")
    user = st.session_state.get('user')

    if user and check_firebase_user_role(user, 'admin'):
        st.info("Welcome to the Admin Dashboard. Here you can manage users, view aggregate data, and process submissions.")

        tab1, tab2, tab3 = st.tabs(["User Management", "Data Overview", "Process Submissions"])

        with tab1:
            st.subheader("User Management & Approval")
            st.warning("User management features (e.g., approval queue) coming soon!")
            # Example if admin_approval_dashboard exists in firebase_auth_integration:
            # if 'admin_approval_dashboard' in globals():
            #     admin_approval_dashboard()
            # else:
            #     st.info("Admin approval dashboard module not loaded.")

        with tab2:
            st.subheader("Overall Data Overview")
            conn = sqlite3.connect(SQLITE_DB)
            try:
                df_trees = pd.read_sql_query("SELECT * FROM trees", conn)
                df_users = pd.read_sql_query("SELECT * FROM user_profiles", conn)

                st.write(f"Total Registered Users: {len(df_users)}")
                st.write(f"Total Trees Planted: {len(df_trees)}")
                st.write(f"Total CO₂ Sequestered (all trees): {df_trees['co2_kg'].sum() if not df_trees.empty else 0:.2f} kg")

                if not df_trees.empty:
                    st.subheader("Tree Status Distribution")
                    fig_status = px.pie(df_trees, names='status', title='Distribution of Tree Status')
                    st.plotly_chart(fig_status, use_container_width=True)

                    st.subheader("Trees Planted Over Time")
                    df_trees['date_planted'] = pd.to_datetime(df_trees['date_planted'])
                    trees_per_month = df_trees.groupby(df_trees['date_planted'].dt.to_period('M')).size().reset_index(name='count')
                    trees_per_month['date_planted'] = trees_per_month['date_planted'].astype(str) # For plotting
                    fig_time = px.line(trees_per_month, x='date_planted', y='count', title='Trees Planted Per Month')
                    st.plotly_chart(fig_time, use_container_width=True)

            except Exception as e:
                st.error(f"Error loading admin dashboard data: {e}")
            finally:
                conn.close()

        with tab3:
            st.subheader("Process New KoBo Submissions")
            st.info("Use this section to manually trigger processing of new tree planting or monitoring submissions.")

            planting_hours = st.slider("Check planting submissions (hours ago)", 1, 168, 24, key="planting_slider")
            if st.button("Process New Planting Submissions", key="process_planting_btn"):
                with st.spinner("Checking for new planting data..."):
                    # Pass None for user_id to process all submissions for admin
                    new_planting_submissions = check_for_new_submissions(user_id=None, hours=planting_hours)
                    if new_planting_submissions:
                        st.success(f"Processed {len(new_planting_submissions)} new planting records.")
                    else:
                        st.info("No new planting records found.")

            monitoring_hours = st.slider("Check monitoring submissions (hours ago)", 1, 168, 24, key="monitoring_slider")
            if st.button("Process New Monitoring Submissions", key="process_monitoring_btn"):
                with st.spinner("Checking for new monitoring data..."):
                    new_monitoring_submissions = check_for_new_monitoring_submissions(hours=monitoring_hours)
                    if new_monitoring_submissions:
                        st.success(f"Processed {len(new_monitoring_submissions)} new monitoring records.")
                    else:
                        st.info("No new monitoring records found.")

            st.markdown("---")
            st.subheader("Maintenance Tools")
            st.warning("Maintenance tools coming soon!")
    else:
        st.error("Access denied. Admin privileges required.")

def main():
    """Main application function to orchestrate the Streamlit app."""

    # Apply custom CSS first
    set_custom_css()

    # Check and update user session
    if 'user' not in st.session_state or not st.session_state.authenticated:
        get_active_user_and_update_state() # Attempt to get user if authenticated flag is set

    # Sidebar Navigation
    with st.sidebar:
        st.header("Navigation")
        menu_options = ["Home", "Donor Dashboard"]

        # Add authenticated user options
        if not st.session_state.authenticated:
            menu_options.extend(["Login", "Sign Up"])
        else:
            menu_options.extend(["User Dashboard", "Plant a Tree", "Monitor Trees"])

            # Admin-specific pages (assuming 'admin' role has higher access than 'institution' here)
            user = st.session_state.get('user')
            if user and check_firebase_user_role(user, 'admin'):
                menu_options.append("Admin Dashboard")

        st.session_state.page = st.selectbox(
            "Go to",
            menu_options,
            index=menu_options.index(st.session_state.page) if st.session_state.page in menu_options else 0
        )

        if st.session_state.authenticated:
            if st.button("Logout", type="secondary"):
                firebase_logout()
                st.session_state.page = "Login" # Redirect to login after logout
                st.success("Logged out successfully!")
                st.rerun()

    # Page Routing
    if st.session_state.page == "Home":
        show_landing_page()
    elif st.session_state.page == "Login":
        firebase_login_ui()
    elif st.session_state.page == "Sign Up":
        firebase_signup_ui()
    elif st.session_state.page == "Donor Dashboard":
        guest_donor_dashboard_ui() # This is the function from donor_dashboard.py
    elif st.session_state.authenticated:
        if st.session_state.page == "User Dashboard":
            unified_user_dashboard_content()
        elif st.session_state.page == "Plant a Tree":
            plant_a_tree_section() # This is the function from kobo_integration.py
        elif st.session_state.page == "Monitor Trees":
            monitoring_section() # This is the function from kobo_monitoring.py
        elif st.session_state.page == "Admin Dashboard":
            admin_dashboard_content() # This is the local function in app.py
    else:
        st.warning("Please log in to access this page")
        st.session_state.page = "Login"
        st.rerun()

    # Footer
    add_branding_footer()


if __name__ == "__main__":
    main()
