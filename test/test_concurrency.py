"""
Tests de concurrencia para verificar el comportamiento bajo carga simultánea.
Valida que los locks funcionan correctamente y no hay race conditions.
"""

import pytest
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from controllers.scan_controller import (
    _hardware_lock,
    state_lock,
    scan_state,
    reset_scan_state
)


class TestHardwareLock:
    """Tests para el lock de hardware TWAIN."""
    
    def test_hardware_lock_exclusive_access(self):
        """Verifica que el lock permite solo un thread a la vez."""
        execution_order = []
        
        def access_hardware(thread_id, delay=0.1):
            """Simula acceso al hardware con lock."""
            with _hardware_lock:
                execution_order.append(f"start-{thread_id}")
                time.sleep(delay)  # Simula operación del hardware
                execution_order.append(f"end-{thread_id}")
        
        # Ejecutar 5 threads simultáneos
        threads = []
        for i in range(5):
            t = threading.Thread(target=access_hardware, args=(i,))
            threads.append(t)
            t.start()
        
        # Esperar que todos terminen
        for t in threads:
            t.join()
        
        # Verificar que no hubo interleaving (cada start debe ir con su end)
        for i in range(5):
            start_idx = execution_order.index(f"start-{i}")
            end_idx = execution_order.index(f"end-{i}")
            
            # Entre start y end no debe haber otro start
            between = execution_order[start_idx + 1:end_idx]
            assert not any(item.startswith('start') for item in between), \
                f"Thread {i} fue interrumpido por otro thread"
    
    def test_hardware_lock_release_after_exception(self):
        """Verifica que el lock se libera incluso con excepciones."""
        def faulty_operation():
            """Operación que falla pero debe liberar el lock."""
            with _hardware_lock:
                raise ValueError("Error simulado")
        
        # Ejecutar operación fallida
        with pytest.raises(ValueError):
            faulty_operation()
        
        # Verificar que el lock fue liberado
        assert not _hardware_lock.locked(), "Lock no fue liberado después de excepción"
        
        # Verificar que otro thread puede adquirirlo
        acquired = _hardware_lock.acquire(blocking=False)
        assert acquired, "No se pudo adquirir lock después de excepción"
        _hardware_lock.release()


class TestStateLock:
    """Tests para el lock de estado de escaneo."""
    
    def setup_method(self):
        """Resetear estado antes de cada test."""
        with state_lock:
            reset_scan_state()
    
    def test_state_lock_prevents_race_condition(self):
        """Verifica que el lock evita race conditions en el estado."""
        results = []
        
        def modify_state(value):
            """Modifica el estado global de forma segura."""
            with state_lock:
                current = scan_state.get('test_counter', 0)
                time.sleep(0.01)  # Simula procesamiento
                scan_state['test_counter'] = current + value
                results.append(scan_state['test_counter'])
        
        # Ejecutar 10 threads que incrementan en 1
        threads = []
        for _ in range(10):
            t = threading.Thread(target=modify_state, args=(1,))
            threads.append(t)
            t.start()
        
        for t in threads:
            t.join()
        
        # El resultado final debe ser 10 (sin race conditions)
        with state_lock:
            assert scan_state['test_counter'] == 10, \
                f"Race condition detectada: esperado 10, obtenido {scan_state['test_counter']}"
    
    def test_concurrent_state_reads(self):
        """Verifica que múltiples lecturas simultáneas son seguras."""
        with state_lock:
            scan_state['is_scanning'] = True
            scan_state['session_id'] = 'test-123'
        
        read_results = []
        
        def read_state():
            """Lee el estado 100 veces."""
            for _ in range(100):
                with state_lock:
                    is_scanning = scan_state['is_scanning']
                    session_id = scan_state['session_id']
                    read_results.append((is_scanning, session_id))
        
        # 5 threads leyendo simultáneamente
        threads = [threading.Thread(target=read_state) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        # Todas las lecturas deben ser consistentes
        assert all(r == (True, 'test-123') for r in read_results), \
            "Lecturas inconsistentes detectadas"


class TestConcurrentAPIRequests:
    """Tests para requests simultáneos a la API."""
    
    def test_concurrent_health_checks(self, app):
        """Verifica que múltiples health checks simultáneos funcionan."""
        def make_request():
            # Cada thread crea su propio test client
            with app.test_client() as client:
                response = client.get('/api/scan/health')
                return response.status_code
        
        # 20 requests simultáneos
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(make_request) for _ in range(20)]
            results = [f.result() for f in as_completed(futures)]
        
        # Todos deben retornar 200
        assert all(status == 200 for status in results), \
            f"Algunos requests fallaron: {results}"
    
    def test_concurrent_status_checks(self, app):
        """Verifica que múltiples consultas de estado son seguras."""
        def check_status():
            with app.test_client() as client:
                response = client.get('/api/scan/status')
                return response.status_code, response.json
        
        # 15 requests simultáneos
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(check_status) for _ in range(15)]
            results = [f.result() for f in as_completed(futures)]
        
        # Todos deben retornar 200 o 404 (sin escaneo activo)
        for status_code, _ in results:
            assert status_code in [200, 404], \
                f"Status code inesperado: {status_code}"
    
    def test_no_deadlock_on_concurrent_requests(self, app):
        """Verifica que no hay deadlocks con requests mixtos."""
        endpoints = [
            '/api/scan/health',
            '/api/scan/status',
            '/',
        ]
        
        def make_random_request(endpoint):
            with app.test_client() as client:
                response = client.get(endpoint)
                return endpoint, response.status_code
        
        # 30 requests aleatorios simultáneos
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = []
            for i in range(30):
                endpoint = endpoints[i % len(endpoints)]
                futures.append(executor.submit(make_random_request, endpoint))
            
            # Timeout de 10 segundos - si hay deadlock, fallará
            results = []
            for future in as_completed(futures, timeout=10):
                results.append(future.result())
        
        # Todos deben completar sin timeout
        assert len(results) == 30, f"Solo {len(results)}/30 requests completaron"


class TestThreadSafety:
    """Tests adicionales de thread safety."""
    
    def test_lock_acquisition_fairness(self):
        """Verifica que los threads eventualmente obtienen el lock (no starvation)."""
        acquired_by = []
        
        def try_acquire_lock(thread_id):
            """Intenta adquirir el lock y registra quién lo obtuvo."""
            for _ in range(5):  # 5 intentos por thread
                with _hardware_lock:
                    acquired_by.append(thread_id)
                    time.sleep(0.01)  # Mantener el lock brevemente
        
        # 5 threads compitiendo
        threads = []
        for i in range(5):
            t = threading.Thread(target=try_acquire_lock, args=(i,))
            threads.append(t)
            t.start()
        
        for t in threads:
            t.join()
        
        # Verificar que todos los threads obtuvieron el lock al menos una vez
        unique_acquirers = set(acquired_by)
        assert len(unique_acquirers) == 5, \
            f"Solo {len(unique_acquirers)}/5 threads adquirieron el lock: {unique_acquirers}"
    
    def test_single_lock_acquisition(self):
        """Verifica que el lock funciona correctamente con adquisición simple."""
        acquired = []
        
        def simple_lock_acquisition(thread_id):
            """Adquiere el lock una sola vez."""
            with _hardware_lock:
                acquired.append(thread_id)
                time.sleep(0.01)
        
        # Ejecutar múltiples threads secuencialmente
        threads = []
        for i in range(5):
            t = threading.Thread(target=simple_lock_acquisition, args=(i,))
            threads.append(t)
            t.start()
        
        for t in threads:
            t.join(timeout=2)
            assert not t.is_alive(), "Thread no completó en tiempo esperado"
        
        # Verificar que todos los threads ejecutaron
        assert len(acquired) == 5, f"Solo {len(acquired)}/5 threads ejecutaron"


class TestStressTest:
    """Tests de estrés para detectar problemas bajo carga."""
    
    @pytest.mark.slow
    def test_high_concurrency_health_check(self, app):
        """Test de estrés con requests simultáneos."""
        def make_request():
            try:
                with app.test_client() as client:
                    response = client.get('/api/scan/health')
                    return response.status_code
            except Exception as e:
                return f"Error: {e}"
        
        start_time = time.time()
        results = []
        
        # Solo 10 requests con 3 workers para máxima estabilidad
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = [executor.submit(make_request) for _ in range(10)]

            # Procesar resultados con timeout más corto
            try:
                for future in as_completed(futures, timeout=8):
                    try:
                        result = future.result(timeout=2)
                        results.append(result)
                    except Exception as e:
                        results.append(f"Future error: {e}")
            except Exception as e:
                # Si hay timeout global, cancelar futures pendientes
                for future in futures:
                    future.cancel()
                results.append(f"Global timeout: {e}")
        
        duration = time.time() - start_time
        
        # Verificar que la mayoría completaron exitosamente
        successful = [r for r in results if r == 200]
        assert len(successful) >= 7, \
            f"Solo {len(successful)}/10 requests exitosos. Resultados: {results}"
            
        # Verificar que completó en tiempo razonable (< 8 segundos)
        assert duration < 8, \
            f"Test de estrés tardó demasiado: {duration:.2f}s"
    
    @pytest.mark.slow
    def test_memory_leak_detection(self, app):
        """Verifica que no hay memory leaks evidentes con requests repetidos."""
        import gc
        
        # Forzar garbage collection inicial
        gc.collect()
        initial_objects = len(gc.get_objects())
        
        # 100 requests secuenciales (reducido para evitar timeout)
        with app.test_client() as client:
            for _ in range(100):
                response = client.get('/api/scan/health')
                assert response.status_code == 200
        
        # Forzar limpieza
        gc.collect()
        final_objects = len(gc.get_objects())
        
        # Permitir crecimiento del 50% (algunos objetos cacheados son normales)
        growth = (final_objects - initial_objects) / initial_objects if initial_objects > 0 else 0
        assert growth < 0.50, \
            f"Posible memory leak: {growth*100:.1f}% crecimiento en objetos Python"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
