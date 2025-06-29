import streamlit as st
from pathlib import Path
import sqlite3
import pandas as pd
import plotly.express as px
import qrcode
from datetime import datetime
import re
from kobo_integration import initialize_database

# Initialize database
initialize_database()

# Streamlit page config - MUST BE THE VERY FIRST STREAMLIT COMMAND
st.set_page_config(
    page_title="CarbonTally",
    page_icon="🌳",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- Paths and Constants ---
BASE_DIR = Path(__file__).parent if "__file__" in locals() else Path.cwd()
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True, parents=True)
SQLITE_DB = DATA_DIR / "trees.db"
QR_CODE_DIR = DATA_DIR / "qr_codes"
QR_CODE_DIR.mkdir(exist_ok=True, parents=True)

# --- Database Helper Functions ---
def get_db_connection():
    return sqlite3.connect(SQLITE_DB)

def get_table_columns(cursor, table_name):
    cursor.execute(f"PRAGMA table_info({table_name})")
    return [col[1] for col in cursor.fetchall()]

# --- Database Initialization ---
def init_db():
    conn = get_db_connection()
    try:
        c = conn.cursor()
        # Create tables and initialize data
        # ... (keep your existing database initialization code)
        pass
    except Exception as e:
        st.error(f"Database initialization failed: {e}")
        raise
    finally:
        conn.close()

# --- Database Initialization & Migration ---
def ensure_database():
    """Ensures database is properly initialized and migrated"""
    init_db()
    migrate_db_schema()

# --- Helper Functions (e.g., for loading tree data) ---
def load_tree_data():
    """Load all tree data from database"""
    conn = get_db_connection()
    try:
        df = pd.read_sql_query("SELECT * FROM trees", conn)
    except pd.io.sql.DatabaseError:
        df = pd.DataFrame() # Return empty DataFrame on error
    finally:
        conn.close()
    return df

def init_db():
    """Initialize database with required tables"""
    conn = get_db_connection()
    try:
        c = conn.cursor()

        # Create 'species' table
        c.execute("""
            CREATE TABLE IF NOT EXISTS species (
                scientific_name TEXT PRIMARY KEY,
                local_name TEXT,
                wood_density REAL,
                benefits TEXT
            )
        """)

        # Create 'institutions' table
        c.execute("""
            CREATE TABLE IF NOT EXISTS institutions (
                id TEXT PRIMARY KEY,
                name TEXT,
                join_date TEXT
            )
        """)

        # Create 'sequences' table
        c.execute("""
            CREATE TABLE IF NOT EXISTS sequences (
                prefix TEXT PRIMARY KEY,
                next_val INTEGER
            )
        """)

        # Create 'monitoring_history' table
        c.execute("""
            CREATE TABLE IF NOT EXISTS monitoring_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tree_id TEXT,
                monitor_date TEXT,
                monitor_status TEXT,
                monitor_stage TEXT,
                height_m REAL,
                dbh_cm REAL,
                rcd_cm REAL,
                co2_kg REAL,
                FOREIGN KEY (tree_id) REFERENCES trees (tree_id)
            )
        """)

        # Insert default species if empty
        c.execute("SELECT COUNT(*) FROM species")
        if c.fetchone()[0] == 0:
            default_species = [
                ("Acacia spp.", "Acacia", 0.65, "Drought-resistant, nitrogen-fixing, provides shade"),
                ("Eucalyptus spp.", "Eucalyptus", 0.55, "Fast-growing, timber production, medicinal uses"),
                ("Mangifera indica", "Mango", 0.50, "Fruit production, shade tree, ornamental"),
                ("Azadirachta indica", "Neem", 0.60, "Medicinal properties, insect repellent, drought-resistant")
            ]
            c.executemany("INSERT INTO species VALUES (?, ?, ?, ?)", default_species)

        conn.commit()
    except Exception as e:
        st.error(f"Database initialization failed: {e}")
        raise
    finally:
        conn.close()

def migrate_db_schema():
    """Migrate database schema if needed"""
    conn = get_db_connection()
    try:
        conn.execute("BEGIN IMMEDIATE TRANSACTION")
        c = conn.cursor()

        c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='trees';")
        if c.fetchone() is None:
            st.info("No 'trees' table found, initializing database from scratch.")
            conn.commit()
            return

        current_columns = get_table_columns(c, "trees")

        target_schema_columns = {
            'tree_id': 'TEXT PRIMARY KEY',
            'form_uuid': 'TEXT UNIQUE',
            'tree_tracking_number': 'TEXT NOT NULL',
            'institution': 'TEXT',
            'local_name': 'TEXT',
            'scientific_name': 'TEXT',
            'planter_id': 'TEXT',
            'planters_name': 'TEXT',
            'planter_email': 'TEXT',
            'planter_uid': 'TEXT',
            'date_planted': 'TEXT',
            'tree_stage': 'TEXT',
            'rcd_cm': 'REAL',
            'dbh_cm': 'REAL',
            'height_m': 'REAL',
            'co2_kg': 'REAL',
            'status': 'TEXT',
            'qr_code': 'TEXT',
            'kobo_submission_id': 'TEXT UNIQUE',
            'last_updated': 'TEXT',
            'country': 'TEXT',
            'county': 'TEXT',
            'sub_county': 'TEXT',
            'ward': 'TEXT',
            'adopter_name': 'TEXT',
            'organization_name': 'TEXT',
            'latitude': 'REAL',
            'longitude': 'REAL'
        }

        needs_major_migration = (
            'planter_tracking_id' in current_columns and 'tree_tracking_number' not in current_columns
        ) or any(col not in current_columns for col in target_schema_columns.keys())

        if needs_major_migration:
            st.info("Migrating: Performing major schema upgrade for 'trees' table.")

            create_cols_sql = ",\n    ".join([f"{col} {dtype}" for col, dtype in target_schema_columns.items()])
            c.execute(f"""
                CREATE TABLE trees_temp (
                    {create_cols_sql}
                )
            """)

            select_parts = []
            insert_parts = []
            column_mapping_from_old_to_new = {
                'planter_tracking_id': 'tree_tracking_number',
            }
            reverse_map = {v: k for k, v in column_mapping_from_old_to_new.items()}

            for new_col in target_schema_columns:
                insert_parts.append(new_col)
                old_col = reverse_map.get(new_col, new_col)
                select_parts.append(old_col if old_col in current_columns else "NULL")

            c.execute(f"""
                INSERT INTO trees_temp ({', '.join(insert_parts)})
                SELECT {', '.join(select_parts)} FROM trees;
            """)

            c.execute("DROP TABLE trees")
            c.execute("ALTER TABLE trees_temp RENAME TO trees")
            st.success("Database 'trees' table schema updated successfully!")
            current_columns = get_table_columns(c, "trees")

        for col, dtype in target_schema_columns.items():
            if col not in current_columns:
                st.info(f"Migrating: Adding '{col}' column to 'trees' table.")
                c.execute(f"ALTER TABLE trees ADD COLUMN {col} {dtype};")
                if 'UNIQUE' in dtype.upper() and col not in ['tree_id']:
                    c.execute(f"UPDATE trees SET {col} = LOWER(HEX(RANDOMBLOB(8))) WHERE {col} IS NULL;")
                elif 'NOT NULL' in dtype.upper():
                    c.execute(f"UPDATE trees SET {col} = '' WHERE {col} IS NULL;")

        conn.commit()

    except Exception as e:
        conn.rollback()
        st.error(f"Migration failed: {e}")
        init_db()
        raise
    finally:
        conn.close()

# --- Custom Module Imports with Error Handling ---
try:
    from unified_user_dashboard import (
        unified_user_dashboard as unified_user_dashboard_content,
    )
except ImportError as e:
    st.error(f"Unified User Dashboard module or its components not found: {e}. Ensure unified_user_dashboard.py exists and is correctly configured.")
    # Fallback dummies if module is missing
    def unified_user_dashboard_content(): st.warning("User dashboard coming soon!")
    def plant_a_tree_section(): st.warning("Tree planting section coming soon!")
    def monitoring_section(): st.warning("Monitoring section coming soon!")
    def generate_qr_code(tree_id): return None, None 
    def get_kobo_secrets(): return None, None, None, None 

try:
    from donor_dashboard import guest_donor_dashboard_ui
except ImportError:
    def guest_donor_dashboard_ui(): st.warning("Donor dashboard coming soon!")

try:
    from unified_user_dashboard_FINAL import unified_user_dashboard_content
    from kobo_integration import plant_a_tree_section, generate_qr_code, get_kobo_secrets
    from kobo_monitoring import monitoring_section
except ImportError as e:
    st.error(f"Error importing modules: {e}")

# Firebase imports
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
        get_all_users, # Used in admin_dashboard_content
        approve_user,
        reject_user,
        delete_user,
        send_approval_email,
        send_rejection_email
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
    def get_all_users(): return []
    def approve_user(uid): pass
    def reject_user(uid): pass
    def delete_user(uid): pass
    def send_approval_email(user): pass
    def send_rejection_email(user): pass

# --- Custom CSS ---
def set_custom_css():
    """Set beautiful, modern CSS styles for the app"""
    st.markdown("""
    <style>
        /* Modern Color Palette */
        :root {
            --primary: #1D7749;
            --primary-light: #28a745;
            --secondary: #6c757d;
            --light: #f8f9fa;
            --dark: #343a40;
            --success: #28a745;
            --info: #17a2b8;
            --warning: #ffc107;
            --danger: #dc3545;
        }
        
        /* Main App Container */
        .main .block-container {
            padding-top: 2rem;
            padding-bottom: 2rem;
            max-width: 1200px;
        }
        
        /* Landing Page Header */
        .landing-header {
            background: linear-gradient(135deg, var(--primary) 0%, var(--primary-light) 100%);
            color: white;
            padding: 4rem 1rem;
            border-radius: 0 0 20px 20px;
            box-shadow: 0 4px 20px rgba(0,0,0,0.1);
            text-align: center;
            margin-bottom: 3rem;
        }
        
        .landing-header h1 {
            font-size: 3.5rem;
            margin-bottom: 0.5rem;
            font-weight: 800;
            text-shadow: 1px 1px 3px rgba(0,0,0,0.2);
        }
        
        .landing-header p {
            font-size: 1.2rem;
            max-width: 800px;
            margin: 0 auto 1.5rem auto;
            opacity: 0.9;
        }
        
        /* Metric Cards */
        .metric-card {
            background: white;
            border-radius: 12px;
            padding: 1.5rem;
            box-shadow: 0 4px 12px rgba(0,0,0,0.05);
            text-align: center;
            margin-bottom: 1rem;
            height: 100%;
            transition: all 0.3s ease;
            border: 1px solid rgba(0,0,0,0.05);
        }
        
        .metric-card:hover {
            transform: translateY(-5px);
            box-shadow: 0 8px 20px rgba(0,0,0,0.1);
        }
        
        .metric-value {
            font-size: 2.2rem;
            font-weight: 700;
            color: var(--primary);
            margin: 0.5rem 0;
            line-height: 1;
        }
        
        .metric-label {
            font-size: 0.9rem;
            color: var(--secondary);
            margin-bottom: 0.5rem;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            font-weight: 600;
        }
        
        /* Feature Cards */
        .feature-card {
            background: white;
            border-radius: 12px;
            padding: 1.8rem;
            box-shadow: 0 4px 12px rgba(0,0,0,0.05);
            margin-bottom: 1.5rem;
            height: 100%;
            transition: all 0.3s ease;
            border: 1px solid rgba(0,0,0,0.05);
        }
        
        .feature-card:hover {
            transform: translateY(-3px);
            box-shadow: 0 8px 20px rgba(0,0,0,0.1);
        }
        
        .feature-card h3 {
            color: var(--primary);
            margin-top: 0;
            margin-bottom: 1rem;
            font-size: 1.4rem;
        }
        
        .feature-card p {
            color: var(--secondary);
            font-size: 0.95rem;
            line-height: 1.6;
        }
        
        /* Recent Activity */
        .activity-item {
            padding: 1.2rem;
            margin-bottom: 0.8rem;
            border-radius: 10px;
            background-color: white;
            box-shadow: 0 2px 8px rgba(0,0,0,0.05);
            transition: all 0.3s ease;
            border-left: 4px solid var(--primary);
        }
        
        .activity-item:hover {
            transform: translateY(-2px);
            box-shadow: 0 4px 12px rgba(0,0,0,0.1);
        }
        
        .activity-highlight {
            font-weight: 700;
            color: var(--primary);
        }
        
        .activity-meta {
            font-size: 0.85rem;
            color: var(--secondary);
            margin-top: 0.5rem;
            display: flex;
            align-items: center;
            gap: 0.8rem;
        }
        
        .activity-content {
            margin-bottom: 0.3rem;
            font-size: 1rem;
        }
        
        /* Buttons */
        .stButton>button {
            background-color: var(--primary);
            color: white;
            border-radius: 8px;
            padding: 0.7rem 1.5rem;
            border: none;
            font-weight: 600;
            transition: all 0.2s ease;
            box-shadow: 0 2px 6px rgba(0,0,0,0.1);
            width: 100%;
        }
        
        .stButton>button:hover {
            background-color: #218838;
            transform: translateY(-2px);
            box-shadow: 0 4px 10px rgba(0,0,0,0.15);
        }
        
        /* Responsive Adjustments */
        @media (max-width: 768px) {
            .landing-header {
                padding: 2.5rem 1rem;
            }
            
            .landing-header h1 {
                font-size: 2.5rem;
            }
            
            .metric-card {
                padding: 1.2rem;
            }
            
            .metric-value {
                font-size: 1.8rem;
            }
        }
        
        /* Section Headers */
        .section-header {
            color: var(--primary);
            margin-top: 2rem;
            margin-bottom: 1.5rem;
            font-weight: 700;
            font-size: 1.8rem;
            position: relative;
            padding-bottom: 0.5rem;
        }
        
        .section-header:after {
            content: '';
            position: absolute;
            bottom: 0;
            left: 0;
            width: 60px;
            height: 3px;
            background: var(--primary);
            border-radius: 3px;
        }
        
        /* Call to Action */
        .cta-container {
            text-align: center;
            margin: 3rem 0;
            padding: 2rem;
            background: linear-gradient(135deg, rgba(29, 119, 73, 0.1) 0%, rgba(40, 167, 69, 0.1) 100%);
            border-radius: 12px;
        }
        
        .cta-container h2 {
            color: var(--primary);
            margin-bottom: 1rem;
        }
        
        .cta-container p {
            font-size: 1.1rem;
            color: var(--secondary);
            margin-bottom: 2rem;
            max-width: 700px;
            margin-left: auto;
            margin-right: auto;
        }
    </style>
    """, unsafe_allow_html=True)

def admin_dashboard_content():
    """Admin dashboard with tree management, user management, analytics, and tree lookup"""
    # Custom CSS for the dashboard
    st.markdown("""
    <style>
        /* Main header styling */
        .header-text {
            color: #2c3e50;
            font-size: 2.5rem;
            font-weight: 700;
            margin-bottom: 1rem;
            border-bottom: 3px solid #27ae60;
            padding-bottom: 0.5rem;
        }
        
        /* Metric card styling */
        .metric-card {
            background-color: #f8f9fa;
            border-radius: 10px;
            padding: 1.5rem;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
            border-left: 5px solid #27ae60;
            transition: transform 0.3s ease;
        }
        
        .metric-card:hover {
            transform: translateY(-5px);
            box-shadow: 0 6px 12px rgba(0, 0, 0, 0.15);
        }
        
        .metric-title {
            color: #7f8c8d;
            font-size: 1rem;
            font-weight: 600;
            margin-bottom: 0.5rem;
        }
        
        .metric-value {
            color: #2c3e50;
            font-size: 2rem;
            font-weight: 700;
        }
        
        /* Tab styling */
        .stTabs [data-baseweb="tab-list"] {
            gap: 0.5rem;
        }
        
        .stTabs [data-baseweb="tab"] {
            background-color: #f8f9fa;
            border-radius: 8px 8px 0 0 !important;
            padding: 0.5rem 1rem;
            font-weight: 600;
            transition: all 0.3s ease;
        }
        
        .stTabs [aria-selected="true"] {
            background-color: #27ae60 !important;
            color: white !important;
        }
        
        /* Table styling */
        .stDataFrame {
            border-radius: 10px;
            box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
        }
        
        /* Button styling */
        .stButton>button {
            border-radius: 8px;
            font-weight: 600;
            transition: all 0.3s ease;
        }
        
        .stButton>button:hover {
            transform: scale(1.02);
        }
        
        /* Custom success button */
        .success-button {
            background-color: #27ae60 !important;
            color: white !important;
        }
        
        /* Custom danger button */
        .danger-button {
            background-color: #e74c3c !important;
            color: white !important;
        }
        
        /* Custom warning button */
        .warning-button {
            background-color: #f39c12 !important;
            color: white !important;
        }
        
        /* Form styling */
        .stForm {
            border-radius: 10px;
            padding: 1.5rem;
            background-color: #f8f9fa;
            box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
        }
        
        /* QR code container */
        .qr-container {
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            padding: 1.5rem;
            background-color: white;
            border-radius: 10px;
            box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
            margin: 1rem 0;
        }
    </style>
    """, unsafe_allow_html=True)

    st.markdown("<h1 class='header-text'>🌳 Admin Dashboard</h1>", unsafe_allow_html=True)

    trees = load_tree_data()
    users = get_all_users()
    
    # Calculate metrics
    total_trees = len(trees)
    alive_trees = len(trees[trees["status"] == "Alive"]) if "status" in trees.columns else 0
    survival_rate = f"{round((alive_trees / total_trees) * 100, 1)}%" if total_trees > 0 else "0%"
    co2_sequestered = f"{round(trees['co2_kg'].sum(), 2)} kg" if "co2_kg" in trees.columns else "0 kg"
    
    # Count unique organizations/individuals
    if 'organization' in trees.columns:
        org_counts = trees['organization'].nunique()
    else:
        org_counts = trees['planter_id'].nunique() if 'planter_id' in trees.columns else 0
    
    # System Overview Metrics with custom cards
    st.markdown("<h4 style='color: #1D7749; margin-bottom: 1.5rem;'>🌍 System Overview</h4>", unsafe_allow_html=True)
    cols = st.columns(4)
    with cols[0]:
        st.markdown("""
            <div class='metric-card'>
                <div class='metric-title'>Total Trees</div>
                <div class='metric-value'>{}</div>
            </div>
        """.format(total_trees), unsafe_allow_html=True)
    
    with cols[1]:
        st.markdown("""
            <div class='metric-card'>
                <div class='metric-title'>CO₂ Sequestered</div>
                <div class='metric-value'>{}</div>
            </div>
        """.format(co2_sequestered), unsafe_allow_html=True)
    
    with cols[2]:
        st.markdown("""
            <div class='metric-card'>
                <div class='metric-title'>Survival Rate</div>
                <div class='metric-value'>{}</div>
            </div>
        """.format(survival_rate), unsafe_allow_html=True)
    
    with cols[3]:
        st.markdown("""
            <div class='metric-card'>
                <div class='metric-title'>Organizations/Individuals</div>
                <div class='metric-value'>{}</div>
            </div>
        """.format(org_counts), unsafe_allow_html=True)

    # Enhanced tabs with icons
    tab1, tab2, tab3, tab4 = st.tabs(["🌳 Tree Management", "👥 User Management", "📊 Analytics", "🔍 Tree Lookup"])

    with tab1:
        st.markdown("<h3 style='color: #1D7749; margin-bottom: 1rem;'>🌲 Tree Management</h3>", unsafe_allow_html=True)
        
        if trees.empty:
            st.info("No tree data available")
        else:
            # Tree Data Table with Filters
            st.markdown("<h4 style='color: #1D7749; margin-bottom: 1rem;'>All Tree Records</h4>", unsafe_allow_html=True)
            
            # Create filters
            col1, col2, col3 = st.columns(3)

            with col1:
                org_options = ["All"] + sorted([str(o) for o in trees['organization'].unique().tolist() if pd.notna(o)]) if 'organization' in trees.columns else ["All"]
                org_filter = st.selectbox("Filter by Organization", org_options)

            with col2:
                status_options = ["All"] + sorted([str(s) for s in trees['status'].unique().tolist() if pd.notna(s)]) if 'status' in trees.columns else ["All"]
                status_filter = st.selectbox("Filter by Status", status_options)

            with col3:
                date_filter = st.date_input("Filter by Planting Date Range", [])

            # Apply filters
            filtered_trees = trees.copy()
            
            if org_filter != "All":
                filtered_trees = filtered_trees[filtered_trees['organization'] == org_filter]

            if status_filter != "All":
                filtered_trees = filtered_trees[filtered_trees['status'] == status_filter]

            if date_filter and isinstance(date_filter, list) and len(date_filter) == 2:
                start_date, end_date = date_filter
                if 'planting_date' in filtered_trees.columns:
                    filtered_trees['planting_date'] = pd.to_datetime(filtered_trees['planting_date'], errors='coerce')
                    filtered_trees = filtered_trees[
                        (filtered_trees['planting_date'] >= pd.to_datetime(start_date)) &
                        (filtered_trees['planting_date'] <= pd.to_datetime(end_date))
                    ]
            
            # Display filtered data
            st.dataframe(filtered_trees)
            
            # Download button
            csv = filtered_trees.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="📥 Download Filtered Data",
                data=csv,
                file_name=f"tree_data_{datetime.now().strftime('%Y%m%d')}.csv",
                mime='text/csv',
                key='download_filtered_trees'
            )
            
            # Tree Status Visualization
            st.markdown("<h4 style='color: #1D7749; margin-bottom: 1rem;'>Tree Status Overview</h4>", unsafe_allow_html=True)
            status_counts = filtered_trees['status'].value_counts() if 'status' in filtered_trees.columns else pd.Series()
            if not status_counts.empty:
                fig = px.pie(
                    values=status_counts.values, 
                    names=status_counts.index, 
                    title="Tree Status Distribution", 
                    color_discrete_sequence=px.colors.sequential.Greens,
                    hole=0.3
                )
                fig.update_traces(textposition='inside', textinfo='percent+label')
                fig.update_layout(showlegend=False)
                st.plotly_chart(fig, use_container_width=True)

            # Tree Editing Section
            st.markdown("<h4 style='color: #1D7749; margin-bottom: 1rem;'>Edit Tree Records</h4>", unsafe_allow_html=True)
            edit_col1, edit_col2 = st.columns(2)
            with edit_col1:
                selected_tree_id = st.selectbox("Select Tree to Edit", options=filtered_trees['tree_id'].unique(), key="admin_tree_selector")

            if selected_tree_id:
                tree_data = filtered_trees[filtered_trees['tree_id'] == selected_tree_id].iloc[0]
                with st.form(f"edit_tree_{selected_tree_id}"):
                    col1, col2 = st.columns(2)
                    with col1:
                        valid_statuses = ["Alive", "Dead", "Dormant", "Removed"]
                        status_value = tree_data.get('status')
                        default_index = valid_statuses.index(status_value) if status_value in valid_statuses else 0
                        updated_status = st.selectbox("Status", valid_statuses, index=default_index)

                        updated_height = st.number_input("Height (m)", value=float(tree_data['height_m']) if 'height_m' in tree_data and pd.notna(tree_data['height_m']) else 0.0, min_value=0.0, step=0.1)
                    with col2:
                        growth_stages = ["Seedling", "Sapling", "Mature"]
                        stage_value = tree_data.get('tree_stage')
                        default_stage_index = growth_stages.index(stage_value) if stage_value in growth_stages else 0
                        updated_stage = st.selectbox("Growth Stage", growth_stages, index=default_stage_index)

                        updated_co2 = st.number_input("CO₂ Sequestered (kg)", value=float(tree_data['co2_kg']) if 'co2_kg' in tree_data and pd.notna(tree_data['co2_kg']) else 0.0, min_value=0.0, step=0.1)

                    if st.form_submit_button("Update Tree Record", type="primary"):
                        try:
                            conn = sqlite3.connect(SQLITE_DB)
                            cursor = conn.cursor()
                            cursor.execute("""UPDATE trees SET status = ?, height_m = ?, tree_stage = ?, co2_kg = ? WHERE tree_id = ?""", 
                                         (updated_status, updated_height, updated_stage, updated_co2, selected_tree_id))
                            conn.commit()
                            st.success("Tree record updated successfully!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Error updating tree: {str(e)}")

    with tab2:
        st.markdown("<h3 style='color: #1D7749; margin-bottom: 1rem;'>👥 User Management</h3>", unsafe_allow_html=True)
        try:
            users = get_all_users()
            pending_users = [u for u in users if u.get('status') == 'pending']
            approved_users = [u for u in users if u.get('status') == 'approved']

            # Pending Applications Section
            st.markdown("<h4 style='color: #1D7749; margin-bottom: 1rem;'>📝 Pending Applications</h4>", unsafe_allow_html=True)
            if not pending_users:
                st.info("No pending applications.")
            else:
                for user in pending_users:
                    uid = user.get('uid')
                    email = user.get('email', 'Unknown')
                    name = user.get('fullName', 'Unnamed')
                    role = user.get('role', 'individual')

                    with st.expander(f"👤 {name} ({email})", expanded=False):
                        st.markdown(f"""
                            <div style="margin-bottom: 1rem;">
                                <p><strong>Role:</strong> {role}</p>
                                <p><strong>UID:</strong> <code>{uid}</code></p>
                            </div>
                        """, unsafe_allow_html=True)

                        col1, col2 = st.columns(2)
                        with col1:
                            if st.button(f"✅ Approve {name}", key=f"approve_{uid}", type="primary"):
                                approve_user(uid)
                                send_approval_email(user)
                                st.success(f"{email} approved and notified via email.")
                                st.rerun()

                        with col2:
                            if st.button(f"❌ Reject {name}", key=f"reject_{uid}"):
                                reject_user(uid)
                                send_rejection_email(user)
                                st.warning(f"{email} rejected and notified via email.")
                                st.rerun()

            # Approved Users Section
            st.markdown("<h4 style='color: #1D7749; margin-bottom: 1rem;'>✅ Registered Users</h4>", unsafe_allow_html=True)
            if not approved_users:
                st.info("No registered users.")
            else:
                for user in approved_users:
                    uid = user.get('uid')
                    email = user.get('email', 'Unknown')
                    name = user.get('fullName', 'Unnamed')
                    role = user.get('role', 'individual')
                    tracking = user.get('treeTrackingNumber', 'N/A')

                    with st.expander(f"👤 {name} ({email})", expanded=False):
                        st.markdown(f"""
                            <div style="margin-bottom: 1rem;">
                                <p><strong>Role:</strong> {role}</p>
                                <p><strong>UID:</strong> <code>{uid}</code></p>
                                <p><strong>Tracking Number:</strong> <code>{tracking}</code></p>
                            </div>
                        """, unsafe_allow_html=True)

                        if st.button(f"🗑️ Remove {name}", key=f"delete_{uid}"):
                            delete_user(uid)
                            st.error(f"{email} removed.")
                            st.rerun()
        except Exception as e:
            st.error(f"Failed to load users: {e}")

    with tab3:
        st.markdown("<h3 style='color: #1D7749; margin-bottom: 1rem;'>📊 System Analytics</h3>", unsafe_allow_html=True)
        if trees.empty:
            st.info("No data available for analytics")
        else:
            # Planting Trends
            st.markdown("<h4 style='color: #1D7749; margin-bottom: 1rem;'>📈 Planting Trends</h4>", unsafe_allow_html=True)
            if 'date_planted' in trees.columns:
                trees['date_planted'] = pd.to_datetime(trees['date_planted'], errors='coerce')
                trees_by_date = trees.groupby(trees['date_planted'].dt.date).size().reset_index()
                trees_by_date.columns = ['Date', 'Trees Planted']
                fig = px.line(
                    trees_by_date, 
                    x='Date', 
                    y='Trees Planted', 
                    title="Trees Planted Over Time", 
                    color_discrete_sequence=["#27ae60"],
                    template="plotly_white"
                )
                fig.update_layout(
                    plot_bgcolor='rgba(0,0,0,0)',
                    paper_bgcolor='rgba(0,0,0,0)',
                    xaxis_title="Date",
                    yaxis_title="Number of Trees Planted"
                )
                st.plotly_chart(fig, use_container_width=True)

            # Species Distribution
            st.markdown("<h4 style='color: #1D7749; margin-bottom: 1rem;'>🌿 Species Distribution</h4>", unsafe_allow_html=True)
            if 'scientific_name' in trees.columns:
                species_counts = trees['scientific_name'].value_counts().head(10)
                fig = px.bar(
                    x=species_counts.values, 
                    y=species_counts.index, 
                    orientation='h', 
                    title="Top 10 Tree Species", 
                    color=species_counts.values, 
                    color_continuous_scale=px.colors.sequential.Greens,
                    labels={'x': 'Count', 'y': 'Species'},
                    template="plotly_white"
                )
                fig.update_layout(
                    plot_bgcolor='rgba(0,0,0,0)',
                    paper_bgcolor='rgba(0,0,0,0)'
                )
                st.plotly_chart(fig, use_container_width=True)

            # Health Analytics
            st.markdown("<h4 style='color: #1D7749; margin-bottom: 1rem;'>💚 Health Analytics</h4>", unsafe_allow_html=True)
            if 'health_status' in trees.columns:
                health_counts = trees['health_status'].value_counts()
                fig = px.pie(
                    values=health_counts.values, 
                    names=health_counts.index, 
                    title="Tree Health Distribution", 
                    hole=0.3, 
                    color_discrete_sequence=px.colors.sequential.Greens
                )
                fig.update_traces(textposition='inside', textinfo='percent+label')
                fig.update_layout(showlegend=False)
                st.plotly_chart(fig, use_container_width=True)
            elif 'status' in trees.columns:
                health_counts = trees['status'].value_counts()
                fig = px.pie(
                    values=health_counts.values, 
                    names=health_counts.index, 
                    title="Tree Status Distribution", 
                    hole=0.3, 
                    color_discrete_sequence=px.colors.sequential.Greens
                )
                fig.update_traces(textposition='inside', textinfo='percent+label')
                fig.update_layout(showlegend=False)
                st.plotly_chart(fig, use_container_width=True, key="admin_dashboard_plot_1")

    with tab4:
        st.markdown("<h3 style='color: #1D7749; margin-bottom: 1rem;'>🔍 Tree Lookup</h3>", unsafe_allow_html=True)
        lookup_col1, lookup_col2 = st.columns([2, 1])
        with lookup_col1:
            search_query = st.text_input("Search by Tree ID, Name, or Planter", key="admin_tree_search", placeholder="Enter tree ID, name, or planter ID")
        with lookup_col2:
            search_type = st.selectbox("Search Type", ["Tree ID", "Local Name", "Planter ID"], key="admin_search_type")

        if search_query:
            if search_type == "Tree ID":
                results = trees[trees['tree_id'].astype(str).str.contains(search_query, case=False)]
            elif search_type == "Local Name":
                results = trees[trees['local_name'].str.contains(search_query, case=False, na=False)]
            elif search_type == "Planter ID":
                results = trees[trees['planter_id'].astype(str).str.contains(search_query, case=False)]
            else:
                results = pd.DataFrame()

            if not results.empty:
                st.success(f"Found {len(results)} matching trees")
                selected_tree = st.selectbox(
                    "Select a tree for details", 
                    options=results.apply(lambda x: f"{x['local_name']} (ID: {x['tree_id']}, Planter: {x['planter_id']})", axis=1),
                    key="tree_selection"
                )

                if selected_tree:
                    tree_id = selected_tree.split("ID: ")[1].split(",")[0].strip()
                    tree_data = results[results['tree_id'].astype(str) == tree_id].iloc[0]
                    
                    # Display tree details in a nicer format
                    st.markdown("<h4 style='color: #1D7749; margin-bottom: 1rem;'>🌲 Tree Details</h4>", unsafe_allow_html=True)
                    
                    col1, col2 = st.columns(2)
                    with col1:
                        st.markdown(f"""
                            <div style="background-color: #f8f9fa; padding: 1rem; border-radius: 10px; margin-bottom: 1rem;">
                                <p><strong>Tree ID:</strong> {tree_data.get('tree_id', 'N/A')}</p>
                                <p><strong>Local Name:</strong> {tree_data.get('local_name', 'N/A')}</p>
                                <p><strong>Scientific Name:</strong> <em>{tree_data.get('scientific_name', 'N/A')}</em></p>
                                <p><strong>Status:</strong> {tree_data.get('status', 'N/A')}</p>
                            </div>
                        """, unsafe_allow_html=True)
                    
                    with col2:
                        st.markdown(f"""
                            <div style="background-color: #f8f9fa; padding: 1rem; border-radius: 10px; margin-bottom: 1rem;">
                                <p><strong>Planter ID:</strong> {tree_data.get('planter_id', 'N/A')}</p>
                                <p><strong>Organization:</strong> {tree_data.get('organization', 'N/A')}</p>
                                <p><strong>Date Planted:</strong> {tree_data.get('date_planted', 'N/A')}</p>
                                <p><strong>CO₂ Sequestered:</strong> {tree_data.get('co2_kg', 'N/A')} kg</p>
                            </div>
                        """, unsafe_allow_html=True)
                    
                    # Location information
                    if 'latitude' in tree_data and 'longitude' in tree_data:
                        st.markdown("<h5 style='color: #1D7749; margin-bottom: 0.5rem;'>📍 Location</h5>", unsafe_allow_html=True)
                        st.map(pd.DataFrame({
                            'lat': [float(tree_data['latitude'])],
                            'lon': [float(tree_data['longitude'])]
                        }), zoom=15)

                    # QR Code Section
                    st.markdown("<h4 style='color: #1D7749; margin-bottom: 1rem;'>📲 Tree QR Code</h4>", unsafe_allow_html=True)
                    with st.container():
                        qr_base64, qr_file_path = generate_qr_code(tree_data['tree_id'])
                        
                        if qr_base64:
                            st.markdown("""
                                <div class="qr-container">
                                    <img src="data:image/png;base64,{}" width="200" style="margin-bottom: 1rem;">
                                    <p style="text-align: center; font-weight: 600;">Scan to view tree details</p>
                                </div>
                            """.format(qr_base64), unsafe_allow_html=True)
                            
                            if qr_file_path and Path(qr_file_path).exists():
                                with open(qr_file_path, "rb") as f:
                                    img_bytes = f.read()
                                st.download_button(
                                    label="Download QR Code",
                                    data=img_bytes,
                                    file_name=f"tree_{tree_id}_qrcode.png",
                                    mime="image/png",
                                    key=f"qr_download_{tree_id}"
                                )
                        else:
                            st.warning("QR code generation failed for this tree.")
            else:
                st.warning("No trees found matching your search")
        else:
            st.info("Enter a search term to look up trees")

# --- Landing Page Metrics ---
def get_landing_metrics():
    """Get current metrics for the landing page"""
    conn = get_db_connection()
    try:
        # Get institutions count
        institutions_count = conn.execute("SELECT COUNT(*) FROM institutions").fetchone()[0]
        
        # Get trees data
        trees_df = pd.read_sql_query("SELECT * FROM trees", conn)
        
        # Calculate survival rate
        alive_trees = len(trees_df[trees_df["status"] == "Alive"]) if "status" in trees_df.columns else 0
        total_trees = len(trees_df)
        survival_rate = round((alive_trees / total_trees * 100), 1) if total_trees > 0 else 0
        
        metrics = {
            "institutions": institutions_count,
            "total_trees": total_trees,
            "alive_trees": alive_trees,
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

def show_donation():
    """Donation page"""
    st.subheader("Support Our Mission")
    
    with st.container():
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("""
            <div class="feature-card">
                <h3>💚 Make a Donation</h3>
                <p>Your contribution helps plant and maintain more trees</p>
            </div>
            """, unsafe_allow_html=True)
            
            amount = st.selectbox("Donation Amount", ["$10", "$25", "$50", "$100", "Custom"])
            if amount == "Custom":
                amount = st.text_input("Enter custom amount")
            
            name = st.text_input("Full Name")
            email = st.text_input("Email")
            
            if st.button("Donate Now"):
                if name and email and amount:
                    st.success(f"Thank you for your donation of {amount}!")
                else:
                    st.warning("Please fill all fields")
        
        with col2:
            st.markdown("""
            <div class="feature-card">
                <h3>🌳 Where Your Money Goes</h3>
                <ul style="padding-left: 20px;">
                    <li>80% to tree planting initiatives</li>
                    <li>15% to community education</li>
                    <li>5% to platform maintenance</li>
                </ul>
            </div>
            """, unsafe_allow_html=True)
            
            st.image("https://images.unsplash.com/photo-1466692476868-aef1dfb1e735", 
                    caption="Our reforestation efforts in action")

# --- Landing Page ---
def show_landing_page():
    set_custom_css()
    metrics = get_landing_metrics()

    # Hero Section
    st.markdown("""
    <div class="landing-header">
        <h1>🌱 CarbonTally</h1>
        <p style="font-size: 1.3rem;">Track, monitor, and contribute to reforestation efforts worldwide</p>
        <p>Join our mission to combat climate change one tree at a time.</p>
    </div>
    """, unsafe_allow_html=True)

    # Impact Metrics
    st.markdown('<div class="section-header">Our Impact at a Glance</div>', unsafe_allow_html=True)
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

    # Global Impact Map
    st.markdown('<div class="section-header">🌍 Our Global Impact</div>', unsafe_allow_html=True)
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

    # Features Section
    st.markdown('<div class="section-header">✨ Why Choose CarbonTally?</div>', unsafe_allow_html=True)
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

    # Call to Action
    st.markdown("""
    <div class="cta-container">
        <h2>Ready to make a difference?</h2>
        <p>Join our community or support our mission today</p>
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
            st.session_state.page = "Donate"
            st.rerun()
# Donor access button (full-width for visibility)
    # Recent Activity in Two Columns - Now properly inside the show_landing_page function
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
            # Split into two columns
            col1, col2 = st.columns(2)
            
            with col1:
                for _, row in df.iloc[:3].iterrows():
                    st.markdown(f"""
                    <div class="activity-item" style="margin-bottom: 1rem;">
                        <div class="activity-content">
                            <span class="activity-highlight">{row['planters_name']}</span> planted a 
                            <span class="activity-highlight">{row['local_name']}</span> tree
                        </div>
                        <div class="activity-meta">
                            🌱 {row['co2_kg']} kg CO₂ • 📅 {row['formatted_date']}
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
            
            with col2:
                for _, row in df.iloc[3:].iterrows():
                    st.markdown(f"""
                    <div class="activity-item" style="margin-bottom: 1rem;">
                        <div class="activity-content">
                            <span class="activity-highlight">{row['planters_name']}</span> planted a 
                            <span class="activity-highlight">{row['local_name']}</span> tree
                        </div>
                        <div class="activity-meta">
                            🌱 {row['co2_kg']} kg CO₂ • 📅 {row['formatted_date']}
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
        else:
            st.info("No recent activity found. Be the first to plant a tree!")
            
    except sqlite3.Error as e:
        st.error(f"Database error: {str(e)}")
    except Exception as e:
        st.error(f"Couldn't load recent activities: {str(e)}")

def main():
    # Ensure database is properly initialized and migrated before any page content loads
    ensure_database()

    # Initialize session state variables if they don't exist
    if 'authenticated' not in st.session_state:
        st.session_state.authenticated = False
    if 'page' not in st.session_state:
        st.session_state.page = "Landing"

    # Route to the landing page if not authenticated and not explicitly trying to log in/sign up/recover
    if st.session_state.page == "Landing":
        show_landing_page()
    else:
        set_custom_css() # Apply app-wide CSS

        # Initialize Firebase if the module is available
        if FIREBASE_AUTH_MODULE_AVAILABLE:
            if not initialize_firebase():
                st.error("Failed to initialize Firebase. Please check your Firebase configuration.")
                return

        # Sidebar navigation
        with st.sidebar:
            st.markdown("<h3 style='color: #1D7749; margin-bottom: 1rem;'>🌱 CarbonTally</h3>", unsafe_allow_html=True)

            if st.session_state.authenticated:
                user = get_current_firebase_user()
                if user:
                    st.markdown(f"**Welcome, {user.get('displayName', 'User')}!**")

                    if check_firebase_user_role(user, 'admin'):
                        # Admin gets access to all dashboards and direct planting/monitoring
                        page_options = ["Admin Dashboard", "User Dashboard", "Plant a Tree", "Monitor Trees", "Donor Dashboard"]
                    else:
                        # Regular users get user dashboard and direct planting/monitoring
                        page_options = ["User Dashboard", "Plant a Tree", "Monitor Trees", "Donor Dashboard"]

                    try:
                        current_page_index = page_options.index(st.session_state.page)
                    except ValueError:
                        current_page_index = 0 # Default to the first option if current page is not in list

                    st.session_state.page = st.radio("Navigate to:", page_options, index=current_page_index)

                    if st.button("Logout", use_container_width=True):
                        firebase_logout()
                        st.session_state.authenticated = False
                        st.session_state.page = "Login"
                        st.rerun() # Rerun to refresh the UI to login page
            else:
                # Options for unauthenticated users
                st.session_state.page = st.radio("Choose an option:",
                    ["Login", "Sign Up", "Password Recovery", "Donor Dashboard"],
                    index=["Login", "Sign Up", "Password Recovery", "Donor Dashboard"].index(st.session_state.page)
                    if st.session_state.page in ["Login", "Sign Up", "Password Recovery", "Donor Dashboard"] else 0)

        # Main content area based on selected page
        if st.session_state.page == "Login":
            firebase_login_ui()
        elif st.session_state.page == "Sign Up":
            firebase_signup_ui()
        elif st.session_state.page == "Password Recovery":
            firebase_password_recovery_ui()
        elif st.session_state.page == "Donor Dashboard":
            guest_donor_dashboard_ui()
        elif st.session_state.authenticated: # Only show these pages if authenticated
            if st.session_state.page == "Admin Dashboard":
                admin_dashboard_content()
            elif st.session_state.page == "User Dashboard":
                # This is the main unified user dashboard with its own internal tabs
                unified_user_dashboard_content()
            elif st.session_state.page == "Plant a Tree":
                # Direct call to planting section (now imported from unified_user_dashboard)
                plant_a_tree_section()
            elif st.session_state.page == "Monitor Trees":
                # Direct call to monitoring section (now imported from unified_user_dashboard)
                monitoring_section()
        else:
            # If authenticated is False and page is not one of the login/signup options, redirect to login
            st.warning("Please log in to access this page.")
            firebase_login_ui()

        add_branding_footer() # Always include the branding footer at the bottom

# --- Custom Module Imports with Error Handling ---
import streamlit as st

try:
    from branding_footer import add_branding_footer
except ImportError:
    def add_branding_footer():
        st.markdown("""
            <style>
                footer {
                    position: fixed;
                    bottom: 0;
                    width: 100%;
                    padding: 10px 0;
                    background-color: #f9f9f9;
                }
            </style>
            <footer>
                <p style='text-align:center;font-size:0.8em;color:grey;'>
                    🌱 CarbonTally – Developed by Basil Okoth
                </p>
            </footer>
        """, unsafe_allow_html=True)

# --- Entry Point for the Streamlit app ---
if __name__ == "__main__":
    main()
    add_branding_footer()  # ✅ Always shown, even before login
