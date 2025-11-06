## Contexte

La documentation Curnagl a évolué depuis la création du package SLURM_RAY. Une analyse sur le cluster Curnagl a identifié des incompatibilités spécifiques entre le code actuel et les modules disponibles. Les problèmes identifiés incluent : Python 3.11.6 n'existe pas (disponible : 3.11.7), les modules gcc/cuda/cudnn sont chargés sans version spécifique (risque d'incompatibilités), et il faut s'assurer de la compatibilité entre les versions cuda et cudnn.

**Incompatibilités identifiées (SLURM 24.05.3, vérifié le 2024) :**
- Python : Code utilise `python/3.11.6` mais Curnagl a `python/3.11.7` et `python/3.12.1` (dernière version disponible)
- **Décision stratégique** : Utiliser `python/3.12.1` (dernière version disponible sur Curnagl) et mettre à jour `pyproject.toml` pour permettre des versions compatibles (>=3.11.7 ou >=3.12.0)
- gcc : Code charge `gcc` sans version, Curnagl a `gcc/9.5.0`, `gcc/12.3.0`, `gcc/13.2.0`
- cuda : Code charge `cuda` sans version, Curnagl a `cuda/11.8.0`, `12.2.1`, `12.3.1`, `12.4.1`, `12.6.2`
- cudnn : Code charge `cudnn` sans version, Curnagl a `cudnn/8.7.0.84-11.8`, `8.8.0.121-12.0`, `9.2.0.82-12`
- Compatibilité : Il faut s'assurer que cuda et cudnn sont compatibles (ex: cuda/12.6.2 avec cudnn/9.2.0.82-12)
- Arguments SLURM : `--exclusive` et `--gres gpu:1` sont supportés (compatibles)
- Partitions : `cpu` et `gpu` existent (compatibles)

## Objectif

Analyser les incompatibilités entre le code actuel de SLURM_RAY et la documentation Curnagl actuelle, puis corriger le code pour qu'il soit compatible avec les spécifications actuelles du cluster. **Priorité : utiliser Python 3.12.1 (dernière version disponible sur Curnagl) et mettre à jour pyproject.toml pour permettre des versions compatibles (>=3.12.0).** Cela inclut également la vérification des versions de modules, des arguments SLURM, et des partitions disponibles.

## Fichiers Concernés

### Du travail effectué précédemment :
- `slurmray/RayLauncher.py` : Lignes 67-71 (chargement des modules : gcc, python/3.11.6, cuda, cudnn), lignes 248-268 (génération des arguments SLURM)
- `slurmray/assets/sbatch_template.sh` : Template SLURM avec les arguments (--partition, --mem, --nodes, --ntasks-per-node, --exclusive, --gres)
- `pyproject.toml` : Version Python requise (3.11.6) - **À mettre à jour vers >=3.12.0 pour utiliser la dernière version disponible (3.12.1) et permettre des versions compatibles**

### Fichiers potentiellement pertinents pour l'exploration :
- Documentation Curnagl : https://wiki.unil.ch/ci/books/high-performance-computing-hpc/page/how-to-run-a-job-on-curnagl
- Documentation Curnagl : https://wiki.unil.ch/ci/books/high-performance-computing-hpc/page/curnagl
- `.cursor/agents/rapport-installer-et-verifier-projet.md` : Rapport d'installation qui pourrait contenir des informations sur les dépendances

### Recherches à effectuer :
- Recherche sémantique : "Comment sont chargés les modules et générés les arguments SLURM dans le codebase ?"
- Recherche web : "Compatibilité cuda cudnn versions Curnagl 12.6.2 9.2.0"
- Documentation : Lire la documentation Curnagl pour comprendre les bonnes pratiques de chargement de modules

**Informations déjà collectées (ne plus rechercher) :**
- Versions Python disponibles : 3.8.18, 3.9.18, 3.10.13, 3.11.7, 3.12.1
- Versions gcc disponibles : 9.5.0, 12.3.0, 13.2.0
- Versions cuda disponibles : 11.8.0, 12.2.1, 12.3.1, 12.4.1, 12.6.2
- Versions cudnn disponibles : 8.7.0.84-11.8, 8.8.0.121-12.0, 9.2.0.82-12
- SLURM version : 24.05.3 (--exclusive et --gres supportés)

**Fichier output pour le rapport final :**
- `.cursor/agents/rapport-corriger-incompatibilites-curnagl.md`

## Instructions de Collaboration

**OBLIGATOIRE ET CRITIQUE** : Cette section doit être extrêmement directive et impérative. Tu DOIS spécifier que l'agent :

- **EST INTERDIT** de commencer à implémenter quoi que ce soit immédiatement
- **DOIT** lire EXHAUSTIVEMENT tous les fichiers listés dans "Fichiers Concernés" avant toute action
- **DOIT** effectuer toutes les recherches web et sémantiques mentionnées
- **DOIT** lire la documentation Curnagl complète pour comprendre les spécifications actuelles
- **DOIT** atteindre une compréhension approfondie du contexte et du projet avant toute discussion
- **DOIT** discuter avec l'utilisateur pour clarifier les attentes précises, poser des questions sur les spécifications Curnagl (versions Python disponibles, modules disponibles, arguments SLURM valides, etc.), et établir un plan d'action détaillé ensemble
- **DOIT TOUJOURS** créer le fichier de rapport final dans le fichier output mentionné après avoir terminé (voir section "Instructions pour les Rapports Finaux")
- Seulement APRÈS avoir complété cette exploration exhaustive et cette planification collaborative, peut commencer toute implémentation

Emphasizer que l'exploration est OBLIGATOIRE, pas optionnelle.

