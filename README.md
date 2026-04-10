# Crucible Metadata Input  
User interface for annotating, managing, and uploading metadata for Crucible experiments.

---

## 0. Prerequisites
Assumption: this README was initially created and tested via MacOS Tahoe 26.0; if you are doing this via Windows, there might be some issues and feel free to reach out to me (GitHub: @tranngocsongtruc) if you have issues. Everything below assumes your working folder is ~/Desktop/mf/.
Before starting, make sure you have:
- [VS Code](https://code.visualstudio.com)
- [Miniconda](https://docs.conda.io/en/latest/miniconda.html)
- [Homebrew](https://brew.sh)
- Git (`brew install git`)
- Xcode Command Line Tools (`xcode-select --install`)

---

## 1. Environment Setup

### 1.1. Create and activate the Conda environment
```bash
conda create -n crucible python=3.10 -y
conda activate crucible
```

### 1.2. Clone the repository
```bash
cd ~/Desktop/mf
git clone -b titanx-interface git@github.com:MolecularFoundry/crucible-metadata-input.git
cd crucible-metadata-input
```

### 1.3. Install dependencies
```bash
pip install numpy qtpy pyqt5 pyqtgraph pyyaml requests pandas Pillow
```
Optional dark theme support (current software might not support so not recommended):
```bash
pip install qdarktheme
```

## 2. Linked Repository Dependency

This project depends on utilities from crucible-rabbit-mq, which must be cloned and installed locally (see its README).
Once installed, you can import functions like:
```bash
from crucible_utils.general_utils import run_rclone_command
```

## 3. Run the Application
```bash
python -m scripts.start
```
You should see terminal logs like:
```bash
ADDING WIDGETS TO THE SUBTREE LINE ...
connected IS AN CHECKBOX
disabling connection
disconnected
...
```
This indicates the PyQt GUI launched successfully.

## 4. Developer Workflow
Create a new feature branch
```bash
git checkout -b login-logout-interface
```
Run tests or app
```bash
python -m scripts.start
```

## 5. Verification Checklist

| Check | Command | Expected Result |
|-------|----------|-----------------|
| Conda environment active | `which python` | Path includes `/envs/crucible/bin/python` |
| GUI runs without error | `python -m scripts.start` | Application launches |
| Utility import works | `from crucible_utils.general_utils import run_rclone_command` | No ImportError |

## 6. Notes

Always activate your crucible environment before running the app.

Keep crucible-metadata-input and crucible-rabbit-mq in the same parent directory (~/Desktop/mf/).

`pip install -e .` for editable installs in linked repos helps with active development.