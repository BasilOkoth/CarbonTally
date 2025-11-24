import sqlite3
import pandas as pd
from pathlib import Path

# --- Define Database Paths ---
# Corrected BASE_DIR: If this script is saved directly in 'CarbonTally-main',
# then Path(__file__).parent points to 'CarbonTally-main'.
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / 'data'
TREES_DB_PATH = DATA_DIR / 'trees.db'
MONITORING_DB_PATH = DATA_DIR / 'monitoring.db'

def get_table_schema(db_path: Path):
    """Connects to a SQLite database and retrieves the schema for all tables."""
    print(f"\n--- Schema for: {db_path.name} ---")
    if not db_path.exists():
        print(f"Error: Database file not found at {db_path}")
        return

    conn = None
    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()

        # Get all table names
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = cursor.fetchall()

        if not tables:
            print("No tables found.")
            return

        for table_name_tuple in tables:
            table_name = table_name_tuple[0]
            print(f"\nTable: {table_name}")
            # Get column information for each table
            cursor.execute(f"PRAGMA table_info({table_name});")
            columns = cursor.fetchall()
            
            if columns:
                # Print header
                print("{:<5} {:<20} {:<15} {:<10} {:<10} {:<10}".format(
                    "CID", "Name", "Type", "NotNull", "Default", "PK"
                ))
                print("-" * 75)
                for col in columns:
                    print("{:<5} {:<20} {:<15} {:<10} {:<10} {:<10}".format(
                        col[0], col[1], col[2], col[3], col[4] if col[4] is not None else 'NULL', col[5]
                    ))
            else:
                print("  No columns found for this table.")

    except sqlite3.Error as e:
        print(f"Database error for {db_path.name}: {e}")
    finally:
        if conn:
            conn.close()

# --- Display Schemas ---
get_table_schema(TREES_DB_PATH)
get_table_schema(MONITORING_DB_PATH)
