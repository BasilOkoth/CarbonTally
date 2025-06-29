import sqlite3

trees_db = r"E:\CarbonTally-maintool\CarbonTally-main\data\trees.db"

conn = sqlite3.connect(trees_db)
cursor = conn.cursor()

# Add missing columns if they don't exist
try:
    cursor.execute("ALTER TABLE trees ADD COLUMN dbh_cm REAL;")
except sqlite3.OperationalError:
    print("Column 'dbh_cm' already exists")

try:
    cursor.execute("ALTER TABLE trees ADD COLUMN height_m REAL;")
except sqlite3.OperationalError:
    print("Column 'height_m' already exists")

try:
    cursor.execute("ALTER TABLE trees ADD COLUMN co2_kg REAL;")
except sqlite3.OperationalError:
    print("Column 'co2_kg' already exists")

try:
    cursor.execute("ALTER TABLE trees ADD COLUMN last_monitored_at TEXT;")
except sqlite3.OperationalError:
    print("Column 'last_monitored_at' already exists")

conn.commit()
conn.close()

print("✅ Trees table updated with necessary columns.")
