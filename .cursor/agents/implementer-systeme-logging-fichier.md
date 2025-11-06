## Contexte

Actuellement, l'affichage en console utilise beaucoup de `print()` directs qui saturent la console, notamment pendant l'attente de nœuds disponibles (affichage de la queue SLURM toutes les 60 secondes ou à chaque changement). Il existe un fichier `queue.log` mais il ne couvre que la queue SLURM, pas toutes les étapes (installation du serveur, connexion SSH, upload de fichiers, attente de nœuds, etc.). Il serait utile d'avoir un système de logging centralisé dans un fichier constamment réécrit pour suivre toutes les étapes sans saturer la console.

## Objectif

Implémenter un système de logging dans un fichier pour centraliser tous les messages (installation du serveur, connexion SSH, upload de fichiers, attente de nœuds disponibles avec la queue SLURM, exécution du job, etc.). Le fichier doit être constamment réécrit (mode 'w') pour garder une trace à jour sans accumulation. Ajouter un paramètre `log_file` au constructeur de `RayLauncher` avec une valeur par défaut `logs/RayLauncher.log` (créer le dossier `logs/` si nécessaire). Optionnellement, garder un affichage minimal en console (messages critiques uniquement) et rediriger le reste vers le fichier de log.

## Fichiers Concernés

### Du travail effectué précédemment :
- `slurmray/RayLauncher.py` : Toutes les méthodes utilisant `print()` (lignes 102, 105, 116, 137, 155, 168, 182, 216, 285, 287, 299, 361, 376, 379, 393, 396, 405, 423, 428, 479, 487, 492, 498, 503, 505, 506, 510)
- `slurmray/RayLauncher.py` : Lignes 294-396 (méthode `__launch_job` avec affichage de la queue)
- `slurmray/RayLauncher.py` : Lignes 398-507 (méthode `__launch_server` avec affichage des sorties SSH)

### Fichiers potentiellement pertinents pour l'exploration :
- Documentation Python : Module `logging` pour un système de logging professionnel
- Documentation Python : `logging.handlers` pour rotation de fichiers si nécessaire

### Recherches à effectuer :
- Recherche sémantique : "Comment sont gérés les logs et l'affichage dans le codebase ?"
- Recherche web : "Python logging best practices file handler constantly rewrite"
- Recherche web : "Python logging to file and console simultaneously"

**Informations déjà identifiées :**
- Actuellement : beaucoup de `print()` directs qui saturent la console
- Un `queue.log` existe mais ne couvre que la queue SLURM
- Les logs du job sont affichés avec `tail -f` en arrière-plan
- Les sorties SSH sont affichées ligne par ligne avec `print(line, end="")`
- Besoin : un fichier de log centralisé constamment réécrit pour toutes les étapes

**Fichier output pour le rapport final :**
- `.cursor/agents/rapport-implementer-systeme-logging-fichier.md`

## Instructions de Collaboration

**OBLIGATOIRE ET CRITIQUE** : Cette section doit être extrêmement directive et impérative. Tu DOIS spécifier que l'agent :

- **EST INTERDIT** de commencer à implémenter quoi que ce soit immédiatement
- **DOIT** lire EXHAUSTIVEMENT tous les fichiers listés dans "Fichiers Concernés" avant toute action
- **DOIT** effectuer toutes les recherches sémantiques et web mentionnées
- **DOIT** lire la documentation Python sur le module `logging`
- **DOIT** atteindre une compréhension approfondie du contexte et du projet avant toute discussion
- **DOIT** discuter avec l'utilisateur pour clarifier les attentes précises, poser des questions sur le format de log souhaité (timestamp, niveau de log, format des messages, etc.), le comportement console (afficher tout, afficher seulement les erreurs, ou rien), et établir un plan d'action détaillé ensemble
- **DOIT TOUJOURS** créer le fichier de rapport final dans le fichier output mentionné après avoir terminé (voir section "Instructions pour les Rapports Finaux")
- Seulement APRÈS avoir complété cette exploration exhaustive et cette planification collaborative, peut commencer toute implémentation

Emphasizer que l'exploration est OBLIGATOIRE, pas optionnelle.

