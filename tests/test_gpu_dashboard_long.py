#!/usr/bin/env python3
"""
Test manuel avec GPU et dashboard pour Curnagl.
Ce script lance un job qui prend du temps (5 minutes) pour permettre l'exploration du dashboard.

Utilisation:
1. Lancer le script: poetry run python tests/test_gpu_dashboard_long.py
2. Attendre que le job soit soumis et démarre
3. Dans un autre terminal, lancer: poetry run python -m slurmray
4. Sélectionner l'option 'd' (Open Dashboard) et entrer le Job ID
5. Le dashboard s'ouvrira automatiquement dans votre navigateur
"""

from slurmray.RayLauncher import RayLauncher
import ray
import os
import time
from getpass import getpass
from dotenv import load_dotenv

# Try to import torch for GPU tests
try:
    import torch
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False
    torch = None


def gpu_long_task(duration_minutes=5):
    """
    Fonction qui exécute des tâches GPU pendant un certain temps.
    Parfait pour tester le dashboard pendant l'exécution.
    
    Args:
        duration_minutes: Durée d'exécution en minutes (par défaut 5)
    """
    import sys
    
    results = {
        "python_version": sys.version.split()[0],
        "torch_available": TORCH_AVAILABLE,
        "gpu_available": False,
        "gpu_count": 0,
        "gpu_names": [],
        "ray_resources": ray.cluster_resources(),
        "tasks_completed": 0,
    }
    
    # Track execution time
    start_time = time.time()
    
    # Check GPU availability
    if TORCH_AVAILABLE and torch is not None:
        results["gpu_available"] = torch.cuda.is_available()
        if results["gpu_available"]:
            results["gpu_count"] = torch.cuda.device_count()
            results["gpu_names"] = [torch.cuda.get_device_name(i) for i in range(results["gpu_count"])]
            
            # Create a GPU tensor and do some work
            print(f"✅ GPU disponible: {results['gpu_names']}")
            print(f"🔥 Démarrage des tâches GPU pour {duration_minutes} minutes...")
            print("   (Vous pouvez maintenant utiliser 'python -m slurmray' pour ouvrir le dashboard)")
            
            # Run GPU tasks for the specified duration
            end_time = start_time + (duration_minutes * 60)
            task_counter = 0
            
            while time.time() < end_time:
                # Create tensors on GPU and do some computation
                for gpu_id in range(results["gpu_count"]):
                    device = torch.device(f"cuda:{gpu_id}")
                    # Simple matrix multiplication on GPU
                    a = torch.randn(1000, 1000, device=device)
                    b = torch.randn(1000, 1000, device=device)
                    c = torch.matmul(a, b)
                    task_counter += 1
                
                # Print progress every 10 seconds
                elapsed = time.time() - start_time
                if task_counter % 10 == 0:
                    remaining = (end_time - time.time()) / 60
                    print(f"⏱️  Temps écoulé: {elapsed/60:.1f} min | Restant: {remaining:.1f} min | Tâches: {task_counter}")
                
                time.sleep(0.5)  # Small delay to avoid overheating
            
            results["tasks_completed"] = task_counter
            print(f"✅ {task_counter} tâches GPU complétées!")
        else:
            print("⚠️  Aucun GPU disponible via CUDA")
            # Wait anyway for dashboard testing
            print(f"⏳ Attente de {duration_minutes} minutes pour tester le dashboard...")
            time.sleep(duration_minutes * 60)
    else:
        print("⚠️  PyTorch non disponible")
        # Wait anyway for dashboard testing
        print(f"⏳ Attente de {duration_minutes} minutes pour tester le dashboard...")
        time.sleep(duration_minutes * 60)
    
    results["execution_time"] = time.time() - start_time
    return results


def test_gpu_dashboard_long():
    """Test manuel pour vérifier GPU et dashboard avec job long."""
    load_dotenv()
    
    print("🚀 Test GPU et Dashboard (Job Long)")
    print("=" * 60)
    print("Ce script lance un job qui s'exécute pendant 5 minutes.")
    print("Pendant ce temps, vous pouvez ouvrir le dashboard via:")
    print("  poetry run python -m slurmray")
    print("  puis sélectionner 'd' (Open Dashboard)")
    print("=" * 60)
    print()
    
    # Get credentials from .env or use getpass as fallback
    server_username = os.getenv("CURNAGL_USERNAME")
    server_password = os.getenv("CURNAGL_PASSWORD")
    
    if server_password is None:
        server_password = getpass("Enter your cluster password: ")
    
    launcher = RayLauncher(
        project_name="test_gpu_dashboard_long",
        func=gpu_long_task,
        args={"duration_minutes": 5},  # 5 minutes pour explorer le dashboard
        files=[],
        modules=[],  # Modules CUDA/CUDNN seront ajoutés automatiquement avec use_gpu=True
        node_nbr=1,
        use_gpu=True,  # Request GPU
        memory=8,
        max_running_time=10,  # Max 10 minutes (marge de sécurité)
        server_run=True,
        server_ssh="curnagl.dcsr.unil.ch",
        server_username=server_username,
        server_password=server_password,
        cluster="slurm",
    )
    
    print()
    print("📤 Lancement du job...")
    print("   Le job sera soumis à SLURM et démarrera dans la file d'attente.")
    print("   Une fois démarré, vous verrez un message indiquant le head node.")
    print()
    
    try:
        result = launcher()
        
        print()
        print("=" * 60)
        print("✅ Job terminé - Résultats:")
        print("=" * 60)
        print(f"Python version: {result.get('python_version')}")
        print(f"Torch disponible: {result.get('torch_available')}")
        print(f"GPU disponible: {result.get('gpu_available')}")
        if result.get('gpu_available'):
            print(f"Nombre de GPU: {result.get('gpu_count')}")
            print(f"Noms des GPU: {result.get('gpu_names')}")
        print(f"Tâches complétées: {result.get('tasks_completed', 0)}")
        print(f"Temps d'exécution: {result.get('execution_time', 0):.1f} secondes")
        print(f"Ressources Ray: {result.get('ray_resources')}")
        print("=" * 60)
        
        if result.get('gpu_available') and result.get('gpu_count', 0) > 0:
            print("✅ SUCCESS: GPU détecté et utilisé!")
        else:
            print("⚠️  WARNING: GPU non détecté ou non disponible.")
            
    except Exception as e:
        print(f"❌ Erreur lors de l'exécution: {e}")
        raise


if __name__ == "__main__":
    test_gpu_dashboard_long()

