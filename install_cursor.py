#!/usr/bin/env python3

# Install Cursor (AppImage) safely on Ubuntu 24.04.

# Usage:
#   python3 install_cursor.py /path/to/Cursor-<version>-x86_64.AppImage
# Optional flags:
#   --install-dir=/path/to/dir        (default: ~/Apps/cursor)
#   --name=Cursor                     (desktop entry Name)
#   --make-desktop=[yes|no]           (default: yes)
#   --system-dir                      (install to /opt/cursor/<version>; needs sudo)
#   --no-apt                          (skip apt checks/installs)

# What this script does:
#   1) (Optionally) installs libfuse2t64 for AppImages.
#   2) Extracts the AppImage instead of running it directly.
#   3) Fixes Chromium's setuid sandbox (root:root, mode 4755) if present.
#   4) Installs a wrapper at ~/.local/bin/cursor-launch that sets CHROME_DEVEL_SANDBOX.
#   5) Creates a .desktop launcher (Icon path absolute) for the app grid/dock.
#   6) Uses a stable "current" symlink so upgrades are trivial.

# Security notes:
#   - We DO NOT use --no-sandbox.
#   - We DO NOT rely on aa-exec. Some setups set PR_SET_NO_NEW_PRIVS which breaks SUID.
#   - We check for 'nosuid' on the target filesystem and suggest /opt fallback if needed.

# You can re-run this script for upgrades; it will keep your existing desktop entry
# and just repoint the "current" symlink.


import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

RUN = lambda *args, **kw: subprocess.run(args, check=True, **kw)

def shlex_quote(s: str) -> str:
    return "'" + s.replace("'", "'\"'\"'") + "'"

def parse_args():
    p = argparse.ArgumentParser(description="Install Cursor AppImage (Ubuntu 24.04)")
    p.add_argument("appimage", help="Path to Cursor AppImage")
    p.add_argument("--install-dir", default=str(Path.home() / "Apps" / "cursor"))
    p.add_argument("--name", default="Cursor")
    p.add_argument("--make-desktop", choices=["yes", "no"], default="yes")
    p.add_argument("--system-dir", action="store_true",
                   help="Install under /opt/cursor/<version> (requires sudo)")
    p.add_argument("--no-apt", action="store_true",
                   help="Skip apt install checks (assume deps present)")
    return p.parse_args()

def require_cmd(cmd: str) -> None:
    if shutil.which(cmd) is None:
        raise RuntimeError(f"Required command not found: {cmd}")

def apt_install(packages):
    # Install packages via apt-get (requires sudo). Skip if --no-apt.
    if not packages:
        return
    print(f"[*] Installing packages (may prompt for password): {' '.join(packages)}")
    RUN("sudo", "apt-get", "update", "-y")
    RUN("sudo", "apt-get", "install", "-y", *packages)

def is_nosuid(path: Path) -> bool:
    try:
        out = subprocess.check_output(["findmnt", "-no", "OPTIONS", "-T", str(path)]).decode()
        return "nosuid" in out
    except Exception:
        # If findmnt not found or fails, assume OK.
        return False

def is_noexec(path: Path) -> bool:
    try:
        out = subprocess.check_output(["findmnt", "-no", "OPTIONS", "-T", str(path)]).decode()
        return "noexec" in out
    except Exception:
        return False

def ensure_exec_dir(base: Path) -> Path:
    base.mkdir(parents=True, exist_ok=True)
    if is_noexec(base):
        # Fallback to ~/.cache if base is noexec
        alt = Path.home() / ".cache" / "cursor-installer"
        print(f"[!] {base} is mounted noexec; using {alt}")
        alt.mkdir(parents=True, exist_ok=True)
        return alt
    return base

def derive_version(appimage_name: str) -> str:
    # Try to pull e.g. "1.4.3" from "Cursor-1.4.3-x86_64.AppImage"
    m = re.search(r"(\d+\.\d+\.\d+)", appimage_name)
    return m.group(1) if m else "unknown"

def copy_to_exec_tmp(appimage: Path) -> Path:
    work = Path.home() / ".cache" / "cursor-installer" / "work"
    work.mkdir(parents=True, exist_ok=True)
    target = work / appimage.name
    shutil.copy2(appimage, target)
    target.chmod(0o755)
    return target

def extract_appimage(appimage_path: Path, dest_dir: Path) -> Path:
    # Extract into a temporary dir, then move resulting squashfs-root to dest_dir/version
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        env = os.environ.copy()
        # Some environments need TMPDIR pointing to an exec-capable path
        env["TMPDIR"] = str(td_path)
        print(f"[*] Extracting AppImage: {appimage_path}")
        RUN(str(appimage_path), "--appimage-extract", cwd=td_path, env=env)
        extracted = td_path / "squashfs-root"
        if not extracted.is_dir():
            raise RuntimeError("Extraction failed: squashfs-root not found.")
        version = derive_version(appimage_path.name)
        target_dir = dest_dir / version
        print(f"[*] Installing to: {target_dir}")
        if target_dir.exists():
            shutil.rmtree(target_dir)
        shutil.copytree(extracted, target_dir)
        return target_dir

def ensure_suid_sandbox(extracted_dir: Path) -> None:
    sandbox = extracted_dir / "chrome-sandbox"
    if sandbox.exists():
        print("[*] Setting chrome-sandbox owner/mode (root:root 4755)")
        RUN("sudo", "chown", "root:root", str(sandbox))
        RUN("sudo", "chmod", "4755", str(sandbox))
    else:
        print("[!] chrome-sandbox not found. The app may still run (userns sandbox).")

def make_symlink_current(install_root: Path, target_dir: Path):
    current = install_root / "current"
    if current.exists() or current.is_symlink():
        current.unlink()
    current.symlink_to(target_dir.name)  # relative symlink inside install_root
    print(f"[*] Symlinked {current} -> {target_dir.name}")

def create_wrapper(install_root: Path, name: str) -> Path:
    bin_dir = Path.home() / ".local" / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    wrapper = bin_dir / f"{name.lower()}-launch"
    with wrapper.open("w") as f:
        f.write("#!/usr/bin/env bash\n")
        f.write('set -euo pipefail\n')
        f.write(f'export CHROME_DEVEL_SANDBOX="{install_root}/current/chrome-sandbox"\n')
        f.write(f'exec "{install_root}/current/AppRun" "$@"\n')
    wrapper.chmod(0o755)
    print(f"[*] Created launcher: {wrapper}")
    return wrapper

def install_icon(extracted_dir: Path, name: str) -> Path:
    # Prefer embedded .DirIcon; otherwise do nothing and inform user.
    icon_src = extracted_dir / ".DirIcon"
    icons_dir = Path.home() / ".local" / "share" / "icons" / "hicolor" / "256x256" / "apps"
    icons_dir.mkdir(parents=True, exist_ok=True)
    icon_dst = icons_dir / f"{name.lower()}.png"
    if icon_src.exists():
        shutil.copy2(icon_src, icon_dst)
        print(f"[*] Installed icon: {icon_dst}")
    else:
        print("[!] No .DirIcon found; place a 256x256 PNG at:", icon_dst)
    return icon_dst

def create_desktop_entry(name: str, wrapper: Path, icon_path: Path):
    apps_dir = Path.home() / ".local" / "share" / "applications"
    apps_dir.mkdir(parents=True, exist_ok=True)
    desktop = apps_dir / f"{name.lower()}.desktop"
    with desktop.open("w") as f:
        f.write("[Desktop Entry]\n")
        f.write(f"Name={name}\n")
        f.write("Comment=AI Code Editor\n")
        f.write(f"Exec={wrapper} %U\n")
        f.write(f"Icon={icon_path}\n")
        f.write("Terminal=false\n")
        f.write("Type=Application\n")
        f.write("Categories=Development;IDE;\n")
        f.write("StartupNotify=true\n")
        # StartupWMClass can be added later after you run xprop
    desktop.chmod(0o644)
    print(f"[*] Created desktop entry: {desktop}")
    # Refresh caches if tools exist
    for cmd, args in [("update-desktop-database", [str(apps_dir)]),
                      ("gtk-update-icon-cache", ["-f", str(icon_path.parent.parent.parent)])]:
        if shutil.which(cmd):
            try:
                RUN(cmd, *args)
            except Exception:
                pass
    return desktop

def main():
    args = parse_args()
    appimage = Path(args.appimage).expanduser().resolve()
    if not appimage.exists():
        print(f"ERROR: AppImage not found: {appimage}", file=sys.stderr)
        sys.exit(1)

    # 0) Tools we need
    for cmd in ["findmnt"]:
        if shutil.which(cmd) is None:
            print(f"[!] Utility '{cmd}' not found; continuing without mount option checks.")

    # 1) Dependencies
    if not args.no_apt:
        try:
            apt_install(["libfuse2t64"])
        except subprocess.CalledProcessError as e:
            print(f"[!] apt install failed ({e}); continuing (you can rerun with --no-apt).")

    # 2) Choose install root (avoid nosuid)
    if args.system_dir:
        install_root = Path("/opt") / "cursor"
        print("[*] Using system install dir:", install_root)
    else:
        install_root = Path(args.install_dir).expanduser()

    install_root_parent = install_root if install_root.is_dir() else install_root.parent
    install_root_parent.mkdir(parents=True, exist_ok=True)

    if is_nosuid(install_root_parent):
        if not args.system_dir:
            print(f"[!] Target filesystem has 'nosuid': {install_root_parent}")
            print("    Consider rerunning with --system-dir (will use /opt/cursor)")
        else:
            print(f"[!] WARNING: /opt might be nosuid on this system; SUID sandbox may fail.")

    # 3) Copy AppImage to an exec-capable temp and extract
    work_app = copy_to_exec_tmp(appimage)
    extracted = extract_appimage(work_app, install_root)

    # 4) Fix sandbox permissions (needs sudo)
    try:
        ensure_suid_sandbox(extracted)
    except subprocess.CalledProcessError as e:
        print("[!] Failed to set SUID sandbox permissions. You may need to run this script again.")
        print("    Error:", e)

    # 5) Create/refresh 'current' symlink
    make_symlink_current(install_root, extracted)

    # 6) Wrapper launcher
    wrapper = create_wrapper(install_root, args.name)

    # 7) Icon + Desktop entry
    if args.make_desktop == "yes":
        icon_path = install_icon(extracted, args.name)
        desktop_file = create_desktop_entry(args.name, wrapper, icon_path)
        print("\n[✓] Installed desktop entry. You may need to log out/in for the app grid to refresh.")
    else:
        print("[*] Skipped desktop entry (per --make-desktop=no).")

    print("\nAll set!")
    print("Run Cursor with:")
    print(f"  {wrapper}")
    print("\nIf the dock icon doesn't group correctly, run:")
    print("  xprop WM_CLASS   # click the Cursor window")
    print("Then add StartupWMClass=<value> to ~/.local/share/applications/{}.desktop".format(args.name.lower()))

if __name__ == "__main__":
    main()
