# Commande Clean — Nettoyage des Tâches in-progress 🧹

## Objectif

Quand l'utilisateur tape `/clean`, tu dois nettoyer automatiquement les tâches marquées comme `in-progress` dans la roadmap centralisée. Pour chaque tâche `in-progress`, vérifier si son fichier résultat existe : si oui, archiver la tâche (comme l'étape 2.0 de `/agent`), sinon remettre la tâche en `todo` pour qu'elle puisse être reprise plus tard.

Cette commande permet de maintenir l'hygiène de la roadmap sans avoir à invoquer `/agent`, et permet de récupérer des tâches qui ont été marquées `in-progress` mais jamais terminées.

## Comportement Requis

Lorsque l'utilisateur tape `/clean` (avec ou sans instructions supplémentaires), tu dois suivre cette séquence exacte :

### Étape 1 : Charger ou Créer la Roadmap

1. **Lire le fichier `.cursor/agents/roadmap.yaml`**
   - Si le fichier n'existe pas → Créer une roadmap vide avec la structure suivante :
     ```yaml
     version: "1.0"
     tasks: []
     ```
     Puis terminer immédiatement avec la sortie : "Aucune roadmap trouvée, roadmap vide créée"
   - Si le fichier existe mais est invalide (YAML mal formé) → **ÉCHOUER EXPLICITEMENT** avec les détails de l'erreur

2. **Valider la structure de la roadmap**
   - Vérifier que `version` existe
   - Vérifier que `tasks` est un tableau
   - Pour chaque tâche, vérifier ou initialiser le champ `state` (doit être `"todo"` ou `"in-progress"`)
   - Si validation échoue → **ÉCHOUER EXPLICITEMENT**

### Étape 2 : Nettoyer les Tâches in-progress

Initialiser deux compteurs :
- `archived_count` = 0 (tâches archivées)
- `reset_count` = 0 (tâches remises en todo)

Initialiser une liste pour collecter les `output_file` des tâches archivées :
- `archived_output_files` = [] (liste des output_file des tâches terminées)

**Pour chaque tâche avec `state: "in-progress"`** :

1. **Vérifier si le fichier `.cursor/agents/{output_file}` existe** (où `output_file` est défini dans la tâche)

2. **Si le fichier existe** (tâche terminée) :
   - La tâche est terminée → archiver la tâche (logique identique à l'étape 2.0 de `/agent`) :
     - Retirer la tâche de `tasks` (supprimer complètement l'entrée)
     - Parcourir toutes les tâches restantes dans `tasks` :
       - Retirer l'ID de cette tâche de leurs `dependencies` (si présent)
       - Pour chaque tâche qui avait cette dépendance, ajouter `{output_file}` (nom de fichier seul, ex: `"rapport-tache-1.md"`) dans leur liste `dependencies-results` (initialiser à liste vide si le champ n'existe pas). Le format de `dependencies-results` est une liste de strings contenant uniquement les noms de fichiers (sans chemin, ex: `["rapport-tache-1.md", "rapport-tache-2.md"]`)
     - Supprimer le fichier de tâche `.cursor/agents/{task_file}` s'il existe encore
     - Ajouter `{output_file}` à la liste `archived_output_files`
   - Incrémenter `archived_count`
   - Sauvegarder `roadmap.yaml` immédiatement après l'archivage

3. **Si le fichier n'existe pas** (tâche non terminée ou abandonnée) :
   - Modifier `state: "in-progress"` → `state: "todo"`
   - Incrémenter `reset_count`
   - Sauvegarder `roadmap.yaml` immédiatement après le changement

### Étape 2.1 : Créer les Descriptions Manquantes et Analyser les Dépendances

**CRITIQUE** : Cette étape doit être effectuée **APRÈS** le nettoyage des tâches in-progress et **AVANT** l'extraction du README.

Initialiser deux compteurs :
- `descriptions_created` = 0 (descriptions créées)
- `dependencies_updated` = 0 (paires de dépendances mises à jour)

**Pour chaque tâche dans `tasks`** :

1. **Vérifier et créer la description si absente** :
   - Si le champ `description` est absent, vide, ou null :
     - Lire le fichier de tâche `.cursor/agents/{task_file}` s'il existe
     - Extraire l'objectif depuis la section "Objectif" du fichier de tâche
     - Générer une description courte de 3 phrases maximum qui résume l'objectif de la tâche
     - Si le fichier de tâche n'existe pas, utiliser le titre de la tâche pour générer une description courte
     - Ajouter le champ `description` à la tâche dans roadmap.yaml
     - Incrémenter `descriptions_created`

2. **Analyser les dépendances avec toutes les autres tâches** :
   - **Pour chaque autre tâche dans `tasks`** (comparaison bidirectionnelle) :
     - Lire le champ `description` de la tâche courante (tâche A)
     - Lire le champ `description` de l'autre tâche (tâche B)
     - Comparer les deux descriptions et analyser les relations logiques :
       - **Si A devrait dépendre de B** : B fournit une infrastructure/base nécessaire, résout un problème bloquant, crée des fichiers/modules requis, ou établit des conventions/patterns à suivre
       - **Si B devrait dépendre de A** : B nécessite ce que A va produire, est bloquée par un problème que A résout, ou étend/utilise ce que A va créer
     - **Si une dépendance est détectée** :
       - Vérifier si la dépendance n'existe pas déjà dans le champ `dependencies` de la tâche concernée
       - Vérifier qu'ajouter cette dépendance ne créerait pas une dépendance circulaire (si A dépend de B, vérifier que B ne dépend pas déjà de A, directement ou transitivement via d'autres tâches)
       - Si la dépendance n'existe pas ET ne crée pas de cycle, l'ajouter au champ `dependencies`
       - Incrémenter `dependencies_updated` seulement si une dépendance a été ajoutée

3. **Sauvegarder roadmap.yaml** après avoir traité toutes les tâches

**Points importants** :
- Ne PAS lire les fichiers de tâches complets pour l'analyse de dépendances, utiliser uniquement le champ `description` de roadmap.yaml
- L'analyse doit être contextuelle et intelligente, pas exhaustive
- Pour créer une description manquante, il est autorisé de lire le fichier de tâche pour extraire l'objectif
- Ne pas créer de dépendances circulaires : si A dépend de B et B dépend déjà de A (directement ou transitivement), ne pas ajouter la dépendance
- En cas d'erreur lors de l'analyse ou de la création de description, **afficher un avertissement** mais **continuer** avec les autres tâches (ne pas bloquer le nettoyage)

**Règle de graphe connecté** :
- **CRITIQUE** : Aucune tâche ne devrait être isolée dans le graphe de dépendances
- Il peut y avoir plusieurs points d'entrée possibles (tâches sans dépendances), mais toutes les tâches devraient avoir au moins un lien de dépendance dans le graphe
- Chaque tâche doit soit avoir des dépendances, soit être une dépendance d'une autre tâche (ou les deux)
- Si une tâche est isolée (ni dépendances, ni dépendue par d'autres), l'analyse doit identifier au moins une relation logique pour créer un lien dans le graphe
- Si aucune relation logique ne peut être établie, créer une dépendance artificielle vers une tâche existante appropriée ou faire en sorte qu'une autre tâche dépende de la tâche isolée

**Note** : Cette analyse globale peut identifier des dépendances qui n'étaient pas détectées lors de la création initiale des tâches, et permet de maintenir la cohérence des dépendances dans la roadmap.

### Étape 2.4 : Extraction et Mise à Jour du README

**Avant** de supprimer chaque fichier `output_file` orphelin (non référencé), extraire les informations importantes et mettre à jour le README conformément à la règle `README.mdc`.

**Pour chaque fichier `output_file` qui sera supprimé** (non référencé dans aucun `dependencies-results`) :

1. **Lire le fichier de rapport complet** :
   - Lire le fichier `.cursor/agents/{output_file}` en entier
   - Si la lecture échoue → **afficher un avertissement** (ex: "Impossible de lire le rapport {output_file} pour extraction") mais **continuer** avec la suppression

2. **Extraire les informations pertinentes** :

   Parser le contenu du rapport pour identifier les sections suivantes et extraire les informations :

   a. **Fichiers modifiés** :
      - Identifier les sections "Fichiers modifiés", "Modifications apportées", "Modifications effectuées"
      - Extraire la liste des fichiers mentionnés (format: chemins relatifs ou absolus)

   b. **Nouvelles commandes** :
      - Rechercher les références à `.cursor/commands/` dans le rapport
      - Identifier les nouvelles commandes mentionnées (ex: `/nouvelle-commande`)
      - Extraire les descriptions et exemples d'usage si présents

   c. **Services et bases de données** :
      - Rechercher les mots-clés : "service", "database", "docker-compose", "postgres", "mysql", "redis", "mongodb"
      - Extraire les informations sur les services ajoutés/supprimés/modifiés

   d. **Variables d'environnement** :
      - Rechercher les mots-clés : "PORT", "DB_URL", "variable d'environnement", "environnement", "env"
      - Extraire les noms de variables et leurs descriptions

   e. **Scripts d'installation** :
      - Rechercher les références à `install.sh`, `setup.sh`, ou autres scripts d'installation
      - Extraire les modifications apportées aux scripts

   f. **Modifications structurelles** :
      - Identifier les créations/suppressions de dossiers mentionnées
      - Extraire les changements dans l'architecture du dépôt

3. **Mettre à jour le README** :

   Lire le README actuel (`README.md`) et mettre à jour les sections pertinentes selon les informations extraites :

   a. **Architecture du dépôt** :
      - Si de nouveaux fichiers/dossiers ont été créés : les ajouter dans la structure de l'arbre de fichiers et dans la section "Structure détaillée des dossiers"
      - Si des dossiers ont été supprimés : les retirer de la structure

   b. **Fichiers importants** :
      - Si de nouveaux fichiers critiques ont été créés : les ajouter dans la section "Fichiers importants et points centraux" avec description et exemples d'usage
      - Si des fichiers critiques ont été modifiés de manière significative : mettre à jour leur description

   c. **Commandes principales** :
      - Si de nouvelles commandes ont été ajoutées : les ajouter dans la section "Custom Commands" avec description, usage et exemples
      - Si des commandes existantes ont été modifiées : mettre à jour leur documentation

   d. **Services & bases de données** :
      - Si de nouveaux services ont été ajoutés : les ajouter dans la section "Services & Databases" avec ports, commandes de lancement et variables d'environnement
      - Si des services ont été supprimés : les retirer de la section

   e. **Variables d'environnement** :
      - Si de nouvelles variables ont été ajoutées : les ajouter dans la section "Environment variables" avec description et exemple de valeur
      - Si des variables ont été modifiées : mettre à jour leur documentation

   f. **Prérequis & installation** :
      - Si des scripts d'installation ont été modifiés : mettre à jour la section "Installation" avec les nouvelles instructions
      - Si de nouvelles dépendances ont été ajoutées : mettre à jour les instructions d'installation

4. **Préservation de la structure** :
   - **Ne pas** réécrire complètement le README
   - **Préserver** le formatage existant, l'ordre des sections et le style d'écriture
   - **Ajouter** les nouvelles informations de manière cohérente avec le style existant
   - **Ne pas** créer de duplication si l'information existe déjà

5. **Gestion des erreurs** :
   - Si l'extraction échoue : afficher un avertissement (ex: "Échec de l'extraction des informations du rapport {output_file}") mais **continuer** avec la suppression
   - Si la mise à jour du README échoue : afficher une erreur (ex: "Échec de la mise à jour du README avec les informations du rapport {output_file}") mais **continuer** avec la suppression (ne pas bloquer le nettoyage)

6. **Sauvegarder le README** :
   - Après chaque mise à jour réussie, sauvegarder le fichier `README.md`
   - Si la sauvegarde échoue → afficher une erreur mais continuer avec la suppression

**Note importante** : Cette étape s'exécute uniquement pour les fichiers qui seront effectivement supprimés (non référencés). Les fichiers encore utilisés (référencés dans `dependencies-results`) sont conservés et ne nécessitent pas d'extraction immédiate.

### Étape 2.5 : Nettoyage Global des Output Files

**Phase de nettoyage global des output_file** (identique à la phase 4 de l'étape 2.0 de `/agent`) :

**Pour chaque `output_file` dans `archived_output_files`** :

1. **Vérifier si le fichier est référencé** :
   - Parcourir toutes les tâches restantes dans `tasks` pour vérifier si `{output_file}` est présent dans leur liste `dependencies-results` (tenir compte des cas où `dependencies-results` est absent ou vide)

2. **Vérifier si le fichier physique existe** :
   - Vérifier si le fichier `.cursor/agents/{output_file}` existe physiquement

3. **Selon les résultats** :
   - **Si le fichier est référencé dans au moins un `dependencies-results` ET le fichier existe physiquement** : conserver le fichier (comportement actuel, fichier utilisé)
   - **Si le fichier est référencé dans au moins un `dependencies-results` MAIS le fichier n'existe pas physiquement** : retirer `{output_file}` de tous les `dependencies-results` concernés (référence invalide/historique, nettoyer la référence) et sauvegarder `roadmap.yaml`
   - **Si le fichier n'est référencé nulle part dans aucun `dependencies-results`** : avant de supprimer le fichier `.cursor/agents/{output_file}`, extraire les informations importantes pour mettre à jour le README (voir étape 2.4), puis supprimer le fichier (fichier orphelin, non utilisé)

### Étape 3 : Afficher la Sortie

Afficher la sortie minimale selon les résultats :

Construire un message de sortie qui inclut toutes les actions effectuées :

1. **Actions de nettoyage** :
   - Si `archived_count` > 0 ou `reset_count` > 0 : inclure ces informations
   - Si `archived_count` = 0 et `reset_count` = 0 : ne rien mentionner sur le nettoyage

2. **Actions d'amélioration** (Étape 2.1) :
   - Si `descriptions_created` > 0 : inclure le nombre de descriptions créées
   - Si `dependencies_updated` > 0 : inclure le nombre de dépendances mises à jour

3. **Format de sortie** :
   - Si aucune action n'a été effectuée (tous les compteurs = 0) :
     ```
     Aucune tâche in-progress à nettoyer
     ```
   - Sinon, construire un message concis en français listant les actions effectuées :
     ```
     Nettoyage terminé : X tâches archivées, Y tâches remises en todo, Z descriptions créées, W dépendances mises à jour
     ```
     (Remplacer X, Y, Z, W par les valeurs correspondantes, omettre les parties avec valeur 0)

## Format de Sortie

La sortie doit être minimale et en français :

**Exemples de sortie :**
- "Nettoyage terminé : 2 tâches archivées, 1 tâche remise en todo, 3 descriptions créées, 5 dépendances mises à jour"
- "Nettoyage terminé : 3 tâches archivées, 0 tâche remise en todo, 2 descriptions créées, 4 dépendances mises à jour"
- "Nettoyage terminé : 0 tâche archivée, 2 tâches remises en todo"
- "Nettoyage terminé : 4 descriptions créées, 8 dépendances mises à jour"
- "Aucune tâche in-progress à nettoyer"
- "Aucune roadmap trouvée, roadmap vide créée"

## Gestion des Erreurs (Fail-Fast)

Si une étape échoue :
- Arrêter immédiatement
- Informer l'utilisateur de l'erreur avec un message clair
- Expliquer ce qui a échoué et pourquoi
- Ne pas continuer avec des données partielles ou invalides

⚠️ **Exception** : Si la roadmap n'existe pas, créer une roadmap vide n'est pas considéré comme une erreur — c'est un comportement normal.

## Notes Importantes

- **Tout en français** : Tous les messages à l'utilisateur doivent être en français
- **Comportement autonome** : La commande peut être exécutée indépendamment de `/agent`
- **Logique identique** : L'archivage et le nettoyage des output_file suivent exactement la même logique que l'étape 2.0 de `/agent` (phases 1-4)
- **Sauvegarde immédiate** : Sauvegarder `roadmap.yaml` après chaque modification (archivage, remise en todo, création de description, ou mise à jour de dépendances)
- **Validation stricte** : Échouer explicitement si quelque chose est invalide ou manquant
- **Fail-Fast** : Si roadmap.yaml existe mais est invalide → échouer explicitement avec détails
- **Analyse des dépendances** : L'étape 2.1 analyse toutes les paires de tâches pour identifier et mettre à jour les dépendances manquantes, similaire à l'analyse bidirectionnelle de `/task`
- **Création de descriptions** : L'étape 2.1 crée automatiquement les descriptions manquantes en lisant les fichiers de tâches ou en utilisant le titre de la tâche
- **Graphe connecté** : Aucune tâche ne doit être isolée dans le graphe de dépendances. Toutes les tâches doivent avoir au moins un lien (dépendance entrante ou sortante) avec le reste du graphe

## Exemple de Séquence Complète

```
1. Lecture ou création de roadmap.yaml ✓
2. Validation de la structure ✓
3. Parcours des tâches in-progress (étape 2) ✓
   - Pour chaque tâche in-progress :
     - Si output_file existe → Archivage (retirer de tasks, mettre à jour dependencies et dependencies-results, supprimer task_file, collecter output_file) ✓
     - Si output_file n'existe pas → Remettre en todo ✓
   - Sauvegarder roadmap.yaml après chaque modification ✓
4. Création des descriptions manquantes et analyse des dépendances (étape 2.1) ✓
   - Pour chaque tâche :
     - Vérifier si description existe, sinon la créer depuis le fichier de tâche ou le titre ✓
     - Analyser les dépendances avec toutes les autres tâches (comparaison bidirectionnelle) ✓
     - Mettre à jour les dépendances détectées dans roadmap.yaml ✓
   - Sauvegarder roadmap.yaml ✓
5. Extraction et mise à jour du README (étape 2.4) ✓
   - Pour chaque output_file qui sera supprimé (non référencé) :
     - Lire le fichier de rapport ✓
     - Extraire les informations pertinentes (fichiers modifiés, commandes, services, variables, scripts, architecture) ✓
     - Mettre à jour le README selon les sections concernées ✓
     - Sauvegarder le README ✓
6. Nettoyage global des output_file (étape 2.5) ✓
   - Pour chaque output_file archivé :
     - Vérifier références dans dependencies-results ✓
     - Vérifier existence physique ✓
     - Conserver / Nettoyer référence / Supprimer (après extraction README si non référencé) selon le cas ✓
7. Affichage de la sortie minimale avec compteurs ✓
```

