import streamlit as st
import requests
import json
import time
import pandas as pd
import sqlite3
import qrcode
from io import BytesIO
import base64
import os
from pathlib import Path
import re
from datetime import datetime, timedelta
import matplotlib.pyplot as plt
import seaborn as sns

# KoBo Toolbox configuration
KOBO_API_URL = "https://kf.kobotoolbox.org/api/v2"
try:
    KOBO_API_TOKEN = st.secrets["KOBO"]["API_TOKEN"]
    KOBO_ASSET_ID = st.secrets["KOBO"]["ASSET_ID"]
    KOBO_MONITORING_ASSET_ID = st.secrets["KOBO"]["MONITORING_ASSET_ID"]
except Exception as e:
    st.warning(f"Could not load KoBo secrets: {e}")
    KOBO_API_TOKEN = "dummy_token"
    KOBO_ASSET_ID = "dummy_asset_id"
    KOBO_MONITORING_ASSET_ID = "aDSNfsXbXygrn8rwKog5Yd"

# Database configuration
BASE_DIR = Path(__file__).parent if "__file__" in locals() else Path.cwd()
DATA_DIR = BASE_DIR / "data"
SQLITE_DB = DATA_DIR / "trees.db"
QR_CODE_DIR = DATA_DIR / "qr_codes"
DATA_DIR.mkdir(exist_ok=True, parents=True)
QR_CODE_DIR.mkdir(exist_ok=True, parents=True)

def initialize_database():
    """Initialize database tables"""
    conn = sqlite3.connect(SQLITE_DB)
    try:
        c = conn.cursor()
        c.execute('''
            CREATE TABLE IF NOT EXISTS trees (
                tree_id TEXT PRIMARY KEY,
                institution TEXT,
                local_name TEXT,
                scientific_name TEXT,
                student_name TEXT,
                date_planted TEXT,
                tree_stage TEXT,
                rcd_cm REAL,
                dbh_cm REAL,
                height_m REAL,
                latitude REAL,
                longitude REAL,
                co2_kg REAL,
                status TEXT,
                country TEXT,
                county TEXT,
                sub_county TEXT,
                ward TEXT,
                adopter_name TEXT,
                last_monitored TEXT,
                monitor_notes TEXT,
                qr_code TEXT,
                kobo_submission_id TEXT UNIQUE,
                tree_tracking_number TEXT
            )
        ''')
        
        # Check and add tree_tracking_number if missing
        c.execute("PRAGMA table_info(trees)")
        if "tree_tracking_number" not in [col[1] for col in c.fetchall()]:
            c.execute("ALTER TABLE trees ADD COLUMN tree_tracking_number TEXT")
        
        # Create monitoring_history table
        c.execute('''
            CREATE TABLE IF NOT EXISTS monitoring_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tree_id TEXT,
                monitor_date TEXT,
                monitor_status TEXT,
                monitor_stage TEXT,
                rcd_cm REAL,
                dbh_cm REAL,
                height_m REAL,
                co2_kg REAL,
                notes TEXT,
                monitor_by TEXT,
                kobo_submission_id TEXT UNIQUE,
                FOREIGN KEY (tree_id) REFERENCES trees (tree_id)
            )
        ''')
        
        # Create processed submissions table
        c.execute('''
            CREATE TABLE IF NOT EXISTS processed_monitoring_submissions (
                submission_id TEXT PRIMARY KEY,
                tree_id TEXT,
                processed_date TEXT,
                FOREIGN KEY (tree_id) REFERENCES trees (tree_id)
            )
        ''')
        
        conn.commit()
    except Exception as e:
        st.error(f"Database initialization error: {str(e)}")
    finally:
        conn.close()

def validate_user_session():
    """Validate user session"""
    if "user" not in st.session_state:
        st.error("Please log in")
        return False
        
    required = ["username", "user_type"]
    missing = [field for field in required if field not in st.session_state.user]
    if missing:
        st.error(f"Missing user fields: {', '.join(missing)}")
        return False
        
    return True

def ensure_institution_assigned():
    """Ensure institution is assigned to user"""
    if "user" not in st.session_state:
        return None
        
    if st.session_state.user.get("institution"):
        return st.session_state.user["institution"]
        
    if st.session_state.user.get('user_type') in ["school", "field", "admin"]:
        conn = sqlite3.connect(SQLITE_DB)
        try:
            institutions = pd.read_sql(
                "SELECT DISTINCT institution FROM trees WHERE institution IS NOT NULL",
                conn
            )["institution"].tolist()
        except Exception as e:
            st.error(f"Error fetching institutions: {str(e)}")
            institutions = []
        finally:
            conn.close()
            
        if not institutions:
            institutions = ["School A", "School B", "Other (specify)"]
            
        selected = st.selectbox("Select institution", ["-- Select --"] + institutions)
        if selected == "Other (specify)":
            selected = st.text_input("Enter institution name")
            
        if selected and selected != "-- Select --":
            st.session_state.user["institution"] = selected
            st.rerun()
            
    return st.session_state.user.get("institution")

def get_tree_details(tree_id):
    """Get details for a specific tree"""
    if not tree_id:
        return None
        
    conn = sqlite3.connect(SQLITE_DB)
    try:
        tree_df = pd.read_sql("SELECT * FROM trees WHERE tree_id = ?", conn, params=(tree_id,))
        if tree_df.empty:
            return None
            
        history_df = pd.read_sql(
            "SELECT * FROM monitoring_history WHERE tree_id = ? ORDER BY monitor_date DESC",
            conn,
            params=(tree_id,)
        )
        
        result = tree_df.iloc[0].to_dict()
        result["monitoring_history"] = history_df.to_dict('records')
        return result
    except Exception as e:
        st.error(f"Error getting tree details: {str(e)}")
        return None
    finally:
        conn.close()

def generate_tree_qr_code(tree_id, tree_data=None):
    """Generate QR code for tree monitoring"""
    try:
        if tree_data is None:
            tree_data = get_tree_details(tree_id)
            if not tree_data:
                return None, None
                
        params = {
            "tree_id": tree_id,
            "local_name": tree_data.get("local_name", ""),
            "scientific_name": tree_data.get("scientific_name", ""),
            "date_planted": tree_data.get("date_planted", ""),
            "planter": tree_data.get("student_name", ""),
            "institution": tree_data.get("institution", ""),
            "tree_tracking_number": tree_data.get("tree_tracking_number", "")
        }
        
        url_params = "&".join([f"{k}={v}" for k, v in params.items() if v])
        monitoring_url = f"https://ee.kobotoolbox.org/x/{KOBO_MONITORING_ASSET_ID}?{url_params}"
        
        qr = qrcode.QRCode(version=1, box_size=10, border=4)
        qr.add_data(monitoring_url)
        qr.make(fit=True)
        img = qr.make_image(fill_color="#2e8b57", back_color="white")
        
        file_path = QR_CODE_DIR / f"{tree_id}.png"
        img.save(file_path)
        
        buffered = BytesIO()
        img.save(buffered, format="PNG")
        img_str = base64.b64encode(buffered.getvalue()).decode()
        
        return img_str, str(file_path)
    except Exception as e:
        st.error(f"QR generation error: {str(e)}")
        return None, None

def admin_tree_lookup():
    """Admin tree lookup interface"""
    if not validate_user_session() or st.session_state.user.get("user_type") != "admin":
        st.error("Admin access required")
        return
        
    tree_id = st.text_input("Enter Tree ID")
    if tree_id:
        tree_data = get_tree_details(tree_id)
        if not tree_data:
            st.error("Tree not found")
            return
            
        col1, col2 = st.columns(2)
        with col1:
            st.write("**Local Name:**", tree_data.get("local_name", "N/A"))
            st.write("**Scientific Name:**", tree_data.get("scientific_name", "N/A"))
            st.write("**Institution:**", tree_data.get("institution", "N/A"))
            st.write("**Planted By:**", tree_data.get("student_name", "N/A"))
            
        with col2:
            st.write("**Status:**", tree_data.get("status", "N/A"))
            st.write("**Growth Stage:**", tree_data.get("tree_stage", "N/A"))
            st.write("**Last Monitored:**", tree_data.get("last_monitored", "N/A"))
            
        # QR Code section
        qr_img, qr_path = generate_tree_qr_code(tree_data['tree_id'], tree_data)
        if qr_img:
            st.image(f"data:image/png;base64,{qr_img}", width=200)
            if os.path.exists(qr_path):
                with open(qr_path, "rb") as f:
                    st.download_button(
                        "Download QR Code",
                        f.read(),
                        file_name=f"tree_{tree_data['tree_id']}_qr.png"
                    )

def get_monitoring_stats():
    """Get monitoring statistics"""
    conn = sqlite3.connect(SQLITE_DB)
    try:
        stats = pd.read_sql(
            """
            SELECT 
                COUNT(DISTINCT tree_id) as monitored_trees,
                COUNT(*) as monitoring_events,
                COALESCE(AVG(co2_kg), 0) as avg_co2,
                SUM(CASE WHEN monitor_status = 'Alive' THEN 1 ELSE 0 END) as alive_count,
                COUNT(DISTINCT monitor_by) as monitors_count
            FROM monitoring_history
            """,
            conn
        )
        
        by_date = pd.read_sql(
            "SELECT monitor_date, COUNT(*) as count FROM monitoring_history GROUP BY monitor_date ORDER BY monitor_date",
            conn
        )
        
        by_institution = pd.read_sql(
            """SELECT t.institution, COUNT(DISTINCT m.tree_id) as monitored_trees, COUNT(*) as monitoring_events
               FROM monitoring_history m JOIN trees t ON m.tree_id = t.tree_id
               GROUP BY t.institution ORDER BY monitored_trees DESC""",
            conn
        )
        
        growth_stages = pd.read_sql(
            "SELECT monitor_stage, COUNT(*) as count FROM monitoring_history GROUP BY monitor_stage ORDER BY count DESC",
            conn
        )
        
        return {
            "stats": stats.iloc[0].to_dict() if not stats.empty else {"avg_co2": 0},
            "monitoring_by_date": by_date.to_dict('records'),
            "monitoring_by_institution": by_institution.to_dict('records'),
            "growth_stages": growth_stages.to_dict('records')
        }
    except Exception as e:
        st.error(f"Error getting stats: {str(e)}")
        return {
            "stats": {"avg_co2": 0},
            "monitoring_by_date": [],
            "monitoring_by_institution": [],
            "growth_stages": []
        }
    finally:
        conn.close()

def display_monitoring_dashboard():
    """Display monitoring dashboard"""
    st.title("🌳 Tree Monitoring Dashboard")
    
    stats = get_monitoring_stats()
    
    cols = st.columns(4)
    with cols[0]:
        st.metric("Trees Monitored", stats["stats"].get("monitored_trees", 0))
    with cols[1]:
        st.metric("Monitoring Events", stats["stats"].get("monitoring_events", 0))
    with cols[2]:
        alive = stats["stats"].get("alive_count", 0)
        total = stats["stats"].get("monitoring_events", 1)
        rate = (alive / total) * 100 if total > 0 else 0
        st.metric("Survival Rate", f"{rate:.1f}%")
    with cols[3]:
        avg_co2 = float(stats["stats"].get("avg_co2", 0))
        st.metric("Avg. CO₂ per Tree", f"{avg_co2:.2f} kg")
    
    # Visualization tabs
    tab1, tab2, tab3 = st.tabs(["By Institution", "Growth Stages", "Over Time"])
    
    with tab1:
        if stats["monitoring_by_institution"]:
            df = pd.DataFrame(stats["monitoring_by_institution"])
            fig, ax = plt.subplots()
            sns.barplot(x="institution", y="monitored_trees", data=df, ax=ax)
            plt.xticks(rotation=45, ha="right")
            st.pyplot(fig)
        else:
            st.info("No institution data")
    
    with tab2:
        if stats["growth_stages"]:
            df = pd.DataFrame(stats["growth_stages"])
            fig, ax = plt.subplots()
            ax.pie(df["count"], labels=df["monitor_stage"], autopct="%1.1f%%")
            st.pyplot(fig)
        else:
            st.info("No growth stage data")
    
    with tab3:
        if stats["monitoring_by_date"]:
            df = pd.DataFrame(stats["monitoring_by_date"])
            df["monitor_date"] = pd.to_datetime(df["monitor_date"])
            fig, ax = plt.subplots()
            sns.lineplot(x="monitor_date", y="count", data=df, ax=ax)
            plt.xticks(rotation=45)
            st.pyplot(fig)
        else:
            st.info("No timeline data")

def monitoring_section():
    """Main monitoring interface"""
    st.title("🌳 Tree Monitoring System")
    initialize_database()
    
    tabs = st.tabs(["Tree Lookup", "Monitoring Dashboard", "Process Submissions"])
    
    with tabs[0]:
        tree_id = st.text_input("Enter Tree ID")
        if tree_id:
            tree_data = get_tree_details(tree_id)
            if tree_data:
                display_tree_details(tree_data)
            else:
                st.error("Tree not found")
    
    with tabs[1]:
        display_monitoring_dashboard()
    
    with tabs[2]:
        hours = st.slider("Hours to check", 1, 168, 24)
        if st.button("Check for New Submissions"):
            if validate_user_session():
                with st.spinner("Processing..."):
                    results = check_for_new_monitoring_submissions(hours)
                    if results:
                        st.success(f"Processed {len(results)} submissions")
                    else:
                        st.info("No new submissions found")
            else:
                st.warning("Please log in")

if __name__ == "__main__":
    st.set_page_config(page_title="Tree Monitoring", layout="wide")
    if 'user' not in st.session_state:
        st.session_state.user = {
            "username": "admin",
            "user_type": "admin",
            "email": "admin@example.com"
        }
    monitoring_section()
