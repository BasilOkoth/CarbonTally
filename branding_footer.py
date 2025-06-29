import streamlit as st

def add_branding_footer():
    """
    Add a branded footer to the Streamlit app with CarbonTally information
    and developer credits.
    """
    # Create space before the footer to push it to the bottom
    st.markdown("<br><br><br>", unsafe_allow_html=True)
    
    # Use container to better control positioning
    footer_container = st.container()
    
    with footer_container:
        st.markdown("""
        <style>
        .footer {
            position: fixed;
            left: 0;
            bottom: 0;
            width: 100%;
            background-color: white;
            padding-top: 1rem;
            padding-bottom: 1rem;
            border-top: 1px solid #e0e0e0;
            text-align: center;
            color: #666;
            font-size: 0.9rem;
            z-index: 999;
        }
        
        .footer-logo {
            font-size: 1.2rem;
            font-weight: bold;
            color: #2e8b57;
            margin-bottom: 0.5rem;
        }
        
        .footer-contact {
            margin: 0.5rem 0;
        }
        
        .footer-contact a {
            color: #2e8b57;
            text-decoration: none;
        }
        
        .footer-contact a:hover {
            text-decoration: underline;
        }
        
        .footer-copyright {
            margin-top: 0.5rem;
            font-size: 0.8rem;
        }
        </style>
        
        <div class="footer">
            <div class="footer-logo">🌱 CarbonTally</div>
            <div class="footer-contact">
                Developed by Basil Okoth<br>
                📧 <a href="mailto:okothbasil45@gmail.com">okothbasil45@gmail.com</a> | 
                🔗 <a href="https://linkedin.com/in/kaudobasil" target="_blank">linkedin.com/in/kaudobasil</a>
            </div>
            <div class="footer-copyright">
                © 2025 | Empowering Tree Monitoring and Climate Action
            </div>
        </div>
        """, unsafe_allow_html=True )

# Example usage:
# Place this at the end of your app
# add_branding_footer()
