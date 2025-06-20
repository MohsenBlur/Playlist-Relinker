#!/usr/bin/env python3
"""
Playlist-Relinker  • 2025-06-20
────────────────────────────────
Fix broken paths in any plain-text playlist
(.m3u, .m3u8, foobar2000 .fplite).

Key features
• Scan a folder (optionally including sub-folders) and list every playlist.
• Highlight the playlist you’re editing, with live two-line before/after previews.
• Change each “root pattern” once instead of line-by-line edits.
• Mass-change drive letters across every scanned playlist.
• Creates a backup copy of every file before overwriting.

No external libraries required — only the Python 3 standard library.
"""

from __future__ import annotations

import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import PureWindowsPath
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Dict, Iterable, List, Set, Tuple

PATTERN_DEPTH = 2
PLAYLIST_EXTS = {".m3u", ".m3u8", ".fplite"}
URI_PREFIXES = ("file:///", "file://", "file:\\\\", "file:\\")  # longest first


# ───────────────────────── helpers ──────────────────────────
def _strip_prefix(line: str) -> Tuple[str, str]:
    """Return (uri_prefix, remainder)."""
    lower = line.lower()
    for pre in URI_PREFIXES:
        if lower.startswith(pre):
            return line[: len(pre)], line[len(pre) :]
    return "", line


def _parse_path_line(line: str) -> Tuple[str, PureWindowsPath] | None:
    """Return (uri_prefix, PureWindowsPath) or None for blank/comment lines."""
    raw = line.lstrip("\ufeff")                # remove UTF-8 BOM if present
    stripped = raw.rstrip("\r\n")
    if not stripped or stripped.lstrip().startswith("#"):
        return None
    prefix, rest = _strip_prefix(stripped)
    rest = rest.replace("/", "\\")
    return prefix, PureWindowsPath(rest)


def _root_of(p: PureWindowsPath, depth: int = PATTERN_DEPTH) -> PureWindowsPath:
    """drive + first <depth> folders → root pattern."""
    return PureWindowsPath(*p.parts[: depth + 1]) if p.parts else p


# ────────────────────── Tooltip helper ──────────────────────
class ListboxTooltip:
    """Lightweight tooltip for Tk Listbox rows (shows full path on hover)."""

    def __init__(self, listbox: tk.Listbox, get_text_for_index):
        self.lb = listbox
        self.get_text = get_text_for_index
        self.tw: tk.Toplevel | None = None
        self.lb.bind("<Motion>", self._motion)
        self.lb.bind("<Leave>", lambda _e: self._hide())

    def _motion(self, event):
        idx = self.lb.nearest(event.y)
        if idx < 0 or idx >= self.lb.size():
            self._hide()
            return
        text = self.get_text(idx)
        if not text:
            self._hide()
            return
        if self.tw is None:
            self.tw = tk.Toplevel(self.lb)
            self.tw.wm_overrideredirect(True)
            self.tw.attributes("-topmost", True)
            label = ttk.Label(self.tw, text=text, background="#ffffe0",
                              relief="solid", borderwidth=1,
                              font=("TkDefaultFont", 9), justify="left")
            label.pack(ipadx=4, ipady=2)
        else:
            self.tw.winfo_children()[0].configure(text=text)
        self.tw.wm_geometry(f"+{event.x_root + 20}+{event.y_root + 10}")

    def _hide(self):
        if self.tw:
            self.tw.destroy()
        self.tw = None


# ────────────────────────── GUI ─────────────────────────────
@dataclass
class GroupUI:
    old_root: PureWindowsPath
    var: tk.StringVar
    example_var: tk.StringVar
    sample_pw: PureWindowsPath
    sample_prefix: str


class PlaylistFixer(tk.Tk):
    HILITE_BG = "#cfe9ff"   # background for current playlist row

    def __init__(self) -> None:
        super().__init__()
        self.title("Playlist-Relinker")
        self.geometry("920x640")

        # 1 ─ scan controls --------------------------------------------------
        scan = ttk.LabelFrame(self, text="1 • Scan for playlists")
        scan.pack(fill="x", padx=10, pady=6)

        self.scan_path = tk.StringVar(value=os.path.expanduser("~"))
        ttk.Entry(scan, textvariable=self.scan_path).pack(
            side="left", fill="x", expand=True, padx=(8, 0), pady=6
        )
        ttk.Button(scan, text="Browse…", command=self._browse).pack(
            side="left", padx=6, pady=6
        )

        self.recursive = tk.BooleanVar(value=True)
        ttk.Checkbutton(scan, text="Include subfolders",
                        variable=self.recursive).pack(side="left", padx=6)

        ttk.Button(scan, text="Scan", command=self._scan).pack(
            side="left", padx=6, pady=6
        )
        ttk.Button(scan, text="Mass-change drive letters…",
                   command=self._mass_change).pack(side="left", padx=8, pady=6)

        # 2 ─ playlist list --------------------------------------------------
        lst = ttk.LabelFrame(self, text="2 • Pick a playlist")
        lst.pack(fill="both", expand=True, padx=10, pady=4)

        self.listbox = tk.Listbox(lst)
        self.listbox.pack(side="left", fill="both", expand=True,
                          padx=(8, 0), pady=6)
        sb = ttk.Scrollbar(lst, orient="vertical", command=self.listbox.yview)
        sb.pack(side="left", fill="y")
        self.listbox.configure(yscrollcommand=sb.set)

        ttk.Button(lst, text="Load selected", command=self._load).pack(
            side="left", padx=6, pady=6
        )
        self.listbox.bind("<Double-Button-1>", lambda _e: self._load())

        # tooltip — full path on hover
        self._idx_to_path: Dict[int, str] = {}
        ListboxTooltip(self.listbox, lambda i: self._idx_to_path.get(i, ""))

        # 3 ─ mapping area ---------------------------------------------------
        self.map_frm = ttk.LabelFrame(self, text="3 • Adjust each root and save")
        self.map_frm.pack(fill="both", expand=False, padx=10, pady=4)

        self.btn_save = ttk.Button(
            self.map_frm, text="Save playlist (backup first)",
            command=self._save, state="disabled"
        )
        self.btn_save.pack(side="bottom", pady=8)

        # internals
        self._all_playlists: List[str] = []
        self._loaded_path: str | None = None
        self._orig_lines: List[str] = []
        self._groups: Dict[PureWindowsPath, List[str]] = {}
        self._group_widgets: List[GroupUI] = []

    # ─────────────── scan / browse ──────────────────────────
    def _browse(self) -> None:
        folder = filedialog.askdirectory(title="Folder to scan",
                                         initialdir=self.scan_path.get())
        if folder:
            self.scan_path.set(folder)

    def _scan(self) -> None:
        root = os.path.expanduser(self.scan_path.get())
        if not os.path.exists(root):
            messagebox.showerror("Invalid path",
                                 "Selected folder doesn’t exist.")
            return

        self.listbox.delete(0, tk.END)
        self._idx_to_path.clear()
        self._all_playlists.clear()

        iterable: Iterable[str]
        if self.recursive.get():
            iterable = (
                os.path.join(dp, f)
                for dp, _dirs, files in os.walk(root)
                for f in files
            )
        else:
            iterable = (
                os.path.join(root, f)
                for f in os.listdir(root)
                if os.path.isfile(os.path.join(root, f))
            )

        for p in iterable:
            if os.path.splitext(p)[1].lower() in PLAYLIST_EXTS:
                idx = self.listbox.size()
                self.listbox.insert(tk.END, os.path.basename(p))
                self._idx_to_path[idx] = p
                self.listbox.itemconfig(idx, bg="white")
                self._all_playlists.append(p)

        if not self.listbox.size():
            messagebox.showinfo("Nothing found",
                                "No playlists in that location.")

    # ─────────────── load one playlist ─────────────────────
    def _load(self) -> None:
        if not self.listbox.curselection():
            messagebox.showwarning("Pick one", "Select a playlist first.")
            return
        idx = self.listbox.curselection()[0]
        self._loaded_path = self._idx_to_path[idx]

        # highlight selected playlist
        for i in range(self.listbox.size()):
            self.listbox.itemconfig(i, bg="white")
        self.listbox.itemconfig(idx, bg=self.HILITE_BG)

        # read playlist lines
        try:
            with open(self._loaded_path, "r", encoding="utf-8-sig") as f:
                self._orig_lines = f.readlines()
        except UnicodeDecodeError:
            with open(self._loaded_path, "r", encoding="latin-1") as f:
                self._orig_lines = f.readlines()

        # group by root pattern
        self._groups.clear()
        samples: Dict[PureWindowsPath, Tuple[str, PureWindowsPath]] = {}
        for ln in self._orig_lines:
            parsed = _parse_path_line(ln)
            if parsed:
                prefix, pw = parsed
                root = _root_of(pw)
                self._groups.setdefault(root, []).append(ln)
                samples.setdefault(root, (prefix, pw))

        # build mapping UI
        for w in self.map_frm.winfo_children():
            if w not in {self.btn_save}:
                w.destroy()
        self._group_widgets.clear()

        for root in sorted(self._groups, key=str):
            row = ttk.Frame(self.map_frm)
            row.pack(fill="x", padx=8, pady=2)

            ttk.Label(row, text=str(root), width=46,
                      anchor="w").pack(side="left")

            var = tk.StringVar(value=str(root))
            ttk.Entry(row, textvariable=var).pack(side="left",
                                                  fill="x", expand=True)

            ex_var = tk.StringVar()
            ttk.Label(row, textvariable=ex_var, anchor="w", justify="left",
                      foreground="#558").pack(side="left", padx=(6, 0))

            prefix, sample_pw = samples[root]
            gui = GroupUI(root, var, ex_var, sample_pw, prefix)
            self._group_widgets.append(gui)

            self._update_example(gui)
            var.trace_add("write",
                          lambda *_a, g=gui: self._update_example(g))

        self.btn_save.config(state="normal")

    def _update_example(self, g: GroupUI) -> None:
        new_root = PureWindowsPath(g.var.get().replace("/", "\\"))
        try:
            tail = g.sample_pw.relative_to(g.old_root)
        except ValueError:
            tail = PureWindowsPath(*g.sample_pw.parts[len(g.old_root.parts):])
        new_pw = new_root / tail
        before = f"{g.sample_prefix}{g.sample_pw}"
        after = f"{g.sample_prefix}{new_pw}"
        g.example_var.set(f"{before}\n→ {after}")

    # ───────────── save current playlist ────────────────────
    def _save(self) -> None:
        if not self._loaded_path:
            return

        bak_dir = os.path.join(os.path.dirname(self._loaded_path), "backup")
        os.makedirs(bak_dir, exist_ok=True)
        shutil.copy2(self._loaded_path,
                     os.path.join(bak_dir, os.path.basename(self._loaded_path)))

        mapping = {
            g.old_root: PureWindowsPath(g.var.get().replace("/", "\\"))
            for g in self._group_widgets
        }

        updated: List[str] = []
        for ln in self._orig_lines:
            parsed = _parse_path_line(ln)
            if not parsed:
                updated.append(ln)
                continue
            prefix, pw = parsed
            old_root = _root_of(pw)
            new_root = mapping.get(old_root, old_root)
            if new_root != old_root:
                try:
                    tail = pw.relative_to(old_root)
                except ValueError:
                    tail = PureWindowsPath(*pw.parts[len(old_root.parts):])
                new_pw = new_root / tail
                le = "\n" if ln.endswith("\n") else "\r\n"
                ln = prefix + str(new_pw) + le
            updated.append(ln)

        try:
            with open(self._loaded_path, "w", encoding="utf-8") as f:
                f.writelines(updated)
            messagebox.showinfo("Saved",
                                f"Playlist updated.\nBackup in: {bak_dir}")
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Write failed", str(exc))

    # ───────── mass-change drive letters ────────────────────
    def _mass_change(self) -> None:
        if not self._all_playlists:
            messagebox.showinfo("Nothing scanned", "Scan first.")
            return

        # collect drive letters in all playlists
        drives: Set[str] = set()
        for pl in self._all_playlists:
            try:
                with open(pl, "r", encoding="utf-8-sig") as f:
                    lines = f.readlines()
            except UnicodeDecodeError:
                with open(pl, "r", encoding="latin-1") as f:
                    lines = f.readlines()
            for ln in lines:
                parsed = _parse_path_line(ln)
                if parsed and parsed[1].drive:
                    drives.add(parsed[1].drive)   # e.g. 'S:'

        if not drives:
            messagebox.showinfo("No drives", "No drive letters detected.")
            return

        # popup window
        win = tk.Toplevel(self)
        win.title("Mass-change drive letters")
        win.minsize(320, 120)            # ensure title fits
        win.grab_set()

        vars: Dict[str, tk.StringVar] = {}
        for drv in sorted(drives):
            row = ttk.Frame(win)
            row.pack(fill="x", padx=10, pady=4)
            ttk.Label(row, text=drv, width=6,
                      anchor="w").pack(side="left")
            var = tk.StringVar(value=drv[0])       # letter only
            ttk.Entry(row, textvariable=var, width=4,
                      justify="center").pack(side="left")
            vars[drv] = var

        def apply():
            mapping = {
                old: (v.get().strip().upper() + ":")
                for old, v in vars.items()
                if v.get().strip() and (v.get().strip().upper() + ":") != old
            }
            if not mapping:
                win.destroy()
                return
            updated = self._apply_drive_changes(mapping)
            messagebox.showinfo("Done",
                                f"Updated {updated} playlist(s).\nBackups created.")
            win.destroy()

        ttk.Button(win, text="Apply to all playlists",
                   command=apply).pack(pady=10)

    def _apply_drive_changes(self, mapping: Dict[str, str]) -> int:
        changed_files = 0
        for pl in self._all_playlists:
            try:
                with open(pl, "r", encoding="utf-8-sig") as f:
                    lines = f.readlines()
            except UnicodeDecodeError:
                with open(pl, "r", encoding="latin-1") as f:
                    lines = f.readlines()

            updated: List[str] = []
            changed = False
            for ln in lines:
                parsed = _parse_path_line(ln)
                if not parsed:
                    updated.append(ln)
                    continue
                prefix, pw = parsed
                drv = pw.drive
                if drv in mapping:
                    new_drv = mapping[drv]
                    tail = PureWindowsPath(*pw.parts[1:])
                    new_pw = PureWindowsPath(new_drv + "\\") / tail
                    le = "\n" if ln.endswith("\n") else "\r\n"
                    ln = prefix + str(new_pw) + le
                    changed = True
                updated.append(ln)

            if changed:
                bak_dir = os.path.join(os.path.dirname(pl), "backup")
                os.makedirs(bak_dir, exist_ok=True)
                shutil.copy2(pl, os.path.join(bak_dir,
                                              os.path.basename(pl)))
                try:
                    with open(pl, "w", encoding="utf-8") as f:
                        f.writelines(updated)
                    changed_files += 1
                except Exception:  # noqa: BLE001
                    messagebox.showwarning("Write failed",
                                           f"Couldn’t update {pl}.")
        return changed_files


# ───────────────────────── launcher ─────────────────────────
def main() -> None:
    if sys.platform != "win32":
        print("⚠  Designed for Windows paths; should still run elsewhere.")
    PlaylistFixer().mainloop()


if __name__ == "__main__":
    main()
