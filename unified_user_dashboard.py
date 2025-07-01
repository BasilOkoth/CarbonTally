import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import datetime
import sqlite3
from pathlib import Path
import uuid

# Configuration
BASE_DIR = Path(__file__).parent if "__file__" in locals() else Path.cwd()
DATA_DIR = BASE_DIR / "data"
SQLITE_DB = DATA_DIR / "trees.db"

def unified_user_dashboard():
    """Main dashboard function displaying user's tree portfolio with metrics and analytics"""
    # Authentication check
    if "user" not in st.session_state:
        st.error("🔒 Please log in to access your dashboard")
        st.page_link("login.py", label="Login", icon="🔑")
        return

    # Get user data
    user_data = st.session_state.user
    user_uid = user_data.get("uid")
    user_role = user_data.get("role", "")
    user_name = user_data.get("displayName", "User")
    institution_name = user_data.get("institution", "")
    
    if not user_uid:
        st.error("⚠️ Invalid user session. Please log in again.")
        st.page_link("login.py", label="Login", icon="🔑")
        return
    
    # Initialize database
    try:
        conn = sqlite3.connect(SQLITE_DB)
    except Exception as e:
        st.error(f"🚨 Database connection failed: {str(e)}")
        st.error("Please try again or contact support if the problem persists.")
        return
    
    # Load user profile and tree data
    with st.spinner("Loading your forest profile..."):
        try:
            # Get tracking number
            tracking_number = user_data.get("treeTrackingNumber")
            
            if not tracking_number:
                st.error("No tracking number found for this user")
                return
            
            # Load tree data
            trees = load_tree_data_by_tracking_number(tracking_number)
            metrics = calculate_tree_metrics(trees)
            
        except Exception as e:
            st.error(f"Failed to load profile: {str(e)}")
            return
        finally:
            conn.close()
    
    # Dashboard header
    if user_role == "institution":
        header_text = f"🏫 {institution_name}'s Forest Dashboard"
    else:
        header_text = f"👤 {user_name}'s Forest Dashboard"
    
    st.markdown(f"""
    <div style="margin-bottom: 1.5rem;">
        <h1 style="color: #1D7749; margin-bottom: 0.25rem;">
            {header_text}
        </h1>
        <p style="color: #666; margin-top: 0;">Last updated: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}</p>
    </div>
    """, unsafe_allow_html=True)
    
    # Display tracking information
    st.markdown(f"""
    <div style="background-color: #f0f7f0; border-left: 4px solid #1D7749; padding: 1rem; margin-bottom: 1.5rem;">
        <h4 style="margin:0; color: #1D7749;">Your Tree Tracking Number</h4>
        <p style="font-size: 1.5rem; font-weight: bold; margin:0.5rem 0 0 0;">{tracking_number}</p>
        <p style="font-size: 0.9rem; margin:0.2rem 0 0 0; color: #666;">Use this number to track your environmental impact</p>
    </div>
    """, unsafe_allow_html=True)
    
    # Display key metrics at the top
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total Trees Planted", metrics['total_trees'])
    with col2:
        st.metric("Unique Species", len(metrics['species_count']))
    with col3:
        st.metric("CO₂ Absorbed (kg)", f"{metrics['total_co2_absorbed']:.2f}")
    with col4:
        health_score = calculate_health_score(metrics['health_status'])
        st.metric("Forest Health Score", f"{health_score}/100")
    
    # Main dashboard tabs - Removed planting and monitoring tabs
    tab1, tab2 = st.tabs(["🌿 Forest Overview", "📊 Tree Analytics"])
    
    with tab1:  # Forest Overview
        display_forest_overview(trees, metrics)
        
    with tab2:  # Tree Analytics
        display_tree_analytics(metrics)

def calculate_tree_metrics(trees):
    """Calculate various metrics about the user's trees"""
    if trees.empty:
        return {
            'total_trees': 0,
            'species_count': {},
            'total_co2_absorbed': 0,
            'growth_stages': {'seedling': 0, 'sapling': 0, 'mature': 0},
            'health_status': {'excellent': 0, 'good': 0, 'fair': 0, 'poor': 0}
        }
    
    metrics = {
        'total_trees': len(trees),
        'species_count': {},
        'total_co2_absorbed': trees['co2_kg'].sum() if 'co2_kg' in trees.columns else 0,
        'growth_stages': {'seedling': 0, 'sapling': 0, 'mature': 0},
        'health_status': {'excellent': 0, 'good': 0, 'fair': 0, 'poor': 0}
    }
    
    # Count species
    if 'local_name' in trees.columns:
        species_counts = trees['local_name'].value_counts().to_dict()
        metrics['species_count'] = species_counts
    
    # Track growth stages
    if 'growth_stage' in trees.columns:
        for stage in trees['growth_stage']:
            stage_lower = str(stage).lower()
            if stage_lower in metrics['growth_stages']:
                metrics['growth_stages'][stage_lower] += 1
    
    # Track health status
    if 'health_status' in trees.columns:
        for health in trees['health_status']:
            health_lower = str(health).lower()
            if health_lower in metrics['health_status']:
                metrics['health_status'][health_lower] += 1
    
    return metrics

def calculate_health_score(health_status):
    """Calculate an overall health score from 0-100"""
    total = sum(health_status.values())
    if total == 0:
        return 0
        
    weights = {
        'excellent': 1.0,
        'good': 0.8,
        'fair': 0.5,
        'poor': 0.2
    }
    
    weighted_sum = sum(weights.get(k.lower(), 0) * v for k, v in health_status.items())
    return min(100, int((weighted_sum / total) * 100))

def display_forest_overview(trees, metrics):
    """Display visual overview of the user's forest"""
    st.subheader("Your Forest at a Glance")
    
    if trees.empty:
        st.info("No trees found in your forest yet.")
        return
    
    # Tree species distribution
    st.write("### 🌲 Tree Species Distribution")
    if metrics['species_count']:
        species_df = pd.DataFrame.from_dict(
            metrics['species_count'], 
            orient='index', 
            columns=['Count']
        ).sort_values('Count', ascending=False)
        st.bar_chart(species_df)
    else:
        st.warning("No species data available")
    
    # Growth stages pie chart
    st.write("### 🌱 Growth Stage Breakdown")
    growth_df = pd.DataFrame.from_dict(
        metrics['growth_stages'], 
        orient='index', 
        columns=['Count']
    )
    fig = px.pie(
        growth_df, 
        values='Count', 
        names=growth_df.index,
        color_discrete_sequence=px.colors.sequential.Greens
    )
    st.plotly_chart(fig, use_container_width=True)
    
    # Tree map if coordinates available
    if 'latitude' in trees.columns and 'longitude' in trees.columns:
        st.write("### 🗺️ Tree Locations")
        map_trees = trees.dropna(subset=['latitude', 'longitude'])
        if not map_trees.empty:
            fig_map = px.scatter_mapbox(
                map_trees,
                lat='latitude',
                lon='longitude',
                hover_name='tree_id',
                hover_data=['local_name', 'date_planted', 'status'],
                color='status',
                color_discrete_map={'Alive': '#28a745', 'Dead': '#dc3545'},
                zoom=10,
                height=400
            )
            fig_map.update_layout(mapbox_style='carto-positron', margin={'r':0,'t':0,'l':0,'b':0})
            st.plotly_chart(fig_map, use_container_width=True)

def display_tree_analytics(metrics):
    """Display detailed tree analytics and metrics"""
    st.subheader("Detailed Tree Analytics")
    
    if metrics['total_trees'] == 0:
        st.info("No tree data available to display analytics.")
        return
    
    # CO2 absorption over time (simulated projection)
    st.write("### 🌍 Environmental Impact")
    years = 10
    co2_projection = [metrics['total_co2_absorbed'] * (1 + i*0.2) for i in range(years)]
    projection_df = pd.DataFrame({
        'Year': [datetime.datetime.now().year + i for i in range(years)],
        'Projected CO2 Absorption (kg)': co2_projection
    })
    st.line_chart(projection_df.set_index('Year'))
    
    # Health metrics
    st.write("### 💚 Forest Health Overview")
    health_df = pd.DataFrame.from_dict(
        metrics['health_status'], 
        orient='index', 
        columns=['Count']
    )
    fig = px.bar(
        health_df,
        color=health_df.index,
        color_discrete_map={
            'excellent': '#28a745',
            'good': '#5cb85c',
            'fair': '#ffc107',
            'poor': '#dc3545'
        }
    )
    st.plotly_chart(fig, use_container_width=True)
    
    # Maintenance alerts
    st.write("### ⚠️ Maintenance Status")
    poor_health = metrics['health_status'].get('poor', 0)
    if poor_health > 0:
        st.warning(f"{poor_health} trees in your forest need attention")
    else:
        st.success("All trees in your forest are healthy")

def load_tree_data_by_tracking_number(tracking_number):
    """Load tree data filtered by tracking number"""
    if not tracking_number:
        return pd.DataFrame()
    
    try:
        conn = sqlite3.connect(SQLITE_DB)
        query = "SELECT * FROM trees WHERE tree_tracking_number = ?"
        df = pd.read_sql(query, conn, params=(tracking_number,))
    except Exception as e:
        st.error(f"Error loading tree data: {str(e)}")
        df = pd.DataFrame()
    finally:
        conn.close()
    
    return df

def unified_user_dashboard_content():
    """Main entry point for the unified user dashboard"""
    unified_user_dashboard()
