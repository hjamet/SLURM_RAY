## Contexte

Pour permettre aux agents de vérifier facilement qu'ils n'ont rien cassé lors de l'implémentation des tâches ultérieures, il est nécessaire de créer des tests basiques "hello world" fonctionnels sur CPU et GPU. Ces tests doivent être simples, rapides à exécuter, et permettre de valider que le package SLURM_RAY fonctionne correctement avec des fonctions minimales sur un cluster SLURM. Ces tests serviront de base de validation pour toutes les modifications futures.

## Objectif

Créer deux tests fonctionnels simples "hello world" : un pour CPU et un pour GPU, qui exécutent des fonctions minimales via Ray sur un cluster SLURM. Ces tests doivent être rapides à exécuter, faciles à comprendre, et permettre de valider rapidement que le système fonctionne correctement après chaque modification majeure du code.

## Fichiers Concernés

### Du travail effectué précédemment :
- `slurmray/RayLauncher.py` : Classe principale qui sera testée avec des fonctions simples.
- `README.md` : Contient des exemples d'utilisation qui peuvent servir de base pour les tests.

### Fichiers potentiellement pertinents pour l'exploration :
- `test_cpu.py` et `test_gpu.py` : Tests existants qui pourraient être adaptés ou servir de référence (s'ils existent).
- `slurmray/assets/spython_template.py` : Template du script Python exécuté sur le cluster, utile pour comprendre le contexte d'exécution.

### Recherches à effectuer :
- Recherche sémantique : "Où se trouvent les tests existants dans le projet ?"
- Recherche sémantique : "Comment structurer des tests simples pour RayLauncher ?"
- Documentation : Lire le README pour comprendre les exemples d'utilisation de base

### Fichiers de résultats d'autres agents (si pertinents) :
- Aucun pour le moment

**Fichier output pour le rapport final :**
- `.cursor/agents/rapport-creer-tests-hello-world-cpu-gpu.md`

## Instructions de Collaboration

**OBLIGATOIRE ET CRITIQUE** : Cette section doit être extrêmement directive et impérative. Tu DOIS spécifier que l'agent :

- **EST INTERDIT** de commencer à implémenter quoi que ce soit immédiatement
- **DOIT** lire EXHAUSTIVEMENT tous les fichiers listés dans "Fichiers Concernés" avant toute action
- **DOIT** effectuer toutes les recherches sémantiques mentionnées
- **DOIT** lire le README et toute documentation pertinente
- **DOIT** atteindre une compréhension approfondie du contexte et du projet avant toute discussion
- **DOIT** discuter avec l'utilisateur pour clarifier les attentes précises, poser des questions sur les contraintes techniques (où placer les tests, format des tests, comment valider CPU vs GPU, etc.), et établir un plan d'action détaillé ensemble
- **DOIT TOUJOURS** créer le fichier de rapport final dans le fichier output mentionné après avoir terminé (voir section "Instructions pour les Rapports Finaux")
- Seulement APRÈS avoir complété cette exploration exhaustive et cette planification collaborative, peut commencer toute implémentation

Emphasizer que l'exploration est OBLIGATOIRE, pas optionnelle.

