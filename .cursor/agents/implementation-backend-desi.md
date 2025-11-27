## Contexte

Une fois l'architecture refactorisée (Task 10), nous devons implémenter le backend spécifique pour le serveur "Desi" (`isipol09`). Ce serveur est une machine unique puissante (sans Slurm) partagée par plusieurs utilisateurs. L'exécution doit être "Stateless" (propre) et robuste.

## Objectif

Implémenter la classe `DesiBackend` qui gère l'exécution de jobs Ray via SSH sur le serveur Desi. Ce backend doit gérer la connexion, le transfert de code, l'exécution isolée, et le nettoyage.

## Fichiers Concernés

### Du travail effectué précédemment :
- `.cursor/agents/rapport-refactoring-architecture-strategy.md` : Pour comprendre l'interface `ClusterBackend` à implémenter.
- `slurmray/RayLauncher.py` (nouvelle version) : Point d'intégration.

### Recherches à effectuer :
- Documentation `paramiko` pour la gestion SSH/SFTP robuste.
- Documentation `ray` pour `ray.init()` : comment lancer une instance isolée sur une machine partagée (gestion des ports dynamiques pour éviter les conflits entre utilisateurs).
- Documentation `cloudpickle` pour la sérialisation de fonctions.

## Instructions de Collaboration

- **EST INTERDIT** d'utiliser des commandes Slurm (`sbatch`, `squeue`) dans ce backend.
- **DOIT** implémenter la logique de connexion SSH via `paramiko`.
- **DOIT** implémenter le workflow : Création dossier tmp -> Upload Pickle -> Exec Runner -> Download Result -> Delete tmp.
- **DOIT** concevoir un script "runner" (python) qui sera exécuté sur le serveur distant. Ce script doit :
    - Détecter un port libre ou utiliser une configuration isolée pour `ray.init()` afin d'éviter les conflits si plusieurs utilisateurs lancent des jobs en même temps sur Desi.
    - Charger la fonction, exécuter, sauvegarder le résultat.
- **DOIT** garantir le nettoyage (`rm -rf`) même en cas d'erreur (blocs `finally`).
- **DOIT** discuter avec l'utilisateur des détails de connexion (IP, User) pour les tests (mocking possible si pas d'accès).
- **DOIT TOUJOURS** créer le fichier de rapport final `rapport-implementation-backend-desi.md` après avoir terminé.

