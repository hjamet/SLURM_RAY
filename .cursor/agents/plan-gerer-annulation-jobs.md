# Plan d'implémentation - Gestion de l'annulation des jobs SLURM

Ce plan détaille les modifications nécessaires pour gérer proprement l'annulation des jobs SLURM lors d'une interruption locale (Ctrl+C) du script.

## 1. Modification de `slurmray/RayLauncher.py`

### A. Structure de données
- Ajouter `self.job_id = None` dans `__init__` pour stocker l'ID du job SLURM courant.
- Ajouter `self.ssh_client = None` dans `__init__` pour maintenir la connexion SSH active accessible au gestionnaire de signaux.

### B. Gestionnaire de signaux (Signal Handler)
Implémenter une méthode `_handle_signal(self, signum, frame)` qui sera appelée lors d'un `SIGINT` ou `SIGTERM`.
- **Logique :**
  1. Logger un message d'avertissement : "Interruption reçue (Signal X). Nettoyage en cours..."
  2. Vérifier si `self.job_id` est défini.
  3. **Si mode Cluster (`self.cluster`)** :
     - Exécuter `scancel {self.job_id}` via `subprocess`.
     - Logger "Job {self.job_id} annulé localement."
  4. **Si mode Server Run (`self.server_run`)** :
     - Vérifier si `self.ssh_client` est connecté.
     - Si connecté, exécuter `scancel {self.job_id}` via SSH.
     - Sinon, tenter une reconnexion rapide (optionnel, risqué si réseau coupé, privilégier l'existant).
     - Logger "Job distant {self.job_id} annulé."
  5. Fermer proprement les connexions (`self.ssh_client.close()` si ouvert).
  6. Quitter avec `sys.exit(1)`.

### C. Intégration dans le flux d'exécution
- **Dans `__call__`** :
  - Enregistrer le handler au début : `signal.signal(signal.SIGINT, self._handle_signal)`.
  - Utiliser un bloc `try...finally` pour s'assurer que le handler est désenregistré ou restauré à la fin de l'exécution, évitant des effets de bord si `RayLauncher` est utilisé plusieurs fois dans un script.
- **Dans `__launch_job`** :
  - Mettre à jour `self.job_id` dès que le job est soumis et l'ID récupéré.
- **Dans `__launch_server`** :
  - Stocker l'objet `ssh_client` dans `self.ssh_client`.
  - Mettre à jour `self.job_id` dès que l'ID est récupéré (via output ou squeue).

## 2. Validation
- Créer un script de test manuel `tests/manual_test_interruption.py` qui lance un job simple (ex: sleep 60) via `RayLauncher`.
- Instructions pour l'utilisateur : lancer le script, attendre que le job soit soumis, faire Ctrl+C, vérifier via `squeue` que le job a disparu.

## 3. Rapport
- Générer le rapport final `.cursor/agents/rapport-gerer-annulation-jobs-interruption-locale.md`.

