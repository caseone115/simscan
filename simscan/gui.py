"""SimScan desktop UI (tkinter).

Layout: header + toolbar, then tabs for Findings / Load order / All files /
Last exception. Findings are evidence-backed and every action is reversible:
"disable" moves files to a _disabled folder and writes an undo log.
"""
import os
import queue
import threading
import time
import traceback
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from . import APP_TITLE, __version__
from .analyzer import (scan_mods_folder, find_exception_files,
                       correlate_exception, parse_exception)
from .discovery import find_mods_dir, user_folder_for
from .dbpf import Package
from . import report as report_mod
from . import recyclex

BG = "#0f1420"
BG2 = "#171e2e"
BG3 = "#1e2739"
FG = "#e8ecf4"
MUTED = "#8b98ad"
ACCENT = "#4f8cff"
SEV_COLOUR = {"high": "#ef4444", "medium": "#f97316",
              "low": "#3b82f6", "info": "#64748b"}
SEV_LABEL = {"high": "HIGH", "medium": "MEDIUM", "low": "LOW", "info": "INFO"}


def plural(n, singular, plural_form=None):
    """'1 script mod' / '3 script mods' - never '1 script mod(s)'."""
    word = singular if n == 1 else (plural_form or singular + "s")
    return f"{n} {word}"


class SimScanApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("1180x740")
        self.minsize(940, 600)
        self.configure(bg=BG)

        self.mods_dir = tk.StringVar(value=find_mods_dir() or "")
        self.status = tk.StringVar(value="Ready.")
        self.result = None
        self.scanning = False
        self._thumb_ref = None
        self._finding_files = {}   # tree row id -> ModFile, Findings tab
        self._all_files = {}       # tree row id -> ModFile, All files tab
        self._exc_files_map = {}   # tree row id -> ModFile, Exception tab

        self._init_style()
        self._build_header()
        self._build_tabs()
        self._build_status()

        if self.mods_dir.get():
            self.after(200, self.start_scan)

    # ------------------------------------------------------------ styling
    def _init_style(self):
        st = ttk.Style(self)
        try:
            st.theme_use("clam")
        except tk.TclError:
            pass
        st.configure(".", background=BG, foreground=FG, fieldbackground=BG2,
                     bordercolor="#232c40", focuscolor=ACCENT)
        st.configure("TFrame", background=BG)
        st.configure("Card.TFrame", background=BG2)
        st.configure("TLabel", background=BG, foreground=FG)
        st.configure("Muted.TLabel", background=BG, foreground=MUTED)
        st.configure("Head.TLabel", background=BG, foreground=FG,
                     font=("Segoe UI", 15, "bold"))
        st.configure("Sub.TLabel", background=BG, foreground=MUTED,
                     font=("Segoe UI", 9))
        st.configure("TButton", background=BG3, foreground=FG, borderwidth=0,
                     padding=(12, 7), font=("Segoe UI", 9))
        st.map("TButton",
               background=[("active", "#2a3550"), ("disabled", "#1a2130")],
               foreground=[("disabled", "#5d6a80")])
        st.configure("Go.TButton", background=ACCENT, foreground="#ffffff",
                     font=("Segoe UI", 9, "bold"))
        st.map("Go.TButton", background=[("active", "#3d7bf0"),
                                         ("disabled", "#2a3550")])
        st.configure("Danger.TButton", background="#5a2028",
                     foreground="#ffc9cf")
        st.map("Danger.TButton", background=[("active", "#7a2a35")])
        st.configure("TEntry", fieldbackground=BG2, foreground=FG,
                     insertcolor=FG, bordercolor="#232c40", padding=6)
        st.configure("TNotebook", background=BG, borderwidth=0, tabmargins=0)
        st.configure("TNotebook.Tab", background=BG, foreground=MUTED,
                     padding=(16, 9), borderwidth=0)
        st.map("TNotebook.Tab",
               background=[("selected", BG2)], foreground=[("selected", FG)])
        st.configure("Treeview", background=BG2, fieldbackground=BG2,
                     foreground=FG, borderwidth=0, rowheight=24,
                     font=("Segoe UI", 9))
        st.configure("Treeview.Heading", background=BG3, foreground=MUTED,
                     relief="flat", font=("Segoe UI", 9))
        st.map("Treeview",
               background=[("selected", ACCENT), ("!selected", BG2)],
               foreground=[("selected", "#ffffff")])
        st.map("Treeview.Heading", background=[("active", BG3)])
        # The clam theme keeps focus/selection colours that fight a dark
        # palette; pin them so the selected row is unmistakable.
        self.option_add("*TCombobox*Listbox.background", BG2)
        self.option_add("*TCombobox*Listbox.foreground", FG)
        self.option_add("*TCombobox*Listbox.selectBackground", ACCENT)
        st.configure("TProgressbar", background=ACCENT,
                     troughcolor=BG2, borderwidth=0, thickness=4)
        # Severity gets its own tint so the summary line's amber means only
        # one thing. "medium" uses a distinct orange rather than the same
        # amber the header uses.
        st.configure("Vertical.TScrollbar", background=BG3, troughcolor=BG,
                     bordercolor=BG, darkcolor=BG3, lightcolor=BG3,
                     arrowcolor=MUTED, borderwidth=0, arrowsize=12,
                     gripcount=0)
        st.map("Vertical.TScrollbar",
               background=[("active", "#2f3b55")],
               arrowcolor=[("active", FG)])
        st.configure("Horizontal.TScrollbar", background=BG3, troughcolor=BG,
                     bordercolor=BG, arrowcolor=MUTED, borderwidth=0,
                     arrowsize=12)
        st.configure("TPanedwindow", background=BG)
        st.configure("Sash", sashthickness=6, gripcount=0)

    # ------------------------------------------------------------- header
    def _build_header(self):
        h = ttk.Frame(self, padding=(18, 14, 18, 6))
        h.pack(fill="x")
        ttk.Label(h, text="SimScan", style="Head.TLabel").pack(side="left")
        ttk.Label(h, text=f"  offline Mods folder auditor  v{__version__}",
                  style="Sub.TLabel").pack(side="left", pady=(6, 0))

        row = ttk.Frame(self, padding=(18, 0, 18, 10))
        row.pack(fill="x")
        ttk.Label(row, text="Mods folder", style="Muted.TLabel").pack(
            side="left", padx=(0, 8))
        e = ttk.Entry(row, textvariable=self.mods_dir, width=64)
        e.pack(side="left", fill="x", expand=True)
        ttk.Button(row, text="Browse…", command=self.browse).pack(
            side="left", padx=6)
        self.scan_btn = ttk.Button(row, text="Scan", style="Go.TButton",
                                   command=self.start_scan)
        self.scan_btn.pack(side="left")

        self.prog = ttk.Progressbar(self, mode="indeterminate")

        self.bar = ttk.Frame(self, padding=(18, 0, 18, 8))
        self.bar.pack(fill="x")
        self.summary = ttk.Label(self.bar, text="", style="Sub.TLabel")
        self.summary.pack(side="left")

    def browsse_placeholder(self):
        pass

    def browse(self):
        d = filedialog.askdirectory(title="Select your Sims 4 Mods folder",
                                    initialdir=self.mods_dir.get() or "~")
        if d:
            self.mods_dir.set(d)
            self.start_scan()

    # --------------------------------------------------------------- tabs
    def _build_tabs(self):
        self.nb = ttk.Notebook(self)
        self.nb.pack(fill="both", expand=True, padx=14, pady=(0, 6))
        self._build_findings_tab()
        self._build_order_tab()
        self._build_files_tab()
        self._build_exception_tab()

    # ---- findings
    def _build_findings_tab(self):
        tab = ttk.Frame(self.nb, padding=8)
        self.nb.add(tab, text="  Findings  ")

        bar = ttk.Frame(tab)
        bar.pack(fill="x", pady=(0, 6))
        self.disable_btn = ttk.Button(bar, text="Disable selected",
                                      state="disabled",
                                      command=self.disable_selected)
        self.disable_btn.pack(side="left")
        self.undo_btn = ttk.Button(bar, text="Undo last change",
                                   state="disabled",
                                   command=self.undo_last)
        self.undo_btn.pack(side="left", padx=6)
        self.reveal_btn = ttk.Button(bar, text="Show in folder",
                                     state="disabled",
                                     command=lambda: self.reveal_selected(
                                         self.find_tree))
        self.reveal_btn.pack(side="left")
        self.del_btn = ttk.Button(bar, text="Delete…", style="Danger.TButton",
                                  state="disabled",
                                  command=self.delete_selected)
        self.del_btn.pack(side="left", padx=6)
        ttk.Button(bar, text="Export report…",
                   command=self.export_report).pack(side="right")

        pane = ttk.Panedwindow(tab, orient="horizontal")
        pane.pack(fill="both", expand=True)

        left = ttk.Frame(pane, style="Card.TFrame")
        self.find_tree = ttk.Treeview(
            left, columns=("sev", "title", "n"), show="headings",
            selectmode="browse")
        self.find_tree.heading("sev", text="Severity", anchor="center")
        self.find_tree.heading("title", text="Finding", anchor="w")
        self.find_tree.heading("n", text="Files", anchor="e")
        self.find_tree.column("sev", width=88, stretch=False, anchor="center")
        self.find_tree.column("title", width=330, anchor="w")
        self.find_tree.column("n", width=60, stretch=False, anchor="e")
        vs = ttk.Scrollbar(left, orient="vertical",
                           command=self.find_tree.yview)
        self.find_tree.configure(yscrollcommand=vs.set)
        self.find_tree.pack(side="left", fill="both", expand=True)
        vs.pack(side="right", fill="y")
        for sev in ("high", "medium", "low", "info"):
            self.find_tree.tag_configure(sev, foreground=SEV_COLOUR[sev])
        self.find_tree.bind("<<TreeviewSelect>>", self.show_finding)
        pane.add(left, weight=2)

        right = ttk.Frame(pane, style="Card.TFrame", padding=12)
        self.detail_title = tk.Text(right, height=5, wrap="word", bg=BG2,
                                    fg=FG, relief="flat", font=("Segoe UI", 10),
                                    highlightthickness=0, padx=2, pady=2)
        self.detail_title.pack(fill="x")
        self.detail_title.configure(state="disabled")
        self.detail_head = ttk.Label(right, text="", style="Sub.TLabel")
        self.detail_head.pack(anchor="w", pady=(8, 2))
        self.file_tree = ttk.Treeview(right, columns=("f", "note"),
                                      show="headings", selectmode="extended")
        self.file_tree.heading("f", text="File", anchor="w")
        self.file_tree.heading("note", text="Detail", anchor="w")
        self.file_tree.column("f", width=420, anchor="w")
        self.file_tree.column("note", width=190, stretch=False, anchor="w")
        vs2 = ttk.Scrollbar(right, orient="vertical",
                            command=self.file_tree.yview)
        self.file_tree.configure(yscrollcommand=vs2.set)
        self.file_tree.pack(side="left", fill="both", expand=True)
        vs2.pack(side="right", fill="y")
        pane.add(right, weight=3)

    # ---- load order
    def _build_order_tab(self):
        tab = ttk.Frame(self.nb, padding=8)
        self.nb.add(tab, text="  Load order  ")
        top = ttk.Frame(tab)
        top.pack(fill="x", pady=(0, 6))
        ttk.Label(top, style="Muted.TLabel",
                  text=("Computed precedence: Resource.cfg priority, then "
                        "folder depth, then filename. Row 1 wins ties.")).pack(
            side="left")
        self.order_filter = tk.StringVar()
        ent = ttk.Entry(top, textvariable=self.order_filter, width=28)
        ent.pack(side="right")
        ent.bind("<KeyRelease>", lambda e: self.fill_order())
        ttk.Label(top, text="Filter", style="Muted.TLabel").pack(
            side="right", padx=6)
        self.order_tree = ttk.Treeview(
            tab, columns=("i", "name", "prio", "depth", "kind", "creator"),
            show="headings")
        for c, t, w in (("i", "#", 48), ("name", "Package", 340),
                        ("prio", "Priority", 70), ("depth", "Depth", 56),
                        ("kind", "Type", 150), ("creator", "Creator", 150)):
            self.order_tree.heading(c, text=t)
            self.order_tree.column(c, width=w,
                                   stretch=(c == "name"),
                                   anchor="center" if c in
                                   ("i", "prio", "depth") else "w")
        vs = ttk.Scrollbar(tab, orient="vertical",
                           command=self.order_tree.yview)
        self.order_tree.configure(yscrollcommand=vs.set)
        self.order_tree.pack(side="left", fill="both", expand=True)
        vs.pack(side="right", fill="y")

    # ---- all files
    def _build_files_tab(self):
        tab = ttk.Frame(self.nb, padding=8)
        self.nb.add(tab, text="  All files  ")
        top = ttk.Frame(tab)
        top.pack(fill="x", pady=(0, 6))
        self.file_filter = tk.StringVar()
        ent = ttk.Entry(top, textvariable=self.file_filter, width=32)
        ent.pack(side="right")
        ent.bind("<KeyRelease>", lambda e: self.fill_files())
        ttk.Label(top, text="Search", style="Muted.TLabel").pack(
            side="right", padx=6)
        self.files_count = ttk.Label(top, text="", style="Muted.TLabel")
        self.files_count.pack(side="left")

        pane = ttk.Panedwindow(tab, orient="horizontal")
        pane.pack(fill="both", expand=True)
        left = ttk.Frame(pane, style="Card.TFrame")
        self.files_tree = ttk.Treeview(
            left, columns=("name", "kind", "res", "size", "creator"),
            show="headings", selectmode="extended")
        for c, t, w in (("name", "File", 380), ("kind", "Type", 150),
                        ("res", "Res", 56), ("size", "Size", 84),
                        ("creator", "Creator", 130)):
            self.files_tree.heading(c, text=t)
            self.files_tree.column(c, width=w, stretch=(c == "name"),
                                   anchor="e" if c in ("res", "size") else "w")
        vs = ttk.Scrollbar(left, orient="vertical",
                           command=self.files_tree.yview)
        self.files_tree.configure(yscrollcommand=vs.set)
        self.files_tree.pack(side="left", fill="both", expand=True)
        vs.pack(side="right", fill="y")
        self.files_tree.bind("<<TreeviewSelect>>", self.show_file_detail)
        pane.add(left, weight=3)

        right = ttk.Frame(pane, style="Card.TFrame", padding=12)
        self.preview = tk.Label(right, bg=BG2, fg=MUTED,
                                text="Select a file to preview",
                                font=("Segoe UI", 9))
        self.preview.pack(fill="x", pady=(0, 8))
        self.file_info = tk.Text(right, height=18, wrap="word", bg=BG2,
                                 fg=FG, relief="flat",
                                 font=("Consolas", 9),
                                 highlightthickness=0)
        self.file_info.pack(fill="both", expand=True)
        self.file_info.configure(state="disabled")
        pane.add(right, weight=2)

    # ---- exception
    def _build_exception_tab(self):
        tab = ttk.Frame(self.nb, padding=8)
        self.nb.add(tab, text="  Last exception  ")
        top = ttk.Frame(tab)
        top.pack(fill="x", pady=(0, 6))
        self.exc_choice = tk.StringVar()
        self.exc_combo = ttk.Combobox(top, textvariable=self.exc_choice,
                                      width=46, state="readonly")
        self.exc_combo.pack(side="left")
        ttk.Button(top, text="Reload list",
                   command=self.load_exception_list).pack(side="left", padx=6)
        ttk.Button(top, text="Analyse", style="Go.TButton",
                   command=self.analyse_exception).pack(side="left")
        ttk.Button(top, text="Make 50/50 plan…",
                   command=self.make_5050_plan).pack(side="right")

        ttk.Label(tab, style="Muted.TLabel", wraplength=1000, justify="left",
                  text=("SimScan reads the game's own crash reports and ranks "
                        "your installed mods by how likely each one explains "
                        "it. It cannot prove guilt - no tool can, because "
                        "nothing but the game can reproduce the fault - so "
                        "the ranking tells you where to start testing.")
                  ).pack(anchor="w", pady=(0, 8))

        self.exc_tree = ttk.Treeview(
            tab, columns=("score", "file", "why"), show="headings",
            selectmode="extended")
        self.exc_tree.heading("score", text="Score")
        self.exc_tree.heading("file", text="Suspect mod")
        self.exc_tree.heading("why", text="Why")
        self.exc_tree.column("score", width=64, stretch=False, anchor="center")
        self.exc_tree.column("file", width=420)
        self.exc_tree.column("why", width=340)
        vs = ttk.Scrollbar(tab, orient="vertical",
                           command=self.exc_tree.yview)
        self.exc_tree.configure(yscrollcommand=vs.set)
        self.exc_tree.pack(side="left", fill="both", expand=True)
        vs.pack(side="right", fill="y")

    def _build_status(self):
        s = ttk.Frame(self, padding=(18, 4, 18, 10))
        s.pack(fill="x")
        ttk.Label(s, textvariable=self.status, style="Sub.TLabel").pack(
            side="left")
        ttk.Label(s, style="Sub.TLabel",
                  text=("SimScan never uploads anything — all analysis runs "
                        "on this PC.")).pack(side="right")

    # -------------------------------------------------------------- scanning
    def start_scan(self):
        if self.scanning:
            return
        root = self.mods_dir.get().strip()
        if not root or not os.path.isdir(root):
            messagebox.showwarning(
                "Folder not found",
                "Please choose your Sims 4 Mods folder.\n\n"
                "It is usually:\n"
                r"Documents\Electronic Arts\The Sims 4\Mods")
            return
        self.scanning = True
        self.scan_btn.configure(state="disabled")
        self.prog.pack(fill="x", padx=18, before=self.bar)
        self.prog.start(12)
        self.status.set("Scanning…")
        # Worker threads must never touch tkinter directly, so results come
        # back through a queue that the main thread polls.
        self._q = queue.Queue()
        threading.Thread(target=self._scan_worker, args=(root,),
                         daemon=True).start()
        self.after(50, self._poll_scan)

    def _scan_worker(self, root):
        try:
            def prog(msg):
                self._q.put(("status", msg))
            res = scan_mods_folder(root, progress=prog)
            self._q.put(("done", res))
        except Exception:
            self._q.put(("error", traceback.format_exc()))

    def _poll_scan(self):
        try:
            while True:
                kind, payload = self._q.get_nowait()
                if kind == "status":
                    self.status.set(payload)
                elif kind == "done":
                    self._scan_done(payload, None)
                    return
                elif kind == "error":
                    self._scan_done(None, payload)
                    return
        except queue.Empty:
            pass
        if self.scanning:
            self.after(50, self._poll_scan)

    def _scan_done(self, res, err):
        self.scanning = False
        self.scan_btn.configure(state="normal")
        try:
            self.prog.stop()
            self.prog.pack_forget()
        except tk.TclError:
            pass
        if err:
            self.status.set("Scan failed.")
            messagebox.showerror("Scan failed", err)
            return
        self.result = res
        self.fill_findings()
        self.fill_order()
        self.fill_files()
        self.load_exception_list()
        s = res.stats
        n_high = s.get("high", 0)
        self.summary.configure(
            text=(f"{s.get('total_files',0)} files · "
                  f"{s.get('packages',0)} packages · "
                  f"{s.get('scripts',0)} script mods · "
                  f"{report_mod.human_bytes(s.get('total_bytes',0))} · "
                  f"{plural(len(res.findings), 'finding')} "
                  f"({n_high} high) · {res.duration:.1f}s"),
            foreground=MUTED)
        self.status.set("Scan complete.")
        self._set_action_state(
            len(self.file_tree.get_children()))

    # ---------------------------------------------------------------- fill
    def fill_findings(self):
        self.find_tree.delete(*self.find_tree.get_children())
        if not self.result:
            return
        order = {"high": 0, "medium": 1, "low": 2, "info": 3}
        for f in sorted(self.result.findings,
                        key=lambda x: order.get(x.severity, 9)):
            self.find_tree.insert(
                "", "end", iid=f.kind, tags=(f.severity,),
                values=(SEV_LABEL.get(f.severity, "?"), f.title,
                        len(f.files) or "—"))
        kids = self.find_tree.get_children()
        if kids:
            self.find_tree.selection_set(kids[0])
            self.find_tree.focus(kids[0])
            self.show_finding()

    def show_finding(self, _evt=None):
        sel = self.find_tree.selection()
        if not sel or not self.result:
            self._set_action_state(0)
            return
        f = next((x for x in self.result.findings if x.kind == sel[0]), None)
        if not f:
            self._set_action_state(0)
            return
        txt = f"{f.title}\n\n{f.detail}"
        if f.evidence:
            txt += f"\n\nEvidence: {f.evidence}"
        if f.fix:
            txt += f"\n\nFix: {f.fix}"
        self.detail_title.configure(state="normal")
        self.detail_title.delete("1.0", "end")
        self.detail_title.insert("1.0", txt)
        self.detail_title.configure(state="disabled")

        n = len(f.files)
        self.detail_head.configure(
            text=(f"{plural(n, 'file')} affected"
                  + (" — select one or more below, then use the buttons "
                     "above" if n else ""))
            if n else "No individual files to act on")
        self.file_tree.delete(*self.file_tree.get_children())
        self._finding_files = {}
        for i, m in enumerate(f.files):
            note = m.error or (f"{m.resources} res" if m.resources else "")
            if m.display_name and not note:
                note = m.display_name[:40]
            iid = f"r{i}"
            self.file_tree.insert("", "end", iid=iid,
                                  values=(m.rel_path, note))
            self._finding_files[iid] = m
        self._set_action_state(len(f.files))

    def _set_action_state(self, n_available):
        """Enable file actions only when the current view has files to act on."""
        state = "normal" if n_available else "disabled"
        for btn in (self.disable_btn, self.del_btn, self.reveal_btn):
            try:
                btn.configure(state=state)
            except tk.TclError:
                pass
        try:
            self.undo_btn.configure(
                state="normal" if recyclex.has_undo(
                    self.result.root if self.result else "") else "disabled")
        except tk.TclError:
            pass

    def fill_order(self):
        self.order_tree.delete(*self.order_tree.get_children())
        if not self.result:
            return
        flt = self.order_filter.get().lower().strip()
        for m in self.result.load_order:
            if flt and flt not in m.rel_path.lower():
                continue
            self.order_tree.insert(
                "", "end", iid=f"o{id(m)}",
                values=(m.order_index + 1, m.rel_path, m.priority, m.depth,
                        m.kind, m.creator or ""))

    def fill_files(self):
        self.files_tree.delete(*self.files_tree.get_children())
        if not self.result:
            return
        flt = self.file_filter.get().lower().strip()
        shown = 0
        for m in self.result.files:
            if flt and flt not in m.rel_path.lower() \
                    and flt not in (m.creator or "").lower() \
                    and flt not in (m.display_name or "").lower():
                continue
            self.files_tree.insert(
                "", "end", iid=f"f{id(m)}",
                values=(m.rel_path, m.kind, m.resources or "",
                        report_mod.human_bytes(m.size), m.creator or ""))
            self._all_files[f"f{id(m)}"] = m
            shown += 1
        self.files_count.configure(text=f"{shown} shown")

    def show_file_detail(self, _evt=None):
        sel = self.files_tree.selection()
        m = self._all_files.get(sel[0]) if sel else None
        if not m:
            return
        lines = [
            f"Path      {m.rel_path}",
            f"Size      {report_mod.human_bytes(m.size)}",
            f"Type      {m.kind}",
            f"Creator   {m.creator or 'unknown'}",
            f"Name      {m.display_name or '—'}",
            f"Resources {m.resources}",
            f"Priority  {m.priority}",
            f"Load #    {m.order_index + 1}",
            f"SHA-256   {m.content_hash or '—'}",
        ]
        if m.error:
            lines.append(f"ERROR     {m.error}")
        if m.types:
            from .analyzer import TYPE_NAMES
            lines.append("")
            lines.append("Resource types:")
            for t, c in sorted(m.types.items(), key=lambda kv: -kv[1])[:12]:
                lines.append(f"   {t:08X}  x{c:<4} {TYPE_NAMES.get(t,'(other)')}")
        self.file_info.configure(state="normal")
        self.file_info.delete("1.0", "end")
        self.file_info.insert("1.0", "\n".join(lines))
        self.file_info.configure(state="disabled")
        self._show_thumbnail(m)

    def _show_thumbnail(self, m):
        self._thumb_ref = None
        self.preview.configure(image="", text="No preview available")
        if not m.is_package or m.error:
            return
        try:
            from PIL import Image, ImageTk
            from .dds import dds_to_rgba
            pkg = Package(m.abs_path)
            best = None
            for r in pkg.resources:
                if r.type_id != 0x00B2D882:
                    continue
                data = pkg.try_payload(r)
                if not data or data[:4] != b"DDS ":
                    continue
                import struct as _s
                h, w = _s.unpack_from("<II", data, 12)
                if best is None or (w * h) > best[0]:
                    best = (w * h, data)
            if not best:
                self.preview.configure(text="This package has no image "
                                            "resources (gameplay/tuning only)")
                return
            rgba, w, h = dds_to_rgba(best[1])
            im = Image.frombytes("RGBA", (w, h), rgba)
            im.thumbnail((230, 230))
            self._thumb_ref = ImageTk.PhotoImage(im)
            self.preview.configure(image=self._thumb_ref,
                                   text=f"{w}×{h}")
        except Exception:
            self.preview.configure(text="Preview unavailable")

    # -------------------------------------------------------------- actions
    def _rowmap_for(self, tree):
        if tree is self.file_tree:
            return self._finding_files
        if tree is self.files_tree:
            return self._all_files
        if tree is self.exc_tree:
            return self._exc_files_map
        return {}

    def _selected_mods(self, tree):
        rowmap = self._rowmap_for(tree)
        out, seen = [], set()
        for iid in tree.selection():
            m = rowmap.get(iid)
            if m and m.abs_path not in seen:
                seen.add(m.abs_path)
                out.append(m)
        return out

    def reveal_selected(self, tree):
        mods = self._selected_mods(tree)
        if not mods:
            messagebox.showinfo("Nothing selected", "Select a file first.")
            return
        p = mods[0].abs_path
        try:
            if os.name == "nt":
                os.startfile(os.path.dirname(p))          # noqa: S606
            elif os.uname().sysname == "Darwin":
                import subprocess
                subprocess.Popen(["open", "-R", p])
            else:
                import subprocess
                subprocess.Popen(["xdg-open", os.path.dirname(p)])
        except Exception as e:
            messagebox.showwarning("Could not open", str(e))

    def disable_selected(self):
        mods = self._selected_mods(self.find_tree)
        if not mods:
            messagebox.showinfo("Nothing selected",
                                "Select one or more files in the right-hand "
                                "list first.")
            return
        if not messagebox.askyesno(
                "Disable files?",
                f"Move {len(mods)} file(s) into a _disabled folder?\n\n"
                "Nothing is deleted — the game simply ignores the folder, "
                "and you can undo this at any time."):
            return
        try:
            log = recyclex.disable_files(self.result.root, mods)
        except Exception as e:
            messagebox.showerror("Could not disable", str(e))
            return
        self.status.set(f"Disabled {len(log)} file(s). "
                        "Press 'Undo last change' to restore.")
        self.start_scan()

    def delete_selected(self):
        mods = self._selected_mods(self.find_tree)
        if not mods:
            messagebox.showinfo("Nothing selected",
                                "Select one or more files in the right-hand "
                                "list first.")
            return
        total = sum(m.size for m in mods)
        if not messagebox.askyesno(
                "Delete files?",
                f"Send {len(mods)} file(s) "
                f"({report_mod.human_bytes(total)}) to the Recycle Bin?\n\n"
                "They can be restored from the Bin until you empty it.",
                icon="warning"):
            return
        ok, failed = recyclex.recycle_files([m.abs_path for m in mods])
        if failed:
            messagebox.showwarning(
                "Some files could not be deleted",
                "\n".join(failed[:10]) +
                ("\n…" if len(failed) > 10 else "") +
                "\n\nThey may be in use by another program.")
        self.status.set(f"Sent {ok} file(s) to the Recycle Bin.")
        self.start_scan()

    def undo_last(self):
        n = recyclex.undo_last_disable(self.result.root if self.result
                                       else self.mods_dir.get())
        if n:
            self.status.set(f"Restored {n} file(s).")
            self.start_scan()
        else:
            self.status.set("Nothing to undo in this folder.")

    # ------------------------------------------------------------ exports
    def export_report(self):
        if not self.result:
            messagebox.showinfo("No scan", "Run a scan first.")
            return
        default = f"SimScan-report-{time.strftime('%Y%m%d')}.html"
        path = filedialog.asksaveasfilename(
            title="Save report", initialfile=default,
            defaultextension=".html",
            filetypes=[("HTML report", "*.html"), ("Text", "*.txt"),
                       ("JSON", "*.json"), ("CSV", "*.csv")])
        if not path:
            return
        ext = os.path.splitext(path)[1].lower()
        try:
            if ext == ".json":
                report_mod.to_json(self.result, path)
            elif ext == ".csv":
                report_mod.to_csv(self.result, path)
            elif ext == ".txt":
                report_mod.to_text(self.result, path)
            else:
                report_mod.to_html(self.result, path)
        except Exception as e:
            messagebox.showerror("Export failed", str(e))
            return
        self.status.set(f"Saved {path}")
        if messagebox.askyesno("Report saved",
                               f"Saved to:\n{path}\n\nOpen it now?"):
            try:
                if os.name == "nt":
                    os.startfile(path)                    # noqa: S606
                elif os.uname().sysname == "Darwin":
                    import subprocess
                    subprocess.Popen(["open", path])
                else:
                    import subprocess
                    subprocess.Popen(["xdg-open", path])
            except Exception:
                pass

    def make_5050_plan(self):
        if not self.result:
            messagebox.showinfo("No scan", "Run a scan first.")
            return
        sel = self._selected_mods(self.exc_tree)
        if not sel:
            messagebox.showinfo(
                "No suspects selected",
                "Analyse a crash report first, or select rows to include.")
            return
        path = filedialog.asksaveasfilename(
            title="Save 50/50 plan", initialfile="SimScan-5050-plan.txt",
            defaultextension=".txt", filetypes=[("Text", "*.txt")])
        if not path:
            return
        report_mod.to_50_50_plan(self.result, path,
                                 [m.rel_path for m in sel])
        self.status.set(f"Saved plan to {path}")
        if messagebox.askyesno("Plan saved", f"Saved to:\n{path}\n\nOpen it?"):
            try:
                if os.name == "nt":
                    os.startfile(path)                    # noqa: S606
                else:
                    import subprocess
                    subprocess.Popen(["xdg-open", path])
            except Exception:
                pass

    # ---------------------------------------------------------- exceptions
    def load_exception_list(self):
        if not self.result:
            return
        uf = user_folder_for(self.result.root)
        files = find_exception_files(uf)
        self._exc_files = files
        names = [os.path.basename(p) for p in files]
        self.exc_combo.configure(values=names)
        if names and not self.exc_choice.get():
            self.exc_choice.set(names[0])
        elif not names:
            if hasattr(self, "exc_combo"):
                self.exc_combo.set("")

    def analyse_exception(self):
        if not self.result:
            messagebox.showinfo("No scan", "Run a scan first.")
            return
        name = self.exc_choice.get()
        if not name:
            messagebox.showinfo(
                "No crash reports found",
                "No LastException files were found in your Sims 4 folder.\n\n"
                "They only exist after the game has actually logged an error.")
            return
        path = next((p for p in getattr(self, "_exc_files", [])
                     if os.path.basename(p) == name), None)
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as fh:
                text = fh.read()
        except OSError as e:
            messagebox.showerror("Could not read", str(e))
            return
        info, ranked = correlate_exception(text, self.result.files)
        self.exc_tree.delete(*self.exc_tree.get_children())
        self._exc_files_map = {}
        for i, (p, score, why) in enumerate(ranked):
            m = next((x for x in self.result.files if x.abs_path == p), None)
            if not m:
                continue
            iid = f"e{i}"
            self.exc_tree.insert("", "end", iid=iid,
                                 values=(f"{score:.1f}", m.rel_path,
                                         "; ".join(why)))
            self._exc_files_map[iid] = m
        exc = info.get("exception") or "no explicit exception line"
        self.status.set(
            f"Parsed {name}: {exc} — {len(ranked)} ranking(s). "
            "Select rows and make a 50/50 plan.")


def main():
    app = SimScanApp()
    app.mainloop()
