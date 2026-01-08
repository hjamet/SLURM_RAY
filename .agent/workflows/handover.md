---
description: "Générer un prompt de passation propre (Handover) pour maintenir le contexte entre sessions."
---

# Workflow: Context Handover

Ce workflow sert à générer un **"Prompt de Passation"** structuré à la fin d'une conversation, pour permettre au prochain agent (ou à la prochaine session) de reprendre le travail sans perte de contexte ni hallucination sur l'état du système.

## 1. Analyse de la Situation
Avant de générer le prompt, l'agent doit faire le point :
*   **Qu'est-ce qui tourne ?** (Processus en background, IDs, DB logs).
*   **Quel est l'état du code ?** (Propre, "dirty fixes" temporaires, refactoring en cours).
*   **Quels sont les bloqueurs ?** (Erreurs visibles, comportements inexpliqués contournés).

## 2. Structure du Prompt
Le prompt doit être généré dans un bloc de code Markdown, rédigé à la **seconde personne de l'impératif** ("Tu..."), s'adressant directement au futur agent.

Il doit contenir OBLIGATOIREMENT les sections suivantes :

### A. 👋 Relai : [Titre de l'Action]
Un titre accrocheur résumant la mission immédiate.

### B. Contexte
*   **Situation** : Où en est le projet global ? (ex: "Optimisation critique sur HotpotQA").
*   **Enjeu** : Pourquoi c'est important ? (ex: "Validation scientifique avant deadline").
*   **État** : Stable, Instable, En cours de réparation ?

### C. Historique (La Vérité Terrain)
*   Ce qui a été fait dans cette session.
*   Ce qui a échoué (très important pour éviter que le prochain agent ne retente la même chose).
*   Les "bricolages" temporaires présents dans le code (ex: "J'ai désactivé tqdm", "J'ai ajouté des prints sales").

### D. Objectif (La Mission)
Une liste numérotée d'actions concrètes à haute valeur ajoutée.
*   Ne pas donner les détails d'implémentation micro (sauf si critique), mais la direction.
*   Ex : "Nettoie le script", "Valide via la DB", "Lance le monitoring".

### E. Fichiers Concernés
*   La liste des fichiers clés à lire absolument.
*   Préciser *pourquoi* (ex: "C'est là que se trouve le bug").
*   Inclure la DB ou les fichiers de logs si pertinent.

### F. Consigne Critique : Plan d'abord !
*   **OBLIGATOIRE** : Ajoute une instruction explicite demandant au prochain agent de NE PAS coder immédiatement.
*   Il DOIT d'abord établir un `Implementation Plan` pour valider la stratégie avec l'utilisateur.
*   Phrase type à inclure : "⛔ **STOP !** Ne te lance pas tout de suite. Analyse ma demande, et propose un **Implementation Plan** détaillé avant de modifier quoi que ce soit."

## 3. Exemple de Sortie
```markdown
# 👋 Relai : Fix Logs & Monitor

### Contexte
Tu reprends une optimisation en cours. Le backend marche (DB OK), mais les logs sont invisibles.

### Historique
J'ai essayé de flusher stdout, sans succès. J'ai fini par rediriger vers un fichier.
Le code contient des `print` de debug un peu partout.

### Objectif
1. Nettoie les `print`.
2. Configure un `StreamHandler` propre.
3. Reprends le monitoring via la DB.

### Fichiers
*   `script.py` (Le code sale)
*   `results.db` (La vérité)

### Consigne
⛔ **STOP !** Avant de toucher au code, propose un **Implementation Plan** pour valider la stratégie de nettoyage.
```
