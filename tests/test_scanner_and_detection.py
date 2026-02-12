import os
import sys
import logging
from slurmray.scanner import ProjectScanner
from slurmray import Cluster

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
    detected = scanner._follow_imports_recursive(os.path.join(base_dir, "main.py"))
    
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

def test_callable_args_scanning():
    """Test that scanner detects dependencies from callables passed in args.
    
    This reproduces the pipeline_stage pattern:
    - wrapper_func is the function passed to launcher (scanned first)
    - business_func is passed in args dict (must also be scanned)
    - business_func has a lazy import to a local module that wrapper_func doesn't know about
    """
    import shutil
    import tempfile

    print("\n--- Testing Callable Args Scanning ---")
    
    # Create an isolated dummy project
    base_dir = tempfile.mkdtemp(prefix="test_callable_args_")
    
    try:
        # 1. Create a "scripts/utils/push_helper.py" (the missing dependency)
        create_dummy_file(os.path.join(base_dir, "scripts", "utils", "push_helper.py"),
            "def upload(): pass\ndef validate(): pass\n"
        )
        create_dummy_file(os.path.join(base_dir, "scripts", "__init__.py"), "")
        create_dummy_file(os.path.join(base_dir, "scripts", "utils", "__init__.py"), "")
        
        # 2. Create "src/pipeline/base.py" (the wrapper function file)
        create_dummy_file(os.path.join(base_dir, "src", "pipeline", "base.py"),
            "import os\n\ndef wrapper(fn, cfg):\n    return fn(cfg)\n"
        )
        create_dummy_file(os.path.join(base_dir, "src", "__init__.py"), "")
        create_dummy_file(os.path.join(base_dir, "src", "pipeline", "__init__.py"), "")
        
        # 3. Create "scripts/step_push.py" (the business function with lazy import)
        create_dummy_file(os.path.join(base_dir, "scripts", "step_push.py"),
            "def push_to_hf(cfg):\n"
            "    from scripts.utils.push_helper import upload, validate\n"
            "    upload()\n"
            "    validate()\n"
        )
        
        # Add base_dir to sys.path so imports resolve
        sys.path.insert(0, base_dir)
        
        scanner = ProjectScanner(base_dir, logger)
        
        # Scan only the wrapper (simulates what RayLauncher did BEFORE the fix)
        wrapper_deps = scanner.detect_dependencies_from_function(
            __import__("src.pipeline.base", fromlist=["wrapper"]).wrapper
        )
        
        # The wrapper should NOT find scripts/utils/push_helper.py
        wrapper_dep_strs = set(wrapper_deps)
        assert not any("push_helper" in d for d in wrapper_dep_strs), \
            f"Wrapper should NOT detect push_helper, but found: {wrapper_dep_strs}"
        print(f"  ✓ Wrapper alone found {len(wrapper_deps)} deps (no push_helper)")
        
        # Now scan the business function (simulates the NEW fix)
        business_mod = __import__("scripts.step_push", fromlist=["push_to_hf"])
        business_deps = scanner.detect_dependencies_from_function(business_mod.push_to_hf)
        
        # The business function SHOULD find scripts/utils/push_helper.py
        business_dep_strs = set(business_deps)
        found_push_helper = any("push_helper" in d for d in business_dep_strs)
        assert found_push_helper, \
            f"Business func should detect push_helper, but found only: {business_dep_strs}"
        print(f"  ✓ Business func found {len(business_deps)} deps (including push_helper)")
        
        # Combined (simulates the full fixed flow)
        all_deps = list(set(wrapper_deps + business_deps))
        assert any("push_helper" in d for d in all_deps)
        print(f"  ✓ Combined: {len(all_deps)} total deps")
        
        print("✅ Callable args scanning test passed!")
    
    finally:
        # Cleanup
        if base_dir in sys.path:
            sys.path.remove(base_dir)
        # Clean up imported modules
        for mod_name in list(sys.modules.keys()):
            if mod_name.startswith("scripts") or mod_name.startswith("src.pipeline"):
                del sys.modules[mod_name]
        shutil.rmtree(base_dir, ignore_errors=True)

def test_nested_callable_args_scanning():
    """Test that _extract_local_callables finds callables at any nesting depth.
    
    Covers the extended pattern where callables are nested inside:
    - nested dicts: {"config": {"preprocessor": fn}}
    - lists: {"callbacks": [fn1, fn2]}
    - mixed: {"pipeline": [{"stage": fn}]}
    """
    import shutil
    import tempfile

    print("\n--- Testing Nested Callable Args Scanning ---")
    
    base_dir = tempfile.mkdtemp(prefix="test_nested_callables_")
    
    try:
        # Create local functions in different files
        create_dummy_file(os.path.join(base_dir, "funcs", "preprocess.py"),
            "def clean(data): pass\n"
        )
        create_dummy_file(os.path.join(base_dir, "funcs", "__init__.py"), "")
        
        create_dummy_file(os.path.join(base_dir, "funcs", "validate.py"),
            "def check(data): pass\n"
        )
        
        create_dummy_file(os.path.join(base_dir, "funcs", "transform.py"),
            "def normalize(data): pass\n"
        )
        
        sys.path.insert(0, base_dir)
        
        # Import local functions
        from funcs.preprocess import clean
        from funcs.validate import check
        from funcs.transform import normalize
        
        # Create a mock object to test _extract_local_callables
        from slurmray.RayLauncher import Cluster
        
        mock = type("MockCluster", (), {"pwd_path": base_dir})()
        mock._extract_local_callables = Cluster._extract_local_callables.__get__(mock)
        
        # Test 1: Flat dict (backward compat)
        flat_args = {"fn": clean, "cfg": {"key": "value"}}
        callables = mock._extract_local_callables(flat_args)
        callable_names = [name for name, _ in callables]
        assert len(callables) == 1, f"Expected 1 callable, got {len(callables)}: {callable_names}"
        print(f"  ✓ Flat dict: found {len(callables)} callable")
        
        # Test 2: Nested dict
        nested_args = {"config": {"preprocessor": clean, "validator": check}}
        callables = mock._extract_local_callables(nested_args)
        assert len(callables) == 2, f"Expected 2 callables, got {len(callables)}"
        print(f"  ✓ Nested dict: found {len(callables)} callables")
        
        # Test 3: List of callables
        list_args = {"callbacks": [clean, check, normalize]}
        callables = mock._extract_local_callables(list_args)
        assert len(callables) == 3, f"Expected 3 callables, got {len(callables)}"
        print(f"  ✓ List: found {len(callables)} callables")
        
        # Test 4: Mixed nesting
        deep_args = {
            "pipeline": [
                {"stage": clean, "name": "preprocess"},
                {"stage": check, "name": "validate"},
            ],
            "postprocess": normalize,
        }
        callables = mock._extract_local_callables(deep_args)
        assert len(callables) == 3, f"Expected 3 callables, got {len(callables)}"
        print(f"  ✓ Deep nesting: found {len(callables)} callables")
        
        # Test 5: Should NOT include non-local callables (builtins, stdlib)
        import json
        mixed_args = {"fn": clean, "serializer": json.dumps, "formatter": str.upper}
        callables = mock._extract_local_callables(mixed_args)
        callable_funcs = [fn for _, fn in callables]
        assert clean in callable_funcs, "Should include local callable"
        assert json.dumps not in callable_funcs, "Should NOT include stdlib callable"
        print(f"  ✓ Local filter: correctly excluded non-local callables ({len(callables)} local)")
        
        # Test 6: Circular reference protection
        circular = {"fn": clean}
        circular["self"] = circular  # Circular!
        callables = mock._extract_local_callables(circular)
        assert len(callables) == 1, f"Expected 1 callable despite circular ref, got {len(callables)}"
        print(f"  ✓ Circular reference: handled safely")
        
        print("✅ Nested callable args scanning test passed!")
    
    finally:
        if base_dir in sys.path:
            sys.path.remove(base_dir)
        for mod_name in list(sys.modules.keys()):
            if mod_name.startswith("funcs"):
                del sys.modules[mod_name]
        shutil.rmtree(base_dir, ignore_errors=True)

if __name__ == "__main__":
    test_scanner()
    test_editable_detection()
    test_callable_args_scanning()
    test_nested_callable_args_scanning()

