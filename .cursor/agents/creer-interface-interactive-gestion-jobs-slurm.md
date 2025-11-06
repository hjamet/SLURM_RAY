## Contexte

Actuellement, il n'existe pas de moyen simple pour l'utilisateur de visualiser et contrôler ses jobs SLURM en cours d'exécution ou en attente depuis une interface interactive. L'utilisateur souhaite pouvoir invoquer `python -m slurmray` pour afficher immédiatement les jobs en attente ou en cours d'exécution et les contrôler (les arrêter au besoin). Cette interface interactive permettrait également d'ouvrir le dashboard Ray en local pour monitorer les jobs actifs.

## Objectif

Créer une interface interactive en console permettant d'afficher les jobs SLURM en cours et leur position dans la file d'attente (si en attente), et de les arrêter au besoin. Cette interface sera accessible via `python -m slurmray` et devra permettre de lister les jobs, afficher leur statut, leur position dans la queue, et offrir des commandes pour les contrôler (annulation, ouverture du dashboard, etc.).

## Fichiers Concernés

### Du travail effectué précédemment :
- `slurmray/RayLauncher.py` : Contient la logique de soumission et de monitoring des jobs SLURM. Les méthodes `__launch_job` et la logique de parsing de `squeue` peuvent être réutilisées.
- `slurmray/__init__.py` : Point d'entrée du package, devra être modifié pour ajouter le point d'entrée `__main__.py`.
- `pyproject.toml` : Configuration du package, pourrait nécessiter des ajustements pour le point d'entrée.

### Fichiers potentiellement pertinents pour l'exploration :
- `slurmray/RayLauncher.py` (lignes 315-376) : Logique de parsing de `squeue` qui peut être extraite et réutilisée pour l'interface interactive.
- `slurmray/RayLauncher.py` (lignes 104-110) : Logique d'annulation des jobs via `scancel` qui peut être réutilisée.

### Recherches à effectuer :
- Recherche sémantique : "Comment créer une interface CLI interactive en Python avec menus et commandes ?"
- Recherche sémantique : "Comment parser et afficher les jobs SLURM depuis squeue de manière structurée ?"
- Recherche web : "Meilleures pratiques pour créer des interfaces CLI interactives en Python (rich, click, etc.)"
- Documentation : Lire le README pour comprendre l'architecture du projet

### Fichiers de résultats d'autres agents (si pertinents) :
- `.cursor/agents/rapport-simplifier-affichage-queue-attente-slurm.md` : Le travail sur la simplification de l'affichage de la queue peut fournir du code réutilisable pour parser `squeue` et extraire la position des jobs.

**Fichier output pour le rapport final :**
- `.cursor/agents/rapport-creer-interface-interactive-gestion-jobs-slurm.md`

## Instructions de Collaboration

**OBLIGATOIRE ET CRITIQUE** : Cette section doit être extrêmement directive et impérative. Tu DOIS spécifier que l'agent :

- **EST INTERDIT** de commencer à implémenter quoi que ce soit immédiatement
- **DOIT** lire EXHAUSTIVEMENT tous les fichiers listés dans "Fichiers Concernés" avant toute action
- **DOIT** lire le rapport de la tâche "simplifier-affichage-queue-attente-slurm" pour réutiliser le code de parsing de la queue
- **DOIT** effectuer toutes les recherches sémantiques et web mentionnées
- **DOIT** lire le README et toute documentation pertinente
- **DOIT** atteindre une compréhension approfondie du contexte et du projet avant toute discussion
- **DOIT** discuter avec l'utilisateur pour clarifier les attentes précises, poser des questions sur les contraintes techniques (format de l'interface, commandes disponibles, gestion des jobs distants via SSH, etc.), et établir un plan d'action détaillé ensemble
- **DOIT TOUJOURS** créer le fichier de rapport final dans le fichier output mentionné après avoir terminé (voir section "Instructions pour les Rapports Finaux")
- Seulement APRÈS avoir complété cette exploration exhaustive et cette planification collaborative, peut commencer toute implémentation

Emphasizer que l'exploration est OBLIGATOIRE, pas optionnelle.

