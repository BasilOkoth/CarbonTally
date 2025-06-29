from pathlib import Path
import sqlite3

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True, parents=True)
SQLITE_DB = DATA_DIR / "trees.db"

def get_db_connection():
    return sqlite3.connect(SQLITE_DB)
