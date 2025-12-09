---
description: "agent"
---
# Commande Agent — Sélection et Traitement de Tâche (Mode README) 🚀

## Objectif

Quand l'utilisateur tape `/agent`, tu dois consulter la section **# Roadmap** du `README.md`, sélectionner la tâche la plus prioritaire disponible, et la traiter. La roadmap dans le README est la source unique de vérité.

## Comportement Requis

### Étape 1 : Lire et Analyser le README

1. **Lire `README.md`**
2. **Extraire la table Markdown de la section `# Roadmap`**
   - Colonnes attendues : `| Tâche | Objectif | État | Dépendances |`
   - Identifier les tâches avec l'état `🏗️ En cours` (priorité absolue si reprise)
   - Identifier les tâches avec l'état `📅 À faire`

### Étape 2 : Sélectionner la Tâche

1. **Vérifier les tâches en cours (`🏗️ En cours`)** :
   - S'il y en a une, c'est la tâche active. Demander à l'utilisateur s'il veut la reprendre.

2. **Si aucune tâche en cours, sélectionner la prochaine tâche `📅 À faire`** :
   - Parcourir le tableau de haut en bas (le tableau est déjà trié par priorité).
   - **Vérification des dépendances** :
     - Lire la colonne "Dépendances".
     - Une dépendance est satisfaite si elle n'apparait **PLUS** dans la colonne "Tâche" du tableau (car les tâches terminées sont supprimées).
     - Si une tâche dépend d'une tâche encore présente dans le tableau, elle est bloquée. Passer à la suivante.
   - Sélectionner la première tâche non bloquée.

### Étape 3 : Démarrer la Tâche

1. **Mettre à jour le `README.md`** :
   - Changer l'icône d'état de la tâche sélectionnée : `📅 À faire` → `🏗️ En cours`.
   - Sauvegarder le `README.md`.

2. **Présenter la Tâche** (Format texte pur, sans bloc de code) :
   - 🎯 **Tâche :** [Titre]
   - 📋 **Contexte & Objectif :** [Contenu de la colonne Objectif ~200 mots]
   - 🧱 **Dépendances :** [Liste des dépendances ou "Aucune"]
   - 🧠 **Analyse :** Résumer brièvement ce qui va être fait.

### Étape 4 : Exécution et Mise à Jour Continue

1. **Discuter et Planifier** : Établir le plan d'action avec l'utilisateur.
2. **Implémenter** : Code, tests, vérifications.
3. **Documentation** : Si des informations manquent, mettre à jour les autres sections du README (Installation, Architecture, etc.) **pendant** le travail.

### Étape 5 : Clôture de la Tâche

Une fois la tâche terminée et validée :

1. **Mettre à jour le `README.md`** :
   - **Supprimer** la ligne de la tâche dans la section `# Roadmap` (une tâche terminée ne doit plus y figurer).
   - **Intégrer** les résultats pertinents dans les sections appropriées du README (ex: `# Principaux résultats`, `# Scripts`, ou une section `# Historique/Changelog` si nécessaire).
   - Vérifier que la suppression de la tâche débloque bien les suivantes (les dépendances vers cette tâche seront désormais considérées comme résolues car le nom ne sera plus trouvé dans la table).

## Gestion des Erreurs

- Si le README n'a pas de section Roadmap : Créer la section avec le tableau vide et informer l'utilisateur.
- Si le format du tableau est invalide : Tenter de le réparer ou demander à l'utilisateur.
- Si une tâche dépend d'une tâche inexistante (non trouvée dans le tableau mais pas terminée) : Signaler l'anomalie (dépendance fantôme).

## Notes Importantes

- **Source Unique** : Pas de fichiers `.json` ou `.yaml` externes. Tout est dans le README.
- **Objectif Détaillé** : La colonne "Objectif" contient les instructions. L'agent doit s'y référer scrupuleusement.
- **Nettoyage Immédiat** : Une tâche finie disparaît de la roadmap instantanément.
