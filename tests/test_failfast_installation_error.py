"""
Test pour vérifier que le fail-fast fonctionne lors d'erreurs d'installation.

Ce test force une erreur d'installation en ajoutant une dépendance invalide
dans requirements.txt et vérifie que l'exception est levée immédiatement
au lieu d'attendre un timeout.
"""

import os
import time
import sys
from slurmray.RayLauncher import RayLauncher
from dotenv import load_dotenv


def simple_func(x):
    """Fonction simple pour le test"""
    return x * 2


def test_desi_failfast_on_installation_error():
    """Test que DesiBackend fail-fast immédiatement lors d'une erreur d'installation"""
    load_dotenv()

    # Skip test if no password in env
    if not os.environ.get("DESI_PASSWORD"):
        print("Skipping Desi fail-fast test (DESI_PASSWORD not found)")
        return

    # Créer un requirements.txt temporaire avec une dépendance qui échouera
    # On utilise un package avec une version spécifique qui nécessite des dépendances système
    # qui ne sont probablement pas installées (comme Go pour wandb)
    # Pour forcer une vraie erreur, on utilise une version de wandb qui nécessite Go
    # OU on peut utiliser un package qui n'existe vraiment pas
    # Essayons d'abord avec un package qui n'existe pas pour être sûr que ça échoue
    test_requirements = (
        "this-package-definitely-does-not-exist-xyz-12345==999.999.999\n"
    )

    # Sauvegarder l'ancien requirements.txt s'il existe
    old_requirements = None
    requirements_path = "requirements.txt"
    if os.path.exists(requirements_path):
        with open(requirements_path, "r") as f:
            old_requirements = f.read()

    try:
        # Écrire le requirements.txt avec la dépendance invalide
        with open(requirements_path, "w") as f:
            f.write(test_requirements)

        print(
            "📝 Created requirements.txt with invalid dependency to force installation error"
        )

        # Créer le launcher avec force_reinstall_venv pour forcer l'installation
        cluster = RayLauncher(
            project_name="test_failfast_installation",
            files=[],
            modules=[],
            node_nbr=1,
            use_gpu=False,
            memory=1,
            max_running_time=5,
            server_run=True,
            server_ssh="130.223.73.209",  # Desi IP
            server_username=os.getenv("DESI_USERNAME", "henri"),  # From env or default
            server_password=os.environ.get("DESI_PASSWORD"),  # From env
            cluster="desi",
            force_reinstall_venv=True,  # Force l'installation pour déclencher l'erreur
        )

        print("🚀 Launching job with invalid dependency (should fail-fast)...")
        start_time = time.time()

        # On s'attend à ce qu'une RuntimeError soit levée immédiatement
        try:
            result = cluster(simple_func, args={"x": 21})
            # Si on arrive ici, c'est un problème : l'exception n'a pas été levée
            print("❌ ERROR: Expected RuntimeError was not raised!")
            print("   The job completed successfully, but it should have failed.")
            sys.exit(1)
        except RuntimeError as e:
            elapsed_time = time.time() - start_time
            error_msg = str(e)

            # Vérifier que l'exception a été levée rapidement (moins de 30 secondes)
            # Au lieu d'attendre le timeout de 5 minutes
            if elapsed_time >= 30:
                print(
                    f"❌ ERROR: Fail-fast took too long: {elapsed_time:.2f}s (expected < 30s)"
                )
                sys.exit(1)

            # Vérifier que le message d'erreur contient le code de sortie
            if "exited with non-zero status" not in error_msg:
                print(f"❌ ERROR: Error message should mention exit status")
                print(f"   Got: {error_msg[:200]}...")
                sys.exit(1)

            # Vérifier que le message contient des informations sur l'erreur
            if "non-zero status" not in error_msg and "Script errors" not in error_msg:
                print(f"❌ ERROR: Error message should contain error details")
                print(f"   Got: {error_msg[:200]}...")
                sys.exit(1)

            print(
                f"✅ Fail-fast test passed! Exception raised after {elapsed_time:.2f}s"
            )
            print(f"   Error message: {error_msg[:200]}...")
        except Exception as e:
            # Autre exception inattendue
            elapsed_time = time.time() - start_time
            print(f"❌ ERROR: Unexpected exception type: {type(e).__name__}")
            print(f"   Message: {str(e)[:200]}...")
            print(f"   Time elapsed: {elapsed_time:.2f}s")
            raise

    finally:
        # Restaurer l'ancien requirements.txt ou le supprimer
        if old_requirements is not None:
            with open(requirements_path, "w") as f:
                f.write(old_requirements)
        elif os.path.exists(requirements_path):
            os.remove(requirements_path)
        print("🧹 Cleaned up test requirements.txt")


if __name__ == "__main__":
    test_desi_failfast_on_installation_error()
