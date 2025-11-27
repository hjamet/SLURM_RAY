## Contexte

Avec deux backends fonctionnels (`SlurmBackend` et `DesiBackend`), la classe `RayLauncher` doit devenir le point d'entrée unifié et intelligent. Certains arguments du launcher actuel sont spécifiques à Slurm et n'ont pas de sens pour Desi, et inversement.

## Objectif

Finaliser l'intégration dans `RayLauncher` pour qu'il expose une interface propre et cohérente. Le launcher doit valider les arguments selon le mode choisi (`curnagl` ou `desi`) et gérer les spécificités comme la demande de GPU pour Desi.

## Fichiers Concernés

### Du travail effectué précédemment :
- `.cursor/agents/rapport-implementation-backend-desi.md` : Détails sur le fonctionnement de Desi.
- `slurmray/RayLauncher.py` : Code à adapter.

## Instructions de Collaboration

- **DOIT** modifier `RayLauncher.__init__` pour accepter `cluster='curnagl'` (défaut) ou `cluster='desi'`.
- **DOIT** ajouter une validation des arguments : avertir ou ignorer proprement les arguments Slurm (ex: `partitions`, `time_limit`) si on est en mode Desi.
- **DOIT** s'assurer que l'argument `use_gpu` est correctement transmis au backend Desi (vérification de la disponibilité CUDA sur le runner distant).
- **DOIT** unifier la gestion des logs et des retours utilisateurs pour que l'expérience soit similaire quel que soit le backend.
- **DOIT TOUJOURS** créer le fichier de rapport final `rapport-unification-et-arguments.md` après avoir terminé.

