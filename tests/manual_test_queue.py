import time
from slurmray.RayLauncher import RayLauncher
import ray
import os
from dotenv import load_dotenv

# Load env vars
load_dotenv()

def simple_func(x):
    return x * x

def main():
    print("\n=== Test manuel d'affichage de queue ===")
    print("Ce script va lancer un job SLURM.")
    print("Observez la console : vous devriez voir 'Waiting for job... (Position in queue : X/Y)'")
    print("Ce message ne doit apparaître que toutes les 30 secondes (si le job reste en attente assez longtemps).")
    print("Si le job démarre tout de suite, vous ne verrez peut-être pas le message.")
    print("========================================\n")

    launcher = RayLauncher(
        project_name="test_queue_display",
        func=simple_func,
        args={"x": 5},
        node_nbr=1,
        use_gpu=False,
        memory=2,
        max_running_time=5,
        server_run=True,
        server_ssh="curnagl.dcsr.unil.ch",
        server_username=os.getenv("CURNAGL_USERNAME"),
        server_password=os.getenv("CURNAGL_PASSWORD"),
    )

    print("Lancement du job...")
    result = launcher()
    print(f"Résultat : {result}")

if __name__ == "__main__":
    main()

