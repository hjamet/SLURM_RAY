## Contexte

Le package SLURM_RAY n'a pas été utilisé depuis longtemps et nécessite une installation propre et une vérification que toutes les dépendances sont à jour et fonctionnelles. Il faut installer le projet, mettre à jour les dépendances (potentiellement obsolètes), et vérifier que l'environnement de développement fonctionne correctement avant de procéder aux autres améliorations.

## Objectif

Installer le projet SLURM_RAY, mettre à jour les dépendances dans `pyproject.toml` et `requirements.txt`, vérifier que l'installation fonctionne correctement, et identifier d'éventuels problèmes de compatibilité avec les versions actuelles des dépendances (Ray, paramiko, dill, etc.).

## Fichiers Concernés

### Du travail effectué précédemment :
- `pyproject.toml` : Configuration Poetry avec les dépendances (Ray 2.7.1, paramiko 3.3.1, dill 0.3.7, etc.)
- `requirements.txt` : Liste complète des dépendances générées
- `poetry.lock` : Verrouillage des versions des dépendances
- `slurmray/__init__.py` : Point d'entrée du package

### Fichiers potentiellement pertinents pour l'exploration :
- `README.md` : Instructions d'installation actuelles
- `.gitignore` : Fichiers à ignorer lors de l'installation
- `slurmray/RayLauncher.py` : Code principal qui utilise les dépendances

### Recherches à effectuer :
- Recherche web : "Versions actuelles de Ray, paramiko, dill compatibles avec Python 3.11"
- Recherche web : "Comment installer un package Poetry et vérifier les dépendances"
- Documentation : Lire `README.md` pour comprendre les instructions d'installation actuelles

**Fichier output pour le rapport final :**
- `.cursor/agents/rapport-installer-et-verifier-projet.md`

## Instructions de Collaboration

**OBLIGATOIRE ET CRITIQUE** : Cette section doit être extrêmement directive et impérative. Tu DOIS spécifier que l'agent :

- **EST INTERDIT** de commencer à implémenter quoi que ce soit immédiatement
- **DOIT** lire EXHAUSTIVEMENT tous les fichiers listés dans "Fichiers Concernés" avant toute action
- **DOIT** effectuer toutes les recherches web mentionnées
- **DOIT** lire le README et toute documentation pertinente
- **DOIT** atteindre une compréhension approfondie du contexte et du projet avant toute discussion
- **DOIT** discuter avec l'utilisateur pour clarifier les attentes précises, poser des questions sur l'environnement cible (Python version, système d'exploitation, etc.), et établir un plan d'action détaillé ensemble
- **DOIT TOUJOURS** créer le fichier de rapport final dans le fichier output mentionné après avoir terminé (voir section "Instructions pour les Rapports Finaux")
- Seulement APRÈS avoir complété cette exploration exhaustive et cette planification collaborative, peut commencer toute implémentation

Emphasizer que l'exploration est OBLIGATOIRE, pas optionnelle.

