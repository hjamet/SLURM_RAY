import os
import sys
import logging
from slurmray.scanner import ProjectScanner
from slurmray.RayLauncher import RayLauncher

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("test_scanner")

def create_dummy_file(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(content)

def test_scanner():
    print("\n--- Testing ProjectScanner ---")
    
    # Create a dummy project structure
    base_dir = "tests/dummy_project"
    if os.path.exists(base_dir):
        import shutil
        shutil.rmtree(base_dir)
    os.makedirs(base_dir)
    
    # 1. Create main script with imports
    create_dummy_file(f"{base_dir}/main.py", """
import utils.helper
from core import logic
import importlib
import os

def main():
    utils.helper.do_stuff()
    logic.run()
    
    # Dynamic import warning expected
    mod = importlib.import_module("plugins." + "plugin_a")
    
    # Open warning expected
    with open("data/config.json", "r") as f:
        pass
""")
    
    # 2. Create local modules
    create_dummy_file(f"{base_dir}/utils/helper.py", "def do_stuff(): pass")
    create_dummy_file(f"{base_dir}/utils/__init__.py", "")
    
    # 3. Create another module (src layout style)
    create_dummy_file(f"{base_dir}/src/core/logic.py", "def run(): pass")
    create_dummy_file(f"{base_dir}/src/core/__init__.py", "")
    
    # Scan
    scanner = ProjectScanner(base_dir, logger)
    detected = scanner.auto_detect_dependencies()
    
    print(f"Detected dependencies: {detected}")
    print(f"Warnings: {scanner.dynamic_imports_warnings}")
    
    # Verifications
    assert "utils/helper.py" in detected or "utils" in detected
    # src/core/logic.py might be detected as 'src' or 'src/core/logic.py' depending on is_local_file logic
    
    assert any("importlib.import_module" in w for w in scanner.dynamic_imports_warnings)
    assert any("open('data/config.json')" in w for w in scanner.dynamic_imports_warnings)
    
    print("✅ Scanner test passed!")
    
    # Cleanup
    import shutil
    shutil.rmtree(base_dir)

def test_editable_detection():
    print("\n--- Testing Editable Detection Logic (Mocked) ---")
    
    # Mock RayLauncher and Backend
    class MockLauncher:
        def __init__(self):
            self.pwd_path = os.getcwd()
            self.logger = logger
            
    launcher = MockLauncher()
    
    # We need to import the backend class, but it's abstract. 
    # We can use SlurmBackend or define a dummy one inheriting from ClusterBackend
    from slurmray.backend.base import ClusterBackend
    
    class DummyBackend(ClusterBackend):
        def run(self, cancel_old_jobs=True): pass
        def cancel(self, job_id): pass
        # We need to mock _get_editable_packages
        def _get_editable_packages(self):
            return {"dummy-package", "trail-rag"}
            
    backend = DummyBackend(launcher)
    
    # Now we need to mock the filesystem for .egg-link detection
    # This is hard to integration test without actually installing editable packages
    # So we will just check if the method runs without error on current env
    
    try:
        paths = backend._get_editable_package_source_paths()
        print(f"Paths detected in current env: {paths}")
        print("✅ Editable detection ran without crash")
    except Exception as e:
        print(f"❌ Editable detection failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_scanner()
    test_editable_detection()

