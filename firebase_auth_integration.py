import time
import streamlit as st
import firebase_admin
from firebase_admin import credentials, auth, firestore
from firebase_admin import exceptions
from firebase_admin.exceptions import FirebaseError
import uuid
import datetime
import re
import json
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pathlib import Path
import logging
import sqlite3
import pandas as pd

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Configuration
BASE_DIR = Path(__file__).parent if "__file__" in locals() else Path.cwd()
DATA_DIR = BASE_DIR / "data"
SQLITE_DB = DATA_DIR / "trees.db"

# Email Templates (aligned with app.py)
EMAIL_TEMPLATES = {
    "approval": {
        "subject": "CarbonTally - Your Account Has Been Approved",
        "body": """
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <div style="max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #e0e0e0; border-radius: 5px;">
                <div style="text-align: center; margin-bottom: 20px;">
                    <h2 style="color: #2e8b57;">CarbonTally</h2>
                </div>
                <p>Dear {fullName},</p>
                <p>Congratulations! Your CarbonTally account has been approved.</p>
                <p>You can now log in using your email and password at <a href="{app_url}" style="color: #2e8b57;">CarbonTally</a>.</p>
                <p><strong>Your Tree Tracking Number:</strong> {treeTrackingNumber}</p>
                <p>This unique tracking number will help you monitor and track all trees you plant through our platform.</p>
                <p>Thank you for joining our mission to combat climate change through tree planting initiatives!</p>
                <div style="margin-top: 30px; padding-top: 20px; border-top: 1px solid #e0e0e0; text-align: center; font-size: 0.8em; color: #666;">
                    <p>CarbonTally - Empowering Tree Monitoring and Climate Action</p>
                    <p>If you have any questions, please contact us at <a href="mailto:okothbasil45@gmail.com" style="color: #2e8b57;">okothbasil45@gmail.com</a></p>
                </div>
            </div>
        </body>
        </html>
        """
    },
    "rejection": {
        "subject": "CarbonTally - Account Application Status",
        "body": """
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <div style="max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #e0e0e0; border-radius: 5px;">
                <div style="text-align: center; margin-bottom: 20px;">
                    <h2 style="color: #2e8b57;">CarbonTally</h2>
                </div>
                <p>Dear {fullName},</p>
                <p>Thank you for your interest in CarbonTally.</p>
                <p>We regret to inform you that your account application has not been approved at this time.</p>
                <p>This could be due to various reasons, such as incomplete information or not meeting our current criteria.</p>
                <p>You are welcome to submit a new application with complete information or contact us for more details.</p>
                <div style="margin-top: 30px; padding-top: 20px; border-top: 1px solid #e0e0e0; text-align: center; font-size: 0.8em; color: #666;">
                    <p>CarbonTally - Empowering Tree Monitoring and Climate Action</p>
                    <p>If you have any questions, please contact us at <a href="mailto:okothbasil45@gmail.com" style="color: #2e8b57;">okothbasil45@gmail.com</a></p>
                </div>
            </div>
        </body>
        </html>
        """
    },
    "password_reset": {
        "subject": "CarbonTally - Password Reset Link",
        "body": """
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <div style="max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #e0e0e0; border-radius: 5px;">
                <div style="text-align: center; margin-bottom: 20px;">
                    <h2 style="color: #2e8b57;">CarbonTally</h2>
                </div>
                <p>Dear User,</p>
                <p>We received a request to reset your password for your CarbonTally account.</p>
                <p>To reset your password, please click on the link below:</p>
                <p style="text-align: center;">
                    <a href="{reset_link}" style="display: inline-block; padding: 10px 20px; background-color: #2e8b57; color: white; text-decoration: none; border-radius: 5px;">Reset Password</a>
                </p>
                <p>This link will expire in 24 hours.</p>
                <p>If you did not request a password reset, please ignore this email or contact us if you have concerns.</p>
                <div style="margin-top: 30px; padding-top: 20px; border-top: 1px solid #e0e0e0; text-align: center; font-size: 0.8em; color: #666;">
                    <p>CarbonTally - Empowering Tree Monitoring and Climate Action</p>
                    <p>If you have any questions, please contact us at <a href="mailto:okothbasil45@gmail.com" style="color: #2e8b57;">okothbasil45@gmail.com</a></p>
                </div>
            </div>
        </body>
        </html>
        """
    }
}

def initialize_firebase():
    """Initialize Firebase Admin SDK if not already initialized"""
    try:
        if not firebase_admin._apps:
            try:
                # Load Firebase config from Streamlit secrets
                firebase_config = {
                    "type": st.secrets["FIREBASE_CONFIG"]["type"],
                    "project_id": st.secrets["FIREBASE_CONFIG"]["project_id"],
                    "private_key_id": st.secrets["FIREBASE_CONFIG"]["private_key_id"],
                    "private_key": st.secrets["FIREBASE_CONFIG"]["private_key"].replace('\\n', '\n'),
                    "client_email": st.secrets["FIREBASE_CONFIG"]["client_email"],
                    "client_id": st.secrets["FIREBASE_CONFIG"]["client_id"],
                    "auth_uri": st.secrets["FIREBASE_CONFIG"]["auth_uri"],
                    "token_uri": st.secrets["FIREBASE_CONFIG"]["token_uri"],
                    "auth_provider_x509_cert_url": st.secrets["FIREBASE_CONFIG"]["auth_provider_x509_cert_url"],
                    "client_x509_cert_url": st.secrets["FIREBASE_CONFIG"]["client_x509_cert_url"]
                }
            except Exception as e:
                st.error(f"Error loading Firebase configuration: {str(e)}")
                show_firebase_setup_guide()
                return None

            # Initialize Firebase app
            cred = credentials.Certificate(firebase_config)
            firebase_admin.initialize_app(cred)

        # Initialize Firestore
        db = firestore.client()

        # Cache in session state
        if 'firebase_db' not in st.session_state:
            st.session_state.firebase_db = db

        return db

    except Exception as e:
        st.error(f"Firebase initialization failed: {str(e)}")
        show_firebase_setup_guide()
        return None

def add_institution_to_db(firebase_uid: str, full_name: str):
    """Adds a new participant record to the SQLite database."""
    conn = None
    try:
        conn = sqlite3.connect(SQLITE_DB)
        c = conn.cursor()
        join_date = datetime.date.today().isoformat()
        c.execute("INSERT INTO institutions (id, name, join_date) VALUES (?, ?, ?)",
                 (firebase_uid, full_name, join_date))
        conn.commit()
        logger.info(f"Participant '{full_name}' ({firebase_uid}) added to institutions table")
    except sqlite3.IntegrityError:
        logger.warning(f"Participant with ID {firebase_uid} already exists in institutions table")
    except Exception as e:
        logger.error(f"Error adding participant '{full_name}' to institutions database: {e}")
    finally:
        if conn:
            conn.close()

def send_email(recipient_email, subject, html_content):
    """Send an email using SMTP settings from secrets.toml"""
    try:
        # Get SMTP settings from secrets.toml
        smtp_server = st.secrets.get("SMTP_SERVER", "smtp.gmail.com")
        smtp_port = int(st.secrets.get("SMTP_PORT", 587))
        smtp_username = st.secrets.get("SMTP_USERNAME", "")
        smtp_password = st.secrets.get("SMTP_PASSWORD", "")
        sender_email = st.secrets.get("SMTP_SENDER", smtp_username)
        
        if not smtp_username or not smtp_password:
            logger.warning("SMTP credentials not found in secrets.toml. Email not sent.")
            return False
            
        # Create message
        message = MIMEMultipart("alternative")
        message["Subject"] = subject
        message["From"] = sender_email
        message["To"] = recipient_email
        
        # Attach HTML content
        html_part = MIMEText(html_content, "html")
        message.attach(html_part)
        
        # Send email
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(smtp_username, smtp_password)
            server.sendmail(sender_email, recipient_email, message.as_string())
            
        logger.info(f"Email sent successfully to {recipient_email}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to send email: {str(e)}")
        return False

def send_approval_email(user_data):
    """Send approval email to user"""
    try:
        recipient_email = user_data.get("email")
        full_name = user_data.get("fullName", "User")
        tracking_number = user_data.get("treeTrackingNumber", "")
        
        # Get app URL from secrets or use default
        app_url = st.secrets.get("APP_URL", "https://carbontally.app")
        
        # Format email template
        template = EMAIL_TEMPLATES["approval"]
        subject = template["subject"]
        body = template["body"].format(
            fullName=full_name,
            treeTrackingNumber=tracking_number,
            app_url=app_url
        )
        
        # Send email
        return send_email(recipient_email, subject, body)
        
    except Exception as e:
        logger.error(f"Failed to send approval email: {str(e)}")
        return False

def send_rejection_email(user_data):
    """Send rejection email to user"""
    try:
        recipient_email = user_data.get("email")
        full_name = user_data.get("fullName", "User")
        
        # Format email template
        template = EMAIL_TEMPLATES["rejection"]
        subject = template["subject"]
        body = template["body"].format(fullName=full_name)
        
        # Send email
        return send_email(recipient_email, subject, body)
        
    except Exception as e:
        logger.error(f"Failed to send rejection email: {str(e)}")
        return False

import requests

import requests

def send_password_reset_email(email):
    """Send a Firebase password reset email using the Web API"""
    api_key = st.secrets["FIREBASE_WEB_API_KEY"]
    url = f"https://identitytoolkit.googleapis.com/v1/accounts:sendOobCode?key={api_key}"
    
    data = {
        "requestType": "PASSWORD_RESET",
        "email": email
    }
    
    response = requests.post(url, json=data)
    if response.status_code == 200:
        return True
    else:
        raise Exception(response.json().get("error", {}).get("message", "Failed to send reset link."))
def generate_password_reset_link(email):
    """Generate a password reset link using Firebase Auth with proper settings"""
    try:
        # Get app URL from secrets or use default
        app_url = st.secrets.get("APP_URL", "https://your-app-url.com")
        
        # Generate action code settings
        action_code_settings = auth.ActionCodeSettings(
            url=f"{app_url}/reset-password",  # Your password reset handler URL
            handle_code_in_app=False,  # Set to True if handling in mobile app
            dynamic_link_domain=None,  # Set if using Firebase Dynamic Links
            android_package_name=None,  # Set for Android apps
            android_minimum_version=None,  # Set for Android apps
            android_install_app=None,  # Set for Android apps
            iOS_bundle_id=None  # Set for iOS apps
        )
        
        # Generate password reset link
        reset_link = auth.generate_password_reset_link(
            email, 
            action_code_settings=action_code_settings
        )
        
        logger.info(f"Generated password reset link for {email}")
        return reset_link
        
    except auth.UserNotFoundError:
        logger.warning(f"Password reset requested for non-existent user: {email}")
        return None
    except Exception as e:
        logger.error(f"Error generating password reset link: {str(e)}")
        return None
def firebase_login_ui():
    """Display Firebase login UI and handle authentication"""
    st.markdown("<h3 style='text-align: center; color: #1D7749;'>Login to Your Account</h3>", unsafe_allow_html=True)
    
    with st.form("firebase_login_form"):
        email = st.text_input("Email", key="login_email")
        password = st.text_input("Password", type="password", key="login_password")
        submitted = st.form_submit_button("Login", use_container_width=True)
        
        if submitted:
            if not email or not password:
                st.warning("Please enter both email and password")
            else:
                try:
                    user_record = auth.get_user_by_email(email)
                    
                    db = st.session_state.firebase_db
                    user_doc = db.collection('users').document(user_record.uid).get()
                    
                    if user_doc.exists:
                        user_data = user_doc.to_dict()
                        
                        # Check if user is approved
                        if user_data.get('status') != 'approved':
                            st.error("Your account is pending approval. Please wait for admin approval.")
                            return
                        
                        # Store ALL required user data in session state
                        st.session_state.user = {
                            'uid': user_record.uid,
                            'email': user_record.email,
                            'username': user_data.get('username', user_record.email.split('@')[0]),
                            'displayName': user_data.get('fullName', 'User'),
                            'role': user_data.get('role', 'individual'),
                            'user_type': user_data.get('role', 'individual'),
                            'institution': user_data.get('institution', ''),
                            'treeTrackingNumber': user_data.get('treeTrackingNumber', '')
                        }
                        
                        st.session_state.authenticated = True
                        
                        # Set appropriate page based on role
                        if user_data.get('role') == 'admin':
                            st.session_state.page = "Admin Dashboard"
                        else:
                            st.session_state.page = "User Dashboard"
                        
                        st.success(f"Welcome {user_data.get('fullName', 'User')}!")
                        st.rerun()
                    else:
                        st.error("User profile not found in Firestore. Please contact support.")
                except exceptions.FirebaseError as e:
                    st.error(f"Firebase error: {e}")
                except Exception as e:
                    st.error(f"An unexpected error occurred: {e}")

def firebase_signup_ui():
    """Display Firebase signup UI and handle new user registration"""
    st.markdown("<h3 style='text-align: center; color: #1D7749;'>Create New Account</h3>", unsafe_allow_html=True)

    with st.form("firebase_signup_form"):
        email = st.text_input("Email", key="signup_email")
        password = st.text_input("Password", type="password", key="signup_password")
        confirm_password = st.text_input("Confirm Password", type="password", key="signup_confirm_password")
        full_name = st.text_input("Full Name", key="signup_full_name")
        user_type = st.selectbox("Account Type", options=["individual", "institution"], key="signup_user_type")
        institution_name = ""
        if user_type == "institution":
            institution_name = st.text_input("Institution Name", key="signup_institution_name")

        submitted = st.form_submit_button("Register", use_container_width=True)

        if submitted:
            if not email or not password or not confirm_password or not full_name:
                st.warning("Please fill in all required fields.")
            elif password != confirm_password:
                st.error("Passwords do not match.")
            elif len(password) < 6:
                st.error("Password must be at least 6 characters long.")
            elif user_type == "institution" and not institution_name:
                st.warning("Please enter institution name for institution account type.")
            else:
                try:
                    # Create user in Firebase Authentication
                    user = auth.create_user(email=email, password=password)
                    
                    # Generate a unique tree tracking number
                    tree_tracking_number = f"CT-{uuid.uuid4().hex[:8].upper()}"

                    # Save user data to Firestore with pending status
                    db = st.session_state.firebase_db
                    user_ref = db.collection('users').document(user.uid)
                    user_data = {
                        'email': email,
                        'fullName': full_name,
                        'role': user_type,
                        'status': 'pending',
                        'createdAt': firestore.SERVER_TIMESTAMP,
                        'treeTrackingNumber': tree_tracking_number
                    }
                    if user_type == "institution":
                        user_data['institution'] = institution_name
                    
                    user_ref.set(user_data)

                    # Add user to the SQLite 'institutions' table for landing page count
                    if user_type in ['individual', 'institution']:
                        add_institution_to_db(user.uid, full_name)

                    st.success("Account created successfully! Your account is pending admin approval. You will receive an email once approved.")
                    logger.info(f"New user registered: {email} (UID: {user.uid})")
                    time.sleep(5)
                    st.session_state.page = "Login"
                    st.rerun()

                except exceptions.FirebaseError as e:
                    if "EMAIL_EXISTS" in str(e):
                        st.error("This email is already registered.")
                    else:
                        st.error(f"Firebase error: {e}")
                except Exception as e:
                    st.error(f"An unexpected error occurred: {e}")

def firebase_password_recovery_ui():
    """Password recovery with custom email like approval message"""
    st.markdown("<h3 style='text-align: center; color: #1D7749;'>Password Recovery</h3>", unsafe_allow_html=True)

    with st.form("firebase_password_recovery_form"):
        email = st.text_input("Enter your registered email", key="recovery_email")
        submitted = st.form_submit_button("Send Reset Link", use_container_width=True)

        if submitted:
            if not email:
                st.warning("Please enter your email address.")
            elif not re.match(r"[^@]+@[^@]+\.[^@]+", email):
                st.warning("Please enter a valid email address.")
            else:
                with st.spinner("Sending password reset email..."):
                    try:
                        # Step 1: Generate reset link
                        reset_link = generate_password_reset_link(email)

                        if reset_link:
                            # Step 2: Format email content using the HTML template
                            template = EMAIL_TEMPLATES["password_reset"]
                            subject = template["subject"]
                            html_body = template["body"].format(reset_link=reset_link)

                            # Step 3: Send the email
                            sent = send_email(email, subject, html_body)

                            if sent:
                                st.success("Password reset link sent! Please check your inbox (and spam folder).")
                            else:
                                st.error("Failed to send email. Please try again later.")
                        else:
                            st.error("No user found with that email or failed to generate reset link.")
                    except Exception as e:
                        st.error(f"An error occurred: {str(e)}")
def firebase_admin_approval_ui():
    """Display UI for admin to approve/reject pending user accounts"""
    st.markdown("<h3 style='text-align: center; color: #1D7749;'>Admin User Approval</h3>", unsafe_allow_html=True)

    db = initialize_firebase()
    if not db:
        st.error("Firebase not initialized. Cannot load pending users.")
        return

    pending_users_ref = db.collection('users').where('status', '==', 'pending')
    pending_users = pending_users_ref.stream()

    pending_users_list = []
    for user_doc in pending_users:
        user_data = user_doc.to_dict()
        user_data['uid'] = user_doc.id
        pending_users_list.append(user_data)

    if not pending_users_list:
        st.info("No pending user accounts for approval.")
        return

    st.write(f"Found {len(pending_users_list)} pending user(s).")

    for user_data in pending_users_list:
        with st.expander(f"Pending User: {user_data.get('fullName', 'N/A')} ({user_data.get('email', 'N/A')})"):
            st.write(f"**Email:** {user_data.get('email')}")
            st.write(f"**Full Name:** {user_data.get('fullName')}")
            st.write(f"**Account Type:** {user_data.get('role')}")
            if user_data.get('role') == 'institution':
                st.write(f"**Institution:** {user_data.get('institution')}")
            st.write(f"**Tree Tracking Number:** {user_data.get('treeTrackingNumber', 'N/A')}")
            st.write(f"**Registered At:** {user_data.get('createdAt').strftime('%Y-%m-%d %H:%M:%S') if user_data.get('createdAt') else 'N/A'}")

            col1, col2 = st.columns(2)
            with col1:
                if st.button(f"Approve {user_data['email']}", key=f"approve_{user_data['uid']}", use_container_width=True):
                    try:
                        db.collection('users').document(user_data['uid']).update({'status': 'approved'})
                        send_approval_email(user_data)
                        st.success(f"User {user_data['email']} approved and email sent.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error approving user: {e}")
            with col2:
                if st.button(f"Reject {user_data['email']}", key=f"reject_{user_data['uid']}", use_container_width=True):
                    try:
                        auth.delete_user(user_data['uid'])
                        db.collection('users').document(user_data['uid']).delete()
                        send_rejection_email(user_data)
                        st.warning(f"User {user_data['email']} rejected and account deleted.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error rejecting user: {e}")
from firebase_admin import auth, firestore

def get_all_users():
    """Fetch all users and their Firestore profile data."""
    db = firestore.client()
    user_docs = db.collection("users").stream()
    users = []

    for doc in user_docs:
        data = doc.to_dict()
        data["uid"] = doc.id
        users.append(data)

    return users

def approve_user(uid: str):
    """Mark user as approved in Firestore."""
    db = firestore.client()
    db.collection("users").document(uid).update({"status": "approved", "approved": True})

def reject_user(uid: str):
    """Mark user as rejected in Firestore."""
    db = firestore.client()
    db.collection("users").document(uid).update({"status": "rejected", "approved": False})

def delete_user(uid: str):
    """Delete user from Firebase Auth and Firestore."""
    db = firestore.client()
    try:
        auth.delete_user(uid)
    except Exception as e:
        print(f"Warning: Unable to delete from Firebase Auth: {e}")

    db.collection("users").document(uid).delete()

def firebase_logout():
    """Handle Firebase user logout"""
    if 'authenticated' in st.session_state:
        del st.session_state.authenticated
    if 'user' in st.session_state:
        del st.session_state.user
    if 'page' in st.session_state:
        del st.session_state.page
    st.info("Logged out successfully.")
    st.rerun()

def get_current_firebase_user():
    """Get the current authenticated Firebase user from session state"""
    return st.session_state.get('user', None)

def check_firebase_user_role(user, role):
    """Check if the current user has the specified role"""
    if user and 'role' in user:
        return user['role'] == role
    return False

def show_firebase_setup_guide():
    """Display instructions for setting up Firebase"""
    st.markdown("""
    ## Firebase Setup Guide
    
    1. Go to the [Firebase Console](https://console.firebase.google.com/)
    2. Create a new project or select an existing one
    3. Enable Authentication (Email/Password provider)
    4. Go to Project Settings > Service Accounts
    5. Generate a new private key (JSON) and download it
    6. Add the JSON content to your Streamlit secrets under 'FIREBASE_CONFIG'
    
    For detailed instructions, see the [Firebase documentation](https://firebase.google.com/docs/admin/setup)
    """)
    st.stop()

if __name__ == "__main__":
    st.set_page_config(page_title="Firebase Auth Test", layout="centered")
    st.title("Firebase Authentication Test")
    
    if 'firebase_db' not in st.session_state:
        initialize_firebase()
    
    menu = st.sidebar.selectbox("Menu", ["Login", "Sign Up", "Password Recovery", "Admin Approval"])
    
    if menu == "Login":
        firebase_login_ui()
    elif menu == "Sign Up":
        firebase_signup_ui()
    elif menu == "Password Recovery":
        firebase_password_recovery_ui()
    elif menu == "Admin Approval":
        firebase_admin_approval_ui()
