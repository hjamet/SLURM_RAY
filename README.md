# SLURM_RAY

👉[Full documentation](https://www.henri-jamet.com/docs/slurmray/slurm-ray/)

## Description

**SlurmRay** is a module for effortlessly distributing tasks on a [Slurm](https://slurm.schedmd.com/) cluster using the [Ray](https://ray.io/) library. **SlurmRay** was initially designed to work with the [Curnagl](https://wiki.unil.ch/ci/books/high-performance-computing-hpc/page/curnagl) cluster at the *University of Lausanne*. However, it should be able to run on any [Slurm](https://slurm.schedmd.com/) cluster with a minimum of configuration.

## Installation

**SlurmRay** is designed to run both locally and on a cluster without any modification. This design is intended to allow work to be carried out on a local machine until the script seems to be working. It should then be possible to run it using all the resources of the cluster without having to modify the code.

```bash
pip install slurmray
```

## Usage

```python
from slurmray.RayLauncher import RayLauncher
import ray
import torch

def function_inside_function():
    with open("slurmray/RayLauncher.py", "r") as f:
        return f.read()[0:10]

def example_func(x):
    result = (
        ray.cluster_resources(),
        f"GPU is available : {torch.cuda.is_available()}",
        x + 1,
        function_inside_function(),
    )
    return result

launcher = RayLauncher(
    project_name="example", # Name of the project (will create a directory with this name in the current directory)
    func=example_func, # Function to execute
    args={"x": 1}, # Arguments of the function
    files=["slurmray/RayLauncher.py"], # List of files to push to the cluster (file path will be recreated on the cluster)
    modules=[], # List of modules to load on the curnagl Cluster (CUDA & CUDNN are automatically added if use_gpu=True)
    node_nbr=1, # Number of nodes to use
    use_gpu=True, # If you need A100 GPU, you can set it to True
    memory=8, # In MegaBytes
    max_running_time=5, # In minutes
    runtime_env={"env_vars": {"NCCL_SOCKET_IFNAME": "eno1"}}, # Example of environment variable
    server_run=True, # To run the code on the cluster and not locally
    server_ssh="curnagl.dcsr.unil.ch", # Address of the SLURM server
    server_username="hjamet", # Username to connect to the server
    server_password=None, # Will be asked in the terminal
)

result = launcher()
print(result)
```

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
|-------|----------|------|-------------|
| **Corriger les incompatibilités Curnagl** | Analyser et corriger les incompatibilités critiques entre le code actuel et l'environnement du cluster Curnagl. Cela inclut la vérification des versions Python, l'ajustement des directives de chargement des modules (module load), la correction des arguments SLURM dépréciés, et la validation des partitions disponibles. L'objectif est de restaurer une exécution stable des jobs simples sur Curnagl avant toute évolution majeure. | 🏗️ En cours | - |
| **Corriger Dashboard Ray** | Résoudre le bug de configuration à la ligne 199 de `RayLauncher.py` qui empêche le lancement correct du dashboard. Implémenter ensuite une redirection de port automatique via le tunnel SSH existant pour rendre le dashboard Ray accessible localement sur `http://localhost:8888` pendant l'exécution du job, offrant ainsi une visibilité en temps réel à l'utilisateur. | 🏗️ En cours | - |
| **Simplifier Affichage Queue SLURM** | Remplacer l'affichage verbeux et polluant de la file d'attente actuel par un message de statut synthétique et apaisé : 'Waiting for job... (Position in queue : x/X)'. Ce message ne doit être rafraîchi que toutes les 30 secondes pour éviter de spammer la console et les logs, améliorant ainsi l'expérience utilisateur (UX) durant les phases d'attente. | 🏗️ En cours | - |
| **Refactoring Architecture Strategy** | Restructurer le cœur de l'application `RayLauncher.py` en appliquant le Design Pattern "Strategy". Il s'agit de créer une classe abstraite `ClusterBackend` définissant l'interface commune (`submit`, `status`, `cancel`, `get_logs`), puis d'encapsuler toute la logique Slurm actuelle dans une classe concrète `SlurmBackend`. Cette étape est cruciale pour permettre l'ajout futur du backend "Desi" sans complexifier le code avec des conditions multiples. Le code existant doit être déplacé sans régression. | 📅 À faire | Corriger les incompatibilités Curnagl |
| **Implémentation Backend Desi** | Développer la classe `DesiBackend` implémentant `ClusterBackend` pour le serveur `isipol09`. Ce backend doit gérer une exécution "Stateless" via SSH/SFTP : création d'un dossier temporaire unique par job, upload du code sérialisé (cloudpickle) et des dépendances, exécution d'un script "runner" distant qui lance une instance Ray isolée (ports dynamiques), récupération des résultats, et suppression impérative du dossier temporaire (nettoyage fail-fast) pour ne pas polluer le serveur partagé. | 📅 À faire | Refactoring Architecture Strategy |
| **Unification et Arguments** | Mettre à jour la classe principale `RayLauncher` (le Context du pattern Strategy) pour instancier dynamiquement le bon backend selon l'argument `cluster='curnagl'` ou `cluster='desi'`. Implémenter une validation des arguments conditionnelle : avertir si des arguments spécifiques à Slurm (partitions, time_limit) sont passés en mode Desi, et adapter la gestion de la demande de GPU (`use_gpu`) pour qu'elle fonctionne correctement avec le backend Desi. | 📅 À faire | Implémentation Backend Desi |
| **Optimiser Stockage et Nettoyage** | Améliorer la performance et l'hygiène du projet : implémenter un système de cache intelligent pour éviter de recréer le virtualenv à chaque exécution si les dépendances n'ont pas changé, optimiser la génération du `requirements.txt`, et garantir un nettoyage systématique des fichiers temporaires locaux après le téléchargement des résultats. Corriger également les incohérences potentielles de versions Python entre le local et le distant. | 📅 À faire | Corriger les incompatibilités Curnagl |
| **Rebranding et Documentation** | Mettre à jour l'identité du projet pour refléter son nouveau statut d'outil officiel du département DESI @ HEC UNIL. Actualiser le README, les docstrings et les métadonnées PyPI pour documenter clairement les deux modes d'exécution (Curnagl/Slurm et Desi/SSH), les pré-requis respectifs, et fournir des exemples d'utilisation adaptés aux nouveaux utilisateurs du département. | 📅 À faire | Unification et Arguments |
| **Tester Package CPU/GPU** | Créer une suite de tests fonctionnels robustes (automatisables via CI si possible, ou scriptés) qui lancent de véritables petits jobs "Hello World" sur CPU et GPU. Ces tests serviront de "Smoke Tests" à lancer avant chaque release pour garantir que la chaîne complète (soumission -> exécution -> récupération) fonctionne sur les deux environnements cibles. | 📅 À faire | Refactoring Architecture Strategy, Optimiser Stockage et Nettoyage |
| **Interface Interactive Jobs SLURM** | Développer une interface en ligne de commande (TUI simple ou menu interactif) accessible via `python -m slurmray`. Cette interface permettra aux utilisateurs de lister leurs jobs en cours, de voir leur position précise dans la file d'attente, et de les annuler facilement sans avoir à mémoriser les commandes `scancel` ou `squeue` complexes. | 📅 À faire | Simplifier Affichage Queue SLURM |
| **Intégration Point d'Entrée** | Finaliser l'implémentation du fichier `__main__.py` dans le package pour exposer proprement l'interface interactive créée précédemment. S'assurer que la commande `python -m slurmray` est intuitive et gère correctement les exceptions (ex: absence de credentials). | 📅 À faire | Interface Interactive Jobs SLURM |
| **Ouverture Auto Dashboard** | Intégrer dans l'interface interactive et le launcher une fonctionnalité d'ouverture automatique du navigateur vers le dashboard Ray local (après établissement du tunnel SSH). Cela simplifie l'accès aux métriques de performance pour l'utilisateur final. | 📅 À faire | Interface Interactive Jobs SLURM, Corriger Dashboard Ray |
| **Améliorer Credentials .env** | Moderniser la gestion des identifiants en supportant nativement le chargement depuis un fichier `.env` local. Le launcher doit chercher `SLURM_USERNAME`/`SLURM_PASSWORD` (ou équivalents) dans l'environnement avant de demander à l'utilisateur ou d'utiliser les arguments, améliorant ainsi la sécurité et l'ergonomie pour les utilisateurs fréquents. | 📅 À faire | - |
| **Documentation Interne** | Migrer toute la documentation externe (liens actuels vers sites tiers ou HTML prévisualisés) directement dans le dépôt (dossier `docs/` ou Markdown). L'objectif est que le repository soit auto-suffisant et que la documentation versionnée suive l'évolution du code. | 📅 À faire | Rebranding et Documentation |
