# SlurmRay v8.1.x - Autonomous Distributed Ray on Slurm

> **The intelligent bridge between your local terminal and High-Performance Computing (HPC) power.**

SlurmRay allows you to transparently distribute your Python tasks across Slurm clusters (like Curnagl) or standalone servers. It handles environment synchronization, local package detection, and task distribution automatically, turning your local machine into a control center for massive compute resources.

**État courant** : Version 8.1.x stabilisée. Le mode Local est maintenant durci et sert de référence de haute-fidélité pour le pré-test avant déploiement sur cluster.

---

# 🚀 Scripts d'entrée principaux

| Script/Commande | Description détaillée | Usage / Exemple |
|-----------------|-----------------------|-----------------|
| `pytest tests/test_local_complete_suite.py` | **Validation Haute-Fidélité Local** : Vérifie que le code tourne parfaitement en local avec l'isolation SlurmRay avant envoi. | `pytest tests/test_local_complete_suite.py` |
| `pytest tests/test_desi_complete_suite.py` | **Validation Backend Desi** : Test complet sur serveur ISIPOL (CPU, GPU, Concurrence, Serialization). | `pytest tests/test_desi_complete_suite.py` |
| `pytest tests/test_raylauncher_example_complete.py` | **Test d'Intégration** : Vérifie le flux complet de détection de dépendances et d'exécution Slurm. | `pytest tests/test_raylauncher_example_complete.py` |

---

# 🛠 Installation

```bash
pip install -e .
```

### Pré-requis
*   **Local**: Python 3.9+
*   **Remote**: Accès SSH à un cluster Slurm ou un serveur avec Ray.
*   **Configuration**: Créer un fichier `.env` à la racine (voir section Configuration).

---

# 📖 Description détaillée

### Le concept "Local-to-Cluster"
SlurmRay orchestre le cycle de vie complet d'une tâche distante :
1.  **Analyse AST** : Scanne automatiquement les imports pour identifier les modules locaux à uploader.
2.  **Synchronisation Chirurgicale** : Utilise `rsync` pour ne pousser que les fichiers modifiés.
3.  **Bridging Ray Autonome** : Alloue les nœuds, installe le venv synchronisé et déploie un cluster Ray temporaire.
4.  **Exécution Transparente** : Retourne les résultats `dill` directement dans votre session locale.

### Direction actuelle
Nous nous concentrons sur la robustesse du mode `cluster='local'`. L'objectif est simple : **si le code tourne en local, il doit tourner en ligne sans modification.** Le backend local simule maintenant l'isolation totale via `spython.py` et gère les priorités de `sys.path` pour éviter les collisions avec les packages installés.

---

# 📊 Principaux résultats

| Scenario | Mode | Status | Temps Moyen |
|----------|------|--------|-------------|
| CPU Task (Simple) | Local | ✅ Pass | < 2s |
| GPU Task (Detection) | Desi | ✅ Pass | ~15s |
| Dependency Detection | Slurm | ✅ Pass | < 1s |
| Concurrent Launch (3 jobs) | Local | ✅ Pass | ~5s |

---

# 🗺 Plan du repo

```text
root/
├── slurmray/              # Cœur du système
│   ├── backend/           # Backends (Slurm, Desi, Local)
│   ├── assets/            # Templates (spython, desi_wrapper)
│   ├── scanner.py         # Détection AST des dépendances
│   └── file_sync.py       # Logique de synchro rsync
├── scripts/               # Scripts utilitaires et maintenance
├── tests/                 # Suites de tests complètes
├── documentation/         # Docs HTML et Markdown
└── README.md              # Source unique de vérité
```

---

# 🔧 Scripts exécutables secondaires & Utilitaires

| Script | Rôle technique | Contexte d'exécution |
|--------|----------------|----------------------|
| `scripts/cleanup_desi_projects.py` | Nettoie les projets expirés sur le serveur Desi. | Cron job journalier sur ISIPOL. |
| `tests/test_auto_detection.py` | Vérifie la détection des imports profonds. | Développement / Debug scanner. |

---

# 🛤 Roadmap

| Priorité | Tâche | Dépendance |
| :--- | :--- | :--- |
| 🔥 **Haute** | **Global Venv Caching** : Optimiser le temps de setup en réutilisant les venvs communs. | - |
| ⚡ **Moyenne** | **Live Dashboard** : Interface web pour monitorer les jobs et les logs en temps réel. | - |
| 🌱 **Basse** | **Container Support** : Support natif d'Apptainer/Singularity sur Slurm. | - |

---

## 👥 Crédits & License

Maintenu par le **DESI Department @ HEC UNIL**.
Licence **MIT**.
