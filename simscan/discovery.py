"""Mods folder discovery for The Sims 4 on Windows, macOS and Linux."""
import os
import glob

DOCS_HINTS = ("Documents", "OneDrive\\Documents", "OneDrive/Documents",
              "My Documents")

WIN_DOCS = [
    r"Documents\Electronic Arts\The Sims 4\Mods",
    r"OneDrive\Documents\Electronic Arts\The Sims 4\Mods",
    r"OneDrive\Documenten\Electronic Arts\The Sims 4\Mods",
]
WIN_DOCS_PATTERNS = [
    r"*\Documents\Electronic Arts\The Sims 4\Mods",
    r"*\OneDrive*\Documents\Electronic Arts\The Sims 4\Mods",
    r"*\OneDrive*\Documenten\Electronic Arts\The Sims 4\Mods",
    r"*\OneDrive*\Dokumente\Electronic Arts\The Sims 4\Mods",
    r"*\Documents\Electronic Arts\De Sims 4\Mods",
    r"*\Documents\Electronic Arts\Los Sims 4\Mods",
    r"*\Documents\Electronic Arts\Die Sims 4\Mods",
]

MAC_DOCS = "~/Documents/Electronic Arts/The Sims 4/Mods"
MAC_ICLOUD = ("~/Library/Mobile Documents/com~apple~CloudDocs/"
              "Electronic Arts/The Sims 4/Mods")
LINUX_DOCS = "~/Documents/Electronic Arts/The Sims 4/Mods"


def _win_drives():
    drives = []
    for letter in "CDEFGHIJKLMNOPQRSTUVWXYZ":
        p = f"{letter}:\\"
        if os.path.exists(p):
            drives.append(p)
    return drives


def candidates():
    """Best-effort list of possible Mods folders, most likely first."""
    out = []
    home = os.path.expanduser("~")

    if os.name == "nt":
        for base in (os.environ.get("USERPROFILE", home),
                     os.environ.get("OneDrive", ""),
                     os.environ.get("OneDriveCommercial", "")):
            if not base:
                continue
            for sub in WIN_DOCS:
                out.append(os.path.join(base, sub))
        for drive in _win_drives():
            for pat in (WIN_DOCS_PATTERNS[0], WIN_DOCS_PATTERNS[1]):
                try:
                    out.extend(glob.glob(os.path.join(drive, pat)))
                except Exception:
                    pass
    else:
        out.append(os.path.expanduser(MAC_DOCS))
        out.append(os.path.expanduser(MAC_ICLOUD))
        out.append(os.path.expanduser(LINUX_DOCS))
        out.append(os.path.join(home, "Documents", "Electronic Arts",
                                "The Sims 4", "Mods"))

    seen, uniq = set(), []
    for p in out:
        try:
            norm = os.path.normcase(os.path.abspath(p))
        except Exception:
            continue
        if norm not in seen:
            seen.add(norm)
            uniq.append(p)
    return uniq


def find_mods_dir():
    """First existing candidate, else None."""
    for p in candidates():
        if os.path.isdir(p):
            return p
    return None


def user_folder_for(mods_dir):
    """The Sims 4 user folder (parent of Mods) - holds exception files."""
    if not mods_dir:
        return None
    return os.path.dirname(os.path.abspath(mods_dir))
