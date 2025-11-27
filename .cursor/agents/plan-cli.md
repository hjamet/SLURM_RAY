# Plan d'implémentation - Interface Interactive (CLI)

## 1. Fichier `slurmray/cli.py`
Créer un nouveau module qui contiendra la logique de l'interface interactive.
- **Imports** : `rich` (Console, Table, Panel, Prompt), `time`, `subprocess`, `os`, `paramiko`, `RayLauncher` (pour réutiliser SSHTunnel et les méthodes de parsing).
- **Fonctions principales** :
  - `get_jobs()`: Wrapper autour de `squeue` avec parsing (réutilisation logique RayLauncher).
  - `display_jobs(jobs)`: Affichage avec Rich Table.
  - `cancel_job(job_id)`: Wrapper `scancel`.
  - `open_dashboard(job_id)`: Logique complexe de tunnel SSH.
  - `main_menu()`: Boucle principale avec Rich Prompt.

## 2. Points d'entrée
- **`pyproject.toml`** : Ajouter `[tool.poetry.scripts]` -> `slurmray = "slurmray.cli:main"`.
- **`slurmray/__main__.py`** : Rediriger vers `slurmray.cli.main()` pour supporter `python -m slurmray`.

## 3. Réutilisation de code
- Il faudra peut-être importer `RayLauncher` ou copier/adapter certaines méthodes privées (`__get_head_node_from_job_id`) si elles ne sont pas accessibles. *Décision : Pour l'instant, dupliquer ou adapter le code minimal nécessaire pour éviter de casser RayLauncher, ou rendre les méthodes publiques si facile.*
- Pour `SSHTunnel`, il est dans `RayLauncher.py`. On peut l'importer `from slurmray.RayLauncher import SSHTunnel`.

## 4. Fonctionnalités CLI
- **Liste des jobs** : Afficher ID, Nom, Partition, Statut, Temps, Nœuds.
- **Actions** :
  - [r] Refresh
  - [c] Cancel Job (demander ID)
  - [d] Dashboard (demander ID du job Ray)
  - [q] Quit

## 5. Validation
- Lancer `poetry run slurmray`.
- Tester les commandes.

