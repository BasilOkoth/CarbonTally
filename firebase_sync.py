import sqlite3
import threading
import time
from pathlib import Path
from datetime import datetime
from firebase_admin import firestore
import pandas as pd
import streamlit as st

class FirebaseSync:
    def __init__(self):
        self.BASE_DIR = Path(__file__).parent
        self.DATA_DIR = self.BASE_DIR / "data"
        self.SQLITE_DB = self.DATA_DIR / "trees.db"
        self.DATA_DIR.mkdir(exist_ok=True, parents=True)
        self.sync_interval = 300  # 5 minutes
        self.running = False
        self.sync_thread = None

    def get_db_connection(self):
        """Get a connection to the SQLite database"""
        return sqlite3.connect(self.SQLITE_DB)

    def initialize_tables(self):
        """Initialize all required tables with proper schema"""
        with self.get_db_connection() as conn:
            c = conn.cursor()
            
            # Institutions table
            c.execute("""
                CREATE TABLE IF NOT EXISTS institutions (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    join_date TEXT NOT NULL,
                    firebase_doc_id TEXT UNIQUE,
                    last_sync_time TEXT
                )
            """)
            
            # Users table
            c.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    uid TEXT PRIMARY KEY,
                    email TEXT NOT NULL,
                    display_name TEXT,
                    role TEXT,
                    status TEXT,
                    tree_tracking_number TEXT,
                    firebase_doc_id TEXT UNIQUE,
                    last_sync_time TEXT
                )
            """)
            
            # Trees table (matches your existing schema)
            c.execute("""
                CREATE TABLE IF NOT EXISTS trees (
                    tree_id TEXT PRIMARY KEY,
                    form_uuid TEXT UNIQUE,
                    tree_tracking_number TEXT NOT NULL,
                    institution TEXT,
                    local_name TEXT,
                    scientific_name TEXT,
                    planter_id TEXT,
                    planters_name TEXT,
                    planter_email TEXT,
                    planter_uid TEXT,
                    date_planted TEXT,
                    tree_stage TEXT,
                    rcd_cm REAL,
                    dbh_cm REAL,
                    height_m REAL,
                    co2_kg REAL,
                    status TEXT,
                    qr_code TEXT,
                    kobo_submission_id TEXT UNIQUE,
                    last_updated TEXT,
                    country TEXT,
                    county TEXT,
                    sub_county TEXT,
                    ward TEXT,
                    adopter_name TEXT,
                    organization_name TEXT,
                    latitude REAL,
                    longitude REAL,
                    firebase_doc_id TEXT UNIQUE,
                    last_sync_time TEXT
                )
            """)
            
            conn.commit()

    def sync_all(self):
        """Sync all data types from Firebase to SQLite"""
        self.sync_institutions()
        self.sync_users()
        self.sync_trees()
        
    def sync_institutions(self):
        """Sync approved institutions from Firebase"""
        current_time = datetime.utcnow().isoformat()
        db = firestore.client()
        
        with self.get_db_connection() as conn:
            c = conn.cursor()
            
            # Get existing institutions for comparison
            existing_ids = {row[0] for row in c.execute("SELECT id FROM institutions").fetchall()}
            
            # Query all approved institutions
            institutions_ref = db.collection('institutions')
            approved_institutions = institutions_ref.where('status', '==', 'approved').stream()
            
            new_count = updated_count = 0
            
            for inst in approved_institutions:
                inst_data = inst.to_dict()
                inst_id = inst.id
                
                if inst_id in existing_ids:
                    # Update existing record
                    c.execute("""
                        UPDATE institutions SET
                            name = ?,
                            join_date = ?,
                            firebase_doc_id = ?,
                            last_sync_time = ?
                        WHERE id = ?
                    """, (
                        inst_data.get('name'),
                        inst_data.get('join_date', current_time),
                        inst.id,
                        current_time,
                        inst_id
                    ))
                    updated_count += 1
                else:
                    # Insert new record
                    c.execute("""
                        INSERT INTO institutions (
                            id, name, join_date, firebase_doc_id, last_sync_time
                        ) VALUES (?, ?, ?, ?, ?)
                    """, (
                        inst_id,
                        inst_data.get('name'),
                        inst_data.get('join_date', current_time),
                        inst.id,
                        current_time
                    ))
                    new_count += 1
            
            conn.commit()
            return new_count, updated_count

    def sync_users(self):
        """Sync user data from Firebase"""
        current_time = datetime.utcnow().isoformat()
        db = firestore.client()
        
        with self.get_db_connection() as conn:
            c = conn.cursor()
            
            # Get existing users for comparison
            existing_uids = {row[0] for row in c.execute("SELECT uid FROM users").fetchall()}
            
            # Query all users
            users_ref = db.collection('users')
            users = users_ref.stream()
            
            new_count = updated_count = 0
            
            for user in users:
                user_data = user.to_dict()
                uid = user.id
                
                if uid in existing_uids:
                    # Update existing record
                    c.execute("""
                        UPDATE users SET
                            email = ?,
                            display_name = ?,
                            role = ?,
                            status = ?,
                            tree_tracking_number = ?,
                            firebase_doc_id = ?,
                            last_sync_time = ?
                        WHERE uid = ?
                    """, (
                        user_data.get('email'),
                        user_data.get('displayName'),
                        user_data.get('role'),
                        user_data.get('status'),
                        user_data.get('treeTrackingNumber'),
                        user.id,
                        current_time,
                        uid
                    ))
                    updated_count += 1
                else:
                    # Insert new record
                    c.execute("""
                        INSERT INTO users (
                            uid, email, display_name, role, status,
                            tree_tracking_number, firebase_doc_id, last_sync_time
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        uid,
                        user_data.get('email'),
                        user_data.get('displayName'),
                        user_data.get('role'),
                        user_data.get('status'),
                        user_data.get('treeTrackingNumber'),
                        user.id,
                        current_time
                    ))
                    new_count += 1
            
            conn.commit()
            return new_count, updated_count

    def sync_trees(self):
        """Sync tree data from Firebase"""
        current_time = datetime.utcnow().isoformat()
        db = firestore.client()
        
        with self.get_db_connection() as conn:
            c = conn.cursor()
            
            # Get existing trees for comparison
            existing_tree_ids = {row[0] for row in c.execute("SELECT tree_id FROM trees").fetchall()}
            
            # Query all trees
            trees_ref = db.collection('trees')
            trees = trees_ref.stream()
            
            new_count = updated_count = 0
            
            for tree in trees:
                tree_data = tree.to_dict()
                tree_id = tree_data.get('tree_id', tree.id)
                
                if tree_id in existing_tree_ids:
                    # Update existing record
                    c.execute("""
                        UPDATE trees SET
                            form_uuid = ?,
                            tree_tracking_number = ?,
                            institution = ?,
                            local_name = ?,
                            scientific_name = ?,
                            planter_id = ?,
                            planters_name = ?,
                            planter_email = ?,
                            planter_uid = ?,
                            date_planted = ?,
                            tree_stage = ?,
                            rcd_cm = ?,
                            dbh_cm = ?,
                            height_m = ?,
                            co2_kg = ?,
                            status = ?,
                            qr_code = ?,
                            kobo_submission_id = ?,
                            last_updated = ?,
                            country = ?,
                            county = ?,
                            sub_county = ?,
                            ward = ?,
                            adopter_name = ?,
                            organization_name = ?,
                            latitude = ?,
                            longitude = ?,
                            firebase_doc_id = ?,
                            last_sync_time = ?
                        WHERE tree_id = ?
                    """, (
                        tree_data.get('form_uuid'),
                        tree_data.get('tree_tracking_number'),
                        tree_data.get('institution'),
                        tree_data.get('local_name'),
                        tree_data.get('scientific_name'),
                        tree_data.get('planter_id'),
                        tree_data.get('planters_name'),
                        tree_data.get('planter_email'),
                        tree_data.get('planter_uid'),
                        tree_data.get('date_planted'),
                        tree_data.get('tree_stage'),
                        tree_data.get('rcd_cm'),
                        tree_data.get('dbh_cm'),
                        tree_data.get('height_m'),
                        tree_data.get('co2_kg'),
                        tree_data.get('status'),
                        tree_data.get('qr_code'),
                        tree_data.get('kobo_submission_id'),
                        tree_data.get('last_updated', current_time),
                        tree_data.get('country'),
                        tree_data.get('county'),
                        tree_data.get('sub_county'),
                        tree_data.get('ward'),
                        tree_data.get('adopter_name'),
                        tree_data.get('organization_name'),
                        tree_data.get('latitude'),
                        tree_data.get('longitude'),
                        tree.id,
                        current_time,
                        tree_id
                    ))
                    updated_count += 1
                else:
                    # Insert new record
                    c.execute("""
                        INSERT INTO trees (
                            tree_id, form_uuid, tree_tracking_number, institution,
                            local_name, scientific_name, planter_id, planters_name,
                            planter_email, planter_uid, date_planted, tree_stage,
                            rcd_cm, dbh_cm, height_m, co2_kg, status, qr_code,
                            kobo_submission_id, last_updated, country, county,
                            sub_county, ward, adopter_name, organization_name,
                            latitude, longitude, firebase_doc_id, last_sync_time
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        tree_id,
                        tree_data.get('form_uuid'),
                        tree_data.get('tree_tracking_number'),
                        tree_data.get('institution'),
                        tree_data.get('local_name'),
                        tree_data.get('scientific_name'),
                        tree_data.get('planter_id'),
                        tree_data.get('planters_name'),
                        tree_data.get('planter_email'),
                        tree_data.get('planter_uid'),
                        tree_data.get('date_planted'),
                        tree_data.get('tree_stage'),
                        tree_data.get('rcd_cm'),
                        tree_data.get('dbh_cm'),
                        tree_data.get('height_m'),
                        tree_data.get('co2_kg'),
                        tree_data.get('status'),
                        tree_data.get('qr_code'),
                        tree_data.get('kobo_submission_id'),
                        tree_data.get('last_updated', current_time),
                        tree_data.get('country'),
                        tree_data.get('county'),
                        tree_data.get('sub_county'),
                        tree_data.get('ward'),
                        tree_data.get('adopter_name'),
                        tree_data.get('organization_name'),
                        tree_data.get('latitude'),
                        tree_data.get('longitude'),
                        tree.id,
                        current_time
                    ))
                    new_count += 1
            
            conn.commit()
            return new_count, updated_count

    def start_background_sync(self):
        """Start the background sync thread"""
        if not self.running:
            self.running = True
            self.sync_thread = threading.Thread(
                target=self._background_sync_worker,
                daemon=True
            )
            self.sync_thread.start()
            return True
        return False

    def _background_sync_worker(self):
        """Background worker that performs regular syncs"""
        while self.running:
            try:
                # Perform initial sync immediately
                self.sync_all()
                
                # Then sync at regular intervals
                time.sleep(self.sync_interval)
            except Exception as e:
                print(f"Background sync error: {e}")
                time.sleep(60)  # Wait a minute before retrying

    def stop_background_sync(self):
        """Stop the background sync thread"""
        self.running = False
        if self.sync_thread:
            self.sync_thread.join(timeout=5)
        return True

# Singleton instance
firebase_sync = FirebaseSync()

# Initialize on import
firebase_sync.initialize_tables()
firebase_sync.start_background_sync()
