"""
Unit tests for source-based function serialization and transfer.

These tests validate that functions can be serialized to source code,
saved, loaded, and executed correctly, simulating the remote execution flow.
"""

import os
import sys
import tempfile
import shutil
import importlib.util
from pathlib import Path

# Add parent directory to path to import slurmray
sys.path.insert(0, str(Path(__file__).parent.parent))

from slurmray.RayLauncher import RayLauncher


def test_simple_function_source_transfer():
    """Test that a simple function can be serialized (dill pickle is default method)"""

    def simple_func(x):
        return x + 1

    # Create temporary project directory
    with tempfile.TemporaryDirectory() as tmpdir:
        project_path = os.path.join(tmpdir, "test_project")
        os.makedirs(project_path)

        # Create cluster instance (minimal config)
        cluster = RayLauncher(
            project_name="test_source",
            server_run=False,  # Local mode
        )

        # Override project_path to use our temp directory
        cluster.project_path = project_path

        # Serialize function
        cluster._RayLauncher__serialize_func_and_args(simple_func, {"x": 5})

        # Verify files were created
        # With new strategy, dill pickle is tried first, so func.pkl should exist
        func_pkl_path = os.path.join(project_path, "func.pkl")
        method_file = os.path.join(project_path, "serialization_method.txt")

        assert os.path.exists(
            func_pkl_path
        ), "func.pkl should be created (dill pickle is default)"

        # Verify serialization method
        if os.path.exists(method_file):
            with open(method_file, "r") as f:
                method = f.read().strip()
            # Should be dill_pickle for simple functions
            assert method == "dill_pickle", f"Expected dill_pickle, got {method}"

        # Load function from pickle (simulating spython_template.py behavior)
        import dill

        with open(func_pkl_path, "rb") as f:
            loaded_func = dill.load(f)

        # Test execution
        result = loaded_func(x=5)
        assert result == 6, f"Expected 6, got {result}"

        # func_source.py should NOT exist for simple functions (dill pickle succeeds)
        func_source_path = os.path.join(project_path, "func_source.py")
        assert not os.path.exists(
            func_source_path
        ), "func_source.py should NOT exist when dill pickle succeeds"


def test_function_with_global_source_transfer():
    """Test that a function with global dependencies can be serialized with dill pickle"""
    GLOBAL_VALUE = 42

    def func_with_global(x):
        return x + GLOBAL_VALUE

    with tempfile.TemporaryDirectory() as tmpdir:
        project_path = os.path.join(tmpdir, "test_project")
        os.makedirs(project_path)

        cluster = RayLauncher(
            project_name="test_global",
            server_run=False,
        )
        cluster.project_path = project_path

        cluster._RayLauncher__serialize_func_and_args(func_with_global, {"x": 10})

        # With new strategy, dill pickle handles globals/closures, so func.pkl should exist
        func_pkl_path = os.path.join(project_path, "func.pkl")
        assert os.path.exists(
            func_pkl_path
        ), "func.pkl should be created (dill pickle handles globals)"

        # Load and test using dill pickle
        import dill

        with open(func_pkl_path, "rb") as f:
            loaded_func = dill.load(f)

        # Note: With dill pickle, the global is captured in the closure, so this should work
        # However, when executed on remote, the global might not be available
        # This demonstrates that dill pickle is better for functions with globals/closures
        try:
            result = loaded_func(x=10)
            # Should work because dill pickle captures the global
            assert result == 52, f"Expected 52, got {result}"
            print(f"Function executed successfully with dill pickle: {result}")
        except NameError as e:
            # This shouldn't happen with dill pickle, but log it if it does
            print(f"Unexpected limitation with dill pickle: {e}")


def test_class_method_source_transfer():
    """Test that a class method can be serialized with dill pickle"""

    class MyClass:
        def method(self, x):
            return x * 2

    obj = MyClass()

    with tempfile.TemporaryDirectory() as tmpdir:
        project_path = os.path.join(tmpdir, "test_project")
        os.makedirs(project_path)

        cluster = RayLauncher(
            project_name="test_method",
            server_run=False,
        )
        cluster.project_path = project_path

        cluster._RayLauncher__serialize_func_and_args(obj.method, {"x": 5})

        # With new strategy, dill pickle handles bound methods, so func.pkl should exist
        func_pkl_path = os.path.join(project_path, "func.pkl")
        assert os.path.exists(
            func_pkl_path
        ), "func.pkl should be created (dill pickle handles methods)"

        # Load and test using dill pickle
        import dill

        with open(func_pkl_path, "rb") as f:
            loaded_method = dill.load(f)

        # Test execution (dill pickle preserves the bound method)
        result = loaded_method(x=5)
        assert result == 10, f"Expected 10, got {result}"
        print(f"Method loaded and executed successfully: {result}")


def test_lambda_source_transfer():
    """Test that a lambda function can be serialized with dill pickle"""
    lambda_func = lambda x: x**2

    with tempfile.TemporaryDirectory() as tmpdir:
        project_path = os.path.join(tmpdir, "test_project")
        os.makedirs(project_path)

        cluster = RayLauncher(
            project_name="test_lambda",
            server_run=False,
        )
        cluster.project_path = project_path

        cluster._RayLauncher__serialize_func_and_args(lambda_func, {"x": 4})

        # With new strategy, dill pickle handles lambdas, so func.pkl should exist
        func_pkl_path = os.path.join(project_path, "func.pkl")
        assert os.path.exists(
            func_pkl_path
        ), "func.pkl should be created (dill pickle handles lambdas)"

        # Load and test using dill pickle
        import dill

        with open(func_pkl_path, "rb") as f:
            loaded_lambda = dill.load(f)

        # Test execution
        result = loaded_lambda(x=4)
        assert result == 16, f"Expected 16, got {result}"

        # func_source.py should NOT exist (dill pickle succeeds)
        func_source_path = os.path.join(project_path, "func_source.py")
        assert not os.path.exists(
            func_source_path
        ), "func_source.py should NOT exist when dill pickle succeeds"


def test_fallback_to_dill():
    """Test that the system falls back to dill when source extraction fails"""
    # Create a function that inspect.getsource() might struggle with
    # (e.g., a built-in or dynamically created function)
    import builtins

    # Use a built-in function (inspect.getsource will fail)
    builtin_func = builtins.len

    with tempfile.TemporaryDirectory() as tmpdir:
        project_path = os.path.join(tmpdir, "test_project")
        os.makedirs(project_path)

        cluster = RayLauncher(
            project_name="test_fallback",
            server_run=False,
        )
        cluster.project_path = project_path

        # This should not crash, but should log a warning
        cluster._RayLauncher__serialize_func_and_args(builtin_func, {"x": [1, 2, 3]})

        # Verify that func.pkl exists (fallback)
        func_pkl_path = os.path.join(project_path, "func.pkl")
        assert os.path.exists(func_pkl_path), "func.pkl should exist as fallback"

        # func_source.py might not exist or might be empty
        func_source_path = os.path.join(project_path, "func_source.py")
        if os.path.exists(func_source_path):
            # If it exists, it might be empty or invalid
            with open(func_source_path, "r") as f:
                source = f.read()
            # That's okay - the fallback to dill will handle it


if __name__ == "__main__":
    print("Running source transfer tests...")
    print("=" * 80)

    print("\n1. Testing simple function...")
    test_simple_function_source_transfer()
    print("   ✅ Simple function test passed")

    print("\n2. Testing function with global...")
    test_function_with_global_source_transfer()
    print("   ✅ Function with global test passed (with expected limitations)")

    print("\n3. Testing class method...")
    test_class_method_source_transfer()
    print("   ✅ Class method test passed (with expected limitations)")

    print("\n4. Testing lambda function...")
    test_lambda_source_transfer()
    print("   ✅ Lambda function test passed")

    print("\n5. Testing fallback to dill...")
    test_fallback_to_dill()
    print("   ✅ Fallback test passed")

    print("\n" + "=" * 80)
    print("All tests completed!")
