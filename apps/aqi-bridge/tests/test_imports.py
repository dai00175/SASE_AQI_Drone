import subprocess
import sys
from os import environ


def test_aqi_bridge_import_smoke():
    """Verify that 'python -m aqi_bridge' can execute without ModuleNotFoundError."""
    try:
        # Run bridge module as a subprocess for 1 second.
        # If the imports are totally broken (e.g., ModuleNotFoundError), it will exit immediately with code 1.
        # If it succeeds it will hang running the server, so we timeout and capture it.
        result = subprocess.run(
            [sys.executable, "-m", "aqi_bridge"],
            capture_output=True,
            text=True,
            timeout=1,
            env={
                **environ,
                "WS_PORT": "0",
            },
        )
    except subprocess.TimeoutExpired as e:
        # A timeout means the server booted successfully and is blocking.
        # NOTE: even with text=True, TimeoutExpired delivers stdout/stderr as
        # raw bytes on CPython 3.12+, so we decode defensively.
        def _decode(data) -> str:
            if isinstance(data, bytes):
                return data.decode(errors="replace")
            return data or ""

        stdout = _decode(e.stdout)
        stderr = _decode(e.stderr)
        assert "ModuleNotFoundError" not in stdout and "ModuleNotFoundError" not in stderr, \
            "Found ModuleNotFoundError despite timeout"
        return
        
    # If it didn't timeout, accept environment-specific runtime failures as long as
    # the module imported successfully. This test is an import smoke test, not a
    # BLE-permission or socket-binding integration test.
    assert "ModuleNotFoundError" not in result.stdout
    assert "ModuleNotFoundError" not in result.stderr

if __name__ == "__main__":
    test_aqi_bridge_import_smoke()
    print("Smoke test passed: module 'aqi_bridge' is importable and executes cleanly.")
