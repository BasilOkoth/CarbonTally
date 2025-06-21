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
        get_tree_details, # Ensure this is also in kobo_monitoring.py if used directly
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

# Initialize directories
DATA_DIR.mkdir(exist_ok=True, parents=True)

# --- Streamlit Configuration ---
st.set_page_config(
    page_title="CarbonTally Tree Tracking",
    page_icon="🌳",
    layout="wide",
    initial_sidebar_state="expanded" # Keep sidebar expanded by default
)

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
    st.title("Welcome to CarbonTally! 🌳")
    st.markdown("""
        **CarbonTally** is a platform dedicated to tracking and monitoring tree planting initiatives.
        We provide tools for individuals, schools, and institutions to record tree data,
        track their growth, estimate CO2 sequestration, and engage in a community committed to a greener future.
    """)

    st.subheader("Our Mission")
    st.markdown("""
        To empower communities with transparent and verifiable data on tree planting efforts,
        fostering environmental stewardship and combating climate change one tree at a time.
    """)

    st.subheader("Key Features")
    st.markdown("""
    * **🌲 Tree Planting:** Record new tree data easily via KoBo forms.
    * **📈 Tree Monitoring:** Track the growth and health of planted trees over time.
    * **📊 CO₂ Sequestration:** Estimate the carbon impact of your trees.
    * **🏅 Leaderboards & Badges:** Gamified engagement for planters.
    * **🌍 Donor Dashboard:** Transparent impact tracking for donors.
    * **🔒 Secure Authentication:** Manage user accounts with Firebase.
    """)

    st.subheader("Get Started")
    st.markdown("""
    * **New Users:** [Sign Up](#sign-up) to start planting and monitoring trees!
    * **Existing Users:** [Login](#login) to access your dashboard.
    * **Donors:** Explore the [Donor Dashboard](#donor-dashboard) to see our impact and support initiatives.
    """)

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
        current_user_tree_tracking_id = user.get('tree_tracking_number') # Corrected from tree_tracking_id to tree_tracking_number

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
            # This would link to or embed the admin_approval_dashboard from firebase_auth_integration
            # Assuming admin_approval_dashboard is imported from firebase_auth_integration
            # You might need to import admin_approval_dashboard from firebase_auth_integration
            # and call it here. For now, it's a placeholder.
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
            # You'll need `bulk_update_co2_calculations` and `update_user_statistics` in your utility functions
            st.warning("Maintenance tools coming soon!")
            # if st.button("🔄 Update All CO₂ Calculations", type="primary"):
            #     with st.spinner("Updating CO₂ calculations..."):
            #         updated_count = bulk_update_co2_calculations()
            #         st.success(f"Updated CO₂ calculations for {updated_count} trees!")

            # if st.button("📊 Refresh User Statistics"):
            #     with st.spinner("Refreshing user statistics..."):
            #         conn = sqlite3.connect(SQLITE_DB)
            #         try:
            #             users = pd.read_sql("SELECT DISTINCT COALESCE(planter_email, student_name) as user_email FROM trees WHERE COALESCE(planter_email, student_name) != ''", conn)
            #             updated_users = 0
            #             for _, user_row in users.iterrows():
            #                 if update_user_statistics(user_row["user_email"]):
            #                     updated_users += 1
            #             st.success(f"Updated statistics for {updated_users} users!")
            #         finally:
            #             conn.close()
    else:
        st.error("Access denied. Admin privileges required.")

def main():
    """Main application function to orchestrate the Streamlit app."""

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
