## Contexte

Le projet `slurmray` doit évoluer pour supporter plusieurs environnements d'exécution (backends). Actuellement, la logique Slurm est fortement couplée à la classe `RayLauncher`. Pour introduire proprement le support du serveur "Desi" (SSH sans Slurm) sans complexifier le code avec des conditions multiples, nous devons adopter le **Pattern Strategy**.

## Objectif

Refactoriser l'architecture actuelle pour séparer l'interface de lancement des implémentations spécifiques (Slurm vs Desi). L'objectif est d'isoler le code existant (qui fonctionne pour Curnagl) dans une classe dédiée, tout en préparant le terrain pour le futur backend Desi.

## Fichiers Concernés

### Du travail effectué précédemment :
- `slurmray/RayLauncher.py` : Fichier principal contenant actuellement toute la logique monolithique.

### Fichiers potentiellement pertinents pour l'exploration :
- `tests/` : S'assurer que les tests existants ne cassent pas après le refactoring.

### Recherches à effectuer :
- Vérifier comment `RayLauncher` est instancié dans les projets utilisateurs pour minimiser les changements d'API (idéalement aucun changement pour l'utilisateur final).

## Instructions de Collaboration

- **EST INTERDIT** de modifier la logique métier Slurm (templates sbatch, commandes) ; elle doit être déplacée "telle quelle" ou presque.
- **DOIT** lire `slurmray/RayLauncher.py` pour identifier toutes les méthodes dépendantes de Slurm.
- **DOIT** créer une classe abstraite `ClusterBackend` définissant le contrat (`submit_job`, `get_status`, `cancel_job`, `get_logs`).
- **DOIT** créer la classe `SlurmBackend` (héritant de `ClusterBackend`) et y déplacer la logique Slurm.
- **DOIT** adapter `RayLauncher` pour qu'il instancie le bon backend et délègue les appels.
- **DOIT** vérifier que les tests "Hello World" sur Curnagl fonctionnent toujours après le refactoring.
- **DOIT** discuter avec l'utilisateur si des changements d'API sont inévitables (ex: signature du constructeur).
- **DOIT TOUJOURS** créer le fichier de rapport final `rapport-refactoring-architecture-strategy.md` après avoir terminé.

