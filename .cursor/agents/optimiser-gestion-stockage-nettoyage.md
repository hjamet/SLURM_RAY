## Contexte

L'analyse du code a révélé plusieurs problèmes dans la gestion du stockage et du nettoyage des fichiers. Le code actuel utilise `/users/{username}/slurmray-server` pour le stockage cluster (ce qui est approprié pour permettre la réutilisation du cache entre plusieurs exécutions d'un même projet), mais il présente des inefficacités et des problèmes de nettoyage. Les problèmes identifiés incluent : pas de nettoyage après téléchargement réussi du résultat, réinstallation systématique du venv même s'il existe déjà, régénération inutile de requirements.txt, et incohérences dans les versions Python hardcodées.

## Objectif

Optimiser la gestion du stockage et du nettoyage pour améliorer les performances et éviter l'accumulation de fichiers inutiles. Cela inclut : implémenter un système de cache intelligent pour réutiliser le venv entre exécutions, nettoyer les fichiers temporaires après téléchargement réussi du résultat, optimiser la génération de requirements.txt, et corriger les incohérences de versions Python dans les scripts.

## Fichiers Concernés

### Du travail effectué précédemment :
- `slurmray/RayLauncher.py` : Lignes 143 (chemin cluster), 430-452 (génération requirements.txt), 455-462 (upload fichiers et nettoyage), 493-506 (téléchargement résultat sans nettoyage)
- `slurmray/assets/slurmray_server.sh` : Lignes 11 (version Python hardcodée), 14-16 (création venv), 20-49 (installation packages), 52 (chemin hardcodé python3.9)
- `slurmray/assets/spython_template.py` : Template pour l'exécution Python

### Fichiers potentiellement pertinents pour l'exploration :
- Documentation Curnagl : Bonnes pratiques pour le nettoyage et la gestion du scratch
- `.cursor/agents/rapport-corriger-incompatibilites-curnagl.md` : Rapport sur les versions Python à utiliser

### Recherches à effectuer :
- Recherche sémantique : "Comment sont gérés le cache et la réutilisation des ressources dans le codebase ?"
- Recherche web : "Meilleures pratiques pour cache venv Python entre exécutions SLURM"
- Recherche web : "Comment optimiser pip install avec cache et requirements.txt hash"

**Informations déjà collectées (ne plus rechercher) :**
- Le code utilise `/users/{username}/slurmray-server` (approprié pour cache persistant)
- Le venv est recréé à chaque fois car le dossier est supprimé avant (ligne 461)
- requirements.txt est régénéré à chaque fois même si identique
- Pas de nettoyage des fichiers après téléchargement réussi

**Fichier output pour le rapport final :**
- `.cursor/agents/rapport-optimiser-gestion-stockage-nettoyage.md`

## Instructions de Collaboration

**OBLIGATOIRE ET CRITIQUE** : Cette section doit être extrêmement directive et impérative. Tu DOIS spécifier que l'agent :

- **EST INTERDIT** de commencer à implémenter quoi que ce soit immédiatement
- **DOIT** lire EXHAUSTIVEMENT tous les fichiers listés dans "Fichiers Concernés" avant toute action
- **DOIT** effectuer toutes les recherches sémantiques et web mentionnées
- **DOIT** lire la documentation Curnagl et les rapports pertinents
- **DOIT** atteindre une compréhension approfondie du contexte et du projet avant toute discussion
- **DOIT** discuter avec l'utilisateur pour clarifier les attentes précises, poser des questions sur les stratégies de cache (hash requirements.txt, nettoyage conditionnel, etc.), et établir un plan d'action détaillé ensemble
- **DOIT TOUJOURS** créer le fichier de rapport final dans le fichier output mentionné après avoir terminé (voir section "Instructions pour les Rapports Finaux")
- Seulement APRÈS avoir complété cette exploration exhaustive et cette planification collaborative, peut commencer toute implémentation

Emphasizer que l'exploration est OBLIGATOIRE, pas optionnelle.

