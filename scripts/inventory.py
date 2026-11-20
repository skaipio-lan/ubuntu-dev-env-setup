#!/usr/bin/env python3
"""Inventory an existing Ubuntu workstation to help curate this setup.

Read-only: runs no sudo and changes nothing. Writes one Markdown report to
inventory/<hostname>-<timestamp>.md (ignored by Git, because it describes
this machine). Review the report and copy only what you want into the roles;
do not install everything it lists.

Collected:
  - Manually installed APT packages, with first-install date and source
  - APT sources (credentials in URIs are masked)
  - Snap and Flatpak applications
  - GNOME Shell extensions
  - VS Code and Zed extensions
  - Commands in ~/.local/bin
  - Non-default GNOME settings for selected dconf paths

Each item is marked "yes" in the "In repo" column when its name already
appears in roles/, group_vars/, playbook.yml, setup.sh, or requirements.yml.
"""

from __future__ import annotations

import datetime as dt
import gzip
import os
import re
import shutil
import socket
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
HOME = Path.home()

# dconf paths worth reviewing. dconf stores only values changed from their
# defaults, so a dump lists exactly what was customised.
DCONF_PATHS = [
    "/org/gnome/desktop/",
    "/org/gnome/shell/",
    "/org/gnome/mutter/",
    "/org/gnome/settings-daemon/plugins/",
    "/org/gnome/nautilus/",
    "/org/gnome/Ptyxis/",
]
# Keys that hold window state, history, or UI bookkeeping rather than
# preferences.
DCONF_NOISE = re.compile(
    r"^(window-|last-|recent|initial-size|app-picker-layout$|.*-history$"
    r"|.*-geometry$|welcome-dialog-|migrated-|application-children$|.*-uuids?$)"
)
# Whole sections GNOME maintains automatically: default app folders and
# per-application notification registrations.
DCONF_NOISE_SECTIONS = re.compile(r"^(app-folders|notifications/application)(/|$)")
# Keys that may hold secrets are never written to the report.
DCONF_SECRET = re.compile(r"password|passwd|secret|token|credential|auth", re.I)


def run(*cmd: str) -> str | None:
    """Return a command's stdout, or None if it is missing or fails."""
    if shutil.which(cmd[0]) is None:
        return None
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=60, check=False
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return result.stdout if result.returncode == 0 else None


def repo_text() -> str:
    """Concatenate the repository files that define what is managed."""
    parts = []
    for base in ("roles", "group_vars"):
        for path in sorted((REPO / base).rglob("*")):
            if path.is_file() and path.suffix in {".yml", ".yaml", ".j2"}:
                parts.append(path.read_text(errors="replace"))
    for name in ("playbook.yml", "setup.sh", "requirements.yml"):
        path = REPO / name
        if path.exists():
            parts.append(path.read_text(errors="replace"))
    return "\n".join(parts)


def make_in_repo(text: str):
    def in_repo(name: str) -> str:
        # Package-style boundaries, so "docker-ce" does not match "docker-ce-cli".
        pattern = rf"(?<![\w.+-]){re.escape(name)}(?![\w.+-])"
        return "yes" if re.search(pattern, text) else ""

    return in_repo


def table(headers: list[str], rows: list[list[str]]) -> str:
    if not rows:
        return "_None found._\n"
    esc = [[str(c).replace("|", "\\|") for c in row] for row in rows]
    lines = ["| " + " | ".join(headers) + " |", "|" + " --- |" * len(headers)]
    lines += ["| " + " | ".join(row) + " |" for row in esc]
    return "\n".join(lines) + "\n"


def os_install_time() -> dt.datetime | None:
    marker = Path("/var/log/installer/media-info")
    if marker.exists():
        return dt.datetime.fromtimestamp(marker.stat().st_mtime)
    return None


def first_install_dates() -> dict[str, dt.datetime]:
    """Earliest 'install' event per package from the dpkg logs."""
    dates: dict[str, dt.datetime] = {}
    for log in sorted(Path("/var/log").glob("dpkg.log*")):
        opener = gzip.open if log.suffix == ".gz" else open
        try:
            with opener(log, "rt", errors="replace") as handle:
                for line in handle:
                    fields = line.split()
                    if len(fields) >= 4 and fields[2] == "install":
                        name = fields[3].split(":")[0]
                        when = dt.datetime.strptime(
                            f"{fields[0]} {fields[1]}", "%Y-%m-%d %H:%M:%S"
                        )
                        if name not in dates or when < dates[name]:
                            dates[name] = when
        except OSError:
            continue
    return dates


def apt_origins(packages: list[str]) -> dict[str, str]:
    """Map package name to the repositories its installed version comes from.

    Uses apt-cache policy, because suite names alone are ambiguous: Docker's
    repository also calls its suite "resolute". A version found only in
    /var/lib/dpkg/status was installed from a local .deb file.
    """
    out = run("apt-cache", "policy", *packages) or ""
    origins: dict[str, list[str]] = {}
    name, in_installed = None, False
    for line in out.splitlines():
        if re.match(r"^\S.*:$", line):  # "package:" header
            name, in_installed = line[:-1].split(":")[0], False
            origins[name] = []
        elif line.startswith(" *** "):  # installed version
            in_installed = True
        elif re.match(r"^ {5}\S", line):  # another version
            in_installed = False
        elif in_installed and name:
            match = re.match(r"^\s+\d+ (\S+)(?: (\S+))?", line)
            if not match or match.group(1) == "/var/lib/dpkg/status":
                continue
            url, dist = match.groups()
            host = re.sub(r"^\w+://([^/@]+@)?([^/]+).*", r"\2", url)
            entry = f"{host} {dist}" if dist else host
            if entry not in origins[name]:
                origins[name].append(entry)
    return {k: ", ".join(v) or "local .deb (no repository)" for k, v in origins.items()}


def section_apt(in_repo) -> str:
    manual = (run("apt-mark", "showmanual") or "").split()
    dates = first_install_dates()
    sources = apt_origins(sorted(set(manual)))
    cutoff = os_install_time()
    rows = []
    for name in sorted(set(manual)):
        when = dates.get(name)
        after = ""
        if when and cutoff:
            after = "yes" if when > cutoff else ""
        rows.append([
            f"`{name}`",
            when.strftime("%Y-%m-%d") if when else "unknown",
            after,
            sources.get(name, ""),
            in_repo(name),
        ])
    # Packages added after the OS install first; they are the likeliest picks.
    rows.sort(key=lambda r: (r[2] != "yes", r[0]))
    cutoff_text = cutoff.strftime("%Y-%m-%d %H:%M") if cutoff else "unknown"
    return (
        "## APT packages (manually installed)\n\n"
        f"OS installed: {cutoff_text}. Packages added later are listed first. "
        "Packages installed by the OS installer are usually not worth adding.\n\n"
        + table(["Package", "First installed", "Added after OS install",
                 "Installed from", "In repo"], rows)
    )


def mask_credentials(text: str) -> str:
    return re.sub(r"(://)[^/@\s]+@", r"\1####@", text)


def section_apt_sources() -> str:
    rows = []
    for path in sorted(Path("/etc/apt/sources.list.d").glob("*")):
        if path.suffix not in {".sources", ".list"}:
            continue
        try:
            text = path.read_text(errors="replace")
        except OSError:
            continue
        uris = re.findall(r"^\s*URIs:\s*(.+)$", text, re.M)
        uris += re.findall(r"^\s*deb(?:-src)?\s+(?:\[[^\]]*\]\s+)?(\S+)", text, re.M)
        uris = sorted({mask_credentials(u.strip()) for u in uris})
        rows.append([f"`{path.name}`", "<br>".join(uris) or "(none)"])
    return (
        "## APT sources\n\nCredentials in URIs are masked.\n\n"
        + table(["File", "URIs"], rows)
    )


def section_snaps(in_repo) -> str:
    out = run("snap", "list")
    if out is None:
        return "## Snaps\n\n_snap not available._\n"
    rows = []
    for line in out.splitlines()[1:]:
        cols = line.split()
        if len(cols) < 6:
            continue
        name, version, publisher, notes = cols[0], cols[1], cols[4], cols[5]
        if notes in {"base", "snapd"}:
            continue
        rows.append([f"`{name}`", version, publisher, notes, in_repo(name)])
    return (
        "## Snaps\n\nBase and snapd snaps are omitted. Runtime snaps such as "
        "`gnome-*`, `mesa-*`, and `gtk-common-themes` are installed as "
        "dependencies.\n\n"
        + table(["Snap", "Version", "Publisher", "Notes", "In repo"], rows)
    )


def section_flatpaks(in_repo) -> str:
    out = run("flatpak", "list", "--app", "--columns=application,origin,version")
    if out is None:
        return "## Flatpak applications\n\n_Flatpak is not installed._\n"
    rows = []
    for line in out.splitlines():
        cols = line.split("\t")
        if cols and cols[0]:
            rows.append([f"`{cols[0]}`", *(cols[1:3] + ["", ""])[:2], in_repo(cols[0])])
    return "## Flatpak applications\n\n" + table(
        ["Application", "Remote", "Version", "In repo"], rows
    )


def section_gnome_extensions(in_repo) -> str:
    if run("gnome-extensions", "list") is None:
        return ("## GNOME Shell extensions\n\n_gnome-extensions is unavailable "
                "or not running in a GNOME session._\n")
    enabled = set((run("gnome-extensions", "list", "--enabled") or "").split())
    user = set((run("gnome-extensions", "list", "--user") or "").split())
    system = set((run("gnome-extensions", "list", "--system") or "").split())
    rows = [
        [f"`{uuid}`", "user" if uuid in user else "system",
         "yes" if uuid in enabled else "", in_repo(uuid)]
        for uuid in sorted(user | system)
    ]
    rows.sort(key=lambda r: (r[1] != "user", r[2] != "yes", r[0]))
    return (
        "## GNOME Shell extensions\n\nSystem extensions ship with Ubuntu; user "
        "extensions were installed separately.\n\n"
        + table(["Extension", "Installed as", "Enabled", "In repo"], rows)
    )


def section_editor_extensions(in_repo) -> str:
    parts = ["## Editor extensions\n"]
    code = run("code", "--list-extensions", "--show-versions")
    if code is None:
        parts.append("### VS Code\n\n_VS Code is not installed._\n")
    else:
        rows = [[f"`{e.split('@')[0]}`", e.partition("@")[2], in_repo(e.split("@")[0])]
                for e in code.split()]
        parts.append("### VS Code\n\n" + table(["Extension", "Version", "In repo"], rows))
    zed_dir = HOME / ".local/share/zed/extensions/installed"
    if zed_dir.is_dir():
        rows = [[f"`{p.name}`", in_repo(p.name)]
                for p in sorted(zed_dir.iterdir()) if p.is_dir()]
        parts.append("### Zed\n\n" + table(["Extension", "In repo"], rows))
    else:
        parts.append("### Zed\n\n_No Zed extensions found._\n")
    return "\n".join(parts)


def section_local_bin(in_repo) -> str:
    bin_dir = HOME / ".local/bin"
    rows = []
    if bin_dir.is_dir():
        for path in sorted(bin_dir.iterdir()):
            target = os.readlink(path) if path.is_symlink() else ""
            target = target.replace(str(HOME), "~")
            rows.append([f"`{path.name}`", f"`{target}`" if target else "", in_repo(path.name)])
    return (
        "## Commands in ~/.local/bin\n\nInstalled outside APT, usually by "
        "vendor install scripts.\n\n"
        + table(["Command", "Links to", "In repo"], rows)
    )


def filter_dconf(dump: str) -> str:
    kept = []
    skip_section = False
    for line in dump.splitlines():
        section = re.match(r"^\[(.*)\]$", line)
        if section:
            skip_section = bool(DCONF_NOISE_SECTIONS.match(section.group(1)))
        if skip_section:
            continue
        key = line.split("=", 1)[0].strip() if "=" in line else ""
        if key and (DCONF_NOISE.match(key) or DCONF_SECRET.search(key)):
            continue
        kept.append(line)
    # Drop sections left empty by the filter.
    text = "\n".join(kept)
    text = re.sub(r"^\[[^\]]*\]\n(?=\n|\[|\Z)", "", text + "\n", flags=re.M)
    return text.strip()


def section_dconf() -> str:
    if shutil.which("dconf") is None:
        return "## GNOME settings\n\n_dconf is not available._\n"
    parts = [
        "## GNOME settings (non-default values)\n\n"
        "From `dconf dump`, which lists only values changed from their defaults. "
        "Window state, history, automatic bookkeeping (app folders, notification "
        "registrations, IDs), and keys that may hold secrets are left out. "
        "Section names are relative to the path in each heading.\n"
    ]
    for path in DCONF_PATHS:
        dump = filter_dconf(run("dconf", "dump", path) or "")
        if dump:
            parts.append(f"### `{path}`\n\n```ini\n{dump}\n```\n")
    if len(parts) == 1:
        parts.append("_No customised settings found._\n")
    return "\n".join(parts)


def main() -> int:
    in_repo = make_in_repo(repo_text())
    host = socket.gethostname()
    now = dt.datetime.now()
    out_dir = REPO / "inventory"
    out_dir.mkdir(exist_ok=True)
    report = out_dir / f"{host}-{now:%Y%m%d-%H%M%S}.md"

    os_release = dict(
        line.split("=", 1)
        for line in Path("/etc/os-release").read_text().splitlines()
        if "=" in line
    )
    sections = [
        f"# Workstation inventory: {host}\n\n"
        f"Generated {now:%Y-%m-%d %H:%M} on "
        f"{os_release.get('PRETTY_NAME', 'unknown').strip(chr(34))}.\n\n"
        "Review this list and copy only what you want into the roles. "
        "\"In repo\" means the name already appears in roles/, group_vars/, "
        "playbook.yml, setup.sh, or requirements.yml.\n",
        section_apt(in_repo),
        section_apt_sources(),
        section_snaps(in_repo),
        section_flatpaks(in_repo),
        section_gnome_extensions(in_repo),
        section_editor_extensions(in_repo),
        section_local_bin(in_repo),
        section_dconf(),
    ]
    report.write_text("\n".join(sections))
    report.chmod(0o600)
    print(f"Inventory written to {report.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
