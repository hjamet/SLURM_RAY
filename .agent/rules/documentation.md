---
trigger: always_on
glob: "**/*"
description: "documentation"
---
# README upkeep rule

Le fichier [README.md](mdc:README.md) doit rester parfaitement synchronisé avec l'état actuel du dépôt. **Chaque conversation doit se conclure par une mise à jour explicite du README**, même si les changements sont purement documentaires. L'agent corrige immédiatement toute information obsolète ou erronée dès qu'elle est détectée.

## Principes directeurs
- **Actualisation continue** : à chaque ajout, suppression ou modification (code, dépendance, script, service, variable d'environnement), mettre le README à jour.
- **Structure immuable** : la hiérarchie de sections ci-dessous est obligatoire.
- **Précision factuelle** : aucune information obsolète tolérée.

## Structure imposée du README

1. **Paragraphe de présentation**
   - Objectif du projet, état courant, grandes fonctionnalités (4-5 phrases).

2. **# Installation**
   - Bloc ultra-concis.
   - Commande unique d'installation si possible (`install.sh`).
   - Pré-requis minimaux.

3. **# Description détaillée**
   - **Cœur du système** : Explication approfondie de ce que fait le repo (Memory Bank pour Cursor).
   - **Flux de travail** : Comment l'agent interagit avec les règles, la mémoire et le système de fichiers.
   - **Rôle de l'Architecte** : Description du mode "Architecte" et de la collaboration homme-machine.
   - **Direction actuelle** : Où on va, quels sont les chantiers en cours (ex: amélioration des règles, tests, etc.).
   - *Cette section doit être vivante et mise à jour par l'agent pour refléter la compréhension profonde du système.*

4. **# Principaux résultats**
   - Tableaux/Graphes synthétiques des performances ou métriques clés.

5. **# Plan du repo**
   - Arborescence `root/` commentée.

6. **# Scripts d'entrée principaux**
   - Tableau détaillé des commandes accessibles à l'utilisateur (via `src/commands`).
   | Script/Commande | Description détaillée | Usage / Exemple |
   |-----------------|-----------------------|-----------------|
   | ... | ... | ... |

7. **# Scripts exécutables secondaires & Utilitaires**
   - Tableau des outils internes ou scripts de maintenance.
   | Script | Rôle technique | Contexte d'exécution |
   |--------|----------------|----------------------|
   | ... | ... | ... |

8. **# Roadmap**
   - Tableau trié par priorité.
   - Uniquement futur (pas de "fait").

## Bonnes pratiques forcées
- **Toujours finir par le README**.
- **Documentation proportionnée** : détails techniques dans `documentation/`.
- **Fail-fast documentaire**.
