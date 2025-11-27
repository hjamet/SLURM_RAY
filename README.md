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
| Dashboard | Intégré | Tunnel SSH automatique vers port 8888 |
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
| `slurmray/cli.py` | Interface CLI principale | `slurmray --help` | *Point d'entrée pour les commandes CLI futures* |

## Scripts exécutables secondaires (scripts/utils/)

| Chemin | Description | Exemple | Explication |
|---|---|---|---|
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
    server_username="your_username",
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
| **Simplifier Affichage Queue SLURM** | Remplacer l'affichage verbeux et polluant de la file d'attente actuel par un message de statut synthétique et apaisé : 'Waiting for job... (Position in queue : x/X)'. Ce message ne doit être rafraîchi que toutes les 30 secondes pour éviter de spammer la console et les logs, améliorant ainsi l'expérience utilisateur (UX) durant les phases d'attente. | 🏗️ En cours | - |
| **Intégrer l'ouverture automatique du dashboard Ray** | Intégrer l'ouverture automatique du dashboard Ray dans l'interface interactive de gestion des jobs SLURM créée précédemment. Cette fonctionnalité doit permettre d'ouvrir le dashboard en local (http://localhost:8888) avec gestion automatique du port forwarding SSH si nécessaire. L'utilisateur doit pouvoir sélectionner un job en cours d'exécution depuis l'interface CLI et avoir le dashboard qui s'ouvre automatiquement dans son navigateur, avec le tunnel SSH établi en arrière-plan. Cela simplifie grandement l'accès aux métriques de performance pour l'utilisateur final. | 🏗️ En cours | Interface Interactive Jobs SLURM |
| **Consolider le transfert de code source pour la compatibilité Python** | Généraliser et nettoyer le mécanisme de transfert de code source (actuellement implémenté via `inspect.getsource` pour Desi) au lieu du bytecode `dill` pour garantir la compatibilité entre des versions Python locales (ex: 3.12) et distantes (ex: 3.8) sur tous les backends. Cela implique de tester les limites de `inspect`, d'envisager des alternatives comme `dill.source`, et de rendre ce mécanisme robuste pour toutes les fonctions utilisateur. | 📅 À faire | - |
| **Corriger les incompatibilités avec Curnagl** | Analyser et corriger les incompatibilités potentielles entre le code actuel (optimisé pour Desi/Local) et l'environnement Curnagl (versions Python, modules SLURM, partitions). Vérifier que les modifications récentes n'ont pas cassé le support Curnagl et adapter le `RayLauncher` si nécessaire pour assurer une compatibilité parfaite avec le cluster de l'UNIL. | 📅 À faire | - |
| **Optimiser la gestion du stockage et le nettoyage des fichiers** | Optimiser la gestion du stockage et du nettoyage pour améliorer les performances globales du système. Implémenter un cache intelligent pour réutiliser le virtualenv entre exécutions si les dépendances n'ont pas changé, évitant ainsi de recréer l'environnement à chaque fois. Nettoyer systématiquement les fichiers temporaires après téléchargement réussi des résultats pour éviter l'accumulation de données inutiles. Optimiser la génération de `requirements.txt` pour qu'elle soit plus rapide et plus précise. Corriger les incohérences potentielles de versions Python entre l'environnement local et distant pour garantir la compatibilité. | 📅 À faire | - |
| **Interface Interactive Jobs SLURM** | Développer une interface en ligne de commande (TUI simple ou menu interactif) accessible via `python -m slurmray`. Cette interface permettra aux utilisateurs de lister leurs jobs en cours, de voir leur position précise dans la file d'attente, et de les annuler facilement sans avoir à mémoriser les commandes `scancel` ou `squeue` complexes. | 📅 À faire | Simplifier Affichage Queue SLURM |
| **Intégration Point d'Entrée** | Finaliser l'implémentation du fichier `__main__.py` dans le package pour exposer proprement l'interface interactive créée précédemment. S'assurer que la commande `python -m slurmray` est intuitive et gère correctement les exceptions (ex: absence de credentials). | 📅 À faire | Interface Interactive Jobs SLURM |
| **Améliorer la gestion des credentials (username/password) via .env** | Modifier RayLauncher pour charger automatiquement `server_username` et `server_password` depuis un fichier `.env` local, tout en gardant la rétrocompatibilité avec les paramètres explicites passés au constructeur. Le système doit d'abord vérifier les variables d'environnement (via `python-dotenv`), puis les paramètres explicites, et enfin demander interactivement si aucun n'est trouvé. Cette amélioration améliore la sécurité (évite de hardcoder les mots de passe) et l'ergonomie pour les utilisateurs fréquents qui peuvent stocker leurs credentials de manière sécurisée dans un fichier `.env` ignoré par Git. | 📅 À faire | - |
| **Mettre à jour la documentation pour tout avoir dans le repo** | Remplacer les liens externes dans README.md par du contenu local, intégrer la documentation de RayLauncher directement dans le repository pour éviter les dépendances vers des sites externes. Migrer toute la documentation externe (liens actuels vers sites tiers ou HTML prévisualisés) directement dans le dépôt (dossier `docs/` ou Markdown). L'objectif est que le repository soit auto-suffisant et que la documentation versionnée suive l'évolution du code. Cela garantit que la documentation est toujours à jour et accessible même si les sites externes changent ou disparaissent. | 📅 À faire | - |
