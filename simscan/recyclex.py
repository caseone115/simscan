"""Reversible file operations: disable (move to _disabled) and recycle.

Everything the tool does to a user's Mods folder must be undoable. Disabling
moves files into a "_disabled" folder inside Mods - the game ignores folders
whose name starts with an underscore, so this is the standard community way
to switch a mod off without deleting it. An undo log is written alongside.
"""
import json
import os
import shutil
import time

DISABLED_DIR = "_disabled"
UNDO_LOG = ".simscan_undo.json"


def _disabled_root(mods_root):
    return os.path.join(mods_root, DISABLED_DIR)


def _undo_path(mods_root):
    return os.path.join(mods_root, DISABLED_DIR, UNDO_LOG)


def _load_undo(mods_root):
    p = _undo_path(mods_root)
    if not os.path.isfile(p):
        return []
    try:
        with open(p, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return []


def _save_undo(mods_root, entries):
    root = _disabled_root(mods_root)
    os.makedirs(root, exist_ok=True)
    try:
        with open(_undo_path(mods_root), "w", encoding="utf-8") as fh:
            json.dump(entries, fh, indent=2)
    except OSError:
        pass


def disable_files(mods_root, mods):
    """Move mods into _disabled, preserving their relative paths.

    Returns the list of moves made.
    """
    entries = _load_undo(mods_root)
    batch = []
    dest_root = _disabled_root(mods_root)
    for m in mods:
        src = m.abs_path
        if not os.path.isfile(src):
            continue
        rel = m.rel_path
        dst = os.path.join(dest_root, rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        # never clobber an existing disabled copy
        base, ext = os.path.splitext(dst)
        n = 1
        while os.path.exists(dst):
            dst = f"{base} ({n}){ext}"
            n += 1
        shutil.move(src, dst)
        batch.append({"from": src, "to": dst, "when": time.time()})
    entries.append({"batch": batch})
    _save_undo(mods_root, entries)
    return batch


def has_undo(mods_root):
    if not mods_root:
        return False
    return bool(_load_undo(mods_root))


def undo_last_disable(mods_root):
    """Restore the most recent disable batch. Returns count restored."""
    entries = _load_undo(mods_root)
    if not entries:
        return 0
    last = entries.pop()
    restored = 0
    for item in reversed(last.get("batch", [])):
        src, dst = item.get("to"), item.get("from")
        if src and dst and os.path.isfile(src):
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            try:
                shutil.move(src, dst)
                restored += 1
            except OSError:
                pass
    _save_undo(mods_root, entries)
    return restored


# ------------------------------------------------------------ Recycle Bin
def _recycle_windows(paths):
    """Send files to the Recycle Bin via SHFileOperationW."""
    import ctypes
    from ctypes import wintypes

    class SHFILEOPSTRUCTW(ctypes.Structure):
        _fields_ = [
            ("hwnd", wintypes.HWND),
            ("wFunc", wintypes.UINT),
            ("pFrom", wintypes.LPCWSTR),
            ("pTo", wintypes.LPCWSTR),
            ("fFlags", ctypes.c_uint16),
            ("fAnyOperationsAborted", wintypes.BOOL),
            ("hNameMappings", ctypes.c_void_p),
            ("lpszProgressTitle", wintypes.LPCWSTR),
        ]

    FO_DELETE = 3
    FOF_ALLOWUNDO = 0x40
    FOF_NOCONFIRMATION = 0x10
    FOF_SILENT = 0x4
    FOF_NOERRORUI = 0x400

    # double-NUL terminated list
    buf = "\0".join(paths) + "\0\0"
    op = SHFILEOPSTRUCTW()
    op.hwnd = None
    op.wFunc = FO_DELETE
    op.pFrom = buf
    op.pTo = None
    op.fFlags = FOF_ALLOWUNDO | FOF_NOCONFIRMATION | FOF_SILENT | FOF_NOERRORUI
    res = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op))
    if res != 0 or op.fAnyOperationsAborted:
        raise OSError(f"SHFileOperationW returned {res}")
    return len(paths)


def recycle_files(paths):
    """Delete to the OS trash. Returns (deleted_count, [errors])."""
    paths = [p for p in paths if os.path.exists(p)]
    if not paths:
        return 0, []
    if os.name == "nt":
        try:
            return _recycle_windows(paths), []
        except Exception as e:
            # fall back to plain delete so the user is not blocked
            ok, failed = 0, []
            for p in paths:
                try:
                    os.remove(p)
                    ok += 1
                except OSError as err:
                    failed.append(f"{p}: {err}")
            if ok:
                return ok, failed
            return 0, [f"Recycle Bin unavailable ({e})"] + failed
    # macOS / Linux
    try:
        from send2trash import send2trash
        for p in paths:
            send2trash(p)
        return len(paths), []
    except Exception:
        ok, failed = 0, []
        for p in paths:
            try:
                os.remove(p)
                ok += 1
            except OSError as err:
                failed.append(f"{p}: {err}")
        return ok, failed
