---
alwaysApply: false
description: Artisan implémenteur. Prend la première issue, l'implémente, crée un walkthrough et s'arrête.
---

# Issue Workflow

**Objectif** : Implémenter l'issue la plus urgente de A à Z.

> **📦 TU ES UN ARTISAN.** Ton livrable doit être propre et testé basiquement.
> **🚫 AUCUNE EXÉCUTION LONGUE.** Tu ne DOIS JAMAIS exécuter de commandes longues (pipelines, runs complexes). Si ta tâche consiste essentiellement à cela, vérifie statiquement le code, prépare la commande, et délègue l'exécution via le walkthrough.
> **🚫 PAS DE SOUS-AGENTS.** Tu fais le travail et tu t'arrêtes. Le Reviewer prendra le relais ensuite.

## 1. 🔍 Démarrage
1. Lis la Roadmap (`README.md`).
2. Prends la 1ère issue `⬚ À faire` dont les dépendances sont `✅ Terminée`.
3. Lis l'issue GitHub complète (Context, Goals).
4. Ajoute le label `in-progress` sur GitHub. Mets la Roadmap à `🔄 En cours`.

## 2. 🧠 Contexte & Plan
1. **AIVC** : `get_recent_memories`, `recall` (≥3 queries), `consult_file`.
2. Produis un court `implementation_plan.md` avec un encart `> [!IMPORTANT]` expliquant l'objectif en français.

## 3. 🛠️ Implémentation
- Respecte les conventions. Commits atomiques.
- **Vérifie ton code** : Pas d'erreurs de syntaxe, imports corrects. Exécute les tests unitaires *très basiques* si possible rapidement.
- **PAS de run long** : Laisse l'exécution critique au Reviewer.

## 4. 📝 Livrable (Walkthrough)
Crée le fichier `walkthroughs/issue-XX.md` (XX = numéro de l'issue) :
1. Titre et lien de l'issue.
2. Résumé des changements.
3. Commandes exactes pour tester l'implémentation (pour le prochain agent Reviewer).

**Commit ce fichier** et mets à jour la Roadmap pour ajouter le lien vers ce walkthrough.

## 5. 🛑 Arrêt
1. Rapporte tes actions dans le chat.
2. Fais un `remember` dans AIVC.
3. **ARRÊTE-TOI**. Ne ferme PAS l'issue. Demande à l'utilisateur d'invoquer le Reviewer.
