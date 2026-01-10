
import sys
import os
sys.path.insert(0, os.path.abspath("."))

import shutil
import logging
from slurmray.scanner import ProjectScanner

# Setup logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("test_reproduce_filescope")

def create_dummy_file(path, content=""):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(content)

def test_readme_detection():
    print("\n--- Testing README.md Detection Reproduction ---")
    
    base_dir = "tests/dummy_filescope"
    if os.path.exists(base_dir):
        shutil.rmtree(base_dir)
    os.makedirs(base_dir)
    
    # 1. Create a Python file referencing README.md
    main_script_path = f"{base_dir}/main.py"
    create_dummy_file(main_script_path, """
import os

def run():
    # Trigger case mentioned by user
    readme = "README.md"
    path = os.path.join("utils", "README.md")
    
    # Also a normal python file
    script = "utils/helper.py"
    
    # Shell script
    shell = "scripts/run.sh"
    
    # Json config
    config = "config.json"
""")
    
    # 2. Create the referenced files
    create_dummy_file(f"{base_dir}/README.md", "# Root Readme")
    create_dummy_file(f"{base_dir}/utils/README.md", "# Utils Readme")
    create_dummy_file(f"{base_dir}/utils/helper.py", "print('helper')")
    create_dummy_file(f"{base_dir}/scripts/run.sh", "#!/bin/bash")
    create_dummy_file(f"{base_dir}/config.json", "{}")
    
    # 3. Setup Scanner
    original_cwd = os.getcwd()
    os.chdir(base_dir)
    
    try:
        scanner = ProjectScanner(".", logger)
        dependencies = scanner.scan_file("main.py")
        
        print(f"Detected dependencies: {dependencies}")
        
        # Check assertions
        if "README.md" in dependencies or "utils/README.md" in dependencies:
            print("❌ REPRODUCED: README.md was detected!")
        else:
            print("✅ NOT REPRODUCED: README.md was correctly ignored.")
            
        # Verify helper.py IS detected
        if "utils/helper.py" in dependencies:
            print("✅ helper.py was detected (normal behavior).")
        else:
            print("❌ FAILURE: helper.py was NOT detected.")
            
        # Check Shell
        if "scripts/run.sh" in dependencies:
            print("❌ FAILURE: run.sh was detected (should be ignored).")
        else:
            print("✅ run.sh was correctly ignored (strict .py only).")
            
        # Check JSON
        if "config.json" in dependencies:
            print("❌ FAILURE: config.json was detected (should be ignored).")
        else:
            print("✅ config.json was correctly ignored (strict .py only).")
            
    finally:
        os.chdir(original_cwd)
        if os.path.exists(base_dir):
            shutil.rmtree(base_dir)

if __name__ == "__main__":
    test_readme_detection()
