#!/usr/bin/env python3
"""
Test complet pour vérifier que l'exemple dans RayLauncher.py fonctionne toujours.
Ce test vérifie que l'exemple peut être initialisé et que la fonction peut être sérialisée.
"""

import os
import sys
import tempfile
from pathlib import Path

# Ajouter le répertoire parent au path pour les imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from slurmray import Cluster
import ray
import torch


def test_raylauncher_example_complete():
    """Test complet de l'exemple dans RayLauncher.py."""
    
    # Créer un environnement temporaire
    with tempfile.TemporaryDirectory() as tmpdir:
        original_cwd = os.getcwd()
        os.chdir(tmpdir)
        
        try:
            # Créer le fichier documentation/RayLauncher.html comme dans l'exemple
            doc_dir = Path(tmpdir) / "documentation"
            doc_dir.mkdir()
            (doc_dir / "RayLauncher.html").write_text("<html>Test content for example</html>")
            
            # Définir les fonctions exactement comme dans l'exemple
            def function_inside_function():
                # Check if file exists before trying to read it, as paths might differ
                if os.path.exists("documentation/RayLauncher.html"):
                    with open("documentation/RayLauncher.html", "r") as f:
                        return f.read()[0:10]
                return "DocNotFound"

            def example_func(x):
                result = (
                    ray.cluster_resources(),
                    f"GPU is available : {torch.cuda.is_available()}",
                    x + 1,
                    function_inside_function(),
                )
                return result
            
            # Initialiser RayLauncher exactement comme dans l'exemple
            # Mais en mode local pour éviter les credentials
            cluster = Cluster(
                project_name="example",  # Name of the project (will create a directory with this name in the current directory)
                files=(
                    ["documentation/RayLauncher.html"]
                    if os.path.exists("documentation/RayLauncher.html")
                    else []
                ),  # List of files to push to the server
                use_gpu=False,  # Pas de GPU pour le test (mais l'exemple utilise True)
                runtime_env={
                    "env_vars": {}  # L'exemple utilise {"NCCL_SOCKET_IFNAME": "eno1"}
                },  # Example of environment variable
                server_run=False,  # Mode local pour le test (l'exemple utilise True)
                cluster="local",  # Mode local (l'exemple utilise "desi")
                force_reinstall_venv=False,  # Pas besoin pour le test
            )
            
            # Vérifier que l'initialisation a réussi
            assert cluster is not None, "RayLauncher devrait être initialisé"
            assert cluster.project_name == "example", "Le nom du projet devrait être 'example'"
            
            # Vérifier que le fichier est dans la liste
            assert "documentation/RayLauncher.html" in cluster.files, \
                "Le fichier documentation/RayLauncher.html devrait être dans la liste"
            
            print("✅ Initialisation de l'exemple réussie")
            
            # Tester la sérialisation de la fonction
            cluster._Cluster__serialize_func_and_args(example_func, {"x": 5})
            
            # Vérifier que les fichiers de sérialisation ont été créés
            assert os.path.exists(os.path.join(cluster.project_path, "func.pkl")), \
                "Le fichier func.pkl devrait être créé"
            assert os.path.exists(os.path.join(cluster.project_path, "args.pkl")), \
                "Le fichier args.pkl devrait être créé"
            
            print("✅ Sérialisation de la fonction de l'exemple réussie")
            
            # Vérifier que la méthode de sérialisation a été enregistrée
            method_file = os.path.join(cluster.project_path, "serialization_method.txt")
            if os.path.exists(method_file):
                with open(method_file, "r") as f:
                    method = f.read().strip()
                    print(f"✅ Méthode de sérialisation : {method}")
            
        finally:
            os.chdir(original_cwd)


def test_raylauncher_example_with_auto_detection():
    """Test que l'exemple fonctionne avec la détection automatique."""
    
    with tempfile.TemporaryDirectory() as tmpdir:
        original_cwd = os.getcwd()
        os.chdir(tmpdir)
        
        try:
            # Créer une structure de projet avec des modules locaux
            doc_dir = Path(tmpdir) / "documentation"
            doc_dir.mkdir()
            (doc_dir / "RayLauncher.html").write_text("<html>Test</html>")
            
            src_dir = Path(tmpdir) / "src"
            src_dir.mkdir()
            (src_dir / "mymodule.py").write_text("""
def helper():
    return "help"
""")
            
            # Créer un fichier principal qui utilise les modules locaux
            main_file = Path(tmpdir) / "main.py"
            main_file.write_text("""
from src.mymodule import helper

def example_func(x):
    return helper(), x + 1
""")
            
            # Initialiser RayLauncher avec files=[] pour tester la détection automatique
            cluster = Cluster(
                # project_name="example_auto", # Removed to test auto-detection
                files=[],  # Liste vide pour tester la détection
                server_run=False,
                cluster="local",
            )
            
            # La détection automatique devrait avoir ajouté des fichiers
            # Project name should be the directory name (tmpdir basename)
            expected_name = os.path.basename(tmpdir)
            assert cluster.project_name == expected_name, f"Project name should be {expected_name}, got {cluster.project_name}"
            
            print(f"✅ Fichiers détectés automatiquement : {cluster.files}")
            
            # Vérifier que la détection n'a pas causé d'erreur
            assert isinstance(cluster.files, list), "files devrait être une liste"
            
        finally:
            os.chdir(original_cwd)


if __name__ == "__main__":
    print("=" * 60)
    print("Test complet de l'exemple RayLauncher")
    print("=" * 60)
    print()
    
    test_raylauncher_example_complete()
    print()
    
    test_raylauncher_example_with_auto_detection()
    print()
    
    print("=" * 60)
    print("✅ Tous les tests de l'exemple complet sont passés !")
    print("=" * 60)

