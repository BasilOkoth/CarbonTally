import sqlite3

def add_rcd_and_notes_columns(db_path="monitoring.db"):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Check existing columns
    cursor.execute("PRAGMA table_info(tree_monitoring)")
    columns = [col[1] for col in cursor.fetchall()]

    if "rcd_cm" not in columns:
        cursor.execute("ALTER TABLE tree_monitoring ADD COLUMN rcd_cm REAL")
        print("✅ Added 'rcd_cm' column.")

    if "notes" not in columns:
        cursor.execute("ALTER TABLE tree_monitoring ADD COLUMN notes TEXT")
        print("✅ Added 'notes' column.")

    conn.commit()
    conn.close()
    print("🎉 Database updated successfully.")

# Run the function
add_rcd_and_notes_columns()
