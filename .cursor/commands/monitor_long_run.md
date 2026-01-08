---
description: Stratégie de monitoring pour les expériences longue durée (Overnight Runs)
---

# Long Run Monitoring Workflow

Ce workflow définit comment l'agent doit surveiller une tâche longue (ex: Optimisation Optuna > 1h) sans saturer le contexte ni perdre le contrôle.

## 1. Pré-requis
*   La commande doit être lancée via `run_command` standard (SANS `&` ni `nohup`).
*   Si la commande est longue, `run_command` retournera automatiquement un CommandID que l'on utilisera pour le monitoring.
*   L'agent doit avoir vérifié que le processus a démarré correctement (Status  + premiers logs valides).

## 2. Boucle de Monitoring (The "Check-In" Loop)
L'agent doit entrer dans une boucle de vérification périodique.

### Fréquence Adaptative (Adaptive Polling)
L'agent doit adapter sa fréquence de vérification pour attraper les erreurs au démarrage (« Fail Fast ») puis passer en régime de croisière.

1.  **Démarrage (Early Watch)** :
    *   **T+30s** : Premier check rapide pour vérifier que la commande ne crashe pas immédiatement.
    *   **T+90s (+1 min)** : Second check pour confirmer la stabilité.
2.  **Régime de Croisière (Cruise Control)** :
    *   **Ensuite** : Enchaîner les boucles de **5 minutes (300s)**.
    *   **Boucle Infinie** : Continuer ces vérifications de 5 minutes **tant que la commande n'est pas terminée**. Peu importe si cela prend 100 appels, l'important est de maintenir la visibilité.

### Actions à chaque Check-In
1.  **Vérifier le Status** : Utiliser  avec un  long.
2.  **Analyser les Logs** :
    *   Regarder les dernières lignes ().
    *   Chercher des erreurs (, , ).
    *   Vérifier la progression (ex: "Trial 5/100 completed", "Epoch 3/10").
3.  **Décision** :
    *   **Tout va bien** : Mettre à jour le `TaskStatus` et continuer la boucle.
    *   **Problème Mineur / Optimisation Possible** : Si l'agent détecte dans les logs un comportement sous-optimal ou une erreur non bloquante mais inquiétante :
        *   **PAUSE** : Arrêter la boucle de monitoring (ne pas tuer la commande tout de suite).
        *   **NOTIFIER** : Demander à l'utilisateur : "J'ai détecté X. Veux-tu corriger et relancer, ou continuer ?"
    *   **Erreur Critique** : Interrompre, analyser et notifier.
    *   **Terminé** : Analyser les résultats, mettre à jour les artefacts et notifier.

## 3. Communication
*   Ne pas notifier l'utilisateur à chaque check-in si tout va bien.
*   Notifier uniquement en cas de :
    *   Succès final (avec résumé des résultats).
    *   Échec critique nécessitant une décision humaine.
    *   Découverte intermédiaire majeure (ex: "Nouveau record battu à Trial 50 !").

## 4. Timeout Strategy
*   **Limite HARD** : `WaitDurationSeconds` est limité à **300 secondes (5 minutes)** max.
*   Pour attendre plus longtemps (ex: 1h), il faut enchaîner les appels (ex: 12 appels de 5 min) dans la boucle de monitoring.
*   Cela garantit que l'agent reste "éveillé" et que les logs sont streamés dans le chat régulièrement.
*   Ne JAMAIS utiliser `time.sleep()` ou de boucles d'attente active. Laisser l'outil gérer l'attente.
