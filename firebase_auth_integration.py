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

def show_firebase_setup_guide():
    """Display instructions for setting up Firebase when initialization fails"""
    st.error("Firebase configuration is missing or incorrect")
    st.markdown("""
    ## Firebase Setup Guide
    
    1. **Create a Firebase Project**:
       - Go to the [Firebase Console](https://console.firebase.google.com/)
       - Click "Add Project" and follow the steps
    
    2. **Generate Service Account Credentials**:
       - Go to Project Settings > Service Accounts
       - Click "Generate New Private Key"
       - Save the JSON file
    
    3. **Configure Streamlit Secrets**:
       - Create a `.streamlit/secrets.toml` file
       - Add your Firebase configuration:
    
    ```toml
    [firebase]
    type = "service_account"
    project_id = "your-project-id"
    private_key_id = "your-private-key-id"
    private_key = "-----BEGIN PRIVATE KEY-----\\n...\\n-----END PRIVATE KEY-----\\n"
    client_email = "your-service-account-email@project-id.iam.gserviceaccount.com"
    client_id = "your-client-id"
    auth_uri = "https://accounts.google.com/o/oauth2/auth"
    token_uri = "https://oauth2.googleapis.com/token"
    auth_provider_x509_cert_url = "https://www.googleapis.com/oauth2/v1/certs"
    client_x509_cert_url = "https://www.googleapis.com/robot/v1/metadata/x509/..."
    ```
    
    4. **Enable Authentication Methods**:
       - In Firebase Console, go to Authentication
       - Enable Email/Password sign-in
    """)

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
                st.session_state.user = {
                    'uid': user.uid,
                    'email': user.email,
                    'displayName': user.display_name,
                    'role': user.custom_claims.get('role', 'individual') if user.custom_claims else 'individual'
                }
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
                
                # Store additional user data in Firestore
                db = firestore.client()
                db.collection("users").document(user.uid).set({
                    'email': email,
                    'displayName': display_name,
                    'role': role,
                    'createdAt': firestore.SERVER_TIMESTAMP,
                    'approved': False if role == 'institution' else True
                })
                
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
    
    current_user = get_current_firebase_user()
    if not current_user or not check_firebase_user_role(current_user, "admin"):
        st.warning("You must be an admin to access this page.")
        return
    
    # Get unapproved users
    db = firestore.client()
    users_ref = db.collection("users").where("approved", "==", False)
    unapproved_users = users_ref.stream()
    
    if not any(unapproved_users):
        st.info("No users pending approval.")
        return
    
    for user in unapproved_users:
        user_data = user.to_dict()
        with st.expander(f"{user_data.get('displayName', 'Unknown')} ({user_data.get('email', 'No email')})"):
            st.write(f"Role: {user_data.get('role', 'individual')}")
            st.write(f"Registered: {user_data.get('createdAt', 'Unknown')}")
            
            col1, col2 = st.columns(2)
            with col1:
                if st.button(f"Approve {user_data.get('displayName')}", key=f"approve_{user.id}"):
                    user.reference.update({"approved": True})
                    st.success("User approved!")
                    st.rerun()
            with col2:
                if st.button(f"Reject {user_data.get('displayName')}", key=f"reject_{user.id}"):
                    try:
                        auth.delete_user(user.id)
                        user.reference.delete()
                        st.success("User rejected and deleted!")
                        st.rerun()
                    except FirebaseError as e:
                        st.error(f"Failed to reject user: {e}")

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
        user_record = auth.get_user(user['uid'])
        claims = user_record.custom_claims or {}
        return claims.get('role') == required_role
    except FirebaseError:
        return False
