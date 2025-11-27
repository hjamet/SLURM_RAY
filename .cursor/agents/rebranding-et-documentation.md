## Contexte

Le package est désormais un outil hybride Curnagl/Desi pour le département DESI @ HEC UNIL. La documentation et les métadonnées du projet doivent refléter cette nouvelle identité et guider les nouveaux utilisateurs.

## Objectif

Mettre à jour toute la documentation (README, Docstrings, PyPI metadata) pour officialiser le support de Desi et le changement de scope du projet.

## Fichiers Concernés

### Du travail effectué précédemment :
- Tous les rapports précédents.

### Fichiers potentiellement pertinents pour l'exploration :
- `README.md`
- `pyproject.toml`
- `slurmray/RayLauncher.py` (docstrings)

## Instructions de Collaboration

- **DOIT** mettre à jour le `README.md` avec :
    - Nouvelle description "Outil officiel DESI @ HEC UNIL".
    - Instructions claires pour utiliser `cluster='desi'`.
    - Pré-requis pour le mode Desi (accès SSH, etc.).
- **DOIT** mettre à jour les docstrings des classes et méthodes principales.
- **DOIT** vérifier `pyproject.toml` (description, mots-clés).
- **DOIT** créer un exemple simple d'utilisation pour Desi dans la documentation.
- **DOIT TOUJOURS** créer le fichier de rapport final `rapport-rebranding-et-documentation.md` après avoir terminé.

