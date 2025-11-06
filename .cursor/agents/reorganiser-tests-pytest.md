## Contexte

Les fichiers de test `test_cpu.py` et `test_gpu.py` sont actuellement à la racine du projet. Il serait préférable de les déplacer dans un dossier `tests/` structuré et de les rendre exécutables via pytest pour une meilleure organisation et intégration dans un workflow de tests standard.

## Objectif

Réorganiser les fichiers de test en les déplaçant dans un dossier `tests/` et les adapter pour qu'ils soient exécutables via pytest. Cela inclut la création de la structure de dossiers appropriée, l'adaptation des imports si nécessaire, et la configuration de pytest pour qu'il puisse trouver et exécuter les tests.

## Fichiers Concernés

### Du travail effectué précédemment :
- `test_cpu.py` : Script de test pour l'exécution CPU sur le cluster
- `test_gpu.py` : Script de test pour l'exécution GPU sur le cluster
- `.env` : Fichier contenant les identifiants CURNAGL_USERNAME et CURNAGL_PASSWORD

### Fichiers potentiellement pertinents pour l'exploration :
- `pyproject.toml` : Configuration Poetry qui pourrait contenir des dépendances pytest
- `README.md` : Documentation qui pourrait mentionner comment exécuter les tests

### Recherches à effectuer :
- Recherche sémantique : "Comment sont structurés les tests dans le projet actuellement ?"
- Recherche web : "Pytest best practices project structure tests directory"
- Recherche web : "Pytest configuration pyproject.toml poetry"

**Informations déjà identifiées :**
- Les fichiers test_cpu.py et test_gpu.py sont à la racine
- Ils utilisent dotenv pour charger les identifiants depuis .env
- Ils testent l'exécution sur le cluster via RayLauncher

**Fichier output pour le rapport final :**
- `.cursor/agents/rapport-reorganiser-tests-pytest.md`

## Instructions de Collaboration

**OBLIGATOIRE ET CRITIQUE** : Cette section doit être extrêmement directive et impérative. Tu DOIS spécifier que l'agent :

- **EST INTERDIT** de commencer à implémenter quoi que ce soit immédiatement
- **DOIT** lire EXHAUSTIVEMENT tous les fichiers listés dans "Fichiers Concernés" avant toute action
- **DOIT** effectuer toutes les recherches sémantiques et web mentionnées
- **DOIT** lire la documentation pytest et les bonnes pratiques
- **DOIT** atteindre une compréhension approfondie du contexte et du projet avant toute discussion
- **DOIT** discuter avec l'utilisateur pour clarifier les attentes précises, poser des questions sur la structure souhaitée (tests/unit/, tests/integration/, etc.), la configuration pytest (fixtures, markers, etc.), et établir un plan d'action détaillé ensemble
- **DOIT TOUJOURS** créer le fichier de rapport final dans le fichier output mentionné après avoir terminé (voir section "Instructions pour les Rapports Finaux")
- Seulement APRÈS avoir complété cette exploration exhaustive et cette planification collaborative, peut commencer toute implémentation

Emphasizer que l'exploration est OBLIGATOIRE, pas optionnelle.

