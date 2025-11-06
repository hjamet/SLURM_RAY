## Contexte

L'utilisateur souhaite que l'interface interactive de gestion des jobs SLURM permette d'ouvrir automatiquement le dashboard Ray en local pour monitorer les jobs actifs. Actuellement, le dashboard Ray est configuré dans le code mais n'est pas accessible facilement depuis la machine locale. Il faut intégrer cette fonctionnalité dans l'interface interactive pour permettre l'ouverture automatique du dashboard via port forwarding SSH ou autre mécanisme.

## Objectif

Intégrer l'ouverture automatique du dashboard Ray dans l'interface interactive de gestion des jobs SLURM. L'utilisateur doit pouvoir ouvrir le dashboard Ray en local (sur http://localhost:8888) depuis l'interface interactive, avec gestion automatique du port forwarding SSH si nécessaire pour les jobs distants.

## Fichiers Concernés

### Du travail effectué précédemment :
- `slurmray/RayLauncher.py` (ligne 199) : Configuration du dashboard Ray avec `include_dashboard=True` et `dashboard_host='0.0.0.0'`, `dashboard_port=8888`. Il y a un bug mentionné dans la tâche task-0d qui doit être corrigé.
- `slurmray/RayLauncher.py` (lignes 398-506) : La méthode `__launch_server` gère la connexion SSH au cluster, pourrait nécessiter l'ajout de port forwarding pour le dashboard.
- `.cursor/agents/corriger-et-rediriger-dashboard-ray.md` : Tâche existante qui traite de la redirection du dashboard, pourrait être liée ou intégrée.

### Fichiers potentiellement pertinents pour l'exploration :
- `slurmray/RayLauncher.py` : Toute la logique de configuration et de lancement de Ray avec dashboard.
- Documentation Ray : Comprendre comment accéder au dashboard et comment configurer le port forwarding.

### Recherches à effectuer :
- Recherche sémantique : "Comment ouvrir automatiquement le dashboard Ray dans un navigateur depuis Python ?"
- Recherche sémantique : "Comment configurer le port forwarding SSH pour le dashboard Ray sur un cluster distant ?"
- Recherche web : "Meilleures pratiques pour accéder au dashboard Ray sur un cluster SLURM distant"
- Documentation : Lire le README et la documentation Ray sur le dashboard

### Fichiers de résultats d'autres agents (si pertinents) :
- `.cursor/agents/rapport-corriger-et-rediriger-dashboard-ray.md` : Si cette tâche est terminée, réutiliser le code de redirection du dashboard.
- `.cursor/agents/rapport-creer-interface-interactive-gestion-jobs-slurm.md` : L'interface interactive doit être créée pour intégrer l'ouverture du dashboard.

**Fichier output pour le rapport final :**
- `.cursor/agents/rapport-integrer-ouverture-automatique-dashboard-ray.md`

## Instructions de Collaboration

**OBLIGATOIRE ET CRITIQUE** : Cette section doit être extrêmement directive et impérative. Tu DOIS spécifier que l'agent :

- **EST INTERDIT** de commencer à implémenter quoi que ce soit immédiatement
- **DOIT** lire EXHAUSTIVEMENT tous les fichiers listés dans "Fichiers Concernés" avant toute action
- **DOIT** lire le rapport de la tâche "creer-interface-interactive-gestion-jobs-slurm" pour comprendre comment intégrer l'ouverture du dashboard dans l'interface
- **DOIT** lire le rapport de la tâche "corriger-et-rediriger-dashboard-ray" si disponible pour réutiliser le code de redirection
- **DOIT** effectuer toutes les recherches sémantiques et web mentionnées
- **DOIT** lire le README et toute documentation pertinente
- **DOIT** atteindre une compréhension approfondie du contexte et du projet avant toute discussion
- **DOIT** discuter avec l'utilisateur pour clarifier les attentes précises, poser des questions sur les contraintes techniques (mécanisme de port forwarding, gestion des ports multiples, ouverture automatique du navigateur, etc.), et établir un plan d'action détaillé ensemble
- **DOIT TOUJOURS** créer le fichier de rapport final dans le fichier output mentionné après avoir terminé (voir section "Instructions pour les Rapports Finaux")
- Seulement APRÈS avoir complété cette exploration exhaustive et cette planification collaborative, peut commencer toute implémentation

Emphasizer que l'exploration est OBLIGATOIRE, pas optionnelle.

