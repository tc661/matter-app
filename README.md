# HPC Remote File Browser & VASP Analysis Tool

A cross-platform PyQt-based application for:
- Connecting to remote HPC servers via SFTP.
- Browsing HPC directories.
- Visualizing VASP `POSCAR` structures in **PyVista** or **VESTA**.
- Running **automatic post-processing and analysis** on VASP outputs.

---

## ✨ Features

### 🔍 HPC Remote File Browser
- **Remote SFTP Browser** – Navigate HPC file systems over SSH without manually running `scp` or `sftp`.
- **Symlink Handling** – Correctly detects symbolic links and their targets.
- **Hidden File Filtering** – Skip `.*` files for cleaner navigation.

### 📐 Structure Visualization
- View structures directly with **PyVista** (integrated 3D view).
- Open in **VESTA** if installed (auto-detected via `PATH`).
- Planned: side-by-side or toggle between PyVista & VESTA.

### 📊 Automated VASP Analysis (`analysis.py`)
The included `analysis.py` script can:
- Detect and classify multiple VASP runs from `OUTCAR`.
- Parse `INCAR` parameters (ENCUT, spin-orbit coupling, etc.).
- Check **relaxation completion** from `OUTCAR`.
- Count atoms from `CONTCAR`.
- Parse **KPOINTS** grid.
- Perform **ENCUT** and **KPOINTS convergence checks**.
- Extract total and per-atom magnetization from `OUTCAR`.
- Generate a **full text report** summarizing all results.