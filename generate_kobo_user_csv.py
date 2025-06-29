# generate_kobo_user_csv.py

import firebase_admin
from firebase_admin import credentials, firestore
import csv
import requests

# --- 1. Firebase Setup ---
cred = credentials.Certificate("serviceAccountKey.json")  # Place this file in the same folder
firebase_admin.initialize_app(cred)
db = firestore.client()

# --- 2. Config ---
CSV_FILENAME = "kobo_user_list.csv"

# Replace with your actual Kobo API token and asset UID
KOBO_API_TOKEN = "your_kobo_api_token_here"
KOBO_ASSET_UID = "your_kobo_asset_uid_here"  # e.g., 'aBCdEfGhIJklmnop'

# --- 3. Fetch Approved Users from Firebase ---
def fetch_users():
    users_ref = db.collection("users")
    docs = users_ref.where("approved", "==", True).stream()
    
    user_list = []
    for doc in docs:
        data = doc.to_dict()
        tree_tracking_id = data.get("tree_tracking_id")
        name = data.get("name")
        if tree_tracking_id and name:
            user_list.append((tree_tracking_id, name))
    
 return user_list

# --- 4. Write to CSV ---
def write_csv(user_list):
    with open(CSV_FILENAME, "w", newline="", encoding="utf-8") as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(["tree_tracking_id", "username"])  # Must match Kobo XLSForm choices
        for row in user_list:
            writer.writerow(row)
    print(f"✅ CSV saved as {CSV_FILENAME}")

# --- 5. Upload to KoboToolbox ---
def upload_to_kobo():
    url = f"https://kf.kobotoolbox.org/api/v2/assets/{KOBO_ASSET_UID}/files/csv/"
    headers = {
        "Authorization": f"Token {KOBO_API_TOKEN}"
    }
    files = {
        'file': (CSV_FILENAME, open(CSV_FILENAME, 'rb'), 'text/csv')
    }
    response = requests.post(url, headers=headers, files=files)
    
    if response.status_code == 201:
        print("✅ CSV uploaded to KoboToolbox.")
    else:
        print(f"❌ Upload failed. Status: {response.status_code}")
        print(response.json())

# --- 6. Run All ---
if _name_ == "_main_":
    users = fetch_users()
    if not users:
        print("⚠ No approved users found.")
    else:
        write_csv(users)
        upload_to_kobo()
