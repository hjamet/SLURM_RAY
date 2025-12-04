import os
import ast
import sys
import pkgutil
import importlib.util
from typing import List, Set, Dict, Tuple
import logging

class ProjectScanner:
    """
    Scans the project for local imports and potential dynamic loading issues.
    """
    
    def __init__(self, project_root: str, logger: logging.Logger = None):
        self.project_root = os.path.abspath(project_root)
        self.logger = logger or logging.getLogger(__name__)
        self.local_modules = set()
        self.dynamic_imports_warnings = []
        
        # Standard library modules to ignore
        self.stdlib_modules = self._get_stdlib_modules()

    def _get_stdlib_modules(self) -> Set[str]:
        """Get a set of standard library module names."""
        stdlib = set(sys.builtin_module_names)
        
        # Add standard library modules from dist-packages/lib-dynload
        for module in pkgutil.iter_modules():
            # This is a heuristic, might include some site-packages if not careful
            # But we primarily filter by checking if file exists locally
            pass
            
        return stdlib

    def is_local_file(self, module_name: str) -> Tuple[bool, str]:
        """
        Check if a module corresponds to a local file in the project.
        Returns (is_local, file_path).
        """
        # Convert module name to path (e.g. my.module -> my/module.py)
        parts = module_name.split('.')
        
        # Check as file
        rel_path_py = os.path.join(*parts) + ".py"
        abs_path_py = os.path.join(self.project_root, rel_path_py)
        
        if os.path.exists(abs_path_py):
            return True, rel_path_py
            
        # Check as package directory
        rel_path_init = os.path.join(*parts, "__init__.py")
        abs_path_init = os.path.join(self.project_root, rel_path_init)
        
        if os.path.exists(abs_path_init):
            return True, os.path.dirname(rel_path_init) # Return dir for package
            
        # Check src/ layout
        rel_path_src_py = os.path.join("src", *parts) + ".py"
        abs_path_src_py = os.path.join(self.project_root, rel_path_src_py)
        
        if os.path.exists(abs_path_src_py):
            return True, "src" # Return src root
            
        rel_path_src_init = os.path.join("src", *parts, "__init__.py")
        abs_path_src_init = os.path.join(self.project_root, rel_path_src_init)
        
        if os.path.exists(abs_path_src_init):
            return True, "src"
            
        return False, None

    def scan_file(self, file_path: str) -> Set[str]:
        """
        Scan a python file for imports and dynamic loading patterns.
        Returns a set of detected local dependencies (relative paths).
        """
        dependencies = set()
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                
            tree = ast.parse(content, filename=file_path)
            
            for node in ast.walk(tree):
                # 1. Static Imports
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        is_local, path = self.is_local_file(alias.name)
                        if is_local:
                            dependencies.add(path)
                            
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        # from module import ...
                        is_local, path = self.is_local_file(node.module)
                        if is_local:
                            dependencies.add(path)
                    elif node.level > 0:
                        # Relative import (from . import ...)
                        # Just mark the current directory structure as needed
                        pass

                # 2. Dynamic Imports & File Operations Warnings
                elif isinstance(node, ast.Call):
                    if isinstance(node.func, ast.Attribute):
                        # importlib.import_module(...)
                        if node.func.attr == 'import_module' and isinstance(node.func.value, ast.Name) and node.func.value.id == 'importlib':
                            self._add_warning(file_path, node.lineno, "importlib.import_module usage detected")
                        
                    elif isinstance(node.func, ast.Name):
                        # __import__(...)
                        if node.func.id == '__import__':
                            self._add_warning(file_path, node.lineno, "__import__ usage detected")
                        # open(...)
                        elif node.func.id == 'open':
                            # Check if argument is a string literal
                            if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                                path_arg = node.args[0].value
                                # Warn if it looks like a path to a file that might be missing
                                if not os.path.isabs(path_arg) and not path_arg.startswith('/'):
                                    self._add_warning(file_path, node.lineno, f"open('{path_arg}') detected. Ensure this file is in 'files' list if needed.")
                            else:
                                self._add_warning(file_path, node.lineno, "open() with dynamic path detected")
                                
        except Exception as e:
            self.logger.debug(f"Failed to scan {file_path}: {e}")
            
        return dependencies

    def _add_warning(self, file_path: str, lineno: int, message: str):
        rel_path = os.path.relpath(file_path, self.project_root)
        self.dynamic_imports_warnings.append(f"{rel_path}:{lineno}: {message}")

    def auto_detect_dependencies(self) -> List[str]:
        """
        Recursively scan the project for python files and their dependencies.
        Start by scanning all python files in the project root and src/ folder.
        """
        detected_files = set()
        
        # Simple strategy: scan ALL python files in the project (excluding venv, git, etc)
        # This is safer than trying to follow import graph from an unknown entry point
        for root, dirs, files in os.walk(self.project_root):
            # Skip common ignored directories
            dirs[:] = [d for d in dirs if d not in {'.git', '.venv', 'venv', '__pycache__', '.idea', '.vscode', 'site-packages', 'node_modules', 'wandb'}]
            
            for file in files:
                if file.endswith('.py'):
                    full_path = os.path.join(root, file)
                    
                    # Scan file for imports and warnings
                    deps = self.scan_file(full_path)
                    detected_files.update(deps)
                    
        return list(detected_files)

