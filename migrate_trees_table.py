import sqlite3
import os

SQLITE_DB = r"E:\CarbonTally-maintool\CarbonTally-main\data\trees.db"

def migrate_remove_form_uid():
    if not os.path.exists(SQLITE_DB):
        print(f"❌ Database not found: {SQLITE_DB}")
        return

    try:
        conn = sqlite3.connect(SQLITE_DB)
        c = conn.cursor()

        print("🔁 Starting migration...")

        # Step 1: Rename old table
        c.execute("ALTER TABLE trees RENAME TO trees_old")

        # Step 2: Create new table (same as before, minus 'form_uid')
        c.execute("""
            CREATE TABLE trees (
                tree_id TEXT PRIMARY KEY,
                local_name TEXT,
                scientific_name TEXT,
                planters_name TEXT,
                date_planted TEXT,
                latitude REAL,
                longitude REAL,
                co2_kg REAL,
                planter_email TEXT,
                planter_uid TEXT,
                tree_tracking_number TEXT,
                dbh_cm REAL,
                height_m REAL,
                tree_stage TEXT,
                status TEXT,
                country TEXT,
                county TEXT,
                sub_county TEXT,
                ward TEXT,
                adopter_name TEXT,
                last_updated TEXT,
                form_uuid TEXT
            )
        """)

        # Step 3: Copy data (excluding form_uid)
        c.execute("""
            INSERT INTO trees (
                tree_id, local_name, scientific_name, planters_name, date_planted,
                latitude, longitude, co2_kg, planter_email, planter_uid, tree_tracking_number,
                dbh_cm, height_m, tree_stage, status, country, county, sub_county, ward,
                adopter_name, last_updated, form_uuid
            )
            SELECT 
                tree_id, local_name, scientific_name, planters_name, date_planted,
                latitude, longitude, co2_kg, planter_email, planter_uid, tree_tracking_number,
                dbh_cm, height_m, tree_stage, status, country, county, sub_county, ward,
                adopter_name, last_updated, form_uuid
            FROM trees_old
        """)

        # Step 4: Drop old table
        c.execute("DROP TABLE trees_old")

        conn.commit()
        print("✅ Migration complete. 'form_uid' removed and 'form_uuid' retained.")

    except Exception as e:
        print(f"❌ Migration failed: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    migrate_remove_form_uid()
