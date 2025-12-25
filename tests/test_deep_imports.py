
import os
import shutil
import pytest
import sys
from slurmray.scanner import ProjectScanner

def create_file(path, content=""):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(content)

@pytest.fixture
def repro_env(tmp_path):
    root = tmp_path / "repro_env"
    root.mkdir()
    
    # Mimic trail-rag structure
    # src/trail_rag/evaluation/datasets/dataset_manager.py
    create_file(root / "src/trail_rag/__init__.py")
    create_file(root / "src/trail_rag/evaluation/__init__.py")
    create_file(root / "src/trail_rag/evaluation/datasets/__init__.py")
    create_file(root / "src/trail_rag/evaluation/datasets/dataset_manager.py", "def load(): print('hello')")
    
    # main.py that triggers the import
    create_file(root / "main.py", "from trail_rag.evaluation.datasets import dataset_manager\ndataset_manager.load()")
    
    return root

def test_deep_import_detection(repro_env):
    root_str = str(repro_env)
    target = os.path.join(root_str, "main.py")
    
    scanner = ProjectScanner(root_str)
    dependencies = scanner._follow_imports_recursive(target)
    
    expected = "src/trail_rag/evaluation/datasets/dataset_manager.py"
    assert expected in dependencies

def test_relative_deep_import_detection(tmp_path):
    root = tmp_path / "pkg_env"
    root.mkdir()
    
    # Structure:
    # pkg/
    #   __init__.py
    #   sub/
    #     __init__.py
    #     mod.py  <-- from . import sibling
    #     sibling.py
    
    create_file(root / "pkg/__init__.py")
    create_file(root / "pkg/sub/__init__.py")
    create_file(root / "pkg/sub/mod.py", "from . import sibling")
    create_file(root / "pkg/sub/sibling.py", "X = 1")
    
    scanner = ProjectScanner(str(root))
    dependencies = scanner._follow_imports_recursive(str(root / "pkg/sub/mod.py"))
    
    assert "pkg/sub/sibling.py" in dependencies

def test_from_module_import_multiple_names(tmp_path):
    root = tmp_path / "multi_env"
    root.mkdir()
    
    # Structure:
    # pkg/
    #   __init__.py
    #   a.py
    #   b.py
    # main.py: from pkg import a, b
    
    create_file(root / "pkg/__init__.py")
    create_file(root / "pkg/a.py", "A = 1")
    create_file(root / "pkg/b.py", "B = 1")
    create_file(root / "main.py", "from pkg import a, b")
    
    scanner = ProjectScanner(str(root))
    dependencies = scanner._follow_imports_recursive(str(root / "main.py"))
    
    assert "pkg/a.py" in dependencies
    assert "pkg/b.py" in dependencies
