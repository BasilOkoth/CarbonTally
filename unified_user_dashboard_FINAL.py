import streamlit as st
import os
from PIL import Image, ImageDraw, ImageFont
import pandas as pd
import plotly.express as px
import datetime
import qrcode
from pathlib import Path
import sqlite3
import pyperclip
import json
import time
import random
import hashlib
import re

# --- Session State Initialization ---
if "user" not in st.session_state:
    st.session_state.user = None
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False
if "page" not in st.session_state:
    st.session_state.page = "login"

# --- Configuration ---
MAX_FILE_SIZE = 1 * 1024 * 1024  # 1MB
LOGO_FOLDER = "logos"
DEFAULT_LOGO_PATH = "assets/default_logo.png"
os.makedirs(LOGO_FOLDER, exist_ok=True)

QR_CODE_DIR = Path("data/qr_codes")
QR_CODE_DIR.mkdir(exist_ok=True, parents=True)

BASE_DIR = Path(__file__).parent if "__file__" in locals() else Path.cwd()
DATA_DIR = BASE_DIR / "data"
SQLITE_DB = DATA_DIR / "trees.db"
MONITORING_DB_PATH = DATA_DIR / "monitoring.db"

# Ensure data directories exist
DATA_DIR.mkdir(exist_ok=True, parents=True)

# ----------------- AUTHENTICATION FUNCTIONS -----------------
def init_users_table():
    """Initialize the users table in the existing trees database"""
    conn = sqlite3.connect(str(SQLITE_DB))
    c = conn.cursor()
    
    # Create users table if it doesn't exist
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            full_name TEXT,
            institution TEXT,
            tree_tracking_number TEXT UNIQUE,
            role TEXT DEFAULT 'user',
            status TEXT DEFAULT 'active',
            field_password TEXT,
            token_created_at INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    conn.commit()
    conn.close()

def hash_password(password):
    """Hash a password using SHA-256"""
    return hashlib.sha256(password.encode()).hexdigest()

def validate_password(password):
    """Validate password strength"""
    if len(password) < 8:
        return False, "Password must be at least 8 characters long"
    if not re.search(r"[A-Z]", password):
        return False, "Password must contain at least one uppercase letter"
    if not re.search(r"[a-z]", password):
        return False, "Password must contain at least one lowercase letter"
    if not re.search(r"\d", password):
        return False, "Password must contain at least one digit"
    return True, "Password is valid"

def validate_email(email):
    """Validate email format"""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

def generate_tracking_number():
    """Generate a unique tree tracking number"""
    return f"CT{random.randint(100000, 999999)}"

def register_user(username, email, password, full_name="", institution=""):
    """Register a new user"""
    try:
        # Validate inputs
        if not username or not email or not password:
            return False, "All fields are required"
        
        if not validate_email(email):
            return False, "Invalid email format"
        
        is_valid, message = validate_password(password)
        if not is_valid:
            return False, message
        
        # Check if user already exists
        conn = sqlite3.connect(str(SQLITE_DB))
        c = conn.cursor()
        
        c.execute("SELECT id FROM users WHERE username = ? OR email = ?", (username, email))
        if c.fetchone():
            conn.close()
            return False, "Username or email already exists"
        
        # Hash password and create user
        password_hash = hash_password(password)
        tracking_number = generate_tracking_number()
        
        c.execute('''
            INSERT INTO users (username, email, password_hash, full_name, institution, tree_tracking_number, role)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (username, email, password_hash, full_name, institution, tracking_number, 'user'))
        
        conn.commit()
        conn.close()
        
        return True, "Registration successful! You can now login."
        
    except Exception as e:
        return False, f"Registration failed: {str(e)}"

def login_user(username, password):
    """Authenticate user login"""
    try:
        conn = sqlite3.connect(str(SQLITE_DB))
        c = conn.cursor()
        
        # Find user by username or email
        c.execute('''
            SELECT id, username, email, password_hash, full_name, institution, tree_tracking_number, role
            FROM users 
            WHERE (username = ? OR email = ?) AND status = 'active'
        ''', (username, username))
        
        user_data = c.fetchone()
        conn.close()
        
        if not user_data:
            return False, "Invalid username/email or password"
        
        # Verify password
        stored_hash = user_data[3]
        input_hash = hash_password(password)
        
        if stored_hash != input_hash:
            return False, "Invalid username/email or password"
        
        # Create user session object
        user = {
            'id': user_data[0],
            'username': user_data[1],
            'email': user_data[2],
            'full_name': user_data[4],
            'institution': user_data[5],
            'treeTrackingNumber': user_data[6],
            'role': user_data[7]
        }
        
        st.session_state.user = user
        st.session_state.authenticated = True
        st.session_state.page = "dashboard"
        
        return True, "Login successful!"
        
    except Exception as e:
        return False, f"Login failed: {str(e)}"

def logout_user():
    """Logout current user"""
    st.session_state.user = None
    st.session_state.authenticated = False
    st.session_state.page = "login"

# ----------------- AUTHENTICATION PAGES -----------------
def show_login_page():
    """Display login form"""
    st.markdown("""
    <style>
        .login-container {
            max-width: 400px;
            margin: 0 auto;
            padding: 2rem;
        }
        .header {
            text-align: center;
            color: #1D7749;
            margin-bottom: 2rem;
        }
    </style>
    """, unsafe_allow_html=True)
    
    st.markdown('<div class="header"><h1>🌳 CarbonTally</h1><p>Tree Management System</p></div>', unsafe_allow_html=True)
    
    with st.form("login_form"):
        st.subheader("Login to Your Account")
        
        username = st.text_input("Username or Email")
        password = st.text_input("Password", type="password")
        
        col1, col2 = st.columns([1, 1])
        with col1:
            login_button = st.form_submit_button("Login")
        with col2:
            switch_to_register = st.form_submit_button("Create Account")
        
        if login_button:
            if username and password:
                success, message = login_user(username, password)
                if success:
                    st.success(message)
                    st.rerun()
                else:
                    st.error(message)
            else:
                st.error("Please fill in all fields")
        
        if switch_to_register:
            st.session_state.page = "register"
            st.rerun()

def show_register_page():
    """Display registration form"""
    st.markdown("""
    <style>
        .register-container {
            max-width: 500px;
            margin: 0 auto;
            padding: 2rem;
        }
    </style>
    """, unsafe_allow_html=True)
    
    st.markdown('<div class="header"><h1>Create Your Account</h1></div>', unsafe_allow_html=True)
    
    with st.form("register_form"):
        col1, col2 = st.columns(2)
        with col1:
            username = st.text_input("Username *")
            full_name = st.text_input("Full Name")
        with col2:
            email = st.text_input("Email *")
            institution = st.text_input("Institution (Optional)")
        
        col3, col4 = st.columns(2)
        with col3:
            password = st.text_input("Password *", type="password")
        with col4:
            confirm_password = st.text_input("Confirm Password *", type="password")
        
        # Password strength indicator
        if password:
            is_valid, message = validate_password(password)
            if is_valid:
                st.success("✓ Password strength: Good")
            else:
                st.warning(f"⚠ {message}")
        
        col5, col6 = st.columns([1, 1])
        with col5:
            register_button = st.form_submit_button("Create Account")
        with col6:
            switch_to_login = st.form_submit_button("Back to Login")
        
        if register_button:
            if not all([username, email, password, confirm_password]):
                st.error("Please fill in all required fields (*)")
            elif password != confirm_password:
                st.error("Passwords do not match")
            else:
                success, message = register_user(username, email, password, full_name, institution)
                if success:
                    st.success(message)
                    st.info("Please login with your new credentials")
                    st.session_state.page = "login"
                    st.rerun()
                else:
                    st.error(message)
        
        if switch_to_login:
            st.session_state.page = "login"
            st.rerun()

# ----------------- DATABASE FUNCTIONS -----------------
def get_db_connection():
    """Establishes and returns a database connection."""
    return sqlite3.connect(SQLITE_DB)

def get_monitoring_db_connection():
    """Establishes connection to monitoring database."""
    return sqlite3.connect(str(MONITORING_DB_PATH))

def load_tree_data_by_tracking_number(tracking_number):
    """Load tree data filtered by tracking number"""
    if not tracking_number:
        return pd.DataFrame()
    
    try:
        conn = get_db_connection()
        query = "SELECT * FROM trees WHERE treeTrackingNumber = ?"
        df = pd.read_sql_query(query, conn, params=(tracking_number,))
        return df
    except Exception as e:
        st.error(f"Error loading tree data: {str(e)}")
        return pd.DataFrame()
    finally:
        if 'conn' in locals():
            conn.close()

def load_monitoring_history(tracking_number):
    """Load monitoring history for trees with given tracking number"""
    tree_id_df = load_tree_data_by_tracking_number(tracking_number)
    if tree_id_df.empty:
        st.warning("No tree found for this tracking number.")
        return pd.DataFrame()

    conn = get_monitoring_db_connection()
    try:
        associated_tree_ids = tuple(tree_id_df['tree_id'].tolist())
        
        if not associated_tree_ids:
            return pd.DataFrame()

        placeholders = ','.join('?' for _ in associated_tree_ids)
        query = f"""
        SELECT *
        FROM tree_monitoring
        WHERE tree_id IN ({placeholders})
        ORDER BY monitored_at DESC
        """
        return pd.read_sql(query, conn, params=associated_tree_ids)
    except Exception as e:
        st.error(f"Error loading monitoring data: {str(e)}")
        return pd.DataFrame()
    finally:
        conn.close()

# ----------------- METRICS CALCULATION -----------------
def calculate_tree_metrics(trees):
    """Calculate various metrics about the user's trees"""
    if not isinstance(trees, pd.DataFrame) or trees.empty:
        return {
            'total_trees': 0,
            'species_count': {},
            'total_co2_absorbed': 0.0,
            'growth_stages': {'seedling': 0, 'sapling': 0, 'mature': 0},
            'health_status': {'excellent': 0, 'good': 0, 'fair': 0, 'poor': 0},
            'status_counts': {'alive': 0, 'dead': 0, 'dormant': 0, 'removed': 0}
        }

    metrics = {
        'total_trees': len(trees),
        'species_count': {},
        'total_co2_absorbed': 0.0,
        'growth_stages': {'seedling': 0, 'sapling': 0, 'mature': 0},
        'health_status': {'excellent': 0, 'good': 0, 'fair': 0, 'poor': 0},
        'status_counts': {'alive': 0, 'dead': 0, 'dormant': 0, 'removed': 0}
    }

    if 'local_name' in trees.columns:
        metrics['species_count'] = trees['local_name'].value_counts().to_dict()

    if 'co2_kg' in trees.columns:
        try:
            trees['co2_kg'] = pd.to_numeric(trees['co2_kg'], errors='coerce').fillna(0.0)
            metrics['total_co2_absorbed'] = trees['co2_kg'].sum()
        except Exception:
            metrics['total_co2_absorbed'] = 0.0

    if 'tree_stage' in trees.columns:
        for stage in trees['tree_stage']:
            if pd.isna(stage):
                continue
            stage_lower = str(stage).lower()
            if 'seedling' in stage_lower:
                metrics['growth_stages']['seedling'] += 1
            elif 'sapling' in stage_lower:
                metrics['growth_stages']['sapling'] += 1
            elif 'mature' in stage_lower:
                metrics['growth_stages']['mature'] += 1

    if 'status' in trees.columns:
        for status_val in trees['status']:
            if pd.isna(status_val):
                continue
            status_lower = str(status_val).lower()
            if 'alive' in status_lower:
                metrics['status_counts']['alive'] += 1
            elif 'dead' in status_lower:
                metrics['status_counts']['dead'] += 1
            elif 'dormant' in status_lower:
                metrics['status_counts']['dormant'] += 1
            elif 'removed' in status_lower:
                metrics['status_counts']['removed'] += 1

    if 'monitor_status' in trees.columns:
        for health in trees['monitor_status']:
            if pd.isna(health):
                continue
            health_lower = str(health).lower()
            if 'excellent' in health_lower:
                metrics['health_status']['excellent'] += 1
            elif 'good' in health_lower:
                metrics['health_status']['good'] += 1
            elif 'fair' in health_lower:
                metrics['health_status']['fair'] += 1
            elif 'poor' in health_lower:
                metrics['health_status']['poor'] += 1

    return metrics

def calculate_health_score(health_status):
    """Calculate an overall health score from 0-100"""
    total = sum(health_status.values())
    if total == 0:
        return 0

    weights = {
        'excellent': 1.0,
        'good': 0.8,
        'fair': 0.6,
        'poor': 0.3
    }

    weighted_sum = sum(weights.get(k.lower(), 0) * v for k, v in health_status.items())
    return min(100, int((weighted_sum / total) * 100))

# ----------------- DISPLAY FUNCTIONS -----------------
def display_forest_overview(trees, metrics):
    """Display visual overview of the user's forest"""
    st.subheader("Your Forest at a Glance")

    if trees.empty:
        st.info("No trees found in your forest yet.")
        return

    col1, col2 = st.columns(2)

    with col1:
        st.write("#### Tree Status")
        status_counts_filtered = {k: v for k, v in metrics['status_counts'].items() if v > 0}
        if status_counts_filtered:
            status_df = pd.DataFrame.from_dict(
                status_counts_filtered,
                orient='index',
                columns=['Count']
            )
            fig = px.pie(
                status_df,
                values='Count',
                names=status_df.index,
                color=status_df.index,
                color_discrete_map={
                    'alive': '#28a745',
                    'dormant': '#ffc107',
                    'dead': '#dc3545',
                    'removed': '#6c757d'
                }
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No tree status data to display.")

    with col2:
        st.write("#### Species Distribution")
        if metrics['species_count']:
            species_df = pd.DataFrame.from_dict(
                metrics['species_count'],
                orient='index',
                columns=['Count']
            ).sort_values('Count', ascending=False).head(5)

            fig = px.bar(
                species_df,
                orientation='h',
                color=species_df.index,
                color_discrete_sequence=px.colors.sequential.Greens
            )
            fig.update_layout(showlegend=False)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No species data to display.")

    if 'latitude' in trees.columns and 'longitude' in trees.columns:
        st.write("#### Tree Locations")
        map_trees = trees.dropna(subset=['latitude', 'longitude'])
        if not map_trees.empty:
            fig_map = px.scatter_mapbox(
                map_trees,
                lat='latitude',
                lon='longitude',
                hover_name='tree_id',
                hover_data=['local_name', 'date_planted', 'status'],
                color='status',
                color_discrete_map={'Alive': '#28a745', 'Dead': '#dc3545', 'Dormant': '#ffc107', 'Removed': '#6c757d'},
                zoom=10,
                height=500
            )
            fig_map.update_layout(
                mapbox_style='open-street-map',
                margin={'r':0,'t':0,'l':0,'b':0},
                hovermode='closest'
            )
            st.plotly_chart(fig_map, use_container_width=True)
        else:
            st.info("No tree location data available.")

def display_growth_analytics(trees, monitoring_history):
    """Display growth analytics and trends"""
    st.subheader("Growth Analytics")

    if trees.empty and monitoring_history.empty:
        st.info("No growth data available yet.")
        return

    if not monitoring_history.empty and 'monitor_date' in monitoring_history.columns:
        monitoring_history['monitor_date'] = pd.to_datetime(monitoring_history['monitor_date'], errors='coerce')
        monitoring_history = monitoring_history.dropna(subset=['monitor_date'])

    if not trees.empty and 'date_planted' in trees.columns:
        trees['date_planted'] = pd.to_datetime(trees['date_planted'], errors='coerce')
        trees = trees.dropna(subset=['date_planted'])

    if not monitoring_history.empty and 'height_m' in monitoring_history.columns:
        st.write("#### Height Growth Over Time")
        fig = px.line(
            monitoring_history,
            x='monitor_date',
            y='height_m',
            color='tree_id',
            labels={'height_m': 'Height (m)', 'monitor_date': 'Date'},
            color_discrete_sequence=px.colors.sequential.Greens
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No height monitoring data available.")

    if not monitoring_history.empty and 'dbh_cm' in monitoring_history.columns:
        st.write("#### Diameter Growth Over Time")
        fig = px.line(
            monitoring_history,
            x='monitor_date',
            y='dbh_cm',
            color='tree_id',
            labels={'dbh_cm': 'Diameter at Breast Height (cm)', 'monitor_date': 'Date'},
            color_discrete_sequence=px.colors.sequential.Greens
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No diameter monitoring data available.")

    if 'co2_kg' in trees.columns and not trees.empty:
        st.write("#### CO₂ Sequestration Projection")
        projection_years = 5
        projection_data = []

        for _, tree in trees.iterrows():
            if pd.isna(tree['co2_kg']):
                continue

            for year in range(projection_years):
                projection_data.append({
                    'tree_id': tree['tree_id'],
                    'year': year + 1,
                    'co2_kg': tree['co2_kg'] * (1 + year * 0.2)
                })

        projection_df = pd.DataFrame(projection_data)
        if not projection_df.empty:
            fig = px.line(
                projection_df,
                x='year',
                y='co2_kg',
                color='tree_id',
                labels={'co2_kg': 'CO₂ Sequestered (kg)', 'year': 'Years from now'},
                color_discrete_sequence=px.colors.sequential.Greens
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Not enough data to project CO₂ sequestration.")
    else:
        st.info("No CO₂ data available for projection.")

def display_tree_inventory(trees_df):
    """Display a clean, professional tree inventory with view and QR code options"""
    if 'selected_tree' not in st.session_state:
        st.session_state.selected_tree = None
    if 'qr_tree' not in st.session_state:
        st.session_state.qr_tree = None

    st.markdown("## 🌳 Tree Inventory")
    st.markdown("---")

    headers = ["Tree ID", "Local Name", "Scientific Name", "Planter", "Date Planted",
               "Status", "Height (m)", "DBH (cm)", "CO₂ (kg)", ""]
    col_widths = [1.2, 2.0, 2.0, 2.0, 1.5, 1.2, 1.0, 1.0, 1.0, 0.6]

    header_cols = st.columns(col_widths)
    for col, header in zip(header_cols, headers):
        col.markdown(f"**{header}**")

    for _, row in trees_df.iterrows():
        cols = st.columns(col_widths)
        cols[0].markdown(f"`{row.get('tree_id', 'N/A')[:8]}`")
        cols[1].write(row.get('local_name', 'N/A'))
        cols[2].write(row.get('scientific_name', 'N/A'))
        cols[3].write(row.get('planters_name', 'N/A') or row.get('planter_id', 'N/A'))
        cols[4].write(row.get('date_planted', 'N/A'))
        cols[5].write(row.get('status', 'N/A'))
        cols[6].write(f"{row.get('height_m', 0):.2f}" if pd.notna(row.get('height_m')) else "N/A")
        cols[7].write(f"{row.get('dbh_cm', 0):.2f}" if pd.notna(row.get('dbh_cm')) else "N/A")
        cols[8].write(f"{row.get('co2_kg', 0):.2f}" if pd.notna(row.get('co2_kg')) else "N/A")

        if cols[9].button("\U0001F441", key=f"view_{row['tree_id']}"):
            st.session_state.selected_tree = row['tree_id']
            st.session_state.qr_tree = row['tree_id']
            st.rerun()

    st.markdown("---")

    if st.session_state.get('selected_tree'):
        show_tree_details(st.session_state.selected_tree, trees_df)

    if st.session_state.get('qr_tree'):
        display_qr_code_if_selected()

def show_tree_details(tree_id, trees_df):
    """Show detailed information about a specific tree"""
    filtered_tree = trees_df[trees_df['tree_id'] == tree_id]
    if filtered_tree.empty:
        st.warning(f"No data found for Tree ID: {tree_id}")
        return

    tree_data = filtered_tree.iloc[0]

    st.markdown(f"### 🌿 Tree Details: `{tree_id}`")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown(f"""
            **Basic Information:**
            - **Local Name:** {tree_data.get('local_name', 'N/A')}
            - **Scientific Name:** {tree_data.get('scientific_name', 'N/A')}
            - **Planter:** {tree_data.get('planters_name', 'N/A') or tree_data.get('planter_id', 'N/A')}
            - **Date Planted:** {tree_data.get('date_planted', 'N/A')}
            - **Status:** {tree_data.get('status', 'N/A')}
        """)

    with col2:
        st.markdown(f"""
            **Measurements:**
            - **Height:** {f"{tree_data.get('height_m', 0):.2f} m" if pd.notna(tree_data.get('height_m')) else "N/A"}
            - **DBH:** {f"{tree_data.get('dbh_cm', 0):.2f} cm" if pd.notna(tree_data.get('dbh_cm')) else "N/A"}
            - **CO₂ Sequestered:** {f"{tree_data.get('co2_kg', 0):.2f} kg" if pd.notna(tree_data.get('co2_kg')) else "N/A"}
            - **Growth Stage:** {tree_data.get('tree_stage', 'N/A')}
        """)

    st.markdown("---")

def display_qr_code_if_selected():
    """Display the QR code section if a tree has been selected for QR"""
    if st.session_state.get('qr_tree'):
        tree_id = st.session_state.qr_tree
        current_tracking_number = st.session_state.get("user", {}).get("treeTrackingNumber", "")
        trees_df = load_tree_data_by_tracking_number(current_tracking_number)

        filtered_tree = trees_df[trees_df['tree_id'] == tree_id]

        if not filtered_tree.empty:
            tree_data = filtered_tree.iloc[0]

            tree_name = tree_data.get('local_name', '')
            planter = tree_data.get('planters_name', '') or tree_data.get('planter_id', '')
            date_planted = tree_data.get('date_planted', '')
            tree_specific_tracking_number = tree_data.get('treeTrackingNumber', current_tracking_number)

            qr_path = generate_qr_code(
                tree_id=tree_id,
                treeTrackingNumber=tree_specific_tracking_number,
                tree_name=tree_name,
                planter=planter,
                date_planted=date_planted
            )

            st.markdown(f"### 📌 QR Code for Tree `{tree_id}`")

            col1, col2 = st.columns([1, 2])
            with col1:
                if qr_path:
                    st.image(qr_path, caption="Scan to open monitoring form", width=200)

            with col2:
                st.markdown(f"""
                    **Tree Details:**
                    - **Local Name:** {tree_name}
                    - **Scientific Name:** {tree_data.get('scientific_name', 'N/A')}
                    - **Planter:** {planter}
                    - **Date Planted:** {date_planted}
                    - **Status:** {tree_data.get('status', 'N/A')}
                """)

                if qr_path:
                    with open(qr_path, "rb") as qr_file:
                        qr_bytes = qr_file.read()
                    st.download_button(
                        label="Download QR Code",
                        data=qr_bytes,
                        file_name=f"tree_{tree_id}_qrcode.png",
                        mime="image/png",
                        key=f"download_qr_{tree_id}"
                    )

            if st.button("Close QR Display", key="close_qr_button"):
                st.session_state.qr_tree = None
                st.session_state.selected_tree = None
                st.rerun()

        else:
            st.warning(f"No data found for Tree ID: {tree_id}")

# ----------------- QR CODE GENERATION -----------------
def generate_qr_code(tree_id, treeTrackingNumber, tree_tracking_number=None, tree_name=None, planter=None, date_planted=None):
    """Generate QR code with prefilled KoBo URL and labels"""
    try:
        tracking_param = treeTrackingNumber or tree_id
        base_url = "https://ee.kobotoolbox.org/x/dXdb36aV"
        params = f"?tree_id={tracking_param}"
        
        if tree_name:
            params += f"&name={tree_name.replace(' ', '+')}"
        if planter:
            params += f"&planter={planter.replace(' ', '+')}"
        if date_planted:
            params += f"&date_planted={date_planted}"
            
        form_url = base_url + params

        qr = qrcode.QRCode(version=1, box_size=10, border=4)
        qr.add_data(form_url)
        qr.make(fit=True)

        qr_img = qr.make_image(fill_color="#2e8b57", back_color="white").convert('RGB')
        width, qr_height = qr_img.size

        img = Image.new('RGB', (width, qr_height + 60), 'white')
        img.paste(qr_img, (0, 0))
        draw = ImageDraw.Draw(img)

        try:
            font = ImageFont.truetype("arial.ttf", 16)
        except:
            font = ImageFont.load_default()

        draw.text((10, qr_height + 10), f"Tree ID: {tree_id}", fill="black", font=font)
        draw.text((10, qr_height + 35), "Powered by CarbonTally", fill="gray", font=font)

        QR_CODE_DIR.mkdir(exist_ok=True, parents=True)
        file_path = QR_CODE_DIR / f"{tree_id}.png"
        img.save(file_path)

        return str(file_path)
    except Exception as e:
        st.error(f"QR generation failed: {e}")
        return None

# ----------------- FIELD AGENT MANAGEMENT -----------------
def generate_field_password():
    """Generates a random 4-digit password prefixed with 'CT'."""
    number = str(random.randint(1000, 9999))
    return f"CT{number}"

def manage_field_agent_credentials(tracking_number, user_name):
    """Manage field agent password generation and expiration"""
    st.subheader("🛡 Generate Field Agent Password")
    conn = None
    try:
        conn = get_db_connection()
        c = conn.cursor()

        c.execute("SELECT field_password, token_created_at FROM users WHERE tree_tracking_number = ?", (tracking_number,))
        result = c.fetchone()

        now = int(time.time())

        if result:
            password, created_at = result[0], result[1]
            remaining_time_seconds = max(0, 86400 - (now - created_at)) if created_at is not None else 0
            hours = remaining_time_seconds // 3600
            minutes = (remaining_time_seconds % 3600) // 60

            if result[0] and result[1] is not None and remaining_time_seconds > 0:
                st.success(f"🔑 Field Password: `{password}` (expires in {hours} hrs {minutes} mins)")
                if st.button("🔄 Regenerate Password", key="regenerate_fa_pass"):
                    new_pass = generate_field_password()
                    c.execute("""
                        UPDATE users SET field_password = ?, token_created_at = ?
                        WHERE tree_tracking_number = ?
                    """, (new_pass, now, tracking_number))
                    conn.commit()
                    st.success(f"✅ New Password Generated: `{new_pass}` (valid 24 hrs)")
                    st.rerun()
            else:
                if result[0] and result[1] is not None and remaining_time_seconds <= 0:
                    st.warning(f"🔑 Field Password: `{password}` (Expired! Please regenerate.)")
                st.info("No active field password found or valid creation time. Generate one below.")
                if st.button("➕ Generate New Password", key="generate_new_fa_pass_expired"):
                    new_pass = generate_field_password()
                    c.execute("SELECT COUNT(*) FROM users WHERE tree_tracking_number = ?", (tracking_number,))
                    user_exists = c.fetchone()[0] > 0
                    if user_exists:
                        c.execute("""
                            UPDATE users SET field_password = ?, token_created_at = ?
                            WHERE tree_tracking_number = ?
                        """, (new_pass, now, tracking_number))
                    else:
                        user_email_for_db = st.session_state.get("user", {}).get("email", f"field_agent_{tracking_number}@carbontally.com")
                        user_display_name_for_db = st.session_state.get("user", {}).get("username", f"Field Agent {tracking_number}")
                        c.execute("""
                            INSERT INTO users (full_name, email, tree_tracking_number, field_password, token_created_at, role, status)
                            VALUES (?, ?, ?, ?, ?, ?, ?)
                        """, (user_display_name_for_db, user_email_for_db, tracking_number, new_pass, now, "field_agent", "approved"))
                    conn.commit()
                    st.success(f"✅ Password Created: `{new_pass}` (valid 24 hrs)")
                    st.rerun()
        else:
            st.info("No active field password found or valid creation time. Generate one below.")
            if st.button("➕ Generate New Password", key="generate_new_fa_pass_new"):
                new_pass = generate_field_password()
                c.execute("SELECT COUNT(*) FROM users WHERE tree_tracking_number = ?", (tracking_number,))
                user_exists = c.fetchone()[0] > 0
                if user_exists:
                    c.execute("""
                        UPDATE users SET field_password = ?, token_created_at = ?
                        WHERE tree_tracking_number = ?
                    """, (new_pass, now, tracking_number))
                else:
                    user_email_for_db = st.session_state.get("user", {}).get("email", f"field_agent_{tracking_number}@carbontally.com")
                    user_display_name_for_db = st.session_state.get("user", {}).get("username", f"Field Agent {tracking_number}")
                    c.execute("""
                        INSERT INTO users (full_name, email, tree_tracking_number, field_password, token_created_at, role, status)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, (user_display_name_for_db, user_email_for_db, tracking_number, new_pass, now, "field_agent", "approved"))
                conn.commit()
                st.success(f"✅ Password Created: `{new_pass}` (valid 24 hrs)")
                st.rerun()
    except Exception as e:
        st.error(f"Error managing field agent credentials: {e}")
    finally:
        if conn:
            conn.close()

# ----------------- LOGO MANAGEMENT -----------------
def get_user_type_and_id():
    """Get user type and ID for logo management"""
    user_type = st.session_state.get("user", {}).get("role", "user")
    user_id = st.session_state.get("user", {}).get("id", "demo_user")
    return user_type, user_id

def get_logo_path(user_type, user_id):
    """Get the path for user's logo"""
    filename = f"{user_type}_{user_id}_logo.png"
    return os.path.join(LOGO_FOLDER, filename)

def display_logo_manager(user_type, user_id):
    """Display logo upload and management interface"""
    logo_path = get_logo_path(user_type, user_id)

    with st.expander("🏷️ Your Logo", expanded=True):
        if os.path.exists(logo_path):
            st.image(logo_path, width=150, caption="Current Logo")
        else:
            st.image(DEFAULT_LOGO_PATH, width=150, caption="Default Logo")

        uploaded_logo = st.file_uploader("Upload a new logo (PNG or JPG)", type=["png", "jpg", "jpeg"])
        if uploaded_logo:
            if uploaded_logo.size > MAX_FILE_SIZE:
                st.error("File too large. Max size is 1MB.")
            else:
                try:
                    with open(logo_path, "wb") as f:
                        f.write(uploaded_logo.getbuffer())
                    st.success("Logo uploaded successfully!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error saving logo: {e}")

        if os.path.exists(logo_path):
            if st.button("🗑️ Delete Logo"):
                try:
                    os.remove(logo_path)
                    st.success("Logo deleted successfully.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error deleting logo: {e}")

# ----------------- MAIN APPLICATION -----------------
def main():
    """Main application controller"""
    # Initialize users table in existing database
    init_users_table()
    
    # Show appropriate page based on authentication state
    if st.session_state.authenticated and st.session_state.user:
        show_dashboard()
    else:
        if st.session_state.page == "login":
            show_login_page()
        elif st.session_state.page == "register":
            show_register_page()
        else:
            show_login_page()

def show_dashboard():
    """Display the main dashboard for authenticated users"""
    # Add logout button in sidebar
    with st.sidebar:
        st.write(f"Welcome, **{st.session_state.user.get('username', 'User')}**!")
        if st.button("🚪 Logout"):
            logout_user()
            st.rerun()
        
        # User info
        st.markdown("---")
        st.markdown("### Account Info")
        user = st.session_state.user
        st.write(f"**Name:** {user.get('full_name', 'N/A')}")
        st.write(f"**Email:** {user.get('email', 'N/A')}")
        st.write(f"**Institution:** {user.get('institution', 'N/A')}")
        st.write(f"**Role:** {user.get('role', 'user').title()}")
        st.write(f"**Tracking Number:** {user.get('treeTrackingNumber', 'N/A')}")
    
    # Call your existing dashboard function
    unified_user_dashboard()

def unified_user_dashboard():
    """Main dashboard function displaying user's tree portfolio with metrics and analytics"""
    # Authentication check (now handled by main())
    if not st.session_state.authenticated:
        st.error("🔒 Please log in to access your dashboard")
        return

    # Get user data
    user_data = st.session_state.user
    current_tracking_number = user_data.get("treeTrackingNumber", "")
    
    if not current_tracking_number:
        st.warning("No tracking number associated with this account.")
        return

    # Load data
    with st.spinner("Loading your forest data..."):
        try:
            trees = load_tree_data_by_tracking_number(current_tracking_number)
            monitoring_history = load_monitoring_history(current_tracking_number)
            
            if not trees.empty and not monitoring_history.empty:
                latest_monitoring = monitoring_history.sort_values('monitor_date').groupby('tree_id').last().reset_index()
                trees = pd.merge(trees, latest_monitoring, on='tree_id', how='left', suffixes=('', '_monitor'))
                
            metrics = calculate_tree_metrics(trees)
        except Exception as e:
            st.error(f"Failed to load data: {str(e)}")
            return

    # Dashboard UI
    st.markdown(f"""
    <style>
        .dashboard-header {{
            background: linear-gradient(135deg, #1D7749 0%, #28a745 100%);
            color: white;
            padding: 1.5rem;
            border-radius: 10px;
            margin-bottom: 1.5rem;
        }}
        .metric-card {{
            background-color: white;
            border-radius: 10px;
            padding: 1rem;
            box-shadow: 0 4px 6px rgba(0,0,0,0.05);
            border-left: 4px solid #1D7749;
            height: 100%;
        }}
        .metric-value {{
            font-size: 1.8rem;
            font-weight: bold;
            color: #1D7749;
            margin: 0.5rem 0;
        }}
    </style>

    <div class="dashboard-header">
        <h1>{'🏫 ' + user_data.get('institution', '') if user_data.get('role') == "institution" else '👤 ' + user_data.get('username', 'User')}'s Forest Dashboard</h1>
        <p>Last updated: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}</p>
    </div>
    """, unsafe_allow_html=True)

    # Display tracking information
    st.markdown(f"""
    <div style="background-color: #f8f9fa; border-left: 4px solid #1D7749; padding: 1rem; margin-bottom: 1.5rem; border-radius: 8px;">
        <h4 style="margin:0; color: #1D7749;">Your Tree Tracking Number</h4>
        <div style="display: flex; align-items: center; gap: 0.5rem;">
            <p style="font-size: 1.5rem; font-weight: bold; margin:0.5rem 0 0 0; color: #333;">{current_tracking_number}</p>
            <button class="copy-btn" onclick="navigator.clipboard.writeText('{current_tracking_number}')">Copy</button>
        </div>
        <p style="font-size: 0.9rem; margin:0.2rem 0 0 0; color: #666;">Use this number to track your environmental impact</p>
    </div>
    """, unsafe_allow_html=True)

    # Key Metrics
    st.subheader("Key Metrics")
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.markdown(f"<div class='metric-card'><div class='metric-value'>{metrics['total_trees']}</div><div class='metric-label'>Total Trees Planted</div></div>", unsafe_allow_html=True)
    with col2:
        st.markdown(f"<div class='metric-card'><div class='metric-value'>{metrics['status_counts']['alive']}</div><div class='metric-label'>Trees Alive</div></div>", unsafe_allow_html=True)
    with col3:
        st.markdown(f"<div class='metric-card'><div class='metric-value'>{metrics['total_co2_absorbed']:.2f} kg</div><div class='metric-label'>Total CO₂ Absorbed</div></div>", unsafe_allow_html=True)
    with col4:
        health_score = calculate_health_score(metrics['health_status'])
        st.markdown(f"<div class='metric-card'><div class='metric-value'>{health_score}%</div><div class='metric-label'>Overall Forest Health</div></div>", unsafe_allow_html=True)

    st.markdown("---")

    # Dashboard Tabs
    tab1, tab2, tab3, tab4 = st.tabs([
        "🌿 Forest Overview", 
        "📈 Growth Analytics", 
        "🌳 Tree Inventory", 
        "🛡 Field Agent Access"
    ])

    with tab1:
        display_forest_overview(trees, metrics)

    with tab2:
        display_growth_analytics(trees, monitoring_history)

    with tab3:
        if not trees.empty:
            display_tree_inventory(trees)
        else:
            st.info("No trees to display in the inventory yet.")

    with tab4:
        manage_field_agent_credentials(current_tracking_number, user_data.get("username", "User"))

    # User settings
    user_type, user_id = get_user_type_and_id()
    display_logo_manager(user_type, user_id)

if __name__ == '__main__':
    main()
