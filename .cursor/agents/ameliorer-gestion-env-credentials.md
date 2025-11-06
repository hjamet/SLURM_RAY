## Contexte

Actuellement, le package SLURM_RAY demande le username et le password pour la connexion SSH soit via les paramètres du constructeur `RayLauncher`, soit via une demande interactive avec `getpass()`. Cette approche n'est pas pratique et peut poser des problèmes de sécurité si les credentials sont codés en dur. Il serait préférable de charger automatiquement ces informations depuis un fichier `.env` pour améliorer la sécurité et la facilité d'utilisation.

## Objectif

Modifier le code pour que `RayLauncher` charge automatiquement le `server_username` et `server_password` depuis un fichier `.env` si ces paramètres ne sont pas fournis explicitement. Le système doit garder la rétrocompatibilité (les paramètres explicites doivent toujours fonctionner) et utiliser `.env` comme fallback. Il faudra également créer un fichier `.env.example` pour documenter les variables nécessaires.

## Fichiers Concernés

### Du travail effectué précédemment :
- `slurmray/RayLauncher.py` : Classe principale qui gère la connexion SSH (lignes 30-32 pour les paramètres, lignes 410-423 pour la gestion du password)
- `README.md` : Documentation qui mentionne actuellement `server_username` et `server_password` dans les exemples

### Fichiers potentiellement pertinents pour l'exploration :
- `pyproject.toml` : Vérifier si `python-dotenv` est déjà une dépendance, sinon il faudra l'ajouter
- `requirements.txt` : Liste des dépendances actuelles
- `.env.example` : Fichier à créer pour documenter les variables d'environnement nécessaires

### Recherches à effectuer :
- Recherche sémantique : "Comment sont gérés les fichiers de configuration ou variables d'environnement dans le codebase ?"
- Recherche web : "Meilleures pratiques pour gérer les credentials SSH avec python-dotenv"
- Documentation : Lire `README.md` pour comprendre comment les credentials sont actuellement documentés

**Fichier output pour le rapport final :**
- `.cursor/agents/rapport-ameliorer-gestion-env-credentials.md`

## Instructions de Collaboration

**OBLIGATOIRE ET CRITIQUE** : Cette section doit être extrêmement directive et impérative. Tu DOIS spécifier que l'agent :

- **EST INTERDIT** de commencer à implémenter quoi que ce soit immédiatement
- **DOIT** lire EXHAUSTIVEMENT tous les fichiers listés dans "Fichiers Concernés" avant toute action
- **DOIT** effectuer toutes les recherches sémantiques et web mentionnées
- **DOIT** lire le README et toute documentation pertinente
- **DOIT** atteindre une compréhension approfondie du contexte et du projet avant toute discussion
- **DOIT** discuter avec l'utilisateur pour clarifier les attentes précises, poser des questions sur les contraintes techniques (noms des variables d'environnement, format du .env, gestion des erreurs si le fichier n'existe pas, etc.), et établir un plan d'action détaillé ensemble
- **DOIT TOUJOURS** créer le fichier de rapport final dans le fichier output mentionné après avoir terminé (voir section "Instructions pour les Rapports Finaux")
- Seulement APRÈS avoir complété cette exploration exhaustive et cette planification collaborative, peut commencer toute implémentation

Emphasizer que l'exploration est OBLIGATOIRE, pas optionnelle.

