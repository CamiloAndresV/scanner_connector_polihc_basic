"""
Tests para gestión de archivos de escaneo.
"""
import shutil
from unittest.mock import patch
from utils.file_manager import ScanFileManager

class TestFileManager:
    """Tests para ScanFileManager."""
    
    def test_get_scanned_pages_empty(self, tmp_path):
        """Test: obtener páginas de sesión vacía."""
        session_id = "test-empty"
        session_folder = tmp_path / f"session_{session_id}"
        session_folder.mkdir()
        
        with patch('utils.file_manager.SCAN_FOLDER', str(tmp_path)):
            manager = ScanFileManager(f"session_{session_id}")
            pages = manager.get_scanned_pages()
            
            assert pages == []
        
        # Cleanup
        if session_folder.exists():
            shutil.rmtree(session_folder)
    
    def test_cleanup_session(self, tmp_path):
        """Test: limpiar sesión correctamente."""
        session_id = "test-cleanup"
        session_folder = tmp_path / f"session_{session_id}"
        session_folder.mkdir()
        
        # Crear archivo de prueba
        test_file = session_folder / "page_01.webp"
        test_file.write_text("test")
        
        with patch('utils.file_manager.SCAN_FOLDER', str(tmp_path)):
            manager = ScanFileManager(f"session_{session_id}")
            result = manager.cleanup_session()
            
            assert result['success'] is True
            assert not session_folder.exists()