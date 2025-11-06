## Contexte

L'affichage actuel de la queue d'attente SLURM dans `RayLauncher.py` est verbeux et génère beaucoup de sortie console. La méthode `__launch_job` affiche régulièrement la queue complète avec tous les détails (utilisateurs, statuts, nœuds, etc.), ce qui peut saturer la console et rendre difficile le suivi de l'état réel du job de l'utilisateur. L'utilisateur souhaite simplifier cet affichage pour ne montrer que l'information essentielle : la position dans la file d'attente.

## Objectif

Simplifier l'affichage de la queue d'attente SLURM pour ne montrer qu'un message concis et clair : "Waiting for job... (Position in queue : x/X)" actualisé uniquement toutes les 30 secondes. Remplacer l'affichage verbeux actuel par cette version simplifiée qui permet de suivre facilement la progression du job sans saturer la console.

## Fichiers Concernés

### Du travail effectué précédemment :
- `slurmray/RayLauncher.py` (lignes 277-396) : La méthode `__launch_job` contient la logique d'affichage de la queue actuelle. Les lignes 315-376 gèrent l'affichage détaillé de la queue via `squeue` et l'écriture dans `queue.log`.
- `slurmray/RayLauncher.py` (lignes 308-376) : La boucle qui attend la création du fichier log et affiche la queue toutes les 0.25 secondes avec beaucoup de détails.

### Fichiers potentiellement pertinents pour l'exploration :
- `slurmray/RayLauncher.py` : Toute la logique de monitoring de la queue est dans cette classe.

### Recherches à effectuer :
- Recherche sémantique : "Comment parser la sortie de squeue pour extraire la position d'un job spécifique dans la file d'attente ?"
- Recherche web : "Format de sortie de squeue SLURM et comment extraire la position d'un job"
- Documentation : Lire la documentation SLURM sur `squeue` pour comprendre le format de sortie

### Fichiers de résultats d'autres agents (si pertinents) :
- Aucun pour le moment

**Fichier output pour le rapport final :**
- `.cursor/agents/rapport-simplifier-affichage-queue-attente-slurm.md`

## Instructions de Collaboration

**OBLIGATOIRE ET CRITIQUE** : Cette section doit être extrêmement directive et impérative. Tu DOIS spécifier que l'agent :

- **EST INTERDIT** de commencer à implémenter quoi que ce soit immédiatement
- **DOIT** lire EXHAUSTIVEMENT tous les fichiers listés dans "Fichiers Concernés" avant toute action
- **DOIT** effectuer toutes les recherches sémantiques et web mentionnées
- **DOIT** lire le README et toute documentation pertinente
- **DOIT** atteindre une compréhension approfondie du contexte et du projet avant toute discussion
- **DOIT** discuter avec l'utilisateur pour clarifier les attentes précises, poser des questions sur les contraintes techniques (comment identifier le job de l'utilisateur dans la queue, format exact du message, etc.), et établir un plan d'action détaillé ensemble
- **DOIT TOUJOURS** créer le fichier de rapport final dans le fichier output mentionné après avoir terminé (voir section "Instructions pour les Rapports Finaux")
- Seulement APRÈS avoir complété cette exploration exhaustive et cette planification collaborative, peut commencer toute implémentation

Emphasizer que l'exploration est OBLIGATOIRE, pas optionnelle.

