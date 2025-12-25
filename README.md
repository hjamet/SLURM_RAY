# SlurmRay v6.0.5 - Autonomous Distributed Ray on Slurm

SlurmRay acts as a bridge between your local development environment and high-performance computing clusters (DESI/Curnagl). It handles environment synchronization, local package detection, and task distribution automatically.

---

### [NEW] Fixes in v6.0.5
- **Local Package Detection**: Fixed a bug where packages with binaries in `bin/` (like `accelerate`, `gdown`) were incorrectly marked as local and excluded from `requirements.txt`.
- **Torch Injection**: Resolved a substring match bug where `fast-pytorch-kmeans` prevented the automatic injection of `torch`.
- **Project Structure**: Improved `RayLauncher` to proactively include editable packages (like `trail-rag`) in the upload set, resolving `ModuleNotFoundError`.

## Project Overview
- **Goal**: Effortslessly distribute Python tasks on Slurm clusters or standalone servers using the Ray library.
- **Status**: Stable (v6.0.4). Correction de la détection erronée des packages locaux (binaires venv).
- **Features**: Utilisation de `uv` pour la génération des requirements, suppression des contraintes de version pour compatibilité multi-Python.

## Main Entry Scripts
| Script | Purpose | Usage Example | Env Vars |
| :--- | :--- | :--- | :--- |
| `slurmray` | CLI entry point for project management and job monitoring. | `slurmray --help` | `SLURMRAY_CONFIG` |

*The `slurmray` command is the primary way to interact with the system once installed via pip or poetry.*

## Installation
1. **Prerequisites**: Python >= 3.9, Poetry (optional).
2. **Commands**:
```bash
pip install slurmray
```
*Installs the stable version of SlurmRay from PyPI.*

```bash
git clone https://github.com/lopilo/SLURM_RAY.git
cd SLURM_RAY
poetry install
```
*Prepares the development environment and installs dependencies in a virtual environment.*

## Key Results
| Benchmark | Cluster | Performance |
| :--- | :--- | :--- |
| Job Startup | Curnagl | < 5s (cached) |
| File Sync | ISIPOL | Incremental (HA-based) |

## Repository Map
```text
.
├── slurmray/         # Core package logic
│   ├── backend/      # Cluster/Server specific implementations
│   ├── scanner.py    # AST-based dependency tracer
│   └── file_sync.py  # Incremental file synchronization
├── tests/            # Automated test suite
├── documentation/    # Extended technical docs
└── pyproject.toml    # Project configuration and metadata
```

## Utility Scripts
*No additional utility scripts in `scripts/utils/` currently.*

## Roadmap
- **Enhanced Caching**: Implement more aggressive caching for large conda/venv environments to reduce startup time. *Estimated: 15h. Priority: High.*
- **Monitoring Dashboard**: Integration with a web-based UI for real-time job monitoring and log visualization. *Estimated: 40h. Priority: Medium.*
- **Docker Support**: Allow running jobs inside custom Docker containers on supported Slurm clusters. *Estimated: 25h. Priority: Low.*
