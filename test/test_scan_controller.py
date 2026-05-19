"""
Tests para endpoints de scan_controller.
"""
import pytest
import json
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
import jwt
from config.settings import settings

class TestScanController:
    """Tests para endpoints de escaneo."""
    
    @pytest.fixture(autouse=True)
    def cleanup(self, client):
        """Limpieza automática antes de cada test."""
        yield
        # Cancelar cualquier sesión activa después de cada test
        client.post('/api/scan/cancel')
    
    def test_check_scanner_success(self, client):
        """Test: verificación exitosa del escáner."""
        with patch('controllers.scan_controller.check_feeder') as mock_feeder, \
             patch('controllers.scan_controller.check_flatbed_sheet') as mock_flatbed:
            
            mock_feeder.return_value = {'available': True, 'success': True}
            mock_flatbed.return_value = {'available': True, 'success': True}
            
            response = client.get('/api/scan/check-scanner')
            data = json.loads(response.data)
            
            assert response.status_code == 200
            assert data['success'] is True
            assert 'adf_status' in data
            assert 'hardware_connected' in data
    
    def test_check_scanner_timeout(self, client):
        """Test: timeout al verificar escáner."""
        with patch('controllers.scan_controller.check_feeder') as mock_feeder:
            mock_feeder.return_value = {'timeout': True}
            
            response = client.get('/api/scan/check-scanner')
            
            assert response.status_code == 504
    
    def test_start_scan_no_user_id(self, client):
        """Test: inicio de escaneo sin user_id usa 'anonymous'."""
        with patch('controllers.scan_controller.validate_and_scan_flatbed') as mock_validate:
            
            # Mock validate_and_scan_flatbed para simular escaneo exitoso
            mock_validate.return_value = {
                'success': True,
                'scanned_count': 1,
                'message': 'Test scan completed'
            }
            
            response = client.post('/api/scan/start', 
                                json={
                                    'feeder': False,
                                    'dpi': 300
                                },
                                content_type='application/json')
            data = json.loads(response.data)
            
            assert response.status_code == 200
            assert data['success'] is True
            assert 'session_id' in data
            
            # Verificar que se llamó validate_and_scan_flatbed
            mock_validate.assert_called_once()
    
    def test_start_scan_invalid_dpi(self, client):
        """Test: inicio de escaneo con DPI inválido."""
        response = client.post('/api/scan/start', 
                              json={
                                  'user_id': 'test',
                                  'feeder': False,
                                  'dpi': 999
                              },
                              content_type='application/json')
        data = json.loads(response.data)
        
        assert response.status_code == 400
        errors_str = str(data.get('errors', [])).lower()
        assert 'dpi' in errors_str
    
    def test_status_no_active_session(self, client):
        """Test: consultar estado sin sesión activa."""
        client.post('/api/scan/cancel')
        
        response = client.get('/api/scan/status')
        data = json.loads(response.data)
        
        assert response.status_code == 200
        assert data['is_scanning'] is False
    
    def test_cancel_no_active_session(self, client):
        """Test: cancelar sin sesión activa."""
        client.post('/api/scan/cancel')
        
        response = client.post('/api/scan/cancel')
        data = json.loads(response.data)
        
        assert response.status_code in [200, 400]
    
    def test_cleanup_nonexistent_session(self, client):
        """Test: limpiar sesión inexistente."""
        response = client.delete('/api/scan/cleanup/nonexistent-session')
        data = json.loads(response.data)
        
        assert response.status_code == 404
        assert 'no existe' in str(data.get('error', '')).lower()

    def test_check_scanner_without_token_returns_401(self, client):
        """Test: /check-scanner sin token retorna 401 cuando la auth está activa."""
        previous_require_auth = settings.flask_require_auth
        previous_secret = settings.flask_shared_secret
        previous_issuer = settings.flask_jwt_issuer
        previous_debug = settings.debug

        settings.flask_require_auth = True
        settings.flask_shared_secret = 'test-shared-secret'
        settings.flask_jwt_issuer = 'django-polihc'
        settings.debug = False

        try:
            response = client.get('/api/scan/check-scanner')
            data = json.loads(response.data)

            assert response.status_code == 401
            assert data['success'] is False
            assert data['error'] == 'invalid_token'
        finally:
            settings.flask_require_auth = previous_require_auth
            settings.flask_shared_secret = previous_secret
            settings.flask_jwt_issuer = previous_issuer
            settings.debug = previous_debug

    def test_check_scanner_invalid_token_returns_401(self, client):
        """Test: /check-scanner con token inválido retorna 401."""
        previous_require_auth = settings.flask_require_auth
        previous_secret = settings.flask_shared_secret
        previous_issuer = settings.flask_jwt_issuer
        previous_debug = settings.debug

        settings.flask_require_auth = True
        settings.flask_shared_secret = 'test-shared-secret'
        settings.flask_jwt_issuer = 'django-polihc'
        settings.debug = False

        try:
            response = client.get(
                '/api/scan/check-scanner',
                headers={'Authorization': 'Bearer token-invalido'}
            )
            data = json.loads(response.data)

            assert response.status_code == 401
            assert data['success'] is False
            assert data['error'] == 'invalid_token'
        finally:
            settings.flask_require_auth = previous_require_auth
            settings.flask_shared_secret = previous_secret
            settings.flask_jwt_issuer = previous_issuer
            settings.debug = previous_debug

    def test_check_scanner_valid_token_returns_200(self, client):
        """Test: /check-scanner con token válido retorna 200."""
        previous_require_auth = settings.flask_require_auth
        previous_secret = settings.flask_shared_secret
        previous_issuer = settings.flask_jwt_issuer
        previous_debug = settings.debug

        settings.flask_require_auth = True
        settings.flask_shared_secret = 'test-shared-secret'
        settings.flask_jwt_issuer = 'django-polihc'
        settings.debug = False

        token = jwt.encode(
            {
                'sub': 'test-user',
                'iss': 'django-polihc',
                'exp': datetime.now(timezone.utc) + timedelta(minutes=5)
            },
            settings.flask_shared_secret,
            algorithm='HS256'
        )

        try:
            with patch('controllers.scan_controller.check_feeder') as mock_feeder, \
                 patch('controllers.scan_controller.check_flatbed_sheet') as mock_flatbed:
                mock_feeder.return_value = {'available': True, 'success': True}
                mock_flatbed.return_value = {'available': True, 'success': True}

                response = client.get(
                    '/api/scan/check-scanner',
                    headers={'Authorization': f'Bearer {token}'}
                )
                data = json.loads(response.data)

                assert response.status_code == 200
                assert data['success'] is True
        finally:
            settings.flask_require_auth = previous_require_auth
            settings.flask_shared_secret = previous_secret
            settings.flask_jwt_issuer = previous_issuer
            settings.debug = previous_debug
