"""
Tests de integración del flujo completo de escaneo.
"""
import pytest
from unittest.mock import patch

class TestScanIntegration:
    """Tests de integración del flujo de escaneo."""
    
    @patch('controllers.scan_controller.validate_and_scan_flatbed')
    @patch('services.twain_connector.scan_document')
    @patch('utils.session_lock.session_manager.acquire_lock')
    def test_full_scan_workflow(self, mock_lock, mock_scan, mock_validate_flatbed, client):
        """Test: flujo completo start → continue → status."""
        
        # Mock de verificaciones
        mock_lock.return_value = {'success': True, 'session_id': 'test-123'}
        mock_scan.return_value = ['mock_image_path.webp']
        mock_validate_flatbed.return_value = {
            'success': True,
            'message': 'Escaneo de prueba completado',
            'filename': 'page_1.webp',
            'scanner_name': 'e-STUDIO2822ASeries Scan Driver'
        }
        
        # 1. START
        start_response = client.post('/api/scan/start', json={
            'user_id': 'test_user',
            'feeder': False,
            'dpi': 300
        })
        assert start_response.status_code in [200, 409]  # 409 si hay sesión activa
        
        # 2. STATUS
        status_response = client.get('/api/scan/status')
        assert status_response.status_code == 200
        assert 'is_scanning' in status_response.json
        
        # 3. CANCEL (si hay sesión activa)
        if status_response.json.get('is_scanning'):
            cancel_response = client.post('/api/scan/cancel')
            assert cancel_response.status_code == 200