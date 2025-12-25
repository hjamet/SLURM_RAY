import os
import ast
import sys
import pkgutil
import importlib.util
import site
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

    def _is_system_or_venv_file(self, file_path: str) -> bool:
        """
        Check if a file belongs to system or venv (installed package or stdlib).
        Uses site.getsitepackages() and sys.prefix for robust detection.
        """
        file_abs = os.path.abspath(file_path)

        # 1. Check against site-packages directories (primary method for installed packages)
        site_packages_dirs = site.getsitepackages()
        if hasattr(site, "getusersitepackages"):
            user_site = site.getusersitepackages()
            if user_site:
                site_packages_dirs = list(site_packages_dirs) + [user_site]

        for site_pkg_dir in site_packages_dirs:
            if file_abs.startswith(os.path.abspath(site_pkg_dir)):
                return True

        # 2. Check against sys.prefix/base_prefix (for standard library and venv files)
        # We verify subdirectories like 'lib', 'include' to avoid matching the project root
        # if the project is located directly in the prefix (unlikely but possible)
        prefixes = [sys.prefix]
        if hasattr(sys, "base_prefix") and sys.base_prefix != sys.prefix:
            prefixes.append(sys.base_prefix)

        # Common system directories to exclude
        system_dirs = ["lib", "include", "bin", "Scripts", "Library", "DLLs", "Lib"]

        for prefix in prefixes:
            prefix_abs = os.path.abspath(prefix)
            if file_abs.startswith(prefix_abs):
                # Check if it's in a system subdirectory
                for sys_dir in system_dirs:
                    sys_dir_abs = os.path.join(prefix_abs, sys_dir)
                    if file_abs.startswith(sys_dir_abs):
                        return True

        return False

    def is_local_file(self, module_name: str) -> Tuple[bool, str]:
        """
        Check if a module corresponds to a local file in the project.
        Uses Python's import system to resolve the module location robustly.
        Returns (is_local, file_path).
        """
        try:
            # Use Python's import system to find where the module actually is
            spec = importlib.util.find_spec(module_name)

            if spec is None:
                # Module not found
                return False, None

            # Check if module has an origin (file location)
            if spec.origin is None:
                # Built-in module or namespace package without origin
                return False, None

            # Check if origin is a file (not a directory for namespace packages)
            if not spec.origin.endswith(".py"):
                # Could be a namespace package or compiled module
                # For namespace packages, check if it's in our project
                if (
                    hasattr(spec, "submodule_search_locations")
                    and spec.submodule_search_locations
                ):
                    for location in spec.submodule_search_locations:
                        location_abs = os.path.abspath(location)
                        if location_abs.startswith(self.project_root):
                            # It's a namespace package in our project
                            rel_path = os.path.relpath(location_abs, self.project_root)
                            return True, rel_path
                return False, None

            # Get absolute path of the module file
            module_file = os.path.abspath(spec.origin)

            # Check if it's a system or venv file
            if self._is_system_or_venv_file(module_file):
                return False, None

            # Check if it's within project root
            if not module_file.startswith(self.project_root):
                return False, None

            # Get relative path from project root
            rel_path = os.path.relpath(module_file, self.project_root)

            # For packages, we might want to return the directory instead of __init__.py
            if rel_path.endswith("__init__.py"):
                # Return the package directory
                rel_path = os.path.dirname(rel_path)
                # If it's empty after removing __init__.py, it's the root package
                if not rel_path:
                    return False, None

            return True, rel_path

        except (ImportError, ValueError, AttributeError) as e:
            # Module resolution failed
            if self.logger:
                self.logger.debug(f"Could not resolve module {module_name}: {e}")
            return False, None

    def scan_file(self, file_path: str) -> Set[str]:
        """
        Scan a python file for imports and dynamic loading patterns.
        Returns a set of detected local dependencies (relative paths from project root).
        """
        dependencies = set()

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()

            tree = ast.parse(content, filename=file_path)

            # Get directory of current file for relative imports
            file_dir = os.path.dirname(os.path.abspath(file_path))

            for node in ast.walk(tree):
                # 1. Static Imports
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        is_local, path = self.is_local_file(alias.name)
                        if is_local:
                            dependencies.add(path)

                elif isinstance(node, ast.ImportFrom):
                    if node.level > 0:
                        # Relative import (from . import ... or from .. import ...)
                        # Resolve relative import based on current file location
                        # Calculate relative path from current file
                        current_rel = os.path.relpath(file_dir, self.project_root)
                        parts = (
                            current_rel.split(os.sep) if current_rel != "." else []
                        )

                        # Go up 'level' directories
                        if node.level <= len(parts):
                            parent_parts = parts[: len(parts) - (node.level - 1)]
                            module_parts = node.module.split(".") if node.module else []
                            
                            # We want to check:
                            # 1. The module itself (if present)
                            # 2. Each name imported from it
                            
                            to_check = []
                            if node.module:
                                to_check.append(parent_parts + module_parts)
                            
                            for alias in node.names:
                                to_check.append(parent_parts + module_parts + [alias.name])
                                
                            for parts_list in to_check:
                                rel_path = os.path.join(*parts_list) if parts_list else ""
                                if rel_path:
                                    # Try as file
                                    abs_path = os.path.join(
                                        self.project_root, rel_path + ".py"
                                    )
                                    if os.path.exists(abs_path):
                                        dependencies.add(rel_path + ".py")
                                    else:
                                        # Try as package
                                        abs_path = os.path.join(
                                            self.project_root, rel_path, "__init__.py"
                                        )
                                        if os.path.exists(abs_path):
                                            dependencies.add(rel_path)
                    elif node.module:
                        # from module import ... (absolute import)
                        # Check the module itself
                        is_local, path = self.is_local_file(node.module)
                        if is_local:
                            dependencies.add(path)
                            
                        # Also check each name in case they are submodules
                        for alias in node.names:
                            full_name = f"{node.module}.{alias.name}"
                            is_local_sub, sub_path = self.is_local_file(full_name)
                            if is_local_sub:
                                dependencies.add(sub_path)

                # 2. Dynamic Imports & File Operations Warnings
                elif isinstance(node, ast.Call):
                    if isinstance(node.func, ast.Attribute):
                        # importlib.import_module(...)
                        if (
                            node.func.attr == "import_module"
                            and isinstance(node.func.value, ast.Name)
                            and node.func.value.id == "importlib"
                        ):
                            self._add_warning(
                                file_path,
                                node.lineno,
                                "importlib.import_module usage detected",
                            )

                    elif isinstance(node.func, ast.Name):
                        # __import__(...)
                        if node.func.id == "__import__":
                            self._add_warning(
                                file_path, node.lineno, "__import__ usage detected"
                            )
                        # open(...)
                        elif node.func.id == "open":
                            # Check if argument is a string literal
                            if (
                                node.args
                                and isinstance(node.args[0], ast.Constant)
                                and isinstance(node.args[0].value, str)
                            ):
                                path_arg = node.args[0].value
                                # Warn if it looks like a path to a file that might be missing
                                if not os.path.isabs(
                                    path_arg
                                ) and not path_arg.startswith("/"):
                                    self._add_warning(
                                        file_path,
                                        node.lineno,
                                        f"open('{path_arg}') detected. Ensure this file is in 'files' list if needed.",
                                    )
                            else:
                                self._add_warning(
                                    file_path,
                                    node.lineno,
                                    "open() with dynamic path detected",
                                )

        except Exception as e:
            self.logger.debug(f"Failed to scan {file_path}: {e}")

        return dependencies

    def _add_warning(self, file_path: str, lineno: int, message: str):
        file_abs = os.path.abspath(file_path)

        # Filter out warnings from installed packages or system files
        if self._is_system_or_venv_file(file_abs):
            return

        # Check if file is within project root
        # If file is outside project root and not in site-packages (already checked), ignore it
        try:
            # If file is outside project root, relpath will start with '../'
            rel_path = os.path.relpath(file_abs, self.project_root)
            if rel_path.startswith("../"):
                # File is outside project root → ignore
                return
        except ValueError:
            # If files are on different drives (Windows), relpath raises ValueError
            # In this case, check if file_abs starts with project_root
            if not file_abs.startswith(self.project_root):
                # File is outside project root → ignore
                return
            rel_path = os.path.relpath(file_abs, self.project_root)

        # Filter out warnings from slurmray's own code and test files
        # Use __file__ to get the absolute path of slurmray package
        try:
            import slurmray

            slurmray_dir = os.path.dirname(os.path.abspath(slurmray.__file__))

            # Check if file is in slurmray directory or its subdirectories
            if file_abs.startswith(slurmray_dir):
                return  # Skip warnings from slurmray framework code
        except (AttributeError, ImportError):
            # Fallback: if we can't determine slurmray location, use path prefix check
            if rel_path.startswith("slurmray/"):
                return

        # Also filter out common non-user directories
        if (
            rel_path.startswith("tests/")
            or rel_path.startswith(".slogs/")
            or rel_path.startswith("old_")
            or rel_path.startswith("debug_")
        ):
            return  # Skip warnings from test files and temporary directories

        self.dynamic_imports_warnings.append(f"{rel_path}:{lineno}: {message}")

    def _follow_imports_recursive(
        self, file_path: str, visited: Set[str] = None, path_modified: bool = False
    ) -> Set[str]:
        """
        Recursively follow imports starting from a file.
        Returns set of relative paths to local dependencies.
        """
        if visited is None:
            visited = set()
            # Ensure project_root is in sys.path for importlib to work
            # (needed for is_local_file to resolve modules correctly)
            project_in_path = self.project_root in sys.path
            src_path = os.path.join(self.project_root, "src")
            src_in_path = src_path in sys.path

            if not project_in_path:
                sys.path.insert(0, self.project_root)
            if not src_in_path and os.path.exists(src_path):
                sys.path.insert(0, src_path)
            path_modified = not project_in_path or (
                not src_in_path and os.path.exists(src_path)
            )

        # Normalize path
        file_path = os.path.abspath(file_path)
        if file_path in visited:
            return set()
        visited.add(file_path)

        # Check if file is within project
        if not file_path.startswith(self.project_root):
            return set()

        # Check if it's a system or venv file (double check to avoid scanning venv inside project)
        if self._is_system_or_venv_file(file_path):
            return set()

        # Get relative path
        try:
            rel_path = os.path.relpath(file_path, self.project_root)
        except ValueError:
            return set()

        dependencies = set()

        try:
            # Scan this file for imports
            deps = self.scan_file(file_path)
            dependencies.update(deps)

            # Recursively follow each dependency
            for dep in deps:
                # Convert relative path to absolute
                dep_abs = os.path.abspath(os.path.join(self.project_root, dep))

                # Check if it's a file or directory
                if os.path.isfile(dep_abs):
                    # It's a file, follow it
                    sub_deps = self._follow_imports_recursive(
                        dep_abs, visited, path_modified
                    )
                    dependencies.update(sub_deps)
                elif os.path.isdir(dep_abs):
                    # It's a directory (package), check for __init__.py
                    init_file = os.path.join(dep_abs, "__init__.py")
                    if os.path.exists(init_file):
                        sub_deps = self._follow_imports_recursive(
                            init_file, visited, path_modified
                        )
                        dependencies.update(sub_deps)

            return dependencies
        finally:
            # Restore sys.path only if we're the top-level call
            if path_modified and len(visited) == 1:  # Only restore on first call
                if self.project_root in sys.path:
                    sys.path.remove(self.project_root)
                src_path = os.path.join(self.project_root, "src")
                if src_path in sys.path:
                    sys.path.remove(src_path)

    def detect_dependencies_from_function(self, func) -> List[str]:
        """
        Detect dependencies starting from a function's source file.
        Follows imports recursively to find all local dependencies.
        """
        import inspect

        try:
            # Get the file where the function is defined
            func_file = inspect.getfile(func)
            func_file = os.path.abspath(func_file)

            # Check if function is in project
            if not func_file.startswith(self.project_root):
                self.logger.debug(
                    f"Function {func.__name__} is not in project root, skipping dependency detection"
                )
                return []

            self.logger.info(
                f"Analyzing dependencies starting from {os.path.relpath(func_file, self.project_root)}"
            )

            # Follow imports recursively (sys.path is managed inside _follow_imports_recursive)
            dependencies = self._follow_imports_recursive(func_file)

            # Convert to relative paths and normalize
            result = set()
            for dep in dependencies:
                if dep:
                    # dep is already a relative path from scan_file
                    result.add(dep)

            return list(result)

        except (OSError, TypeError) as e:
            self.logger.warning(
                f"Could not determine source file for function {func.__name__}: {e}"
            )
            return []
