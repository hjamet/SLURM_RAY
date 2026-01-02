# SlurmRay v6.0.7 - Autonomous Distributed Ray on Slurm

> **Le pont intelligent entre votre terminal local et la puissance du HPC.**

SlurmRay permet de distribuer vos tâches Python sur des clusters Slurm (Curnagl, ISIPOL) ou des serveurs distants en toute transparence. Il transforme votre machine locale en une console de pilotage pour le calcul haute performance.

---

## 🚀 Le Concept : "Local-to-Cluster"
SlurmRay ne se contente pas de lancer du code Ray. Il orchestre tout le flux de travail :
1. **Analyse AST** : Détecte automatiquement les dépendances de votre projet local.
2. **Sync Incrémentale** : Pousse vos fichiers et vos packages vers le cluster via rsync.
3. **Bridge Ray** : Installe un environnement virtuel, alloue les nœuds Slurm et déploie un cluster Ray à la volée.
4. **Exécution Transparente** : Exécute votre fonction locale sur le cluster et vous rend le résultat.

[**Consulter la Documentation Interactive (HTML)**](https://htmlpreview.github.io/?https://github.com/lopilo/SLURM_RAY/blob/master/documentation/index.html)

---

### [NEW] Nouveautés v6.0.7
- **Remote Execution** : Correction du nettoyage agressif du `DesiBackend`.
- **Dependency Detection** : Scanner amélioré pour préserver les structures `__init__.py`.
- **Serialization** : Auto-injection des imports du package racine pour corriger les erreurs `dill`.

## Quick Start

### Installation
```bash
pip install slurmray
```

### Usage Exemple
```python
from slurmray import RayLauncher

def my_heavy_compute(n):
    # Ce code s'exécutera sur le cluster
    return sum(i*i for i in range(n))

launcher = RayLauncher(cluster="curnagl", node_nbr=2)
result = launcher(my_heavy_compute, args={"n": 10**8})
print(f"Résultat : {result}")
```

## Repository Map
| Composant | Rôle |
| :--- | :--- |
| `slurmray/` | Logique coeur (Backend, Scanner, Sync) |
| `documentation/` | [Docs HTML](documentation/index.html) et [API Reference](documentation/RayLauncher.md) |
| `tests/` | Suite de tests automatisés |

## Roadmap 2026
- [ ] **Enhanced Caching** : Réduction du temps de démarrage via mise en cache agressive.
- [ ] **Monitoring Dashboard** : Interface web pour le suivi des jobs en temps réel.
- [ ] **Docker Support** : Support des containers personnalisés sur Slurm.

---
*SlurmRay est un outil officiel de DESI @ HEC UNIL.*

