import time
from slurmray.RayLauncher import RayLauncher
import ray
import os
from dotenv import load_dotenv

# Load env vars
load_dotenv()

def long_running_function(x):
    """A function that sleeps for a long time to allow manual interruption"""
    print(f"Starting task with x={x}")
    time.sleep(60)
    return x * 2

def main():
    print("\n=== Test manuel d'interruption (Ctrl+C) ===")
    print("Ce script va lancer un job SLURM qui dort pendant 60 secondes.")
    print("Une fois le job soumis (ID affiché), faites Ctrl+C pour interrompre le script.")
    print("Le script devrait capturer l'interruption et annuler le job SLURM automatiquement.")
    print("==========================================\n")

    launcher = RayLauncher(
        project_name="test_interruption",
        node_nbr=1,
        use_gpu=False,
        memory=2,
        max_running_time=5,
        server_run=True,
        server_ssh="curnagl.dcsr.unil.ch",
        server_username=os.getenv("CURNAGL_USERNAME"),
        server_password=os.getenv("CURNAGL_PASSWORD"),
    )

    print("Lancement du job... Préparez-vous à faire Ctrl+C une fois le Job ID affiché !")
    try:
        result = launcher(long_running_function, args={"x": 10})
        print(f"Résultat (inattendu si interrompu): {result}")
    except KeyboardInterrupt:
        print("\nInterruption capturée dans le main (normalement géré par RayLauncher avant)")
    except SystemExit:
        print("\nSortie système capturée (attendu après nettoyage RayLauncher)")

if __name__ == "__main__":
    main()

