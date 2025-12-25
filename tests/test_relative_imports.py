import os
import shutil
import pytest
import logging
from slurmray.scanner import ProjectScanner

# Setup logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("test_relative_imports")

def create_dummy_file(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(content)

@pytest.fixture
def dummy_project(tmp_path):
    """Creates a dummy project structure with relative imports."""
    base_dir = tmp_path / "relative_import_project"
    base_dir.mkdir()
    
    # Create package structure
    # src/trail_rag/utils/logging/
    #   logger.py          <-- Main logger
    #   log_formatters.py  <-- Dependency
    #   log_sampler.py     <-- Dependency
    
    (base_dir / "src" / "trail_rag" / "utils" / "logging").mkdir(parents=True)
    (base_dir / "src" / "trail_rag" / "__init__.py").touch()
    (base_dir / "src" / "trail_rag" / "utils" / "__init__.py").touch()
    (base_dir / "src" / "trail_rag" / "utils" / "logging" / "__init__.py").touch()
    
    create_dummy_file(
        base_dir / "src/trail_rag/utils/logging/log_formatters.py", 
        "class ColoredFormatter: pass\nclass JsonFormatter: pass"
    )
    create_dummy_file(
        base_dir / "src/trail_rag/utils/logging/log_sampler.py", 
        "class LogSampler: pass"
    )
    
    create_dummy_file(
        base_dir / "src/trail_rag/utils/logging/logger.py", 
        """
from .log_formatters import ColoredFormatter, JsonFormatter
from .log_sampler import LogSampler

class Logger:
    def __init__(self):
        self.formatter = ColoredFormatter()
        self.sampler = LogSampler()
"""
    )
    
    return str(base_dir)

def test_relative_import_tracing(dummy_project):
    """Verifies that the scanner correctly identifies relative imports as dependencies."""
    scanner = ProjectScanner(dummy_project, logger)
    
    logger_file = os.path.join(dummy_project, "src/trail_rag/utils/logging/logger.py")
    dependencies = scanner.scan_file(logger_file)
    
    print(f"Detected dependencies: {dependencies}")
    
    expected = {
        "src/trail_rag/utils/logging/log_formatters.py",
        "src/trail_rag/utils/logging/log_sampler.py"
    }
    
    # Check if expected dependencies are in the detected set
    # Using set comparison to be robust
    assert expected.issubset(dependencies), f"Missing dependencies: {expected - dependencies}"

if __name__ == "__main__":
    # Allow running this test directly
    pytest.main([__file__])
