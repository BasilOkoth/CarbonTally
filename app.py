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
        
        /* User Welcome */
        .user-welcome {{
            font-size: 1.8rem;
            color: #1D7749;
            margin-bottom: 1.5rem;
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
        
        /* Tree Table */
        .tree-table {{
            margin-top: 2rem;
        }}
    </style>
    """, unsafe_allow_html=True)

# --- Database Helpers ---
def get_metrics_from_db():
    """Fetch all metrics from database with corrected column names"""
    conn = None
    try:
        conn = sqlite3.connect(SQLITE_DB)
        cursor = conn.cursor()
        
        # Get all column names to check what's available
        cursor.execute("PRAGMA table_info(trees)")
        columns = [column[1] for column in cursor.fetchall()]
        
        # Tree metrics
        trees_planted = pd.read_sql("SELECT COUNT(*) FROM trees", conn).iloc[0,0]
        trees_alive = pd.read_sql("SELECT COUNT(*) FROM trees WHERE status='Alive'", conn).iloc[0,0]
        total_co2 = pd.read_sql("SELECT SUM(co2_kg) FROM trees", conn).iloc[0,0] or 0
        
        # User metrics - checking for available planter identifier columns
        institutions = pd.read_sql("SELECT COUNT(*) FROM institutions", conn).iloc[0,0]
        
        # Check which planter identifier column exists
        planter_column = None
        for col in ['planter_name', 'planter_id', 'adopter_name', 'user_id']:
            if col in columns:
                planter_column = col
                break
                
        if planter_column:
            individuals = pd.read_sql(f"SELECT COUNT(DISTINCT {planter_column}) FROM trees", conn).iloc[0,0]
        else:
            individuals = 0
        
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
        # Return default values if query fails
        return {
            "trees_planted": 0,
            "trees_alive": 0,
            "total_co2": 0,
            "institutions": 0,
            "individuals": 0,
            "survival_rate": 0
        }
    finally:
        if conn:
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
    
    col1, col2, col3, col4, col5 = st.columns(5)
    
    metric_data = [
        {"value": metrics['trees_planted'], "label": "Trees Planted"},
        {"value": metrics['trees_alive'], "label": "Trees Thriving"},
        {"value": f"{metrics['survival_rate']}%", "label": "Survival Rate"},
        {"value": f"{metrics['total_co2']} kg", "label": "CO₂ Sequestered"},
        {"value": metrics['institutions'] + metrics['individuals'], "label": "Active Contributors"}
    ]
    
    for i, col in enumerate([col1, col2, col3, col4, col5]):
        with col:
            st.markdown(f"""
            <div class="metric-card">
                <div class="metric-value">{metric_data[i]['value']}</div>
                <div class="metric-label">{metric_data[i]['label']}</div>
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
        st.markdown(f"""
        <div class="feature-card">
            <h3>👥 Community Engagement</h3>
            <p>Join {metrics['institutions']} institutions and {metrics['individuals']} 
            planters making a difference in their communities.</p>
        </div>
        """, unsafe_allow_html=True)
    
    # Call to Action
    st.markdown("---")
    st.header("Ready to Make a Difference?")
    
    if not st.session_state.get('authenticated'):
        col1, col2 = st.columns(2)
        with col1:
            if st.button("Join as Planter", use_container_width=True):
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

# --- User Dashboard ---
def unified_user_dashboard_content():
    """Complete user dashboard with personalized welcome"""
    if not st.session_state.get('authenticated'):
        st.warning("Please log in to access your dashboard")
        st.session_state.page = "Login"
        st.rerun()
        return

    user = st.session_state.user
    user_name = user.get('fullName', user.get('displayName', user.get('email', 'User')))
    
    # Personalized welcome
    st.markdown(f"""
    <div class="user-welcome">
        Welcome back, <strong>{user_name.split(' ')[0]}</strong>! 🌟
    </div>
    """, unsafe_allow_html=True)
    
    # User stats header
    cols = st.columns(3)
    with cols[0]:
        st.metric("Account Type", user.get('role', 'individual').capitalize())
    with cols[1]:
        st.metric("Member Since", user.get('join_date', 'N/A'))
    with cols[2]:
        st.metric("Tree Tracking ID", user.get('tree_tracking_number', 'Not assigned'))
    
    st.markdown("---")
    
    # Get user-specific tree data
    conn = sqlite3.connect(SQLITE_DB)
    try:
        # Check which planter identifier column exists
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(trees)")
        columns = [column[1] for column in cursor.fetchall()]
        
        user_trees = pd.DataFrame()
        if 'planter_tracking_id' in columns:
            user_trees = pd.read_sql(
                f"SELECT * FROM trees WHERE planter_tracking_id = '{user.get('tree_tracking_number', '')}'", 
                conn
            )
        elif 'planter_name' in columns:
            user_trees = pd.read_sql(
                f"SELECT * FROM trees WHERE planter_name = '{user_name}'", 
                conn
            )
        
        if not user_trees.empty:
            # Trees summary metrics
            st.subheader("🌳 Your Tree Planting Impact")
            stat_cols = st.columns(4)
            with stat_cols[0]:
                st.metric("Total Planted", len(user_trees))
            with stat_cols[1]:
                alive = user_trees[user_trees['status'] == 'Alive'].shape[0]
                st.metric("Trees Thriving", alive)
            with stat_cols[2]:
                st.metric("Survival Rate", f"{round(alive/len(user_trees)*100, 1)}%")
            with stat_cols[3]:
                total_co2 = user_trees['co2_kg'].sum()
                st.metric("CO₂ Sequestered", f"{round(total_co2, 2)} kg")
            
            # Tree data table
            st.subheader("Your Trees")
            st.dataframe(
                user_trees[['tree_id', 'local_name', 'scientific_name', 
                           'date_planted', 'status', 'co2_kg']],
                use_container_width=True
            )
            
            # Monitoring history
            st.subheader("📊 Monitoring History")
            monitoring_data = pd.read_sql(
                f"SELECT * FROM monitoring_history WHERE tree_id IN ({','.join(['?']*len(user_trees))})",
                conn,
                params=user_trees['tree_id'].tolist()
            )
            if not monitoring_data.empty:
                st.dataframe(monitoring_data, use_container_width=True)
            else:
                st.info("No monitoring records found for your trees")
        else:
            st.info("You haven't planted any trees yet")
            if st.button("Plant Your First Tree 🌱"):
                st.session_state.page = "Plant a Tree"
                st.rerun()
                
    except Exception as e:
        st.error(f"Error loading your data: {str(e)}")
    finally:
        conn.close()
    
    # Quick actions
    st.markdown("---")
    st.subheader("Quick Actions")
    action_cols = st.columns(3)
    with action_cols[0]:
        if st.button("🌱 Plant New Tree"):
            st.session_state.page = "Plant a Tree"
            st.rerun()
    with action_cols[1]:
        if st.button("🔍 Monitor Trees"):
            st.session_state.page = "Monitor Trees"
            st.rerun()
    with action_cols[2]:
        if st.button("📜 View Certificates"):
            st.session_state.page = "Certificates"
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
        st.image("https://via.placeholder.com/150x50?text=CarbonTally", use_container_width=True)
        st.title("Navigation")
        
        if st.session_state.get('authenticated'):
            user = st.session_state.get('user', {})
            user_name = user.get('fullName', user.get('displayName', user.get('email', 'User')))
            st.write(f"Hi, {user_name.split(' ')[0]}! 👋")
            
            if st.button("Logout"):
                firebase_logout()
                st.rerun()
        
        menu_options = ["Home", "Donor Dashboard"]
        if not st.session_state.authenticated:
            menu_options.extend(["Login", "Sign Up"])
        else:
            menu_options.extend(["User Dashboard", "Plant a Tree", "Monitor Trees"])
        
        st.session_state.page = st.selectbox(
            "Go to", 
            menu_options,
            index=menu_options.index(st.session_state.page) if st.session_state.page in menu_options else 0
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
    else:
        st.warning("Please log in to access this page")
        st.session_state.page = "Login"
        st.rerun()

# Placeholder functions for unimplemented sections
def donor_dashboard():
    st.warning("Donor dashboard coming soon!")

def plant_a_tree_section():
    st.warning("Tree planting section coming soon!")

def monitoring_section():
    st.warning("Monitoring section coming soon!")

if __name__ == "__main__":
    main()
