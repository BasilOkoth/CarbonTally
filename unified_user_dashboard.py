import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import datetime
import sqlite3
from pathlib import Path

# This file implements the unified dashboard for individual and institution users
# It merges the functionality previously separated into different dashboards

# Configuration
BASE_DIR = Path(__file__).parent if "__file__" in locals() else Path.cwd()
DATA_DIR = BASE_DIR / "data"
SQLITE_DB = DATA_DIR / "trees.db"

def unified_user_dashboard():
    """
    Unified dashboard for both individual and institution users
    """
    # Get user data from session state
    user_data = st.session_state.get("user", {})
    user_role = user_data.get("role", "")
    user_name = user_data.get("displayName", "User")
    institution_name = user_data.get("institution", "")
    tracking_number = user_data.get("treeTrackingNumber", "")
    
    # Determine header text based on user role
    if user_role == "institution":
        header_text = f"🏫 {institution_name} Dashboard"
    else:
        header_text = f"👤 {user_name}'s Dashboard"
    
    st.markdown(f"<h1 class='header-text'>{header_text}</h1>", unsafe_allow_html=True)
    
    # Display tracking number prominently
    st.markdown(f"""
    <div style="background-color: #f0f7f0; border-left: 4px solid #1D7749; padding: 1rem; margin-bottom: 1.5rem;">
        <h4 style="margin:0; color: #1D7749;">Your Tree Tracking Number</h4>
        <p style="font-size: 1.5rem; font-weight: bold; margin:0.5rem 0 0 0;">{tracking_number}</p>
        <p style="font-size: 0.9rem; margin:0.2rem 0 0 0; color: #666;">Use this number when planting trees to track your impact</p>
    </div>
    """, unsafe_allow_html=True)
    
    # Load tree data filtered by tracking number
    trees = load_tree_data_by_tracking_number(tracking_number)
    
    # Display metrics
    display_user_metrics(trees)
    
    # Main dashboard tabs
    tab1, tab2, tab3 = st.tabs(["📊 My Trees", "🌱 Growth Tracking", "🌍 Environmental Impact"])
    
    with tab1:
        display_my_trees_tab(trees, tracking_number)
    
    with tab2:
        display_growth_tracking_tab(trees)
    
    with tab3:
        display_environmental_impact_tab(trees)

def load_tree_data_by_tracking_number(tracking_number):
    """
    Load tree data filtered by the user's tracking number
    """
    if not tracking_number:
        return pd.DataFrame()
    
    conn = sqlite3.connect(SQLITE_DB)
    try:
        query = "SELECT * FROM trees WHERE tree_tracking_number = ?"
        df = pd.read_sql(query, conn, params=(tracking_number,))
    except Exception as e:
        st.error(f"Error loading tree data: {str(e)}")
        df = pd.DataFrame()
    finally:
        conn.close()
    
    return df

def display_user_metrics(trees):
    """
    Display key metrics for the user's trees
    """
    # Calculate metrics
    total_trees = len(trees)
    alive_trees = len(trees[trees["status"] == "Alive"]) if "status" in trees.columns and not trees.empty else 0
    survival_rate = f"{round((alive_trees / total_trees) * 100, 1)}%" if total_trees > 0 else "0%"
    co2_sequestered = f"{round(trees['co2_kg'].sum(), 2)} kg" if "co2_kg" in trees.columns and not trees.empty else "0 kg"
    
    # Display metrics in cards
    cols = st.columns(4)
    metrics_data = [
        (total_trees, "Total Trees"),
        (alive_trees, "Alive Trees"),
        (survival_rate, "Survival Rate"),
        (co2_sequestered, "CO₂ Sequestered")
    ]
    
    for i, (value, label) in enumerate(metrics_data):
        with cols[i]:
            st.markdown(f"""
            <div class="metric-card">
                <div class="metric-value">{value}</div>
                <div class="metric-label">{label}</div>
            </div>
            """, unsafe_allow_html=True)

def display_my_trees_tab(trees, tracking_number):
    """
    Display the user's trees with details and map
    """
    st.markdown("<h3 style='color: #1D7749; margin-top:1rem; margin-bottom: 0.5rem;'>My Trees</h3>", unsafe_allow_html=True)
    
    if trees.empty:
        st.info(f"No trees found for tracking number {tracking_number}. Plant your first tree to get started!")
        return
    
    # Display recent trees table
    st.markdown("<h4 style='color: #333; margin-top:1rem; margin-bottom: 0.5rem;'>Recently Planted Trees</h4>", unsafe_allow_html=True)
    recent_trees = trees.sort_values("date_planted", ascending=False).head(10)
    st.dataframe(
        recent_trees[["tree_id", "local_name", "scientific_name", "date_planted", "status"]],
        use_container_width=True
    )
    
    # Display tree map if coordinates are available
    if "latitude" in trees.columns and "longitude" in trees.columns:
        st.markdown("<h4 style='color: #333; margin-top:1rem; margin-bottom: 0.5rem;'>Tree Map</h4>", unsafe_allow_html=True)
        
        # Filter out trees with missing coordinates
        map_trees = trees.dropna(subset=["latitude", "longitude"])
        
        if not map_trees.empty:
            fig_map = px.scatter_mapbox(
                map_trees, 
                lat="latitude", 
                lon="longitude", 
                hover_name="tree_id",
                hover_data={
                    "local_name": True, 
                    "date_planted": True, 
                    "status": True,
                    "latitude": False, 
                    "longitude": False
                },
                color="status", 
                color_discrete_map={"Alive": "#28a745", "Dead": "#dc3545"},
                zoom=10, 
                height=400
            )
            fig_map.update_layout(mapbox_style="carto-positron", margin={"r":0,"t":0,"l":0,"b":0})
            st.plotly_chart(fig_map, use_container_width=True)
        else:
            st.info("No location data available for your trees.")

def display_growth_tracking_tab(trees):
    """
    Display growth tracking charts and monitoring history
    """
    st.markdown("<h3 style='color: #1D7749; margin-top:1rem; margin-bottom: 0.5rem;'>Growth Tracking</h3>", unsafe_allow_html=True)
    
    if trees.empty:
        st.info("No trees found. Plant your first tree to track growth!")
        return
    
    # Get monitoring history for all trees
    monitoring_history = load_monitoring_history(trees["tree_id"].tolist())
    
    if monitoring_history.empty:
        st.info("No monitoring data available yet. Monitor your trees to track their growth!")
        return
    
    # Display growth charts
    st.markdown("<h4 style='color: #333; margin-top:1rem; margin-bottom: 0.5rem;'>Growth Trends</h4>", unsafe_allow_html=True)
    
    # Aggregate monitoring data by date
    monitoring_by_date = monitoring_history.groupby("monitor_date").agg({
        "height_m": "mean",
        "dbh_cm": "mean",
        "rcd_cm": "mean",
        "co2_kg": "mean"
    }).reset_index()
    
    # Convert date to datetime
    monitoring_by_date["monitor_date"] = pd.to_datetime(monitoring_by_date["monitor_date"])
    monitoring_by_date = monitoring_by_date.sort_values("monitor_date")
    
    # Create growth charts
    col1, col2 = st.columns(2)
    
    with col1:
        # Height chart
        fig_height = px.line(
            monitoring_by_date, 
            x="monitor_date", 
            y="height_m",
            title="Average Tree Height (m)",
            markers=True
        )
        fig_height.update_layout(margin=dict(l=20, r=20, t=30, b=20))
        st.plotly_chart(fig_height, use_container_width=True)
    
    with col2:
        # DBH/RCD chart (choose based on data availability)
        if monitoring_by_date["dbh_cm"].sum() > 0:
            fig_diameter = px.line(
                monitoring_by_date, 
                x="monitor_date", 
                y="dbh_cm",
                title="Average Diameter at Breast Height (cm)",
                markers=True
            )
        else:
            fig_diameter = px.line(
                monitoring_by_date, 
                x="monitor_date", 
                y="rcd_cm",
                title="Average Root Collar Diameter (cm)",
                markers=True
            )
        fig_diameter.update_layout(margin=dict(l=20, r=20, t=30, b=20))
        st.plotly_chart(fig_diameter, use_container_width=True)
    
    # Display recent monitoring history
    st.markdown("<h4 style='color: #333; margin-top:1rem; margin-bottom: 0.5rem;'>Recent Monitoring</h4>", unsafe_allow_html=True)
    recent_monitoring = monitoring_history.sort_values("monitor_date", ascending=False).head(10)
    st.dataframe(
        recent_monitoring[["tree_id", "monitor_date", "monitor_status", "monitor_stage", "height_m", "co2_kg"]],
        use_container_width=True
    )

def display_environmental_impact_tab(trees):
    """
    Display environmental impact metrics and visualizations
    """
    st.markdown("<h3 style='color: #1D7749; margin-top:1rem; margin-bottom: 0.5rem;'>Environmental Impact</h3>", unsafe_allow_html=True)
    
    if trees.empty:
        st.info("No trees found. Plant your first tree to track environmental impact!")
        return
    
    # Calculate total CO2 sequestered
    total_co2 = trees["co2_kg"].sum() if "co2_kg" in trees.columns else 0
    
    # Display CO2 impact visualization
    st.markdown("<h4 style='color: #333; margin-top:1rem; margin-bottom: 0.5rem;'>Carbon Sequestration</h4>", unsafe_allow_html=True)
    
    col1, col2 = st.columns([1, 2])
    
    with col1:
        # CO2 gauge chart
        fig_gauge = go.Figure(go.Indicator(
            mode="gauge+number+delta",
            value=total_co2,
            title={"text": "Total CO₂ Sequestered (kg)"},
            delta={"reference": 0},
            gauge={
                "axis": {"range": [None, max(100, total_co2 * 1.2)]},
                "bar": {"color": "#1D7749"},
                "steps": [
                    {"range": [0, 50], "color": "#e6f2e6"},
                    {"range": [50, 100], "color": "#c6e6c6"}
                ]
            }
        ))
        fig_gauge.update_layout(margin=dict(l=20, r=20, t=50, b=20), height=300)
        st.plotly_chart(fig_gauge, use_container_width=True)
    
    with col2:
        # CO2 by species chart
        co2_by_species = trees.groupby("local_name").agg({
            "co2_kg": "sum",
            "tree_id": "count"
        }).reset_index()
        co2_by_species.columns = ["Species", "CO2 (kg)", "Tree Count"]
        co2_by_species = co2_by_species.sort_values("CO2 (kg)", ascending=False)
        
        fig_species = px.bar(
            co2_by_species,
            x="Species",
            y="CO2 (kg)",
            title="CO₂ Sequestered by Species",
            color="CO2 (kg)",
            color_continuous_scale=px.colors.sequential.Greens,
            hover_data=["Tree Count"]
        )
        fig_species.update_layout(margin=dict(l=20, r=20, t=50, b=20))
        st.plotly_chart(fig_species, use_container_width=True)
    
    # Environmental equivalents
    st.markdown("<h4 style='color: #333; margin-top:1rem; margin-bottom: 0.5rem;'>Environmental Equivalents</h4>", unsafe_allow_html=True)
    
    # Calculate equivalents
    car_km = total_co2 / 0.12  # Approx. 120g CO2 per km driven
    flight_km = total_co2 / 0.09  # Approx. 90g CO2 per km flown
    phone_charges = total_co2 / 0.005  # Approx. 5g CO2 per phone charge
    
    equiv_cols = st.columns(3)
    
    with equiv_cols[0]:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-value">{int(car_km)} km</div>
            <div class="metric-label">Car Travel Offset</div>
        </div>
        """, unsafe_allow_html=True)
    
    with equiv_cols[1]:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-value">{int(flight_km)} km</div>
            <div class="metric-label">Flight Distance Offset</div>
        </div>
        """, unsafe_allow_html=True)
    
    with equiv_cols[2]:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-value">{int(phone_charges)}</div>
            <div class="metric-label">Phone Charges Offset</div>
        </div>
        """, unsafe_allow_html=True)

def load_monitoring_history(tree_ids):
    """
    Load monitoring history for the specified tree IDs
    """
    if not tree_ids or (isinstance(tree_ids, list) and len(tree_ids) == 0):
        return pd.DataFrame()
    
    conn = sqlite3.connect(SQLITE_DB)
    try:
        # Handle both single tree_id and list of tree_ids
        if isinstance(tree_ids, list):
            placeholders = ','.join(['?'] * len(tree_ids))
            query = f"SELECT * FROM monitoring_history WHERE tree_id IN ({placeholders})"
            df = pd.read_sql(query, conn, params=tree_ids)
        else:
            query = "SELECT * FROM monitoring_history WHERE tree_id = ?"
            df = pd.read_sql(query, conn, params=(tree_ids,))
    except Exception as e:
        st.error(f"Error loading monitoring history: {str(e)}")
        df = pd.DataFrame()
    finally:
        conn.close()
    
    return df

# Main function to be called from app.py
def unified_user_dashboard_content():
    """
    Main entry point for the unified user dashboard
    """
    unified_user_dashboard()
