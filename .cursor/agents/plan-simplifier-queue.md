# Plan d'implémentation - Simplifier l'affichage de la queue SLURM

## 1. Modification de `__launch_job` dans `RayLauncher.py`

### A. Logique de parsing et d'affichage
Remplacer la boucle d'attente actuelle (lignes ~617-721) par une nouvelle logique :
- Conserver la récupération de la queue via `subprocess.run(["squeue", ...])`.
- Conserver le parsing actuel pour générer `to_queue` (utilisé pour `queue.log`).
- **Calcul de la position** :
  - Parcourir `to_queue`.
  - Trouver l'index où le `job_id` (ou le nom d'utilisateur/nom de job) apparaît.
  - Position = index + 1.
  - Taille totale = len(to_queue).
- **Gestion de l'affichage** :
  - Utiliser une variable `last_print_time` initialisée à 0.
  - Si `time.time() - last_print_time > 30` :
    - Afficher `Waiting for job... (Position in queue : {pos}/{total})` (ou "Position unknown" si non trouvé).
    - Mettre à jour `last_print_time`.
  - Si le job passe en statut "R" (Running), sortir de la boucle immédiatement.

### B. Gestion de `queue.log`
- Conserver l'écriture détaillée dans `queue.log` comme demandé (option 1.a).
- L'écriture dans `queue.log` peut se faire à chaque itération ou synchronisée avec l'affichage console pour éviter trop d'I/O (toutes les 30s semble raisonnable aussi pour le fichier log, ou garder le comportement actuel si l'utilisateur veut un historique précis). *Décision : Synchroniser l'écriture du log avec l'affichage console (30s) pour cohérence et performance, sauf si changement d'état détecté.*

## 2. Validation
- Créer un script de test `tests/manual_test_queue.py` (similaire à celui d'interruption) qui lance un job.
- Observer la sortie console pour vérifier que le message apparaît bien toutes les 30s et qu'il est formaté comme demandé.
- Vérifier que `queue.log` contient toujours les détails.

## 3. Rapport
- Générer le rapport final.

