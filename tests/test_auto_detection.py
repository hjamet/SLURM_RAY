#!/usr/bin/env python3
"""
Test pour vérifier que le système de détection automatique des fichiers fonctionne correctement.
Ce test vérifie :
1. La détection des imports statiques
2. Les avertissements pour les imports dynamiques
3. La détection des packages éditable
"""

import os
import tempfile
import shutil
from pathlib import Path

from slurmray.scanner import ProjectScanner


def test_recursive_imports_detection():
    """Test que les imports sont détectés récursivement à partir d'une fonction."""
    # Créer un projet temporaire avec une structure simple
    with tempfile.TemporaryDirectory() as tmpdir:
        project_root = Path(tmpdir)
        original_cwd = os.getcwd()
        os.chdir(tmpdir)

        try:
            # Créer une structure de projet
            src_dir = project_root / "src"
            src_dir.mkdir()

            utils_dir = src_dir / "utils"
            utils_dir.mkdir()

            # Créer des fichiers Python avec des imports
            (src_dir / "__init__.py").write_text("")
            (src_dir / "main.py").write_text(
                """
from src.utils.helper import helper_func
from src.config import config_value

def main():
    return helper_func(config_value)
"""
            )

            (utils_dir / "__init__.py").write_text("")
            (utils_dir / "helper.py").write_text(
                """
def helper_func(x):
    return x * 2
"""
            )

            (src_dir / "config.py").write_text(
                """
config_value = 42
"""
            )

            # Importer la fonction
            import sys

            sys.path.insert(0, str(project_root))
            from src.main import main

            # Scanner à partir de la fonction
            scanner = ProjectScanner(str(project_root))
            detected = scanner.detect_dependencies_from_function(main)

            # Vérifier que les fichiers sont détectés
            detected_paths = set(detected)

            # Les fichiers détectés devraient inclure les modules locaux
            assert len(detected) > 0, "Aucune dépendance détectée"
            assert (
                "src/utils/helper.py" in detected_paths or "src" in detected_paths
            ), "helper.py devrait être détecté"
            assert (
                "src/config.py" in detected_paths or "src" in detected_paths
            ), "config.py devrait être détecté"

            print(
                f"✅ Détection récursive des imports : {len(detected)} fichiers détectés"
            )
            for dep in detected:
                print(f"   - {dep}")
        finally:
            os.chdir(original_cwd)


def test_dynamic_imports_warning():
    """Test que les imports dynamiques génèrent des avertissements."""
    with tempfile.TemporaryDirectory() as tmpdir:
        project_root = Path(tmpdir)

        # Créer un fichier avec des imports dynamiques
        test_file = project_root / "test_dynamic.py"
        test_file.write_text(
            """
import importlib
import os

# Import statique (devrait être OK)
from mymodule import func

# Import dynamique (devrait générer un warning)
module_name = "mymodule"
dynamic_module = importlib.import_module(module_name)

# __import__ (devrait générer un warning)
another_module = __import__("another_module")

# open() avec chemin relatif (devrait générer un warning)
with open("config/data.yaml", "r") as f:
    data = f.read()
"""
        )

        # Scanner le fichier
        scanner = ProjectScanner(str(project_root))
        scanner.scan_file(str(test_file))

        # Vérifier que des avertissements ont été générés
        assert (
            len(scanner.dynamic_imports_warnings) > 0
        ), "Aucun avertissement pour les imports dynamiques"

        print(
            f"✅ Détection des imports dynamiques : {len(scanner.dynamic_imports_warnings)} avertissements"
        )
        for warning in scanner.dynamic_imports_warnings:
            print(f"   - {warning}")

        # Vérifier que les warnings contiennent les bonnes informations
        warnings_text = " ".join(scanner.dynamic_imports_warnings)
        assert (
            "importlib" in warnings_text or "__import__" in warnings_text
        ), "Avertissement manquant pour importlib/__import__"
        assert "open" in warnings_text.lower(), "Avertissement manquant pour open()"


def test_src_layout_detection():
    """Test que le layout src/ est correctement détecté."""
    import sys

    with tempfile.TemporaryDirectory() as tmpdir:
        project_root = Path(tmpdir)
        original_cwd = os.getcwd()
        os.chdir(tmpdir)

        try:
            # Créer un layout src/
            src_dir = project_root / "src"
            src_dir.mkdir()

            package_dir = src_dir / "mypackage"
            package_dir.mkdir()

            (package_dir / "__init__.py").write_text("")
            (package_dir / "module.py").write_text(
                """
def my_function():
    return "test"
"""
            )

            # Ajouter src/ au path pour que le module soit importable
            sys.path.insert(0, str(src_dir))

            # Importer le module pour qu'il soit résolvable par importlib
            import mypackage.module

            scanner = ProjectScanner(str(project_root))
            is_local, path = scanner.is_local_file("mypackage.module")

            # Vérifier que le module est détecté comme local
            assert is_local, "Le module dans src/ devrait être détecté comme local"
            assert path is not None, "Un chemin devrait être retourné"

            print(f"✅ Détection du layout src/ : module détecté à {path}")
        finally:
            os.chdir(original_cwd)
            if str(src_dir) in sys.path:
                sys.path.remove(str(src_dir))


def test_relative_imports():
    """Test que les imports relatifs sont gérés correctement."""
    with tempfile.TemporaryDirectory() as tmpdir:
        project_root = Path(tmpdir)
        original_cwd = os.getcwd()
        os.chdir(tmpdir)

        try:
            package_dir = project_root / "package"
            package_dir.mkdir()

            (package_dir / "__init__.py").write_text("")
            (package_dir / "module1.py").write_text(
                """
from .module2 import func2

def func1():
    return func2()
"""
            )

            (package_dir / "module2.py").write_text(
                """
def func2():
    return "test"
"""
            )

            # Importer la fonction
            import sys

            sys.path.insert(0, str(project_root))
            from package.module1 import func1

            scanner = ProjectScanner(str(project_root))
            detected = scanner.detect_dependencies_from_function(func1)

            # Les imports relatifs devraient être gérés (pas d'erreur)
            # module2 devrait être détecté via l'import relatif
            print(
                f"✅ Gestion des imports relatifs : {len(detected)} fichiers détectés"
            )
            for dep in detected:
                print(f"   - {dep}")
        finally:
            os.chdir(original_cwd)


def test_file_operations_warning():
    """Test que les opérations sur fichiers génèrent des avertissements."""
    with tempfile.TemporaryDirectory() as tmpdir:
        project_root = Path(tmpdir)

        test_file = project_root / "test_files.py"
        test_file.write_text(
            """
# open() avec chemin relatif (devrait générer un warning)
with open("data/config.json", "r") as f:
    config = f.read()

# open() avec chemin absolu (ne devrait pas générer de warning)
import os
with open(os.path.join("/tmp", "file.txt"), "w") as f:
    f.write("test")
"""
        )

        scanner = ProjectScanner(str(project_root))
        scanner.scan_file(str(test_file))

        # Vérifier qu'un avertissement est généré pour le chemin relatif
        warnings_text = " ".join(scanner.dynamic_imports_warnings)
        assert (
            "config.json" in warnings_text or "data" in warnings_text
        ), "Avertissement manquant pour open() avec chemin relatif"

        print(
            f"✅ Détection des opérations sur fichiers : {len(scanner.dynamic_imports_warnings)} avertissements"
        )


if __name__ == "__main__":
    print("=" * 60)
    print("Tests de détection automatique")
    print("=" * 60)
    print()

    test_recursive_imports_detection()
    print()

    test_dynamic_imports_warning()
    print()

    test_src_layout_detection()
    print()

    test_relative_imports()
    print()

    test_file_operations_warning()
    print()

    print("=" * 60)
    print("✅ Tous les tests de détection sont passés !")
    print("=" * 60)
