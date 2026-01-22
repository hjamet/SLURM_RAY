# SlurmRay v8.1.x - Autonomous Distributed Ray on Slurm

> [!TIP]
> **Full Documentation**: Access the complete documentation [here](https://htmlpreview.github.io/?https://raw.githubusercontent.com/hjamet/SLURM_RAY/main/documentation/index.html).

> **The intelligent bridge between your local terminal and High-Performance Computing (HPC) power.**

SlurmRay allows you to transparently distribute your Python tasks across Slurm clusters (like Curnagl) or standalone servers (like Desi). It handles environment synchronization, local package detection, and task distribution automatically, turning your local machine into a control center for massive compute resources.

**Current State**: Version 8.1.x stabilized. Local mode is hardened and serves as a high-fidelity reference for pre-testing before cluster deployment.

---

# 🚀 Main Entry Scripts

| Script/Command | Description | Usage / Example |
|-----------------|-----------------------|-----------------|
| `pytest tests/test_local_complete_suite.py` | **High-Fidelity Local Validation**: Ensures code runs perfectly in local isolation before deployment. | `pytest tests/test_local_complete_suite.py` |
| `pytest tests/test_desi_complete_suite.py` | **Desi Backend Validation**: Complete test on Desi server (CPU, GPU, Concurrency, Serialization). | `pytest tests/test_desi_complete_suite.py` |
| `pytest tests/test_raylauncher_example_complete.py` | **Integration Test**: Verifies full dependency detection and Slurm execution flow. | `pytest tests/test_raylauncher_example_complete.py` |

---

# 🛠 Installation

```bash
pip install -e .
```

### Prerequisites
*   **Local**: Python 3.9+
*   **Remote**: SSH access to a Slurm cluster or a standalone server with Ray support.
*   **Configuration**: Create a `.env` file at the root (see Configuration section).

---

# 📖 Core Concepts

### Local-to-Cluster Orchestration
SlurmRay manages the entire lifecycle of a remote task:
1.  **AST Analysis**: Automatically scans imports to identify local modules and dependencies to upload. **You don't need to manually push your source code.**
2.  **Surgical Synchronization**: Uses incremental transfers to push only modified files.
3.  **Autonomous Ray Bridging**: Allocates nodes, installs the synchronized venv, and deploys a temporary Ray cluster.
4.  **Transparent Execution**: Returns results (serialized via `dill`) directly to your local session.

### Pro-Tip: Venv Reuse & Project Naming
We recommend using a consistent `project_name` for all related computations. SlurmRay computes a hash of your `requirements.txt`: if it hasn't changed, the remote virtual environment is reused instantly, drastically reducing setup time.

### Automatic Cleanup
Files and virtual environments on remote servers are automatically deleted after a retention period (defined by `retention_days`, default 1 day). This ensures the server storage remains clean.

---

# 🖥 SlurmRay CLI

SlurmRay includes a powerful interactive CLI for managing your jobs on both Slurm and Desi.

```bash
# Connect to Curnagl (Slurm)
slurmray curnagl

# Connect to Desi server
slurmray desi
```

**Features:**
*   **Live Monitoring**: Real-time status of your running and waiting jobs.
*   **Job Management**: Cancel jobs directly from the interface.
*   **Dashboard Access**: Automatically sets up an SSH tunnel to the Ray Dashboard for any running job.

---

# 📁 Log Locations

*   **Local Logs**: Detailed launcher logs are stored in `logs/RayLauncher.log`.
*   **Remote Execution Logs**: 
    - On **Slurm**: Standard Slurm output files in the project directory.
    - On **Desi**: Located in `slurmray-server/{project_name}/.slogs/server/`.

---

# 📊 Performance Baseline

| Scenario | Mode | Status | Avg Time |
|----------|------|--------|-------------|
| CPU Task (Simple) | Local | ✅ Pass | < 2s |
| GPU Task (Detection) | Desi | ✅ Pass | ~15s |
| Dependency Detection | Slurm | ✅ Pass | < 1s |
| Concurrent Launch (3 jobs) | Local | ✅ Pass | ~5s |

---

# 🗺 Repository Structure

```text
root/
├── slurmray/              # Core logic
│   ├── backend/           # Backends (Slurm, Desi, Local)
│   ├── assets/            # Templates & Wrappers
│   ├── scanner.py         # AST Dependency Detection
│   ├── RayLauncher.py     # Main API Entry Point
│   └── cli.py             # Interactive CLI
├── scripts/               # Maintenance & Cleanup utilities
├── tests/                 # Comprehensive test suites
├── documentation/         # HTML/Markdown docs
└── README.md              # Documentation source
```

---

# 🛤 Roadmap

| Priority | Task | Status |
| :--- | :--- | :--- |
| 🔥 **High** | **Global Venv Caching** | Optimization of setup times. |
| ⚡ **Medium** | **Live Dashboard** | Real-time monitoring UI. |
| 🌱 **Low** | **Container Support** | Apptainer/Singularity support on Slurm. |

---

## 👥 Credits & License

**Bugs & Support**: This library is currently in **beta**. If you encounter any bugs, please report them on the [GitHub Issues](https://github.com/hjamet/SLURM_RAY/issues) page. For urgent resolution, you can contact Henri Jamet directly at [henri.jamet@unil.ch](mailto:henri.jamet@unil.ch).

Maintained by the **DESI Department @ HEC UNIL**.
License: **MIT**.
