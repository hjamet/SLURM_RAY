# SlurmRay v9.0.3 - Autonomous Distributed Ray on Slurm

> [!IMPORTANT]
> **Bug Reports**: SlurmRay is in beta. If you find a bug, please [report it on GitHub](https://github.com/hjamet/SLURM_RAY/issues).

> [!TIP]
> **Full Documentation**: Access the complete documentation [here](https://htmlpreview.github.io/?https://raw.githubusercontent.com/hjamet/SLURM_RAY/main/documentation/index.html).

> **The intelligent bridge between your local terminal and High-Performance Computing (HPC) power.**

SlurmRay allows you to transparently distribute your Python tasks across Slurm clusters (like Curnagl) or standalone servers (like Desi). It handles environment synchronization, local package detection, and task distribution automatically, turning your local machine into a control center for massive compute resources.

**Current State**: Version 9.0.3 (Feb 08). **File Sync Fix**: Replaced heredoc SSH with SFTP `put` for hash cache writes, fixing silent truncation that caused stale file uploads on large projects (100+ files).

> [!NOTE]
> **Ray Multiprocessing Patch (v9.0.2)**: Uses a **proxy module** that preserves all `multiprocessing` attributes (`Queue`, `Process`, `Lock`, `reduction`, etc.) while overriding only `Pool` with Ray's distributed version. Fixes all `ImportError` issues from v9.0.0-9.0.1.
>
> **Libraries Supported**: `sentence-transformers`, `ColBERT`, `torch.multiprocessing`, and any library using standard `multiprocessing`.

### ⚠️ Infrastructure Warning (Jan 28 2026)
> **Python 3.12.1 on Desi** is currently unstable (Ray Segfaults).
> While the new `uv` integration fixes the installation issues, runtime crashes (Exit 245) have been observed.
> **Recommendation**: Use **Python 3.11.6** for critical workloads until the Ray binary incompatibility is resolved.

## 🌟 Key Features (SlurmRay v9.0.2)
- **Ray Multiprocessing Patch**: Transparently replaces `multiprocessing.Pool` with `ray.util.multiprocessing.Pool` for distributed execution.
- **Local Wheel Packages Auto-Upload**: Reads `[tool.hatch.build.targets.wheel].packages` from your `pyproject.toml` and automatically uploads declared local packages (e.g. vendored libraries) to the cluster. Excludes them from `requirements.txt` to prevent failed PyPI installs.
- **Zero-Config Launch**: No `project_name` required. Auto-git detection.
- **Robust Venv**: Uses `uv venv` to safely create environments even on broken system Pythons.
- **Precision Logging**: Explicitly reports *why* a venv is reused or rebuilt (Hash Match vs Missing).

# Main Entry Scripts

| Script/Command | Description | Usage / Example |
|-----------------|-----------------------|-----------------|
| `slurmray curnagl` | Connect to Curnagl cluster via CLI | `slurmray curnagl` |
| `slurmray desi` | Connect to Desi server via CLI | `slurmray desi` |
| `pytest tests/...` | Run test suites | `pytest tests/test_local_complete_suite.py` |

# Installation

```bash
pip install -e .
```

### Prerequisites
*   **Local**: Python 3.9+
*   **Remote**: SSH access to a Slurm cluster or a standalone server with Ray support.
*   **Configuration**: Create a `.env` file at the root.

# Key Results (Performance Baseline)

| Scenario | Mode | Status | Avg Time |
|----------|------|--------|-------------|
| CPU Task (Simple) | Local | ✅ Pass | < 2s |
| GPU Task (Detection) | Desi | ✅ Pass | ~15s |
| Dependency Detection | Slurm | ✅ Pass | < 1s |
| Concurrent Launch (3 jobs) | Local | ✅ Pass | ~5s |
| **Multiprocessing Patch** | Local | ✅ Pass | ~30s |

# Repository Map

```text
root/
├── slurmray/              # Core logic
│   ├── backend/           # Backends (Slurm, Desi, Local)
│   ├── assets/            # Templates & Wrappers
│   ├── scanner.py         # AST Dependency Detection
│   ├── file_sync.py       # File Synchronization Logic
│   ├── RayLauncher.py     # Main API Entry Point
│   └── cli.py             # Interactive CLI
├── scripts/               # Maintenance & Cleanup utilities
├── tests/                 # Comprehensive test suites
├── documentation/         # HTML/Markdown docs
├── install.sh             # Installation Helper
└── README.md              # Documentation source
```

# Utility Scripts (`scripts/`)

| Script | Rôle technique | Contexte d'exécution |
|--------|----------------|----------------------|
| `diagnose_uv.py` | Validates `uv` based environment handling | Local/Remote |
| `diagnose_ray_segfault.py` | Diagnoses 3.12.1 Segfaults on Desi | Remote |
| `check_desi_locks.py` | Inspects lock files on Desi | Local (connects to Remote) |
| `check_desi_resources.py` | Checks CPU/GPU availability | Local (connects to Remote) |
| `cleanup_desi_projects.py` | Removes old projects/venvs | Maintenance |

# Roadmap

| Priority | Task | Status |
| :--- | :--- | :--- |
| 🔥 **High** | **Global Venv Caching** | Optimization of setup times. |
| ⚡ **Medium** | **Live Dashboard** | Real-time monitoring UI. |
| 🌱 **Low** | **Container Support** | Apptainer/Singularity support on Slurm. |

## 👥 Credits & License

**Bugs & Support**: This library is currently in **beta**. If you encounter any bugs, please report them on the [GitHub Issues](https://github.com/hjamet/SLURM_RAY/issues) page.

Maintained by the **DESI Department @ HEC UNIL**.
License: **MIT**.
