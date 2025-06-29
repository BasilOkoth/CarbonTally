import unittest
import os
import sys
import pandas as pd
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add parent directory to path to import modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import modules to test
from app import (
    initialize_data_files,
    load_tree_data,
    load_species_data,
    generate_tree_id,
    generate_qr_code,
    calculate_co2
)

class TestAppIntegration(unittest.TestCase):
    """Test cases for main app integration with KoBo"""
    
    def setUp(self):
        """Set up test environment"""
        # Create test directories
        self.test_data_dir = Path("test_data")
        self.test_data_dir.mkdir(exist_ok=True)
        self.test_qr_dir = Path("test_qr_codes")
        self.test_qr_dir.mkdir(exist_ok=True)
        
    def tearDown(self):
        """Clean up after tests"""
        # Clean up test directories
        for file in self.test_data_dir.glob("*"):
            file.unlink()
        if self.test_data_dir.exists():
            self.test_data_dir.rmdir()
            
        for file in self.test_qr_dir.glob("*.png"):
            file.unlink()
        if self.test_qr_dir.exists():
            self.test_qr_dir.rmdir()
    
    @patch('app.DATA_DIR')
    @patch('app.SQLITE_DB')
    def test_initialize_data_files(self, mock_db, mock_data_dir):
        """Test database initialization"""
        mock_data_dir.return_value = self.test_data_dir
        mock_db.return_value = self.test_data_dir / "test_trees.db"
        
        # Mock sqlite3 connection
        with patch('sqlite3.connect') as mock_connect:
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_connect.return_value = mock_conn
            mock_conn.cursor.return_value = mock_cursor
            mock_conn.commit = MagicMock()
            
            # Call the function
            initialize_data_files()
            
            # Verify database operations were called
            mock_connect.assert_called()
            mock_conn.cursor.assert_called()
            mock_conn.commit.assert_called()
    
    @patch('app.SQLITE_DB')
    def test_load_tree_data(self, mock_db):
        """Test loading tree data"""
        mock_db.return_value = self.test_data_dir / "test_trees.db"
        
        # Mock sqlite3.connect and pandas.read_sql
        with patch('sqlite3.connect') as mock_connect:
            mock_conn = MagicMock()
            mock_connect.return_value = mock_conn
            
            with patch('pandas.read_sql') as mock_read_sql:
                mock_df = pd.DataFrame()
                mock_read_sql.return_value = mock_df
                
                # Call the function
                result = load_tree_data()
                
                # Verify pandas read_sql was called
                mock_read_sql.assert_called_once()
    
    @patch('app.SQLITE_DB')
    def test_load_species_data(self, mock_db):
        """Test loading species data"""
        mock_db.return_value = self.test_data_dir / "test_trees.db"
        
        # Mock sqlite3.connect and pandas.read_sql
        with patch('sqlite3.connect') as mock_connect:
            mock_conn = MagicMock()
            mock_connect.return_value = mock_conn
            
            with patch('pandas.read_sql') as mock_read_sql:
                mock_df = pd.DataFrame()
                mock_read_sql.return_value = mock_df
                
                # Call the function
                result = load_species_data()
                
                # Verify pandas read_sql was called
                mock_read_sql.assert_called_once()
    
    def test_generate_tree_id(self):
        """Test tree ID generation"""
        # Mock load_tree_data
        with patch('app.load_tree_data') as mock_load_tree_data:
            import pandas as pd
            mock_df = pd.DataFrame({
                'tree_id': ['TEST001', 'TEST002'],
                'institution': ['Test Institution', 'Test Institution']
            })
            mock_load_tree_data.return_value = mock_df
            
            # Call the function
            result = generate_tree_id("Test Institution")
            
            # Verify ID format and incrementation
            self.assertTrue(result.startswith("TES"))
            self.assertEqual(len(result), 6)  # 3 letters + 3 digits
            self.assertEqual(result, "TES003")  # Should increment from TEST002
    
    @patch('app.QR_CODE_DIR')
    def test_generate_qr_code(self, mock_qr_dir):
        """Test QR code generation"""
        mock_qr_dir.return_value = self.test_qr_dir
        
        # Call the function with mocked dependencies
        with patch('qrcode.QRCode') as mock_qr_code:
            mock_qr = MagicMock()
            mock_qr_code.return_value = mock_qr
            mock_qr.make_image.return_value = MagicMock()
            
            # Mock BytesIO and base64
            with patch('io.BytesIO') as mock_bytesio:
                mock_buffer = MagicMock()
                mock_bytesio.return_value = mock_buffer
                
                with patch('base64.b64encode') as mock_b64encode:
                    mock_b64encode.return_value = b'test_encoded_string'
                    
                    # Call the function
                    result = generate_qr_code("TEST003")
                    
                    # Verify QR code generation
                    mock_qr.add_data.assert_called_with("TEST003")
                    mock_qr.make.assert_called_with(fit=True)
                    mock_qr.make_image.assert_called()
                    mock_b64encode.assert_called()
    
    def test_calculate_co2(self):
        """Test CO2 calculation"""
        # Mock load_species_data
        with patch('app.load_species_data') as mock_load_species_data:
            import pandas as pd
            import numpy as np
            mock_df = pd.DataFrame({
                'scientific_name': ['Acacia spp.'],
                'wood_density': [0.65]
            })
            mock_load_species_data.return_value = mock_df
            
            # Call the function
            result = calculate_co2("Acacia spp.", 3.2, None)
            
            # Verify calculation
            self.assertIsInstance(result, float)
            self.assertGreater(result, 0)

if __name__ == '__main__':
    unittest.main()
