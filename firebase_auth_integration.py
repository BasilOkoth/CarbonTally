import streamlit as st
import firebase_admin
from firebase_admin import credentials, auth, firestore
from firebase_admin.exceptions import FirebaseError
from typing import Optional, Dict, Any

# Initialize Firebase
def initialize_firebase():
    """Initialize Firebase Admin SDK"""
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
        st.error(f"Firebase initialization failed: {str(e)}")
        return None

# Alias for backward compatibility
def get_current_firebase_user() -> Optional[Dict[str, Any]]:
    """Alias for get_current_user (legacy support)"""
    return get_current_user()

def get_current_user() -> Optional[Dict[str, Any]]:
    """Get current authenticated user from session"""
    return st.session_state.get('user')

def check_auth() -> bool:
    """Check if user is authenticated"""
    return st.session_state.get('authenticated', False)

def check_firebase_user_role(user: Dict[str, Any], required_role: str) -> bool:
    """Check if user has required role"""
    if not user:
        return False
    return user.get('role') == required_role

def firebase_login_ui():
    """Render login UI"""
    st.title("🔐 Login")
    
    with st.form("login_form"):
        email = st.text_input("Email")
        password = st.text_input("Password", type="password")
        submit = st.form_submit_button("Login")
        
        if submit:
            try:
                user = auth.get_user_by_email(email)
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
    """Render signup UI"""
    st.title("📝 Sign Up")
    
    with st.form("signup_form"):
        email = st.text_input("Email")
        password = st.text_input("Password", type="password")
        display_name = st.text_input("Full Name")
        role = st.selectbox("Account Type", ["individual", "institution"])
        submit = st.form_submit_button("Create Account")
        
        if submit:
            try:
                user = auth.create_user(
                    email=email,
                    password=password,
                    display_name=display_name
                )
                auth.set_custom_user_claims(user.uid, {'role': role})
                
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
                st.error(f"Signup failed: {e}")

def firebase_password_recovery_ui():
    """Render password recovery UI"""
    st.title("🔒 Password Recovery")
    
    with st.form("recovery_form"):
        email = st.text_input("Enter your registered email")
        submit = st.form_submit_button("Send Reset Link")
        
        if submit:
            try:
                reset_link = auth.generate_password_reset_link(email)
                st.success(f"Password reset link sent to {email}")
                st.markdown(f"[Click here to reset password]({reset_link})")
            except FirebaseError as e:
                st.error(f"Password reset failed: {e}")

def firebase_admin_approval_ui():
    """Render admin approval UI"""
    user = get_current_user()
    if not check_firebase_user_role(user, "admin"):
        st.warning("Admin access required")
        return
    
    st.title("👥 User Approvals")
    db = firestore.client()
    unapproved_users = db.collection("users").where("approved", "==", False).stream()
    
    for user_doc in unapproved_users:
        user_data = user_doc.to_dict()
        with st.expander(user_data.get('email')):
            st.write(f"Name: {user_data.get('displayName')}")
            st.write(f"Role: {user_data.get('role')}")
            if st.button(f"Approve {user_data.get('email')}", key=f"approve_{user_doc.id}"):
                db.collection("users").document(user_doc.id).update({"approved": True})
                st.success(f"Approved {user_data.get('email')}")
                st.rerun()

def firebase_logout():
    """Handle user logout"""
    for key in ['user', 'authenticated']:
        if key in st.session_state:
            del st.session_state[key]
    st.success("Logged out successfully!")
    st.rerun()
