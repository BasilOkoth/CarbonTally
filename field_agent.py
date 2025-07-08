import streamlit as st
import pandas as pd
import geopy.distance
import sqlite3
import math
from pathlib import Path
from streamlit_js_eval import streamlit_js_eval
# Assuming these modules are available in the same directory or installed
# from unified_user_dashboard_FINAL import generate_qr_code
# from kobo_integration import get_kobo_secrets

# Placeholder functions for external modules to make the code runnable for correction purposes
def generate_qr_code(data):
    """Placeholder for QR code generation."""
    return f"QR_CODE_FOR_{data}"

def get_kobo_secrets():
    """Fetch Kobo secrets from Streamlit's secrets.toml."""
    api_token = st.secrets["KOBO_API_TOKEN"]
    asset_id = st.secrets["KOBO_ASSET_ID"]
    form_code = st.secrets["KOBO_ASSET_FORM_CODE"]
    monitoring_asset_id = st.secrets["KOBO_MONITORING_ASSET_ID"]
    monitoring_form_code = st.secrets["KOBO_MONITORING_ASSET"]
    return api_token, asset_id, form_code, monitoring_asset_id, monitoring_form_code


def field_agent_portal():
    st.markdown("""
        <style>
            .section-header {
                font-size: 1.5rem;
                font-weight: 600;
                margin-top: 2rem;
                color: #1D7749;
            }
            .custom-button,
            div.stButton > button#find-nearby-btn,
            div.stButton > button#logout-field-btn {
                background-color: #1D7749 !important;
                color: white !important;
                padding: 0.6em 1.2em;
                font-size: 1rem;
                border: none;
                border-radius: 5px;
                cursor: pointer;
                text-decoration: none;
                display: inline-block;
                margin-top: 0.5rem;
            }
            .custom-button:hover,
            div.stButton > button#find-nearby-btn:hover,
            div.stButton > button#logout-field-btn:hover {
                background-color: #166534 !important;
            }
        </style>
    """, unsafe_allow_html=True)

    st.title("🌍 Field Agent Portal")

    BASE_DIR = Path(__file__).parent if "__file__" in locals() else Path.cwd()
    DATA_DIR = BASE_DIR / "data"
    SQLITE_DB = DATA_DIR / "trees.db"

    def get_bearing(lat1, lon1, lat2, lon2):
        dLon = math.radians(lon2 - lon1)
        y = math.sin(dLon) * math.cos(math.radians(lat2))
        x = math.cos(math.radians(lat1)) * math.sin(math.radians(lat2)) - math.sin(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.cos(dLon)
        bearing = math.degrees(math.atan2(y, x))
        return (bearing + 360) % 360

    def bearing_to_compass(bearing):
        directions = ["North", "North-East", "East", "South-East", "South", "South-West", "West", "North-West"]
        ix = round(bearing / 45) % 8
        return directions[ix]

    def find_nearby_trees(lat, lon, trees_dataframe, tracking_number):
        nearby = []
        # Filter the DataFrame for the specific tracking number
        df_filtered = trees_dataframe[trees_dataframe["tree_tracking_number"] == tracking_number]

        for _, row in df_filtered.iterrows():
            if pd.notna(row["latitude"]) and pd.notna(row["longitude"]):
                dist = geopy.distance.distance((row["latitude"], row["longitude"]), (lat, lon)).m
                if 3 <= dist <= 5:
                    bearing = get_bearing(lat, lon, row["latitude"], row["longitude"])
                    direction = bearing_to_compass(bearing)
                    nearby.append({
                        "Tree ID": row["tree_id"],
                        "Species": row["local_name"],
                        "Distance (m)": round(dist, 2),
                        "Direction": direction,
                        "Planted By": row["planters_name"]
                    })
        return pd.DataFrame(nearby)

    KOBO_API_TOKEN, KOBO_ASSET_ID, KOBO_FORM_CODE, KOBO_MONITORING_ASSET_ID, KOBO_MONITORING_FORM_CODE = get_kobo_secrets()

    # Using st.secrets.get for a more robust way to get secrets in Streamlit
    KOBO_MONITORING_FORM_ID = st.secrets.get("KOBO_MONITORING_FORM_CODE", "your_monitoring_form_code")

    field_access_granted = st.session_state.get("field_agent_authenticated", False)
    entered_tracking_number = st.session_state.get("field_agent_tracking_number", None)
    field_agent_name = st.session_state.get("field_agent_name", "Field Agent")

    if not field_access_granted:
        st.warning("🚫 You must log in to access the Field Agent Portal.")
        if st.button("🔐 Go to Field Agent Login"):
            st.session_state.page = "FieldAgentLogin"
            st.rerun()
        return

    st.success(f"✅ Welcome, {field_agent_name} — Access granted for tracking number: `{entered_tracking_number}`")

    # Establish database connection and load data
    conn = sqlite3.connect(str(SQLITE_DB))
    trees_df = pd.read_sql_query("""
        SELECT tree_id, local_name, scientific_name, latitude, longitude, tree_tracking_number, planters_name
        FROM trees
    """, conn)
    conn.close()

    st.markdown('<div class="section-header">🌐 How to Monitor Trees</div>', unsafe_allow_html=True)
    st.markdown("""
You can monitor a tree in two ways:

- 📷 **Scan a QR Code** attached to the tree (using your camera or scanner)
- 📍 **Find a Nearby Tree** using your GPS location (3–5 meters range)
""")

    st.markdown('<div class="section-header">📍 Your GPS Location</div>', unsafe_allow_html=True)

    # Initialize session state for user location if not present
    if "user_lat" not in st.session_state:
        st.session_state["user_lat"] = None
    if "user_lon" not in st.session_state:
        st.session_state["user_lon"] = None

    user_lat = st.session_state["user_lat"]
    user_lon = st.session_state["user_lon"]

    # Only try to get location if we don't have it yet
    if user_lat is None or user_lon is None:
        st.info("⏳ Fetching your current GPS location...")
        loc = streamlit_js_eval(
            js_expressions="""
            new Promise((resolve, reject) => {
                navigator.geolocation.getCurrentPosition(
                    (position) => resolve({coords: {latitude: position.coords.latitude, longitude: position.coords.longitude}}),
                    (error) => {
                        console.error("Geolocation error:", error);
                        resolve({error: error.message}); // Resolve with error info
                    },
                    { enableHighAccuracy: true, timeout: 10000, maximumAge: 0 } // Options for better accuracy
                );
            })
            """,
            key="getGeo"
        )

        if loc:
            if "coords" in loc:
                st.session_state["user_lat"] = loc["coords"]["latitude"]
                st.session_state["user_lon"] = loc["coords"]["longitude"]
                user_lat = st.session_state["user_lat"] # Update local variables immediately
                user_lon = st.session_state["user_lon"]
                st.success(f"📍 Location found: **Latitude {user_lat:.5f}, Longitude {user_lon:.5f}**")
                # Rerun to update the UI with the fetched location and enable "Find Trees Nearby"
                st.rerun()
            elif "error" in loc:
                st.error(f"⚠️ Geolocation error: {loc['error']}. Please ensure location access is granted.")
                st.info("If it doesn’t prompt you, reset your location permission in the browser settings.")
            else:
                st.warning("⚠️ Please allow GPS location in your browser to find nearby trees.")
                st.info("If it doesn’t prompt you, reset your location permission in the browser settings.")
    else:
        st.success(f"📍 Location found: **Latitude {user_lat:.5f}, Longitude {user_lon:.5f}**")


    st.markdown('<div class="section-header">🌲 Find Nearby Trees</div>', unsafe_allow_html=True)

    # Initialize session state for 'find_nearby' if it doesn't exist
    if "find_nearby" not in st.session_state:
        st.session_state["find_nearby"] = False

    # Disable the button if location is not yet available
    if st.button("🔍 Find Trees Nearby", key="find-nearby-btn", disabled=(user_lat is None or user_lon is None)):
        st.session_state["find_nearby"] = True

    if st.session_state.get("find_nearby"):
        if user_lat and user_lon:
            # Pass trees_df and entered_tracking_number to find_nearby_trees
            nearby = find_nearby_trees(user_lat, user_lon, trees_df, entered_tracking_number)
            if not nearby.empty:
                st.success(f"🎉 Found {len(nearby)} tree(s) within 3–5 meters.")
                st.dataframe(nearby)
                selected_tree_id = st.selectbox("Select a tree to monitor", nearby["Tree ID"])
                if st.button("📋 Monitor This Tree"):
                    form_url = f"https://ee.kobotoolbox.org/x/{KOBO_MONITORING_ASSET}?tree_id={selected_tree_id}&tree_tracking_number={entered_tracking_number}"
                    st.markdown(f"**[📝 Open Monitoring Form for Tree {selected_tree_id}]({form_url})**", unsafe_allow_html=True)
            else:
                st.info("No trees found within 3–5 meters.")
        else:
            # This else block should ideally not be hit if the button is disabled when location is not available
            st.error("🌐 Location not available. Please ensure location access is granted and try again.")

    st.markdown('<div class="section-header">🌱 Plant a New Tree</div>', unsafe_allow_html=True)
    
    planting_url = f"https://ee.kobotoolbox.org/x/{KOBO_FORM_CODE}?tree_tracking_number={entered_tracking_number}"
    st.markdown("Click the button below to record a newly planted tree using the official form:")
    st.markdown(f"""
    <a href="{planting_url}" target="_blank">
        <button class="custom-button">
            ➕ Fill Planting Form
        </button>
    </a>
    """, unsafe_allow_html=True)

    st.markdown('<div class="section-header">📋 All Submitted Trees</div>', unsafe_allow_html=True)
    submitted = trees_df[trees_df["tree_tracking_number"] == entered_tracking_number]
    if submitted.empty:
        st.info("You have not submitted any trees yet.")
    else:
        st.dataframe(submitted.sort_values(by="tree_id", ascending=False))

    st.markdown("---")
    if st.button("🚪 Logout from Field Portal", key="logout-field-btn"):
        st.session_state.field_agent_authenticated = False
        st.session_state.field_agent_tracking_number = None
        st.session_state.field_agent_name = None
        # Clear location from session state on logout
        st.session_state["user_lat"] = None
        st.session_state["user_lon"] = None
        st.session_state.page = "Landing"
        st.rerun()

# This is typically how you'd run a Streamlit app, though it might be called from app.py
# if __name__ == "__main__":
#     field_agent_portal()
