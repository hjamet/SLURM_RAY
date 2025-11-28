"""
Test script to explore limits of inspect.getsource() and dill.source
for function serialization across Python versions.
"""
import inspect
import dill
import os
import sys

# Test 1: Simple function
def simple_func(x):
    return x + 1

# Test 2: Function with closure
def outer_func(y):
    def inner_func(x):
        return x + y
    return inner_func

closure_func = outer_func(10)

# Test 3: Function with global dependency
GLOBAL_VAR = 42

def func_with_global(x):
    return x + GLOBAL_VAR

# Test 4: Function defined inside a class
class MyClass:
    def method(self, x):
        return x * 2
    
    @staticmethod
    def static_method(x):
        return x + 5

# Test 5: Function with nested function
def outer_with_nested(x):
    def nested(y):
        return x * y
    return nested(2)

# Test 6: Lambda function
lambda_func = lambda x: x ** 2

# Test 7: Function with imports inside
def func_with_imports(x):
    import math
    return math.sqrt(x)

def test_inspect_getsource(func, name):
    """Test inspect.getsource() on a function"""
    print(f"\n=== Testing {name} with inspect.getsource() ===")
    try:
        source = inspect.getsource(func)
        print(f"✅ Success: Got {len(source)} characters")
        print(f"Source preview: {source[:100]}...")
        
        # Test deduplication logic (from RayLauncher)
        lines = source.split('\n')
        if lines:
            first_line = lines[0]
            indent = len(first_line) - len(first_line.lstrip())
            deduplicated = '\n'.join([line[indent:] for line in lines])
            print(f"Deduplicated preview: {deduplicated[:100]}...")
        
        return True, source
    except Exception as e:
        print(f"❌ Failed: {e}")
        return False, None

def test_dill_source(func, name):
    """Test dill.source.getsource() on a function"""
    print(f"\n=== Testing {name} with dill.source.getsource() ===")
    try:
        if hasattr(dill, 'source'):
            source = dill.source.getsource(func)
            print(f"✅ Success: Got {len(source)} characters")
            print(f"Source preview: {source[:100]}...")
            return True, source
        else:
            print("⚠️ dill.source not available")
            return False, None
    except Exception as e:
        print(f"❌ Failed: {e}")
        return False, None

def test_dill_getsource(func, name):
    """Test dill.detect.getsource() on a function"""
    print(f"\n=== Testing {name} with dill.detect.getsource() ===")
    try:
        if hasattr(dill, 'detect') and hasattr(dill.detect, 'getsource'):
            source = dill.detect.getsource(func)
            print(f"✅ Success: Got {len(source)} characters")
            print(f"Source preview: {source[:100]}...")
            return True, source
        else:
            print("⚠️ dill.detect.getsource not available")
            return False, None
    except Exception as e:
        print(f"❌ Failed: {e}")
        return False, None

def main():
    print("=" * 80)
    print("Testing function source extraction methods")
    print("=" * 80)
    
    tests = [
        (simple_func, "simple_func"),
        (closure_func, "closure_func (from closure)"),
        (func_with_global, "func_with_global"),
        (MyClass.method, "MyClass.method"),
        (MyClass.static_method, "MyClass.static_method"),
        (lambda_func, "lambda_func"),
        (func_with_imports, "func_with_imports"),
    ]
    
    results = {}
    
    for func, name in tests:
        print(f"\n{'='*80}")
        print(f"Testing: {name}")
        print(f"{'='*80}")
        
        inspect_ok, inspect_source = test_inspect_getsource(func, name)
        dill_source_ok, dill_source = test_dill_source(func, name)
        dill_detect_ok, dill_detect_source = test_dill_getsource(func, name)
        
        results[name] = {
            'inspect': inspect_ok,
            'dill.source': dill_source_ok,
            'dill.detect': dill_detect_ok,
        }
    
    # Summary
    print(f"\n{'='*80}")
    print("SUMMARY")
    print(f"{'='*80}")
    print(f"{'Function':<30} {'inspect':<10} {'dill.source':<12} {'dill.detect':<12}")
    print("-" * 80)
    for name, result in results.items():
        inspect_str = "✅" if result['inspect'] else "❌"
        dill_source_str = "✅" if result['dill.source'] else "❌"
        dill_detect_str = "✅" if result['dill.detect'] else "❌"
        print(f"{name:<30} {inspect_str:<10} {dill_source_str:<12} {dill_detect_str:<12}")
    
    # Check dill version
    print(f"\nDill version: {dill.__version__}")
    print(f"Python version: {sys.version}")

if __name__ == "__main__":
    main()

