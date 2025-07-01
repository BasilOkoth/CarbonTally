import streamlit as st
import pandas as pd
import plotly.express as px
import datetime
import sqlite3
from pathlib import Path
import pyperclip
import json

# Configuration
BASE_DIR = Path(__file__).parent if "__file__" in locals() else Path.cwd()
DATA_DIR = BASE_DIR / "data"
SQLITE_DB = DATA_DIR / "trees.db"

def load_tree_data_by_tracking_number(tracking_number):
    """Load tree data filtered by tracking number"""
    if not tracking_number:
        return pd.DataFrame()
    
    try:
        conn = sqlite3.connect(SQLITE_DB)
        query = """
        SELECT * FROM trees 
        WHERE tree_tracking_number = ?
        """
        df = pd.read_sql(query, conn, params=(tracking_number,))
    except Exception as e:
        st.error(f"Error loading tree data: {str(e)}")
        df = pd.DataFrame()
    finally:
        conn.close()
    return df
from PIL import Image, ImageDraw, ImageFont
import qrcode
from pathlib import Path

QR_CODE_DIR = Path("qr_codes")

def generate_qr_code(tree_id, tree_tracking_number=None, tree_name=None, planter=None, date_planted=None):
    """Generate QR code with prefilled KoBo URL and labels"""
    try:
        # Use tracking number if provided, else fallback to tree_id
        tracking_param = tree_tracking_number or tree_id

        # Construct KoBo URL with optional prefill parameters
        base_url = "https://ee.kobotoolbox.org/x/dXdb36aV"
        params = f"?tree_id={tracking_param}"
        if tree_name:
            params += f"&name={tree_name.replace(' ', '+')}"
        if planter:
            params += f"&planter={planter.replace(' ', '+')}"
        if date_planted:
            params += f"&date_planted={date_planted}"
        form_url = base_url + params

        # Create green QR code
        qr = qrcode.QRCode(version=1, box_size=10, border=4)
        qr.add_data(form_url)
        qr.make(fit=True)

        # Generate image with labels
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

        # Save using Tree ID
        QR_CODE_DIR.mkdir(exist_ok=True, parents=True)
        file_path = QR_CODE_DIR / f"{tree_id}.png"
        img.save(file_path)

        return str(file_path)
    except Exception as e:
        st.error(f"QR generation failed: {e}")
        return None

def load_monitoring_history(tracking_number):
    """Load monitoring history for trees with given tracking number"""
    if not tracking_number:
        return pd.DataFrame()
    
    try:
        conn = sqlite3.connect(SQLITE_DB)
        query = """
        SELECT m.* 
        FROM monitoring_records m
        JOIN trees t ON m.tree_id = t.tree_id
        WHERE t.tree_tracking_number = ?
        ORDER BY m.monitor_date DESC
        """
        df = pd.read_sql(query, conn, params=(tracking_number,))
    except Exception as e:
        st.error(f"Error loading monitoring data: {str(e)}")
        df = pd.DataFrame()
    finally:
        conn.close()
    return df

def calculate_tree_metrics(trees):
    """Calculate various metrics about the user's trees"""
    if trees.empty:
        return {
            'total_trees': 0,
            'species_count': {},
            'total_co2_absorbed': 0.0,
            'growth_stages': {'seedling': 0, 'sapling': 0, 'mature': 0},
            'health_status': {'excellent': 0, 'good': 0, 'fair': 0, 'poor': 0},
            'status_counts': {'alive': 0, 'dead': 0, 'dormant': 0}
        }
    
    # Ensure co2_kg is numeric
    if 'co2_kg' in trees.columns:
        trees['co2_kg'] = pd.to_numeric(trees['co2_kg'], errors='coerce').fillna(0.0)
        total_co2_absorbed = trees['co2_kg'].sum()
    else:
        total_co2_absorbed = 0.0

    metrics = {
        'total_trees': len(trees),
        'species_count': trees['local_name'].value_counts().to_dict() if 'local_name' in trees.columns else {},
        'total_co2_absorbed': total_co2_absorbed,
        'growth_stages': {'seedling': 0, 'sapling': 0, 'mature': 0},
        'health_status': {'excellent': 0, 'good': 0, 'fair': 0, 'poor': 0},
        'status_counts': {'alive': 0, 'dead': 0, 'dormant': 0}
    }

    # Track growth stages
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

    # Track health status
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

def display_forest_overview(trees, metrics):
    """Display visual overview of the user's forest"""
    st.subheader("Your Forest at a Glance")
    
    if trees.empty:
        st.info("No trees found in your forest yet.")
        return
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.write("#### Tree Status")
        if metrics['status_counts']:
            status_df = pd.DataFrame.from_dict(
                metrics['status_counts'], 
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
                    'dead': '#dc3545'
                }
            )
            st.plotly_chart(fig, use_container_width=True)
    
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
                color_discrete_map={'Alive': '#28a745', 'Dead': '#dc3545', 'Dormant': '#ffc107'},
                zoom=10,
                height=500
            )
            fig_map.update_layout(
                mapbox_style='open-street-map',
                margin={'r':0,'t':0,'l':0,'b':0},
                hovermode='closest'
            )
            st.plotly_chart(fig_map, use_container_width=True)

def display_growth_analytics(trees, monitoring_history):
    """Display growth analytics and trends"""
    st.subheader("Growth Analytics")
    
    if trees.empty or monitoring_history.empty:
        st.info("No growth data available yet.")
        return
    
    monitoring_history['monitor_date'] = pd.to_datetime(monitoring_history['monitor_date'])
    trees['date_planted'] = pd.to_datetime(trees['date_planted'])
    
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
    
    if 'co2_kg' in trees.columns:
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
        fig = px.line(
            projection_df,
            x='year',
            y='co2_kg',
            color='tree_id',
            labels={'co2_kg': 'CO₂ Sequestered (kg)', 'year': 'Years from now'},
            color_discrete_sequence=px.colors.sequential.Greens
        )
        st.plotly_chart(fig, use_container_width=True)

import streamlit as st
import pandas as pd
import qrcode
from io import BytesIO
import base64

import streamlit as st
import pandas as pd

import streamlit as st
import pandas as pd

import streamlit as st
import pandas as pd

import streamlit as st
import pandas as pd

def display_tree_inventory(trees_df):
    """Display a clean, professional tree inventory with view and QR code options"""
    if 'selected_tree' not in st.session_state:
        st.session_state.selected_tree = None
    if 'qr_tree' not in st.session_state:
        st.session_state.qr_tree = None

    st.markdown("## 🌳 Tree Inventory")
    st.markdown("---")

    # Updated headers to include planter name
    headers = ["Tree ID", "Local Name", "Scientific Name", "Planter", "Date Planted",
               "Status", "Height (m)", "DBH (cm)", "CO₂ (kg)", ""]
    
    # Adjusted column widths
    col_widths = [1.2, 2.0, 2.0, 2.0, 1.5, 1.2, 1.0, 1.0, 1.0, 0.6]

    # Display headers
    header_cols = st.columns(col_widths)
    for col, header in zip(header_cols, headers):
        col.markdown(f"**{header}**")

    # Display each tree row
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

    st.markdown("---")

    # Show tree details when selected
    if st.session_state.get('selected_tree'):
        show_tree_details(st.session_state.selected_tree, trees_df)
        st.session_state.selected_tree = None

    # Generate and display QR code when selected
    if st.session_state.get('qr_tree'):
        tree_id = st.session_state.qr_tree
        tree_data = trees_df[trees_df['tree_id'] == tree_id].iloc[0]

        # Get tree details for QR code
        tree_name = tree_data.get('local_name', '')
        planter = tree_data.get('planters_name', '') or tree_data.get('planter_id', '')
        date_planted = tree_data.get('date_planted', '')
        tracking_number = tree_data.get('tree_tracking_number', tree_id)

        # Generate QR code that links to monitoring form
        qr_path = generate_qr_code(
            tree_id=tree_id,
            tree_tracking_number=tracking_number,
            tree_name=tree_name,
            planter=planter,
            date_planted=date_planted
        )

        # Display QR code section
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


def show_tree_details(tree_id, trees_df):
    """Show detailed information about a specific tree (without map)"""
    tree_data = trees_df[trees_df['tree_id'] == tree_id].iloc[0]
    
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
def unified_user_dashboard():
    """Main dashboard function displaying user's tree portfolio with metrics and analytics"""
    # Authentication check
    if "user" not in st.session_state:
        st.error("🔒 Please log in to access your dashboard")
        return
    
    # Get user data
    user_data = st.session_state.user
    user_uid = user_data.get("uid")
    user_role = user_data.get("role", "")
    user_name = user_data.get("displayName", "User")
    institution_name = user_data.get("institution", "")
    tracking_number = user_data.get("treeTrackingNumber", "")
    
    if not user_uid:
        st.error("⚠️ Invalid user session. Please log in again.")
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
            # Load tree data with monitoring history
            trees = load_tree_data_by_tracking_number(tracking_number)
            monitoring_history = load_monitoring_history(tracking_number)
            
            if not trees.empty and not monitoring_history.empty:
                # Merge monitoring data with tree data
                latest_monitoring = monitoring_history.sort_values('monitor_date').groupby('tree_id').last().reset_index()
                trees = pd.merge(trees, latest_monitoring, on='tree_id', how='left', suffixes=('', '_monitor'))
            
            metrics = calculate_tree_metrics(trees)
            
        except Exception as e:
            st.error(f"Failed to load profile: {str(e)}")
            return
        finally:
            conn.close()
    
    # Dashboard header with custom styling
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
        .copy-btn {{
            background-color: #e9ecef;
            border: none;
            border-radius: 4px;
            padding: 0.25rem 0.5rem;
            cursor: pointer;
            font-size: 0.8rem;
            margin-left: 0.5rem;
        }}
        .copy-btn:hover {{
            background-color: #dee2e6;
        }}
        .download-btn {{
            background-color: #1D7749;
            color: white;
            border: none;
            border-radius: 4px;
            padding: 0.5rem 1rem;
            cursor: pointer;
            font-size: 0.9rem;
            margin-top: 0.5rem;
        }}
        .download-btn:hover {{
            background-color: #166534;
        }}
    </style>
    
    <div class="dashboard-header">
        <h1>{'🏫 ' + institution_name if user_role == "institution" else '👤 ' + user_name}'s Forest Dashboard</h1>
        <p>Last updated: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}</p>
    </div>
    """, unsafe_allow_html=True)
    
    # Display tracking information with working copy button
    st.markdown(f"""
    <div style="background-color: #f8f9fa; border-left: 4px solid #1D7749; padding: 1rem; margin-bottom: 1.5rem; border-radius: 8px;">
        <h4 style="margin:0; color: #1D7749;">Your Tree Tracking Number</h4>
        <div style="display: flex; align-items: center; gap: 0.5rem;">
            <p style="font-size: 1.5rem; font-weight: bold; margin:0.5rem 0 0 0; color: #333;">{tracking_number}</p>
            <button class="copy-btn" onclick="navigator.clipboard.writeText('{tracking_number}')">Copy</button>
        </div>
        <p style="font-size: 0.9rem; margin:0.2rem 0 0 0; color: #666;">Use this number to track your environmental impact</p>
    </div>
    """, unsafe_allow_html=True)
    
    # Display key metrics at the top
    cols = st.columns(4)
    with cols[0]:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">Total Trees</div>
            <div class="metric-value">{metrics['total_trees']}</div>
            <div style="font-size: 0.8rem; color: #666;">{'🌳' * min(metrics['total_trees'], 5)}</div>
        </div>
        """, unsafe_allow_html=True)
    
    with cols[1]:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">Unique Species</div>
            <div class="metric-value">{len(metrics['species_count'])}</div>
            <div style="font-size: 0.8rem; color: #666;">Top: {list(metrics['species_count'].keys())[0] if metrics['species_count'] else 'N/A'}</div>
        </div>
        """, unsafe_allow_html=True)
    
    with cols[2]:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">CO₂ Sequestered</div>
            <div class="metric-value">{metrics['total_co2_absorbed']:.1f} kg</div>
            <div style="font-size: 0.8rem; color: #666;">≈ {int(metrics['total_co2_absorbed']/22):,} km car travel</div>
        </div>
        """, unsafe_allow_html=True)
    
    with cols[3]:
        health_score = calculate_health_score(metrics['health_status'])
        health_color = "#28a745" if health_score > 75 else "#ffc107" if health_score > 50 else "#dc3545"
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">Forest Health</div>
            <div class="metric-value" style="color: {health_color};">{health_score}/100</div>
            <div style="font-size: 0.8rem; color: #666;">{'🌿' * (health_score//20)}</div>
        </div>
        """, unsafe_allow_html=True)
    
    # Main dashboard tabs
    tab1, tab2, tab3 = st.tabs(["🌿 Forest Overview", "📈 Growth Analytics", "🌳 Tree Inventory"])
    
    with tab1:  # Forest Overview
        display_forest_overview(trees, metrics)
        
    with tab2:  # Growth Analytics
        display_growth_analytics(trees, monitoring_history)
        
    with tab3:  # Tree Inventory
        st.subheader("🌳 Your Tree Inventory")
        
        if trees.empty:
            st.info("No trees found in your account yet.")
        else:
            # Add download button at the top
            col1, col2 = st.columns([3, 1])
            with col2:
                # CSV Download
                csv = trees.to_csv(index=False).encode('utf-8')
                st.download_button(
                    label="📥 Download Tree Data (CSV)",
                    data=csv,
                    file_name=f"my_trees_{datetime.datetime.now().strftime('%Y%m%d')}.csv",
                    mime='text/csv',
                    key='download_trees_csv',
                    help="Download all your tree data as a CSV file"
                )
            
            # Display the tree table
            display_tree_inventory(trees)

def unified_user_dashboard_content():
    """Entry point for Streamlit"""
    unified_user_dashboard()

# JavaScript for copy functionality
st.markdown("""
<script>
function copyToClipboard(text) {
    navigator.clipboard.writeText(text).then(function() {
        console.log('Copied to clipboard: ' + text);
    }, function(err) {
        console.error('Could not copy text: ', err);
    });
}
document.addEventListener('DOMContentLoaded', function() {
    const copyButtons = document.querySelectorAll('.copy-btn');
    copyButtons.forEach(btn => {
        btn.addEventListener('click', function() {
            const text = this.getAttribute('data-text') || '{tracking_number}';
            copyToClipboard(text);
            // Visual feedback
            const originalText = this.textContent;
            this.textContent = 'Copied!';
            setTimeout(() => {
                this.textContent = originalText;
            }, 2000);
        });
    });
});
</script>
""", unsafe_allow_html=True)
