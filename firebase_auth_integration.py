import streamlit as st
import firebase_admin
from firebase_admin import credentials, auth, firestore
from firebase_admin.exceptions import FirebaseError
import json
from typing import Optional, Dict, Any

# Initialize Firebase app (singleton pattern)
def initialize_firebase():
    """Initialize Firebase Admin SDK with credentials from Streamlit secrets"""
    try:
        # Check if Firebase app is already initialized
        if not firebase_admin._apps:
            # Load Firebase config from Streamlit secrets
            firebase_config = {
                "type": st.secrets["firebase"]["type"],
                "project_id": st.secrets["firebase"]["project_id"],
                "private_key_id": st.secrets["firebase"]["private_key_id"],
                "private_key": st.secrets["firebase"]["private_key"].replace('\\n', '\n'),
                "client_email": st.secrets["firebase"]["client_email"],
                "client_id": st.secrets["firebase"]["client_id"],
                "auth_uri": st.secrets["firebase"]["auth_uri"],
                "token_uri": st.secrets["firebase"]["token_uri"],
                "auth_provider_x509_cert_url": st.secrets["firebase"]["auth_provider_x509_cert_url"],
                "client_x509_cert_url": st.secrets["firebase"]["client_x509_cert_url"]
            }
            
            # Create credentials and initialize app
            cred = credentials.Certificate(firebase_config)
            firebase_admin.initialize_app(cred)
            
        return firestore.client()
    except Exception as e:
        st.error(f"Failed to initialize Firebase: {str(e)}")
        return None

# Authentication UI Components
def firebase_login_ui():
    """Render the Firebase login UI"""
    st.title("Login to CarbonTally")
    
    with st.form("login_form"):
        email = st.text_input("Email")
        password = st.text_input("Password", type="password")
        submit = st.form_submit_button("Login")
        
        if submit:
            try:
                user = auth.get_user_by_email(email)
                st.session_state.user = user
                st.session_state.authenticated = True
                st.success("Login successful!")
                st.rerun()
            except FirebaseError as e:
                st.error(f"Login failed: {e}")

def firebase_signup_ui():
    """Render the Firebase signup UI"""
    st.title("Create an Account")
    
    with st.form("signup_form"):
        email = st.text_input("Email")
        password = st.text_input("Password", type="password")
        display_name = st.text_input("Full Name")
        role = st.selectbox("Role", ["individual", "institution"])
        submit = st.form_submit_button("Create Account")
        
        if submit:
            try:
                user = auth.create_user(
                    email=email,
                    password=password,
                    display_name=display_name
                )
                
                # Set custom claims for role-based access
                auth.set_custom_user_claims(user.uid, {'role': role})
                
                st.success("Account created successfully! Please login.")
                st.session_state.page = "Login"
                st.rerun()
            except FirebaseError as e:
                st.error(f"Account creation failed: {e}")

def firebase_password_recovery_ui():
    """Render the password recovery UI"""
    st.title("Password Recovery")
    
    with st.form("recovery_form"):
        email = st.text_input("Enter your email address")
        submit = st.form_submit_button("Send Reset Link")
        
        if submit:
            try:
                auth.generate_password_reset_link(email)
                st.success("Password reset link sent to your email!")
            except FirebaseError as e:
                st.error(f"Password reset failed: {e}")

def firebase_admin_approval_ui():
    """Render the admin approval UI"""
    st.title("User Approvals")
    
    if not check_firebase_user_role(get_current_firebase_user(), "admin"):
        st.warning("You must be an admin to access this page.")
        return
    
    # Get unapproved users
    db = firestore.client()
    users_ref = db.collection("users").where("approved", "==", False)
    unapproved_users = users_ref.stream()
    
    if not unapproved_users:
        st.info("No users pending approval.")
        return
    
    for user in unapproved_users:
        with st.expander(f"User: {user.id}"):
            st.json(user.to_dict())
            if st.button(f"Approve {user.id}"):
                user_ref = db.collection("users").document(user.id)
                user_ref.update({"approved": True})
                st.success(f"User {user.id} approved!")
                st.rerun()

def firebase_logout():
    """Handle user logout"""
    st.session_state.authenticated = False
    st.session_state.user = None
    st.session_state.page = "Landing"
    st.success("Logged out successfully!")
    st.rerun()

# User Management Functions
def get_current_firebase_user() -> Optional[Dict[str, Any]]:
    """Get the currently authenticated Firebase user"""
    if 'user' in st.session_state and st.session_state.user:
        return st.session_state.user
    return None

def check_firebase_user_role(user: Dict[str, Any], required_role: str) -> bool:
    """Check if user has the required role"""
    if not user:
        return False
    
    # Get custom claims (including role)
    try:
        user_record = auth.get_user(user.uid)
        claims = user_record.custom_claims or {}
        return claims.get('role') == required_role
    except FirebaseError:
        return False
