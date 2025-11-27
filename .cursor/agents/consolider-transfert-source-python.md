## Contexte

Nous venons de résoudre un problème majeur de compatibilité de version Python entre l'environnement local (Python 3.12) et le serveur Desi (Python 3.8). La sérialisation `dill` échouait avec `SystemError: unknown opcode`. La solution implémentée consiste à transférer le *code source* de la fonction au lieu de son bytecode sérialisé lorsque possible, et à exécuter ce code source sur le serveur distant. Cette modification rend `RayLauncher` beaucoup plus robuste face aux différences de versions Python.

Les tests manuels (`tests/manual_test_desi_gpu_dashboard.py`) ont validé cette approche : l'exécution réussit, Ray et Torch sont détectés, les GPUs sont vus, et le tunnel SSH pour le dashboard est établi.

Cependant, cette robustesse pourrait être étendue à d'autres backends ou améliorée pour gérer des cas plus complexes (fonctions avec fermetures, etc.). De plus, le code a été modifié "à chaud" pour faire passer le test. Une revue et un refactoring plus propres pourraient être nécessaires pour garantir que `func_source.py` est généré proprement dans tous les cas.

## Objectif

Consolider et généraliser le mécanisme de transfert de code source pour assurer la compatibilité inter-versions Python sur tous les backends (Slurm et Desi). Nettoyer le code de `RayLauncher` pour rendre cette fonctionnalité standard et documentée. Ajouter des tests unitaires spécifiques pour vérifier la sérialisation/désérialisation via source.

## Fichiers Concernés

### Du travail effectué précédemment :
- `slurmray/RayLauncher.py` : Implémentation de la sauvegarde du code source (`__serialize_func_and_args`).
- `slurmray/assets/spython_template.py` : Implémentation du chargement depuis le code source.
- `tests/manual_test_desi_gpu_dashboard.py` : Test de validation (à conserver comme référence).

### Fichiers potentiellement pertinents pour l'exploration :
- `slurmray/backend/base.py` : Vérifier si d'autres mécanismes de sérialisation existent.
- `tests/test_hello_world_cpu.py` : Vérifier si les autres tests passent toujours.

### Recherches à effectuer :
- Recherche sémantique : "Comment gérer les fermetures (closures) avec inspect.getsource ?" (car `dill` le fait bien, mais `getsource` non).
- Documentation : Vérifier si `dill.source` offre une meilleure alternative que `inspect.getsource`.

**Fichier output pour le rapport final :**
- `.cursor/agents/rapport-consolidation-transfert-source.md`

## Instructions de Collaboration

L'agent :
- **EST INTERDIT** de supprimer la fonctionnalité `dill` existante (c'est le fallback et la méthode principale pour les mêmes versions).
- **DOIT** lire `RayLauncher.py` et `spython_template.py` pour comprendre la logique actuelle.
- **DOIT** évaluer les limites de `inspect.getsource` (ex: dépendances globales, fermetures) et proposer des solutions ou des avertissements.
- **DOIT** discuter avec l'utilisateur pour savoir si cette fonctionnalité doit être activée par défaut ou via un flag `use_source_transfer=True`.
- **DOIT TOUJOURS** créer le fichier de rapport final.
- Seulement APRÈS, peut refactoriser ou étendre le code.

