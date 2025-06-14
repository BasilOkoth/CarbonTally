import unittest
import os
import sys
import sqlite3
import pandas as pd
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add parent directory to path to import modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import modules to test
from kobo_integration import (
    map_kobo_to_database_fields,
    generate_tree_id,
    generate_qr_code,
    calculate_co2,
    save_tree_from_kobo_submission
)

class TestKoboIntegration(unittest.TestCase):
    """Test cases for KoBo integration functionality"""
    
    def setUp(self):
        """Set up test environment"""
        # Create test database
        self.test_db_path = Path("test_trees.db")
        self.conn = sqlite3.connect(self.test_db_path)
        self.c = self.conn.cursor()
        
        # Create necessary tables
        self.c.execute("""CREATE TABLE IF NOT EXISTS trees (
            tree_id TEXT PRIMARY KEY,
            institution TEXT,
            local_name TEXT,
            scientific_name TEXT,
            student_name TEXT,
            date_planted TEXT,
            tree_stage TEXT,
            rcd_cm REAL,
            dbh_cm REAL,
            height_m REAL,
            latitude REAL,
            longitude REAL,
            co2_kg REAL,
            status TEXT,
            country TEXT,
            county TEXT,
            sub_county TEXT,
            ward TEXT,
            adopter_name TEXT,
            last_monitored TEXT,
            monitor_notes TEXT,
            qr_code TEXT
        )""")
        
        self.c.execute("""CREATE TABLE IF NOT EXISTS species (
            scientific_name TEXT PRIMARY KEY,
            local_name TEXT,
            wood_density REAL,
            benefits TEXT
        )""")
        
        self.c.execute("""CREATE TABLE IF NOT EXISTS monitoring_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tree_id TEXT,
            monitor_date TEXT,
            monitor_status TEXT,
            monitor_stage TEXT,
            rcd_cm REAL,
            dbh_cm REAL,
            height_m REAL,
            co2_kg REAL,
            notes TEXT,
            monitor_by TEXT,
            FOREIGN KEY (tree_id) REFERENCES trees (tree_id)
        )""")
        
        # Insert test species
        self.c.execute("""INSERT INTO species VALUES (?, ?, ?, ?)""", 
                      ("Acacia spp.", "Acacia", 0.65, "Test benefits"))
        
        # Insert test tree
        self.c.execute("""INSERT INTO trees VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                      ("TEST001", "Test Institution", "Acacia", "Acacia spp.", "Test Student", 
                       "2025-05-31", "Seedling", 2.5, 0.0, 1.2, -1.2921, 36.8219, 0.5, 
                       "Alive", "Kenya", "Nairobi", "Westlands", "Parklands", None, 
                       "2025-05-31", "Test notes", "test_qr_code"))
        
        self.conn.commit()
        
        # Create test QR code directory
        self.test_qr_dir = Path("test_qr_codes")
        self.test_qr_dir.mkdir(exist_ok=True)
        
        # Sample KoBo submission data
        self.sample_kobo_data = {
            "institution": "Test School",
            "local_name": "Mango",
            "scientific_name": "Mangifera indica",
            "student_name": "John Doe",
            "date_planted": "2025-05-31",
            "tree_stage": "Seedling",
            "rcd_cm": "3.2",
            "dbh_cm": "0",
            "height_m": "0.8",
            "_geolocation": [-1.2921, 36.8219],
            "country": "Kenya",
            "county": "Nairobi",
            "sub_county": "Westlands",
            "ward": "Parklands",
            "_submission_time": "2025-05-31T12:00:00",
            "notes": "Test planting"
        }
    
    def tearDown(self):
        """Clean up after tests"""
        self.conn.close()
        if self.test_db_path.exists():
            self.test_db_path.unlink()
        
        # Clean up QR code files
        for file in self.test_qr_dir.glob("*.png"):
            file.unlink()
        if self.test_qr_dir.exists():
            self.test_qr_dir.rmdir()
    
    def test_map_kobo_to_database_fields(self):
        """Test mapping KoBo form fields to database fields"""
        # Patch the function to use test data
        with patch('kobo_integration.map_kobo_to_database_fields', return_value={
            "institution": "Test School",
            "local_name": "Mango",
            "scientific_name": "Mangifera indica",
            "student_name": "John Doe",
            "date_planted": "2025-05-31",
            "tree_stage": "Seedling",
            "rcd_cm": 3.2,
            "dbh_cm": 0.0,
            "height_m": 0.8,
            "latitude": -1.2921,
            "longitude": 36.8219,
            "status": "Alive",
            "country": "Kenya",
            "county": "Nairobi",
            "sub_county": "Westlands",
            "ward": "Parklands",
            "adopter_name": None,
            "last_monitored": "2025-05-31T12:00:00",
            "monitor_notes": "Test planting"
        }):
            result = map_kobo_to_database_fields(self.sample_kobo_data)
            
            # Verify mapping
            self.assertEqual(result["institution"], "Test School")
            self.assertEqual(result["local_name"], "Mango")
            self.assertEqual(result["scientific_name"], "Mangifera indica")
            self.assertEqual(result["latitude"], -1.2921)
            self.assertEqual(result["longitude"], 36.8219)
            self.assertEqual(result["status"], "Alive")
    
    def test_generate_tree_id(self):
        """Test tree ID generation"""
        # Patch the function to use test database
        with patch('sqlite3.connect') as mock_connect:
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_connect.return_value = mock_conn
            mock_conn.cursor.return_value = mock_cursor
            mock_cursor.fetchall.return_value = [('TEST001',), ('TEST002',)]
            
            result = generate_tree_id("Test Institution")
            
            # Verify ID format and incrementation
            self.assertTrue(result.startswith("TES"))
            self.assertEqual(len(result), 6)  # 3 letters + 3 digits
            self.assertEqual(result, "TES003")  # Should increment from TEST002
    
    def test_generate_qr_code(self):
        """Test QR code generation"""
        # Patch the function to use test directory
        with patch('qrcode.QRCode') as mock_qr_code:
            mock_qr = MagicMock()
            mock_qr_code.return_value = mock_qr
            mock_img = MagicMock()
            mock_qr.make_image.return_value = mock_img
            
            # Mock BytesIO and base64
            with patch('io.BytesIO') as mock_bytesio:
                mock_buffer = MagicMock()
                mock_bytesio.return_value = mock_buffer
                
                with patch('base64.b64encode') as mock_b64encode:
                    mock_b64encode.return_value = b'base64_encoded_string'
                    
                    # Call the function with mocked dependencies
                    result, file_path = generate_qr_code("TEST002")
                    
                    # Verify QR code generation
                    mock_qr.add_data.assert_called_with("TEST002")
                    mock_qr.make.assert_called_with(fit=True)
                    mock_qr.make_image.assert_called()
                    mock_b64encode.assert_called()
                    self.assertEqual(result, "base64_encoded_string")
    
    def test_calculate_co2(self):
        """Test CO2 calculation"""
        # Patch the function to use test database
        with patch('sqlite3.connect') as mock_connect:
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_connect.return_value = mock_conn
            
            # Mock pandas read_sql
            with patch('pandas.read_sql') as mock_read_sql:
                mock_df = pd.DataFrame({
                    'scientific_name': ['Acacia spp.'],
                    'wood_density': [0.65]
                })
                mock_read_sql.return_value = mock_df
                
                # Call the function
                result = calculate_co2("Acacia spp.", 3.2, None)
                
                # Verify calculation
                self.assertIsInstance(result, float)
                self.assertGreater(result, 0)
    
    def test_save_tree_from_kobo_submission(self):
        """Test saving tree data from KoBo submission"""
        # Patch dependencies
        with patch('kobo_integration.SQLITE_DB', self.test_db_path):
            with patch('kobo_integration.QR_CODE_DIR', self.test_qr_dir):
                with patch('kobo_integration.map_kobo_to_database_fields', return_value={
                    "institution": "Test School",
                    "local_name": "Mango",
                    "scientific_name": "Mangifera indica",
                    "student_name": "John Doe",
                    "date_planted": "2025-05-31",
                    "tree_stage": "Seedling",
                    "rcd_cm": 3.2,
                    "dbh_cm": 0.0,
                    "height_m": 0.8,
                    "latitude": -1.2921,
                    "longitude": 36.8219,
                    "status": "Alive",
                    "country": "Kenya",
                    "county": "Nairobi",
                    "sub_county": "Westlands",
                    "ward": "Parklands",
                    "adopter_name": None,
                    "last_monitored": "2025-05-31T12:00:00",
                    "monitor_notes": "Test planting"
                }):
                    with patch('kobo_integration.generate_tree_id', return_value="TES002"):
                        with patch('kobo_integration.calculate_co2', return_value=0.42):
                            with patch('kobo_integration.generate_qr_code', return_value=("base64_encoded_string", f"{self.test_qr_dir}/TES002_qr.png")):
                                # Mock the database operations
                                with patch('sqlite3.connect') as mock_connect:
                                    mock_conn = MagicMock()
                                    mock_cursor = MagicMock()
                                    mock_connect.return_value = mock_conn
                                    mock_conn.cursor.return_value = mock_cursor
                                    mock_conn.commit = MagicMock()
                                    
                                    # Call the function
                                    success, tree_id, qr_code_path = save_tree_from_kobo_submission(self.sample_kobo_data)
                                    
                                    # Verify results
                                    self.assertTrue(success)
                                    self.assertEqual(tree_id, "TES002")
                                    self.assertTrue("TES002_qr.png" in qr_code_path)
                                    
                                    # Verify database operations were called
                                    mock_conn.cursor.assert_called()
                                    mock_conn.commit.assert_called()

if __name__ == '__main__':
    unittest.main()
