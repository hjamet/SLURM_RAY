# SLURM_RAY

**Official tool from DESI @ HEC UNIL**

👉[Full documentation](https://www.henri-jamet.com/docs/slurmray/slurm-ray/)

## Description

**SlurmRay** is a module for effortlessly distributing tasks on a [Slurm](https://slurm.schedmd.com/) cluster (like Curnagl) or a standalone server (like ISIPOL09/Desi) using the [Ray](https://ray.io/) library. **SlurmRay** was initially designed to work with the [Curnagl](https://wiki.unil.ch/ci/books/high-performance-computing-hpc/page/curnagl) cluster at the *University of Lausanne*. It is now an official tool of the **DESI department @ HEC UNIL** and supports both Slurm-based clusters and direct SSH execution on dedicated servers.

## Installation

**SlurmRay** is designed to run both locally and on a cluster without any modification. This design is intended to allow work to be carried out on a local machine until the script seems to be working. It should then be possible to run it using all the resources of the cluster without having to modify the code.

```bash
pip install slurmray
```

## Prerequisites

### For Slurm clusters (e.g., Curnagl)
- Access to a Slurm cluster with SSH access
- Valid credentials (username/password)
- Python 3.12+ on both local and cluster machines

### For Desi server (ISIPOL09)
- VPN access to the DESI network (if required)
- SSH access to `130.223.73.209`
- Valid credentials (username/password)
- Python 3.12+ on both local and remote machines

## Principaux résultats

| Métrique | Valeur | Notes |
|---|---|---|
| Support Backend | Slurm, Desi (SSH) | Curnagl & ISIPOL09 supportés |
| Gestion de tâches | Ray | Distribution automatique |
| Installation | Optimisée | Installation incrémentale avec cache et détection de versions |
| Dashboard | Intégré | Ouverture automatique dans le navigateur (via tunnel SSH) |
| Compatibilité | Python 3.8 - 3.12 | Gestion automatique de la sérialisation inter-versions |

## Plan du repo

```
root/
├── slurmray/               # Code source du package
│   ├── backend/            # Implémentations backends (Slurm, Desi, Local)
│   ├── assets/             # Templates de scripts (sbatch, spython)
│   └── RayLauncher.py      # Classe principale
├── tests/                  # Tests unitaires et d'intégration
├── documentation/          # Documentation générée
├── logs/                   # Logs d'exécution
├── poetry.lock             # Dépendances lock
├── pyproject.toml          # Configuration Poetry
└── README.md               # Documentation principale
```

## Scripts d'entrée principaux (scripts/)

| Chemin | Description | Exemple | Explication |
|---|---|---|---|
| `slurmray/cli.py` | Interface CLI principale | `slurmray curnagl` ou `slurmray desi` | *Lance l'interface interactive pour gérer les jobs et accéder au dashboard. Supporte Curnagl (Slurm) et Desi (ISIPOL09). Par défaut, affiche l'aide si aucun cluster n'est spécifié.* |

## Scripts exécutables secondaires (scripts/utils/)

| Chemin | Description | Exemple | Explication |
|---|---|---|---|
| `tests/test_gpu_dashboard_long.py` | Test GPU et dashboard avec job long | `poetry run python tests/test_gpu_dashboard_long.py` | *Lance un job GPU de 5 minutes pour tester le dashboard via l'interface CLI* |
| `tests/manual_test_desi_gpu_dashboard.py` | Test manuel complet pour Desi | `python tests/manual_test_desi_gpu_dashboard.py` | *Vérifie la connexion, le GPU, Ray et le Dashboard sur Desi* |

## Usage

### Mode 1: Slurm Cluster (Curnagl)

```python
from slurmray.RayLauncher import RayLauncher
import ray
import torch

def example_func(x):
    result = (
        ray.cluster_resources(),
        f"GPU is available : {torch.cuda.is_available()}",
        x + 1,
    )
    return result

launcher = RayLauncher(
    project_name="example_slurm",
    func=example_func,
    args={"x": 1},
    files=[],  # List of files to push to the cluster
    modules=[],  # List of modules to load (CUDA & CUDNN auto-added if use_gpu=True)
    node_nbr=1,  # Number of nodes to use
    use_gpu=True,  # Request GPU resources
    memory=8,  # RAM per node in GB
    max_running_time=5,  # Maximum runtime in minutes
    runtime_env={"env_vars": {"NCCL_SOCKET_IFNAME": "eno1"}},
    server_run=True,  # Run on cluster, not locally
    server_ssh="curnagl.dcsr.unil.ch",  # Slurm cluster address
    server_username="your_username",
    server_password=None,  # Will be prompted or loaded from .env
    cluster="slurm",  # Use Slurm backend (default)
)

# Note: When running with server_run=True, SlurmRay automatically sets up an SSH tunnel 
# to the Ray Dashboard, accessible at http://localhost:8888 during job execution.

result = launcher()
print(result)
```

### Mode 2: Desi Server (ISIPOL09)

```python
from slurmray.RayLauncher import RayLauncher
import ray

def example_func(x):
    result = (
        ray.cluster_resources(),
        x * 2,
    )
    return result

launcher = RayLauncher(
    project_name="example_desi",
    func=example_func,
    args={"x": 21},
    files=[],  # List of files to push to the server
    node_nbr=1,  # Always 1 for Desi (single server)
    use_gpu=False,  # GPU available via Smart Lock
    memory=8,  # Not enforced, shared resource
    max_running_time=30,  # Not enforced by scheduler
    server_run=True,  # Run on remote server
    server_ssh="130.223.73.209",  # Desi server IP (or use default)
    server_username="your_username",  # Will be loaded from DESI_USERNAME env var if not provided
    server_password=None,  # Will be prompted or loaded from DESI_PASSWORD env var
    cluster="desi",  # Use Desi backend (Smart Lock scheduling)
)

result = launcher()
print(result)
```

### Environment Variables

You can store credentials in a `.env` file to avoid entering them each time:

```bash
# For Curnagl
CURNAGL_USERNAME=your_username
CURNAGL_PASSWORD=your_password

# For Desi
DESI_USERNAME=your_username
DESI_PASSWORD=your_password
```

**Note:** The `.env` file should be in your `.gitignore` to avoid committing credentials.

## Key Differences Between Modes

| Feature | Slurm Mode | Desi Mode |
|---|---|---|
| **Scheduler** | Slurm (sbatch/squeue) | Smart Lock (file-based) |
| **Multi-node** | Supported (`node_nbr > 1`) | Single node only |
| **Modules** | Supported (`module load`) | Not supported |
| **Memory allocation** | Enforced by Slurm | Shared resource |
| **Time limit** | Enforced by Slurm | Not enforced |
| **Queue management** | Slurm queue | Smart Lock queue |
| **Default server** | `curnagl.dcsr.unil.ch` | `130.223.73.209` |

## Function Serialization and Python Version Compatibility

SlurmRay uses **source code extraction** (via `inspect.getsource()` or `dill.source.getsource()`) as the primary method for function serialization. This approach provides better compatibility across Python versions (e.g., Python 3.12 locally and Python 3.8 on the remote server) compared to bytecode serialization.

### How It Works

1. **Source extraction**: The function's source code is extracted and saved to `func_source.py`
2. **Remote execution**: The source code is executed on the remote server, avoiding bytecode incompatibilities
3. **Fallback**: If source extraction fails, SlurmRay falls back to `dill` bytecode serialization (may fail with version mismatches)

### Limitations

**Functions with closures**: Only the function body is captured, not the captured variables. Functions that depend on closure variables may fail at runtime.

**Functions with global dependencies**: Global variables referenced in the function are not automatically included. Ensure all required globals are available on the remote server or pass them as function arguments.

**Built-in functions**: Built-in functions (e.g., `len`, `max`) cannot be serialized via source extraction and will fall back to `dill`.

**Dynamically created functions**: Functions created at runtime or in interactive shells may not have accessible source code.

### Best Practices

- **Prefer simple functions**: Functions with minimal dependencies work best
- **Pass dependencies as arguments**: Instead of using closures or globals, pass required values as function arguments
- **Test locally first**: Validate your function works correctly before submitting to the cluster
- **Check logs**: If source extraction fails, check the logs for warnings and ensure `func.pkl` fallback is available

## Tests

The project includes simple "hello world" tests to quickly validate that SLURM_RAY works correctly after major modifications. These tests can be executed directly or via pytest.

### Running tests directly

```bash
# Test CPU
poetry run python tests/test_hello_world_cpu.py

# Test GPU
poetry run python tests/test_hello_world_gpu.py
```

### Running tests with pytest

```bash
# Run all tests
poetry run pytest tests/

# Run specific test
poetry run pytest tests/test_hello_world_cpu.py
poetry run pytest tests/test_hello_world_gpu.py
```

The tests require credentials for the cluster. You can provide them via a `.env` file with `CURNAGL_USERNAME` and `CURNAGL_PASSWORD`, or they will be prompted interactively.

## Publishing to PyPI

This project uses [Poetry](https://python-poetry.org/) for package management and publishing. Follow these steps to publish a new version to PyPI:

### 1. Update the version

Increment the version in `pyproject.toml` according to the type of change:

```bash
# Automatic version bumping
poetry version patch   # 3.6.4 -> 3.6.5 (bugfix)
poetry version minor   # 3.6.4 -> 3.7.0 (new feature)
poetry version major   # 3.6.4 -> 4.0.0 (breaking change)
```

Or manually edit the `version` field in `pyproject.toml`.

### 2. Build the package

```bash
poetry build
```

This creates distribution files in the `dist/` directory:
- `slurmray-{version}.tar.gz` (source distribution)
- `slurmray-{version}-py3-none-any.whl` (wheel)

### 3. Configure PyPI credentials

**First-time setup:**

1. Create an API token on [PyPI](https://pypi.org/manage/account/token/)
2. Configure Poetry to use the token:

```bash
poetry config pypi-token.pypi your-token-here
```

**Alternative:** Poetry will prompt for credentials during publishing. Use `__token__` as username and your API token as password.

### 4. Publish to PyPI

**Production (PyPI):**

```bash
poetry publish
```

**Testing (TestPyPI):**

To test the publishing process without affecting production:

```bash
poetry publish --repository testpypi
```

### Pre-publication checklist

Before publishing, ensure:

- [ ] Version incremented in `pyproject.toml`
- [ ] All tests pass (`poetry run pytest tests/`)
- [ ] README.md is up to date
- [ ] Code tested locally
- [ ] `poetry build` completes without errors
- [ ] PyPI credentials configured

### Quick reference

```bash
# Complete publishing workflow
poetry version patch          # Update version
poetry build                  # Build package
poetry publish                # Publish to PyPI

# Optional: test on TestPyPI first
poetry publish --repository testpypi
```

**Important notes:**

- Each version must be unique on PyPI (versions cannot be overwritten)
- TestPyPI is useful for testing the publishing process
- Consider creating a Git tag after publishing:
  ```bash
  git tag v3.6.5
  git push origin v3.6.5
  ```

## Launcher documentation

The Launcher documentation is available [here](https://htmlpreview.github.io/?https://raw.githubusercontent.com/hjamet/SLURM_RAY/main/documentation/RayLauncher.html).

# Roadmap

| Tâche | Objectif | État | Dépendances |
|---|---|---|---|
| **Corriger les incompatibilités avec Curnagl** | Analyser et corriger les incompatibilités potentielles entre le code actuel (optimisé pour Desi/Local) et l'environnement Curnagl (versions Python, modules SLURM, partitions). Vérifier que les modifications récentes n'ont pas cassé le support Curnagl et adapter le `RayLauncher` si nécessaire pour assurer une compatibilité parfaite avec le cluster de l'UNIL. | 📅 À faire | - |
| **Optimiser la gestion du stockage et le nettoyage des fichiers** | Optimiser la gestion du stockage et du nettoyage pour améliorer les performances globales du système. Implémenter un cache intelligent pour réutiliser le virtualenv entre exécutions si les dépendances n'ont pas changé, évitant ainsi de recréer l'environnement à chaque fois. Nettoyer systématiquement les fichiers temporaires après téléchargement réussi des résultats pour éviter l'accumulation de données inutiles. Optimiser la génération de `requirements.txt` pour qu'elle soit plus rapide et plus précise. Corriger les incohérences potentielles de versions Python entre l'environnement local et distant pour garantir la compatibilité. | 📅 À faire | - |
| **Ajouter la possibilité de forcer la réinstallation complète des requirements** | Actuellement, les environnements virtuels (`.venv` pour Slurm, `venv` pour Desi) sont créés automatiquement s'ils n'existent pas, mais il n'existe pas de mécanisme pour forcer une réinstallation complète en cas de corruption, d'incompatibilité de versions, ou de besoin de nettoyage. Cette tâche consiste à ajouter une option (flag ou paramètre) permettant de forcer la suppression complète de l'environnement virtuel existant et sa recréation depuis zéro, suivie d'une réinstallation complète de tous les packages depuis `requirements.txt`. L'implémentation doit couvrir à la fois l'environnement local (Poetry avec `.venv`) et les environnements distants (Slurm avec `.venv` dans `slurmray-server/`, Desi avec `venv` dans le répertoire de projet). Pour l'environnement local, cela pourrait être un script d'installation (`install.sh` ou commande Poetry) avec un flag `--force-reinstall` ou `--clean`. Pour les environnements distants, cela pourrait être un paramètre du `RayLauncher` (ex: `force_reinstall_venv=True`) qui modifie les scripts générés (`slurmray_server.sh` pour Slurm, `runner_script.sh` pour Desi) pour supprimer le venv existant avant création. La suppression doit être sécurisée (vérifier que le venv n'est pas utilisé par un job en cours) et la recréation doit suivre exactement le même processus que la création normale, garantissant la cohérence. | 📅 À faire | - |
| **Améliorer la gestion des credentials (username/password) via .env** | Modifier RayLauncher pour charger automatiquement `server_username` et `server_password` depuis un fichier `.env` local, tout en gardant la rétrocompatibilité avec les paramètres explicites passés au constructeur. Le système doit d'abord vérifier les variables d'environnement (via `python-dotenv`), puis les paramètres explicites, et enfin demander interactivement si aucun n'est trouvé. Cette amélioration améliore la sécurité (évite de hardcoder les mots de passe) et l'ergonomie pour les utilisateurs fréquents qui peuvent stocker leurs credentials de manière sécurisée dans un fichier `.env` ignoré par Git. | 📅 À faire | - |
| **Mettre à jour la documentation pour tout avoir dans le repo** | Remplacer les liens externes dans README.md par du contenu local, intégrer la documentation de RayLauncher directement dans le repository pour éviter les dépendances vers des sites externes. Migrer toute la documentation externe (liens actuels vers sites tiers ou HTML prévisualisés) directement dans le dépôt (dossier `docs/` ou Markdown). L'objectif est que le repository soit auto-suffisant et que la documentation versionnée suive l'évolution du code. Cela garantit que la documentation est toujours à jour et accessible même si les sites externes changent ou disparaissent. | 📅 À faire | - |
| **Créer des scripts de test GPU et dashboard pour Curnagl et Desi** | Créer deux scripts de test automatisés et complets pour valider le bon fonctionnement des deux clusters. Le script pour Curnagl (`tests/test_curnagl_gpu_dashboard.py`) doit lancer un job Slurm avec GPU, vérifier l'accès au GPU via PyTorch (disponibilité CUDA, nombre de GPUs, noms des GPUs), valider les ressources Ray, et s'assurer que le dashboard Ray est accessible localement via le tunnel SSH automatique sur http://localhost:8888 pendant l'exécution du job. Le script pour Desi (`tests/test_desi_gpu_dashboard.py`) doit effectuer les mêmes vérifications mais adaptées au backend Desi (Smart Lock, pas de modules Slurm). Les deux scripts doivent inclure des vérifications explicites de l'accessibilité du dashboard local (test de connexion HTTP sur le port local, vérification que le tunnel SSH est actif, validation que le contenu du dashboard répond correctement). Après la création des scripts, exécuter le script Desi pour valider immédiatement l'accès au GPU et l'accessibilité locale du dashboard sur le serveur ISIPOL09. Ces scripts serviront de tests de validation rapide après toute modification importante du système de lancement ou des backends. | 📅 À faire | - |
