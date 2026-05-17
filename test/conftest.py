"""
Fixtures compartidos para todos los tests.
"""
import pytest
import sys
import shutil
from pathlib import Path

# Añadir el directorio raíz al PATH
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app import app as flask_app  # 👈 IMPORTAR la instancia app directamente
from config.settings import settings

@pytest.fixture
def app():
    """Devuelve la aplicación Flask configurada para testing."""
    flask_app.config['TESTING'] = True
    flask_app.config['DEBUG'] = False
    previous_require_auth = settings.flask_require_auth
    settings.flask_require_auth = False
    yield flask_app
    settings.flask_require_auth = previous_require_auth

@pytest.fixture
def client(app):
    """Cliente de prueba para endpoints."""
    return app.test_client()

@pytest.fixture
def test_scan_folder(tmp_path):
    """Carpeta temporal para tests de escaneo."""
    scan_folder = tmp_path / "test_scans"
    scan_folder.mkdir()
    yield scan_folder
    # Cleanup
    if scan_folder.exists():
        shutil.rmtree(scan_folder)

@pytest.fixture
def mock_session_id():
    """Session ID de prueba."""
    return "test-session-123"

@pytest.fixture
def sample_user():
    """Usuario de prueba."""
    return {
        "user_id": "test_user",
        "feeder": False,
        "dpi": 300,
        "color_mode": "color"
    }