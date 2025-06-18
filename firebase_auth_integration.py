import streamlit as st
import firebase_admin
from firebase_admin import credentials, auth, firestore
from firebase_admin.exceptions import FirebaseError
from typing import Optional, Dict, Any

# Initialize Firebase (singleton pattern)
def initialize_firebase():
    """Initialize Firebase Admin SDK with credentials"""
    try:
        if not firebase_admin._apps:
            if not all(key in st.secrets["firebase"] for key in ["type", "project_id", "private_key"]):
                st.error("Missing Firebase credentials in secrets")
                return None

            cred = credentials.Certificate({
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
            })
            firebase_admin.initialize_app(cred)
        return firestore.client()
    except Exception as e:
        st.error(f"Firebase init error: {str(e)}")
        return None

# Authentication UI Components
def firebase_login_ui():
    """Render login form and handle authentication"""
    st.title("🔐 Login")
    
    with st.form("login_form"):
        email = st.text_input("Email", placeholder="your@email.com")
        password = st.text_input("Password", type="password")
        submit = st.form_submit_button("Sign In")

        if submit:
            handle_login(email, password)

def handle_login(email: str, password: str):
    """Authenticate user with Firebase"""
    try:
        # Verify credentials (you might need Firebase Client SDK here)
        # This is a placeholder - actual implementation depends on your auth method
        user = auth.get_user_by_email(email)
        
        # Store user in session
        st.session_state.user = {
            'uid': user.uid,
            'email': user.email,
            'displayName': user.display_name or email.split('@')[0],
            'role': user.custom_claims.get('role', 'individual')
        }
        st.session_state.authenticated = True
        st.success("Login successful!")
        st.rerun()
    except FirebaseError as e:
        st.error(f"Login failed: {e}")

def firebase_signup_ui():
    """Render user registration form"""
    st.title("📝 Create Account")
    
    with st.form("signup_form"):
        email = st.text_input("Email", placeholder="your@email.com")
        password = st.text_input("Password", type="password")
        display_name = st.text_input("Full Name")
        role = st.selectbox("Account Type", ["individual", "institution"])
        submit = st.form_submit_button("Register")

        if submit:
            handle_signup(email, password, display_name, role)

def handle_signup(email: str, password: str, display_name: str, role: str):
    """Register new user in Firebase"""
    try:
        user = auth.create_user(
            email=email,
            password=password,
            display_name=display_name
        )
        
        # Set custom claims for role-based access
        auth.set_custom_user_claims(user.uid, {'role': role})
        
        # Store additional user data in Firestore
        db = firestore.client()
        db.collection("users").document(user.uid).set({
            'email': email,
            'displayName': display_name,
            'role': role,
            'createdAt': firestore.SERVER_TIMESTAMP
        })
        
        st.success("Account created! Please login.")
        st.session_state.page = "login"
        st.rerun()
    except FirebaseError as e:
        st.error(f"Registration failed: {e}")

def firebase_logout():
    """Terminate user session"""
    keys = ['user', 'authenticated']
    for key in keys:
        if key in st.session_state:
            del st.session_state[key]
    st.rerun()

# User Management
def get_current_user() -> Optional[Dict[str, Any]]:
    """Retrieve current user from session"""
    return st.session_state.get('user')

def check_auth() -> bool:
    """Verify authentication status"""
    return st.session_state.get('authenticated', False)

def check_user_role(required_role: str) -> bool:
    """Check if user has required role"""
    user = get_current_user()
    return user and user.get('role') == required_role

def require_auth():
    """Redirect to login if not authenticated"""
    if not check_auth():
        st.warning("Please login to access this page")
        st.session_state.page = "login"
        st.rerun()
