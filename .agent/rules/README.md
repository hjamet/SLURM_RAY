---
trigger: always_on
glob: "**/*"
description: "README"
---

# README Sync Rule

The [README.md](mdc:README.md) is the single source of truth. **It must be updated immediately upon any change** (code, config, scripts).

## Mandatory Structure
1. **Project Overview**: distinct goal, status, and features.
2. **Main Entry Scripts (`scripts/`)**: Table of primary entry points, their purpose, usage example, and environment variables. *Moved to top for visibility.*
3. **Installation**: Prerequisites and step-by-step commands.
4. **Key Results**: Data-only tables/charts of benchmarks.
5. **Repository Map**: Tree view + role of key directories.
6. **Utility Scripts (`scripts/utils/`)**: Table of helper scripts.
7. **Roadmap**: Future actions only (remove completed). Sorted by dependency.

## Zero Tolerance Protocol
- **Outdated = Broken**: A PR/Task is not complete until the README matches reality.
- **Atomic**: No "see previous version". The current README stands alone.
- **Precision**: If a detail is missing, find it. Do not guess.
