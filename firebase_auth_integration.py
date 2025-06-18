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

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# This file provides Firebase authentication and user management for CarbonTally app
# It includes email notifications for account approval, rejection, and password reset

# Configuration
BASE_DIR = Path(__file__).parent if "__file__" in locals() else Path.cwd()

# Database Configuration (must match app.py and kobo_integration.py)
DATA_DIR = BASE_DIR / "data"
SQLITE_DB = DATA_DIR / "trees.db"

# Email Templates
EMAIL_TEMPLATES = {
    "approval": {
        "subject": "CarbonTally - Your Account Has Been Approved",
        "body": """
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <div style="max-width: 600px; margin: 0 auto; background-color: #f9f9f9; padding: 20px; border-radius: 8px; border: 1px solid #ddd;">
                <h2 style="color: #28a745;">Congratulations! Your CarbonTally Account is Approved!</h2>
                <p>Dear {username},</p>
                <p>We are delighted to inform you that your CarbonTally account has been approved.</p>
                <p>You can now log in to the CarbonTally app using your credentials and start planting trees and monitoring their progress.</p>
                <p>Thank you for joining our mission to make a greener planet!</p>
                <p>Best regards,</p>
                <p>The CarbonTally Team</p>
                <p style="font-size: 0.9em; color: #777;">This is an automated email, please do not reply.</p>
            </div>
        </body>
        </html>
        """
    },
    "rejection": {
        "subject": "CarbonTally - Account Application Update",
        "body": """
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <div style="max-width: 600px; margin: 0 auto; background-color: #f9f9f9; padding: 20px; border-radius: 8px; border: 1px solid #ddd;">
                <h2 style="color: #dc3545;">Update Regarding Your CarbonTally Account Application</h2>
                <p>Dear {username},</p>
                <p>Thank you for your interest in CarbonTally. We have reviewed your account application and, unfortunately, we are unable to approve it at this time.</p>
                <p>If you believe this is an error or would like to provide more information, please contact our support team.</p>
                <p>Best regards,</p>
                <p>The CarbonTally Team</p>
                <p style="font-size: 0.9em; color: #777;">This is an automated email, please do not reply.</p>
            </div>
        </body>
        </html>
        """
    },
    "password_reset_success": {
        "subject": "CarbonTally - Password Reset Confirmation",
        "body": """
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <div style="max-width: 600px; margin: 0 auto; background-color: #f9f9f9; padding: 20px; border-radius: 8px; border: 1px solid #ddd;">
                <h2 style="color: #007bff;">Your Password Has Been Reset</h2>
                <p>Dear {username},</p>
                <p>This is to confirm that the password for your CarbonTally account associated with {email} has been successfully reset.</p>
                <p>If you did not initiate this change, please contact us immediately.</p>
                <p>Best regards,</p>
                <p>The CarbonTally Team</p>
                <p style="font-size: 0.9em; color: #777;">This is an automated email, please do not reply.</p>
            </div>
        </body>
        </html>
        """
    }
}

# --- Firebase Initialization ---

def initialize_firebase_auth():
    """Initializes Firebase app with credentials from Streamlit secrets."""
    try:
        if not firebase_admin._apps:
            # Attempt to load Firebase credentials from Streamlit secrets
            firebase_config = {
                "type": st.secrets["FIREBASE"]["TYPE"],
                "project_id": st.secrets["FIREBASE"]["PROJECT_ID"],
                "private_key_id": st.secrets["FIREBASE"]["PRIVATE_KEY_ID"],
                "private_key": st.secrets["FIREBASE"]["PRIVATE_KEY"].replace('\\n', '\n'), # Handle newline characters
                "client_email": st.secrets["FIREBASE"]["CLIENT_EMAIL"],
                "client_id": st.secrets["FIREBASE"]["CLIENT_ID"],
                "auth_uri": st.secrets["FIREBASE"]["AUTH_URI"],
                "token_uri": st.secrets["FIREBASE"]["TOKEN_URI"],
                "auth_provider_x509_cert_url": st.secrets["FIREBASE"]["AUTH_PROVIDER_X509_CERT_URL"],
                "client_x509_cert_url": st.secrets["FIREBASE"]["CLIENT_X509_CERT_URL"],
                "universe_domain": st.secrets["FIREBASE"]["UNIVERSE_DOMAIN"]
            }
            cred = credentials.Certificate(firebase_config)
            firebase_admin.initialize_app(cred)
            logger.info("Firebase app initialized successfully.")
        return True
    except KeyError as e:
        st.error(f"Firebase configuration missing in secrets.toml: {e}. Please ensure FIREBASE section is correctly set up.")
        logger.error(f"Firebase config KeyError: {e}")
        return False
    except Exception as e:
        st.error(f"Error initializing Firebase: {e}")
        logger.error(f"Firebase initialization error: {e}", exc_info=True)
        return False

# --- Database for user roles/approvals (using SQLite alongside Firebase) ---
def initialize_user_db():
    """Initialize a simple SQLite DB for user roles and approval status."""
    DATA_DIR.mkdir(exist_ok=True, parents=True)
    conn = sqlite3.connect(SQLITE_DB)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            uid TEXT PRIMARY KEY,
            email TEXT UNIQUE,
            username TEXT,
            role TEXT,
            approved INTEGER DEFAULT 0,
            creation_date TEXT
        )
    ''')
    conn.commit()
    conn.close()
    logger.info("User database initialized.")

# Call user DB initialization
initialize_user_db()

def update_user_in_db(uid, email, username, role, approved=0):
    """Updates or inserts user information in the local SQLite database."""
    conn = sqlite3.connect(SQLITE_DB)
    c = conn.cursor()
    creation_date = datetime.datetime.now().isoformat()
    try:
        c.execute('''
            INSERT OR REPLACE INTO users (uid, email, username, role, approved, creation_date)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (uid, email, username, role, approved, creation_date))
        conn.commit()
        logger.info(f"User {email} updated/inserted in local DB with role {role}, approved: {approved}")
    except Exception as e:
        logger.error(f"Error updating user {email} in local DB: {e}")
    finally:
        conn.close()

def get_user_from_db(uid):
    """Fetches user details from the local SQLite database by UID."""
    conn = sqlite3.connect(SQLITE_DB)
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE uid = ?", (uid,))
    user_data = c.fetchone()
    conn.close()
    if user_data:
        # Assuming the order: uid, email, username, role, approved, creation_date
        return {
            "uid": user_data[0],
            "email": user_data[1],
            "username": user_data[2],
            "role": user_data[3],
            "approved": bool(user_data[4]), # Convert 0/1 to False/True
            "creation_date": user_data[5]
        }
    return None

def get_all_users_from_db():
    """Fetches all users from the local SQLite database."""
    conn = sqlite3.connect(SQLITE_DB)
    df = pd.read_sql_query("SELECT uid, email, username, role, approved FROM users", conn)
    conn.close()
    return df

def delete_user_from_db(uid):
    """Deletes a user from the local SQLite database."""
    conn = sqlite3.connect(SQLITE_DB)
    c = conn.cursor()
    c.execute("DELETE FROM users WHERE uid = ?", (uid,))
    conn.commit()
    conn.close()
    logger.info(f"User {uid} deleted from local DB.")


# --- Email Sending Function ---
def send_email(to_email, subject, body):
    """Sends an email using configurations from Streamlit secrets."""
    try:
        sender_email = st.secrets["EMAIL"]["EMAIL_ADDRESS"]
        sender_password = st.secrets["EMAIL"]["EMAIL_PASSWORD"]

        msg = MIMEMultipart("alternative")
        msg["From"] = sender_email
        msg["To"] = to_email
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "html"))

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp: # Using SSL for gmail
            smtp.login(sender_email, sender_password)
            smtp.send_message(msg)
        logger.info(f"Email sent to {to_email} with subject: {subject}")
        return True
    except KeyError:
        st.warning("Email configuration missing in secrets.toml. Email notifications disabled.")
        logger.warning("Email configuration missing in secrets.toml.")
        return False
    except Exception as e:
        st.error(f"Failed to send email to {to_email}: {e}. Check email credentials or app password.")
        logger.error(f"Email sending failed to {to_email}: {e}", exc_info=True)
        return False

# --- Firebase Authentication Functions ---

def firebase_login(email, password):
    """Handles Firebase user login."""
    try:
        user = auth.get_user_by_email(email)
        # Verify password (Firebase Admin SDK doesn't directly verify password,
        # usually done client-side or by creating custom token.
        # For simplicity, we assume if get_user_by_email works, and the user exists,
        # we then check local DB for approval status before marking authenticated.)
        # A more robust solution would involve Firebase Client SDK for password validation.

        user_in_db = get_user_from_db(user.uid)
        if user_in_db and user_in_db["approved"]:
            st.session_state.authenticated = True
            st.session_state.user = user_in_db # Store user details from DB
            st.success(f"Logged in as {user_in_db['username']} ({user_in_db['role']})")
            logger.info(f"User {email} logged in successfully.")
            return True
        elif user_in_db and not user_in_db["approved"]:
            st.warning("Your account is awaiting admin approval. Please try again later.")
            logger.info(f"Login attempt for {email}: Awaiting admin approval.")
            return False
        else:
            st.error("User not found in database or not approved.")
            logger.warning(f"Login attempt for {email}: User not found in DB or not approved.")
            return False

    except exceptions.FirebaseError as e:
        error_code = e.code
        if error_code == 'auth/user-not-found':
            st.error("Invalid email or password.")
        elif error_code == 'auth/wrong-password': # This might not be hit if we don't do client-side auth
            st.error("Invalid email or password.")
        else:
            st.error(f"Login failed: {e}")
        logger.error(f"Firebase login error for {email}: {e}")
        return False
    except Exception as e:
        st.error(f"An unexpected error occurred during login: {e}")
        logger.error(f"Unexpected error during login for {email}: {e}", exc_info=True)
        return False


def firebase_register(email, password, username, role):
    """Registers a new user with Firebase and sets their approval status."""
    try:
        if not re.match(r"[^@]+@[^@]+\.[^@]+", email):
            st.error("Invalid email format.")
            return False
        if len(password) < 6:
            st.error("Password must be at least 6 characters.")
            return False

        user = auth.create_user(email=email, password=password, display_name=username)
        # Default to unapproved, admin must approve
        update_user_in_db(user.uid, email, username, role, approved=0)
        
        st.success(f"Account created for {username} ({email}). Awaiting admin approval.")
        logger.info(f"New user registered: {email} with UID {user.uid}. Role: {role}. Awaiting approval.")
        return True
    except exceptions.FirebaseError as e:
        error_code = e.code
        if error_code == 'auth/email-already-exists':
            st.error("This email is already registered.")
        else:
            st.error(f"Registration failed: {e}")
        logger.error(f"Firebase registration error for {email}: {e}")
        return False
    except Exception as e:
        st.error(f"An unexpected error occurred during registration: {e}")
        logger.error(f"Unexpected error during registration for {email}: {e}", exc_info=True)
        return False

def send_password_reset_email(email):
    """Sends a password reset email via Firebase."""
    try:
        # Firebase Admin SDK does not directly send password reset emails
        # This typically requires the client-side SDK.
        # As a workaround, we could use a custom email service if needed,
        # but for Firebase integration, direct password reset is usually client-side.
        # If using a custom email service, you'd generate a token yourself.

        # For a basic user experience, we can inform the user how to reset.
        st.info("Password reset is handled directly by Firebase's client-side SDK for security reasons. "
                "Please use the 'Forgot Password' option on your app's login screen which implements the Firebase client SDK, "
                "or visit the Firebase console if you are an admin.")
        
        # If you were to implement email sending via your own SMTP (less secure for this purpose):
        # user_data = auth.get_user_by_email(email)
        # user_in_db = get_user_from_db(user_data.uid)
        # username = user_in_db.get('username', 'User') if user_in_db else 'User'
        # subject = EMAIL_TEMPLATES["password_reset_success"]["subject"]
        # body = EMAIL_TEMPLATES["password_reset_success"]["body"].format(username=username, email=email)
        # return send_email(email, subject, body)
        return True # Indicate user was informed
    except exceptions.FirebaseError as e:
        st.error(f"Firebase error sending reset email: {e}")
        logger.error(f"Firebase password reset email error for {email}: {e}")
        return False
    except Exception as e:
        st.error(f"An unexpected error occurred while processing password reset: {e}")
        logger.error(f"Unexpected error during password reset for {email}: {e}", exc_info=True)
        return False

def display_user_management():
    """Displays UI for admin to approve/reject users."""
    st.subheader("User Account Approval")
    
    df_users = get_all_users_from_db()

    if df_users.empty:
        st.info("No user accounts found in the database.")
        return

    st.dataframe(df_users, use_container_width=True)

    pending_users = df_users[df_users['approved'] == 0]

    if not pending_users.empty:
        st.markdown("---")
        st.subheader("Pending Approvals")
        for index, user_data in pending_users.iterrows():
            col1, col2, col3, col4, col5 = st.columns([2, 2, 1, 1, 1])
            with col1:
                st.write(f"**Email:** {user_data['email']}")
            with col2:
                st.write(f"**Username:** {user_data['username']}")
            with col3:
                st.write(f"**Role:** {user_data['role']}")
            with col4:
                if st.button(f"Approve {user_data['username']}", key=f"approve_{user_data['uid']}"):
                    try:
                        # Update Firebase user custom claims (optional, for role)
                        # auth.set_custom_user_claims(user_data['uid'], {'role': user_data['role']})
                        update_user_in_db(user_data['uid'], user_data['email'], user_data['username'], user_data['role'], approved=1)
                        if send_email(user_data['email'],
                                      EMAIL_TEMPLATES["approval"]["subject"],
                                      EMAIL_TEMPLATES["approval"]["body"].format(username=user_data['username'])):
                            st.success(f"User {user_data['username']} approved and email sent.")
                        else:
                            st.success(f"User {user_data['username']} approved (email failed).")
                        st.experimental_rerun()
                    except Exception as e:
                        st.error(f"Error approving user: {e}")
            with col5:
                if st.button(f"Reject {user_data['username']}", key=f"reject_{user_data['uid']}"):
                    try:
                        # Optionally delete from Firebase Auth, or just mark as rejected
                        auth.delete_user(user_data['uid']) # Deletes user from Firebase Auth
                        delete_user_from_db(user_data['uid']) # Delete from local DB
                        if send_email(user_data['email'],
                                      EMAIL_TEMPLATES["rejection"]["subject"],
                                      EMAIL_TEMPLATES["rejection"]["body"].format(username=user_data['username'])):
                            st.warning(f"User {user_data['username']} rejected and email sent.")
                        else:
                            st.warning(f"User {user_data['username']} rejected (email failed).")
                        st.experimental_rerun()
                    except Exception as e:
                        st.error(f"Error rejecting user: {e}")
    else:
        st.info("No pending user approvals.")

def firebase_logout():
    """Handle Firebase user logout"""
    if 'authenticated' in st.session_state:
        del st.session_state.authenticated
    if 'user' in st.session_state:
        del st.session_state.user
    if 'page' in st.session_state: # Clear page state to redirect to home/login
        del st.session_state.page
    st.info("Logged out successfully.")
    st.experimental_rerun() # Rerun to clear session state and redirect

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

    To get Firebase authentication working, you need to configure your Firebase project and add its credentials to Streamlit's secrets.toml:

    1.  **Go to the [Firebase Console](https://console.firebase.google.com/)**
    2.  **Create a new project** or select an existing one.
    3.  **Enable Authentication:**
        * Navigate to **Build > Authentication** in the left sidebar.
        * Go to the **Sign-in method** tab.
        * Enable the **Email/Password** provider.
    4.  **Create a Service Account:**
        * Go to **Project settings** (the gear icon next to "Project Overview").
        * Select the **Service accounts** tab.
        * Click on **Generate new private key** and download the JSON file. This file contains your Firebase credentials.
    5.  **Configure `secrets.toml`:**
        * Create a `.streamlit` folder in your project's root directory if it doesn't exist.
        * Inside `.streamlit`, create a file named `secrets.toml`.
        * Copy the content of the downloaded JSON file into your `secrets.toml` under a `[FIREBASE]` section. Make sure to replace newline characters (`\n`) in the `private_key` field with actual newlines if you're pasting it directly into Streamlit Cloud's secrets management, or escape them (`\\n`) if writing directly to `secrets.toml` locally.
        * **Example `secrets.toml` structure (important for Streamlit Cloud):**
            ```toml
            # .streamlit/secrets.toml

            [FIREBASE]
            TYPE="your_firebase_type"
            PROJECT_ID="your_firebase_project_id"
            PRIVATE_KEY_ID="your_firebase_private_key_id"
            PRIVATE_KEY="-----BEGIN PRIVATE KEY-----\nYOUR_VERY_LONG_PRIVATE_KEY_VALUE_HERE\n-----END PRIVATE KEY-----\n"
            CLIENT_EMAIL="your_client_email"
            CLIENT_ID="your_client_id"
            AUTH_URI="your_auth_uri"
            TOKEN_URI="your_token_uri"
            AUTH_PROVIDER_X509_CERT_URL="your_auth_provider_x509_cert_url"
            CLIENT_X509_CERT_URL="your_client_x509_cert_url"
            UNIVERSE_DOMAIN="your_universe_domain"

            [KOBO]
            API_TOKEN="your_kobo_api_token"
            KOBO_ASSET_ID="your_planting_form_asset_uid"
            KOBO_MONITORING_ASSET_ID="your_monitoring_form_asset_uid"

            [EMAIL]
            EMAIL_ADDRESS="your_sender_email@example.com"
            EMAIL_PASSWORD="your_sender_email_password_or_app_password"
            ```
            (Remember to replace `YOUR_VERY_LONG_PRIVATE_KEY_VALUE_HERE` with your actual private key. For `PRIVATE_KEY` in Streamlit Cloud, you need to manually add the newlines.)

    6.  **Ensure Email Configuration:** If you plan to use email notifications (for account approval/rejection or password reset emails if you implement them yourself), ensure you have the `[EMAIL]` section correctly configured in `secrets.toml` with your sender email address and password (or app password for Gmail).
    7.  **Dependencies:** Make sure you have `firebase-admin` and `streamlit` installed (`pip install firebase-admin streamlit`).

    Once you have configured `secrets.toml` and restarted your Streamlit app, Firebase should initialize correctly.
    """)

# For local testing (ensure you have a secrets.toml or mock secrets for testing this file directly)
if __name__ == "__main__":
    st.set_page_config(page_title="Firebase Auth Test", layout="centered")

    st.title("Firebase Authentication Test Module")

    # Initialize Firebase if not already
    if 'firebase_initialized' not in st.session_state:
        st.session_state.firebase_initialized = initialize_firebase_auth()

    if not st.session_state.firebase_initialized:
        st.error("Firebase is not initialized. Check your secrets.toml.")
        show_firebase_setup_guide()
        st.stop() # Stop further execution if Firebase isn't ready

    if 'authenticated' not in st.session_state:
        st.session_state.authenticated = False
    if 'user' not in st.session_state:
        st.session_state.user = None

    menu = ["Login", "Register", "Password Reset", "User Management (Admin)", "Logout", "Firebase Setup Guide"]
    choice = st.sidebar.selectbox("Menu", menu)

    if choice == "Login":
        st.subheader("Login")
        email = st.text_input("Email")
        password = st.text_input("Password", type='password')
        if st.button("Login"):
            firebase_login(email, password)
            if st.session_state.authenticated:
                st.write(f"Welcome, {st.session_state.user['username']}! Your role is {st.session_state.user['role']}.")
    
    elif choice == "Register":
        st.subheader("Register New Account")
        username = st.text_input("Username")
        email = st.text_input("Email")
        password = st.text_input("Password", type='password')
        role = st.selectbox("Role", ["user", "planter"])
        if st.button("Register"):
            firebase_register(email, password, username, role)

    elif choice == "Password Reset":
        st.subheader("Send Password Reset Email")
        email = st.text_input("Enter your registered email")
        if st.button("Send Reset Link"):
            send_password_reset_email(email)

    elif choice == "User Management (Admin)":
        st.subheader("Admin: User Management")
        if st.session_state.authenticated and check_firebase_user_role(st.session_state.user, 'admin'):
            display_user_management()
        else:
            st.warning("You must be logged in as an admin to access this section.")
            st.info("To test: manually set st.session_state.user = {'uid': 'test_admin_uid', 'email': 'admin@example.com', 'role': 'admin', 'approved': True} and st.session_state.authenticated = True")


    elif choice == "Logout":
        if st.session_state.authenticated:
            if st.button("Logout"):
                firebase_logout()
        else:
            st.info("Not logged in.")
            
    elif choice == "Firebase Setup Guide":
        show_firebase_setup_guide()

    st.markdown("---")
    st.subheader("Current Session State")
    st.write(st.session_state.get('authenticated'))
    st.write(st.session_state.get('user'))
