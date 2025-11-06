## Contexte

Lors de l'analyse du comportement du système lors d'une interruption locale (Ctrl+C), il a été découvert que si la commande est interrompue localement, le job SLURM continue à s'exécuter sur le cluster. Le code actuel ne gère pas les signaux d'interruption (KeyboardInterrupt, SIGINT, SIGTERM) et ne nettoie pas les jobs SLURM en cours lors de l'arrêt du processus local. Cela peut entraîner une consommation inutile de ressources sur le cluster et des jobs "fantômes" qui continuent à tourner.

## Objectif

Implémenter une gestion robuste des interruptions locales qui annule automatiquement les jobs SLURM en cours sur le cluster lorsque le processus local est interrompu (Ctrl+C ou arrêt du processus). Le système doit capturer les signaux d'interruption, identifier les jobs SLURM actifs (via job ID ou nom de job), les annuler via `scancel`, et nettoyer les ressources locales avant de quitter proprement.

## Fichiers Concernés

### Du travail effectué précédemment :
- `slurmray/RayLauncher.py` : Contient la logique de lancement des jobs SLURM via `__launch_job` et `__launch_server`. Les méthodes `__call__` et les boucles d'attente doivent être protégées contre les interruptions.
- `slurmray/RayLauncher.py` (lignes 87-127) : La méthode `__call__` contient une boucle d'attente qui peut être interrompue sans nettoyage.
- `slurmray/RayLauncher.py` (lignes 277-396) : La méthode `__launch_job` soumet le job via `sbatch` mais ne stocke pas le job ID pour pouvoir l'annuler plus tard.
- `slurmray/RayLauncher.py` (lignes 398-506) : La méthode `__launch_server` lance le script serveur via SSH mais ne gère pas l'interruption pour annuler le job sur le cluster distant.

### Fichiers potentiellement pertinents pour l'exploration :
- `slurmray/assets/slurmray_server.sh` : Script shell qui lance le serveur sur le cluster, pourrait nécessiter une gestion de signaux.
- `slurmray/assets/slurmray_server_template.py` : Template du script serveur qui crée un RayLauncher sur le cluster.

### Recherches à effectuer :
- Recherche sémantique : "Comment capturer et gérer KeyboardInterrupt dans Python pour nettoyer les ressources ?"
- Recherche sémantique : "Comment obtenir le job ID SLURM après soumission via sbatch ?"
- Recherche web : "Meilleures pratiques pour gérer les signaux d'interruption dans Python avec subprocess et SSH"
- Documentation : Lire la documentation de `subprocess.Popen` et `paramiko.SSHClient` pour comprendre comment gérer les interruptions de connexions SSH

### Fichiers de résultats d'autres agents (si pertinents) :
- Aucun pour le moment

**Fichier output pour le rapport final :**
- `.cursor/agents/rapport-gerer-annulation-jobs-interruption-locale.md`

## Instructions de Collaboration

**OBLIGATOIRE ET CRITIQUE** : Cette section doit être extrêmement directive et impérative. Tu DOIS spécifier que l'agent :

- **EST INTERDIT** de commencer à implémenter quoi que ce soit immédiatement
- **DOIT** lire EXHAUSTIVEMENT tous les fichiers listés dans "Fichiers Concernés" avant toute action
- **DOIT** effectuer toutes les recherches sémantiques et web mentionnées
- **DOIT** lire le README et toute documentation pertinente
- **DOIT** atteindre une compréhension approfondie du contexte et du projet avant toute discussion
- **DOIT** discuter avec l'utilisateur pour clarifier les attentes précises, poser des questions sur les contraintes techniques (comment identifier les jobs à annuler, gestion des jobs distants via SSH, etc.), et établir un plan d'action détaillé ensemble
- **DOIT TOUJOURS** créer le fichier de rapport final dans le fichier output mentionné après avoir terminé (voir section "Instructions pour les Rapports Finaux")
- Seulement APRÈS avoir complété cette exploration exhaustive et cette planification collaborative, peut commencer toute implémentation

Emphasizer que l'exploration est OBLIGATOIRE, pas optionnelle.

