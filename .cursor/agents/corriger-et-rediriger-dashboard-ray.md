## Contexte

Le dashboard Ray est configuré pour démarrer sur le cluster (dans `sbatch_template.sh`), mais il y a un bug dans `RayLauncher.py` ligne 199 où la configuration du dashboard n'est pas correctement assignée à `local_mode`, ce qui empêche le dashboard d'être configuré dans `ray.init()`. De plus, le dashboard tourne sur le nœud head du cluster mais n'est pas accessible directement depuis la machine locale. Il faut corriger le bug et implémenter une redirection automatique via port forwarding SSH pour permettre l'accès local au dashboard.

## Objectif

Corriger le bug de configuration du dashboard dans `RayLauncher.py` et implémenter une redirection automatique du dashboard Ray vers la machine locale via port forwarding SSH. Cela permettra d'accéder au dashboard sur `http://localhost:8888` pendant que le job SLURM tourne, sans avoir à créer manuellement le tunnel SSH.

## Fichiers Concernés

### Du travail effectué précédemment :
- `slurmray/RayLauncher.py` : Ligne 199 (bug : f-string non assignée à local_mode), lignes 277-396 (méthode __launch_job qui pourrait extraire le nom du nœud head), lignes 398-507 (méthode __launch_server qui pourrait gérer le port forwarding)
- `slurmray/assets/sbatch_template.sh` : Ligne 53 (démarrage du dashboard avec --include-dashboard=true --dashboard-host 0.0.0.0)
- `slurmray/assets/spython_template.py` : Ligne 12 (ray.init avec {{LOCAL_MODE}} qui devrait contenir la config dashboard)

### Fichiers potentiellement pertinents pour l'exploration :
- Documentation Ray : Comment configurer le dashboard et accéder à distance
- Documentation Curnagl : Restrictions réseau et port forwarding SSH

### Recherches à effectuer :
- Recherche sémantique : "Comment sont gérés les processus en arrière-plan et les tunnels SSH dans le codebase ?"
- Recherche web : "Ray dashboard port forwarding SSH automatic tunnel Python"
- Recherche web : "Comment extraire le nom du nœud head depuis SLURM_JOB_NODELIST"

**Informations déjà identifiées :**
- Le dashboard est démarré dans sbatch_template.sh sur le port 8888
- Le nœud head est le premier nœud de SLURM_JOB_NODELIST
- Il faut créer un tunnel SSH : `ssh -L 8888:node_head:8888 curnagl.dcsr.unil.ch`
- Le bug ligne 199 : `local_mode` reste vide au lieu de contenir la config dashboard

**Fichier output pour le rapport final :**
- `.cursor/agents/rapport-corriger-et-rediriger-dashboard-ray.md`

## Instructions de Collaboration

**OBLIGATOIRE ET CRITIQUE** : Cette section doit être extrêmement directive et impérative. Tu DOIS spécifier que l'agent :

- **EST INTERDIT** de commencer à implémenter quoi que ce soit immédiatement
- **DOIT** lire EXHAUSTIVEMENT tous les fichiers listés dans "Fichiers Concernés" avant toute action
- **DOIT** effectuer toutes les recherches sémantiques et web mentionnées
- **DOIT** lire la documentation Ray et Curnagl pertinente
- **DOIT** atteindre une compréhension approfondie du contexte et du projet avant toute discussion
- **DOIT** discuter avec l'utilisateur pour clarifier les attentes précises, poser des questions sur la gestion du port forwarding (processus en arrière-plan, nettoyage à la fin du job, gestion des erreurs, etc.), et établir un plan d'action détaillé ensemble
- **DOIT TOUJOURS** créer le fichier de rapport final dans le fichier output mentionné après avoir terminé (voir section "Instructions pour les Rapports Finaux")
- Seulement APRÈS avoir complété cette exploration exhaustive et cette planification collaborative, peut commencer toute implémentation

Emphasizer que l'exploration est OBLIGATOIRE, pas optionnelle.

