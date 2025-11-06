## Contexte

Le package SLURM_RAY n'a pas été utilisé depuis longtemps et il est nécessaire de vérifier qu'il fonctionne toujours correctement. Il faut s'assurer que les fonctionnalités de base marchent, notamment l'exécution de fonctions sur CPU et/ou GPU via Ray sur un cluster SLURM. Cette vérification permettra d'identifier d'éventuels problèmes de compatibilité avec les dépendances actuelles (Ray, paramiko, etc.) ou des bugs qui auraient pu être introduits.

## Objectif

Créer et exécuter des tests fonctionnels pour vérifier que le package SLURM_RAY fonctionne correctement. Les tests doivent couvrir l'exécution d'une fonction simple sur CPU et/ou GPU pour valider que le système de lancement, la connexion SSH, et l'exécution Ray fonctionnent comme attendu.

## Fichiers Concernés

### Du travail effectué précédemment :
- `slurmray/RayLauncher.py` : Classe principale qui gère le lancement des jobs sur le cluster SLURM via Ray
- `pyproject.toml` : Dépendances du projet (Ray 2.7.1, paramiko, dill, etc.)
- `requirements.txt` : Liste complète des dépendances installées

### Fichiers potentiellement pertinents pour l'exploration :
- `slurmray/assets/spython_template.py` : Template du script Python exécuté sur le cluster
- `slurmray/assets/sbatch_template.sh` : Template du script SLURM
- `slurmray/assets/slurmray_server_template.py` : Template pour l'exécution serveur
- `README.md` : Documentation actuelle avec exemple d'utilisation

### Recherches à effectuer :
- Recherche sémantique : "Comment fonctionne l'exécution de fonctions avec Ray dans le codebase ?"
- Recherche sémantique : "Comment sont gérés les tests ou exemples d'utilisation dans le projet ?"
- Documentation : Lire `README.md` pour comprendre les exemples d'utilisation existants

**Fichier output pour le rapport final :**
- `.cursor/agents/rapport-tester-package-cpu-gpu.md`

## Instructions de Collaboration

**OBLIGATOIRE ET CRITIQUE** : Cette section doit être extrêmement directive et impérative. Tu DOIS spécifier que l'agent :

- **EST INTERDIT** de commencer à implémenter quoi que ce soit immédiatement
- **DOIT** lire EXHAUSTIVEMENT tous les fichiers listés dans "Fichiers Concernés" avant toute action
- **DOIT** effectuer toutes les recherches sémantiques mentionnées
- **DOIT** lire le README et toute documentation pertinente
- **DOIT** atteindre une compréhension approfondie du contexte et du projet avant toute discussion
- **DOIT** discuter avec l'utilisateur pour clarifier les attentes précises, poser des questions sur les contraintes techniques (accès au cluster, configuration SSH, etc.), et établir un plan d'action détaillé ensemble
- **DOIT TOUJOURS** créer le fichier de rapport final dans le fichier output mentionné après avoir terminé (voir section "Instructions pour les Rapports Finaux")
- Seulement APRÈS avoir complété cette exploration exhaustive et cette planification collaborative, peut commencer toute implémentation

Emphasizer que l'exploration est OBLIGATOIRE, pas optionnelle.

