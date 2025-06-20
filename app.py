import streamlit as st
import pandas as pd
import sqlite3
from pathlib import Path
from typing import Optional, Dict
import time

# Database configuration
BASE_DIR = Path(__file__).parent if "__file__" in locals() else Path.cwd()
DATA_DIR = BASE_DIR / "data"
SQLITE_DB = DATA_DIR / "trees.db"

# Custom module imports
try:
    from firebase_auth_integration import (
        firebase_login_ui, firebase_signup_ui, firebase_password_recovery_ui,
        firebase_logout, check_firebase_user_role, initialize_firebase,
        admin_approval_dashboard, get_current_firebase_user
    )
    FIREBASE_AVAILABLE = True
except ImportError as e:
    st.error(f"Firebase Auth Integration Error: {str(e)}")
    FIREBASE_AVAILABLE = False

# Initialize directories
DATA_DIR.mkdir(exist_ok=True, parents=True)

# --- Streamlit Configuration ---
st.set_page_config(
    page_title="CarbonTally Tree Tracking",
    page_icon="🌳",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- Custom CSS Styling ---
def load_custom_css():
    st.markdown(f"""
    <style>
        /* Main Layout */
        .stApp {{
            background-color: #f8f9fa;
        }}
        
        /* Header Styles */
        .landing-header {{
            background: linear-gradient(135deg, #1D7749 0%, #28a745 100%);
            color: white;
            padding: 3rem;
            text-align: center;
            border-radius: 15px;
            margin-bottom: 2rem;
            box-shadow: 0 4px 12px rgba(0,0,0,0.1);
        }}
        
        /* Metric Cards */
        .metric-card {{
            background: white;
            border-radius: 10px;
            padding: 1.5rem;
            margin: 1rem;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
            text-align: center;
            transition: transform 0.3s ease;
        }}
        .metric-card:hover {{
            transform: translateY(-5px);
            box-shadow: 0 6px 12px rgba(0,0,0,0.15);
        }}
        .metric-value {{
            font-size: 2.5rem;
            font-weight: bold;
            color: #28a745;
            margin: 0.5rem 0;
        }}
        .metric-label {{
            font-size: 1rem;
            color: #555;
        }}
        
        /* Feature Cards */
        .feature-card {{
            background: white;
            border-left: 4px solid #28a745;
            border-radius: 8px;
            padding: 1.5rem;
            margin-bottom: 1.5rem;
            box-shadow: 0 2px 6px rgba(0,0,0,0.05);
        }}
        
        /* Buttons */
        .stButton>button {{
            background-color: #28a745;
            color: white;
            border-radius: 8px;
            padding: 0.5rem 1rem;
            font-weight: 500;
        }}
        
        /* Responsive Grid */
        @media (max-width: 768px) {{
            .metric-grid {{
                grid-template-columns: repeat(2, 1fr) !important;
            }}
        }}
    </style>
    """, unsafe_allow_html=True)

# --- Database Helpers ---
def get_metrics_from_db():
    """Fetch all metrics from database"""
    conn = sqlite3.connect(SQLITE_DB)
    try:
        # Tree metrics
        trees_planted = pd.read_sql("SELECT COUNT(*) FROM trees", conn).iloc[0,0]
        trees_alive = pd.read_sql("SELECT COUNT(*) FROM trees WHERE status='Alive'", conn).iloc[0,0]
        total_co2 = pd.read_sql("SELECT SUM(co2_kg) FROM trees", conn).iloc[0,0] or 0
        
        # User metrics
        institutions = pd.read_sql("SELECT COUNT(*) FROM institutions", conn).iloc[0,0]
        individuals = pd.read_sql("SELECT COUNT(DISTINCT student_name) FROM trees", conn).iloc[0,0]
        
        return {
            "trees_planted": trees_planted,
            "trees_alive": trees_alive,
            "total_co2": round(total_co2, 2),
            "institutions": institutions,
            "individuals": individuals,
            "survival_rate": round((trees_alive / trees_planted * 100) if trees_planted > 0 else 0, 1)
        }
    except Exception as e:
        st.error(f"Database error: {str(e)}")
        return None
    finally:
        conn.close()

# --- Landing Page ---
def show_landing_page():
    """Display the enhanced landing page with metrics"""
    load_custom_css()
    
    # Header Section
    st.markdown("""
    <div class="landing-header">
        <h1 style="font-size: 3rem; margin-bottom: 1rem;">Welcome to CarbonTally 🌱</h1>
        <p style="font-size: 1.2rem; opacity: 0.9;">
            Track your tree planting impact and contribute to a sustainable future
        </p>
    </div>
    """, unsafe_allow_html=True)
    
    # Metrics Section
    metrics = get_metrics_from_db()
    if metrics:
        col1, col2, col3, col4, col5 = st.columns(5)
        
        with col1:
            st.markdown(f"""
            <div class="metric-card">
                <div class="metric-value">{metrics['trees_planted']}</div>
                <div class="metric-label">Trees Planted</div>
            </div>
            """, unsafe_allow_html=True)
            
        with col2:
            st.markdown(f"""
            <div class="metric-card">
                <div class="metric-value">{metrics['trees_alive']}</div>
                <div class="metric-label">Trees Thriving</div>
            </div>
            """, unsafe_allow_html=True)
            
        with col3:
            st.markdown(f"""
            <div class="metric-card">
                <div class="metric-value">{metrics['survival_rate']}%</div>
                <div class="metric-label">Survival Rate</div>
            </div>
            """, unsafe_allow_html=True)
            
        with col4:
            st.markdown(f"""
            <div class="metric-card">
                <div class="metric-value">{metrics['total_co2']} kg</div>
                <div class="metric-label">CO₂ Sequestered</div>
            </div>
            """, unsafe_allow_html=True)
            
        with col5:
            st.markdown(f"""
            <div class="metric-card">
                <div class="metric-value">{metrics['institutions'] + metrics['individuals']}</div>
                <div class="metric-label">Active Contributors</div>
            </div>
            """, unsafe_allow_html=True)
    
    # Features Section
    st.markdown("---")
    st.header("Our Impact")
    
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("""
        <div class="feature-card">
            <h3>🌍 Environmental Impact</h3>
            <p>Every tree planted contributes to carbon sequestration, 
            biodiversity preservation, and ecosystem restoration.</p>
        </div>
        """, unsafe_allow_html=True)
        
    with col2:
        st.markdown("""
        <div class="feature-card">
            <h3>👥 Community Engagement</h3>
            <p>Join {metrics['institutions']} institutions and {metrics['individuals']} 
            individuals making a difference in their communities.</p>
        </div>
        """, unsafe_allow_html=True)
    
    # Call to Action
    st.markdown("---")
    st.header("Ready to Make a Difference?")
    
    if not st.session_state.get('authenticated'):
        col1, col2 = st.columns(2)
        with col1:
            if st.button("Join as Individual", use_container_width=True):
                st.session_state.page = "Sign Up"
                st.rerun()
        with col2:
            if st.button("Register Your Institution", use_container_width=True):
                st.session_state.page = "Sign Up"
                st.rerun()
    else:
        if st.button("Go to Your Dashboard →", use_container_width=True):
            st.session_state.page = "User Dashboard"
            st.rerun()

# --- Main App Logic ---
def main():
    # Initialize session state
    if 'page' not in st.session_state:
        st.session_state.page = "Home"
    if 'authenticated' not in st.session_state:
        st.session_state.authenticated = False
    
    # Initialize Firebase
    if FIREBASE_AVAILABLE and not st.session_state.get('firebase_initialized'):
        st.session_state.firebase_initialized = initialize_firebase() is not None
    
    # Sidebar Navigation
    with st.sidebar:
        st.image("https://via.placeholder.com/150x50?text=CarbonTally", use_column_width=True)
        st.title("Navigation")
        
        if st.session_state.get('authenticated'):
            user = st.session_state.get('user', {})
            st.write(f"Welcome, {user.get('email', 'User')}!")
            
            if st.button("Logout"):
                firebase_logout()
                st.rerun()
        
        menu_options = ["Home", "Donor Dashboard"]
        if not st.session_state.authenticated:
            menu_options.extend(["Login", "Sign Up"])
        else:
            menu_options.extend(["User Dashboard", "Plant a Tree", "Monitor Trees"])
            if check_firebase_user_role(st.session_state.user, 'institution'):
                menu_options.append("Admin Dashboard")
        
        st.session_state.page = st.selectbox(
            "Go to", 
            menu_options,
            index=menu_options.index(st.session_state.page) 
            if st.session_state.page in menu_options else 0
        )
    
    # Page Routing
    if st.session_state.page == "Home":
        show_landing_page()
    elif st.session_state.page == "Login":
        firebase_login_ui()
    elif st.session_state.page == "Sign Up":
        firebase_signup_ui()
    elif st.session_state.page == "Donor Dashboard":
        donor_dashboard()
    elif st.session_state.authenticated:
        if st.session_state.page == "User Dashboard":
            unified_user_dashboard_content()
        elif st.session_state.page == "Plant a Tree":
            plant_a_tree_section()
        elif st.session_state.page == "Monitor Trees":
            monitoring_section()
        elif st.session_state.page == "Admin Dashboard":
            if check_firebase_user_role(st.session_state.user, 'institution'):
                admin_approval_dashboard()
            else:
                st.error("Admin access requires institution role")
                st.session_state.page = "Home"
                st.rerun()
    else:
        st.warning("Please log in to access this page")
        st.session_state.page = "Login"
        st.rerun()

if __name__ == "__main__":
    main()
