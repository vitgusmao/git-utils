# Dev Tools Setup Scripts

This repository contains scripts to help automate and manage your local development environment, Git configuration, and other common setup tasks.

---

## 📌 Scripts

### `setup_git_gpg_config.py`

Interactive script to configure a GPG signing key for all Git repositories under a specific parent folder. It:

- Creates a custom `.gitconfig-<foldername>` file with your GPG key.
- Automatically appends an `[includeIf "gitdir:<path>/"]` block to your global `~/.gitconfig`, applying the config to all repositories in that folder.

#### 🔧 Usage

```bash
python3 setup_git_gpg_config.py
```

### `install_cursor.py`

Securely installs the Cursor AppImage on Ubuntu 24.04. It extracts the AppImage, configures the Chromium sandbox, adds a wrapper launcher, and optionally creates a desktop entry.

#### 🔧 Usage

```bash
python3 install_cursor.py /path/to/Cursor-<version>-x86_64.AppImage
```
