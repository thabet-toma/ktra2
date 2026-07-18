import subprocess
import sys


def test_logging_config_starts_and_stops_cleanly():
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import logging; import logging.config; "
                "from core.settings import LOGGING; "
                "logging.config.dictConfig(LOGGING); "
                "logging.getLogger('core.health').info('logging-ready'); "
                "logging.shutdown()"
            ),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "logging-ready" in result.stderr
