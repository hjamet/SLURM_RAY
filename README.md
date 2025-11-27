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
| **Corriger les incompatibilités avec Curnagl** | Analyser et corriger les incompatibilités entre le code actuel et la documentation Curnagl actuelle. Cette tâche implique la vérification et l'ajustement des versions Python utilisées, l'identification et la correction des modules chargés via `module load`, la mise à jour des arguments SLURM qui pourraient être dépréciés, et la validation des partitions disponibles sur le cluster. L'objectif est de garantir que le code fonctionne correctement avec l'environnement Curnagl actuel, en s'assurant que toutes les dépendances système sont compatibles et que les jobs peuvent être soumis et exécutés sans erreur. Cette étape est fondamentale avant toute évolution majeure du code. | 🏗️ En cours | - |
| **Corriger et rediriger automatiquement le dashboard Ray vers local** | Corriger le bug de configuration du dashboard dans RayLauncher.py (ligne 199) qui empêche le lancement correct du dashboard Ray. Une fois le bug corrigé, implémenter une redirection automatique du dashboard Ray vers la machine locale via port forwarding SSH. Le système doit établir un tunnel SSH automatiquement lorsque le job démarre, permettant l'accès au dashboard sur `http://localhost:8888` pendant l'exécution du job. Cette fonctionnalité améliore significativement l'expérience utilisateur en permettant un monitoring en temps réel des ressources et de l'état des tâches Ray sans nécessiter de configuration manuelle de tunnels SSH. | 🏗️ En cours | - |
| **Intégrer l'ouverture automatique du dashboard Ray** | Intégrer l'ouverture automatique du dashboard Ray dans l'interface interactive de gestion des jobs SLURM créée précédemment. Cette fonctionnalité doit permettre d'ouvrir le dashboard en local (http://localhost:8888) avec gestion automatique du port forwarding SSH si nécessaire. L'utilisateur doit pouvoir sélectionner un job en cours d'exécution depuis l'interface CLI et avoir le dashboard qui s'ouvre automatiquement dans son navigateur, avec le tunnel SSH établi en arrière-plan. Cela simplifie grandement l'accès aux métriques de performance pour l'utilisateur final. | 📅 À faire | - |
| **Améliorer la gestion des credentials (username/password) via .env** | Modifier RayLauncher pour charger automatiquement `server_username` et `server_password` depuis un fichier `.env` local, tout en gardant la rétrocompatibilité avec les paramètres explicites passés au constructeur. Le système doit d'abord vérifier les variables d'environnement (via `python-dotenv`), puis les paramètres explicites, et enfin demander interactivement si aucun n'est trouvé. Cette amélioration améliore la sécurité (évite de hardcoder les mots de passe) et l'ergonomie pour les utilisateurs fréquents qui peuvent stocker leurs credentials de manière sécurisée dans un fichier `.env` ignoré par Git. | 📅 À faire | - |
| **Optimiser la gestion du stockage et le nettoyage des fichiers** | Optimiser la gestion du stockage et du nettoyage pour améliorer les performances globales du système. Implémenter un cache intelligent pour réutiliser le virtualenv entre exécutions si les dépendances n'ont pas changé, évitant ainsi de recréer l'environnement à chaque fois. Nettoyer systématiquement les fichiers temporaires après téléchargement réussi des résultats pour éviter l'accumulation de données inutiles. Optimiser la génération de `requirements.txt` pour qu'elle soit plus rapide et plus précise. Corriger les incohérences potentielles de versions Python entre l'environnement local et distant pour garantir la compatibilité. | 📅 À faire | Corriger les incompatibilités avec Curnagl |
| **Refactoring Architecture Strategy** | Refactoriser l'architecture du projet pour introduire le Design Pattern "Strategy" afin de préparer le support multi-backend. Créer une classe abstraite `ClusterBackend` définissant l'interface commune (méthodes `submit`, `status`, `cancel`, `get_logs`, etc.), puis encapsuler toute la logique SLURM actuelle dans une classe concrète `SlurmBackend` qui implémente cette interface. Cette étape est cruciale pour permettre l'ajout futur du backend "Desi" sans complexifier le code avec des conditions multiples. Le refactoring doit être effectué sans régression, en s'assurant que toutes les fonctionnalités existantes continuent de fonctionner exactement comme avant. | 📅 À faire | Corriger les incompatibilités avec Curnagl |
| **Tester le package SLURM_RAY sur CPU et GPU** | Créer et exécuter des tests fonctionnels complets pour vérifier que le package fonctionne correctement avec des fonctions simples sur CPU et/ou GPU via Ray sur un cluster SLURM. Ces tests doivent être des "smoke tests" qui valident la chaîne complète : soumission du job, exécution sur le cluster, récupération des résultats. Les tests doivent être rapides à exécuter et permettre de valider rapidement que le système fonctionne correctement après chaque modification majeure. Ils serviront de garde-fou pour éviter les régressions lors des évolutions futures du code. | 📅 À faire | Corriger les incompatibilités avec Curnagl, Optimiser la gestion du stockage et le nettoyage des fichiers |
| **Implémentation Backend Desi** | Implémenter le backend Desi (SSH/SFTP) avec exécution Ray isolée et gestion des ports dynamiques pour le support multi-utilisateurs. Ce backend doit gérer une exécution "stateless" via SSH/SFTP : création d'un dossier temporaire unique par job sur le serveur distant, upload du code sérialisé et des dépendances, exécution d'un script "runner" distant qui lance une instance Ray isolée avec des ports dynamiques pour éviter les conflits entre utilisateurs, récupération des résultats, et suppression impérative du dossier temporaire (nettoyage fail-fast) pour ne pas polluer le serveur partagé. | 📅 À faire | Refactoring Architecture Strategy |
| **Unification et Arguments** | Unifier l'interface RayLauncher pour gérer proprement les deux backends (SLURM et Desi) et adapter la validation des arguments. Mettre à jour la classe principale `RayLauncher` (le Context du pattern Strategy) pour instancier dynamiquement le bon backend selon un argument `cluster='curnagl'` ou `cluster='desi'`. Implémenter une validation des arguments conditionnelle : avertir si des arguments spécifiques à SLURM (partitions, time_limit) sont passés en mode Desi, et adapter la gestion de la demande de GPU (`use_gpu`) pour qu'elle fonctionne correctement avec le backend Desi. | 📅 À faire | Implémentation Backend Desi |
| **Rebranding et Documentation** | Mettre à jour la documentation et les métadonnées pour officialiser le support DESI @ HEC UNIL. Actualiser le README, les docstrings et les métadonnées PyPI pour documenter clairement les deux modes d'exécution (Curnagl/SLURM et Desi/SSH), les pré-requis respectifs, et fournir des exemples d'utilisation adaptés aux nouveaux utilisateurs du département. Cette tâche inclut également la mise à jour de l'identité visuelle du projet pour refléter son nouveau statut d'outil officiel du département. | 📅 À faire | Unification et Arguments |
| **Mettre à jour la documentation pour tout avoir dans le repo** | Remplacer les liens externes dans README.md par du contenu local, intégrer la documentation de RayLauncher directement dans le repository pour éviter les dépendances vers des sites externes. Migrer toute la documentation externe (liens actuels vers sites tiers ou HTML prévisualisés) directement dans le dépôt (dossier `docs/` ou Markdown). L'objectif est que le repository soit auto-suffisant et que la documentation versionnée suive l'évolution du code. Cela garantit que la documentation est toujours à jour et accessible même si les sites externes changent ou disparaissent. | 📅 À faire | Tester le package SLURM_RAY sur CPU et GPU, Améliorer la gestion des credentials (username/password) via .env, Corriger les incompatibilités avec Curnagl, Rebranding et Documentation |
