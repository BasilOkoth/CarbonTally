import sqlite3
import pandas as pd

trees_db = r"E:\CarbonTally-maintool\CarbonTally-main\data\trees.db"
monitoring_db = "monitoring.db"

# Check trees table
conn = sqlite3.connect(trees_db)
df_trees = pd.read_sql_query("SELECT * FROM trees ORDER BY last_monitored_at DESC LIMIT 10", conn)
print("trees.db:")
print(df_trees)
conn.close()

# Check monitoring table
conn2 = sqlite3.connect(monitoring_db)
df_monitor = pd.read_sql_query("SELECT * FROM tree_monitoring ORDER BY monitored_at DESC LIMIT 10", conn2)
print("monitoring.db:")
print(df_monitor)
conn2.close()
