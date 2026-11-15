"""Asset Replacer GUI - a front end for shibahex/asset-replacer-roblox (animation-replace-roblox.exe)."""
import os, re, sys, threading, subprocess, queue, tkinter as tk
from tkinter import ttk, filedialog, messagebox

ENGINE = "animation-replace-roblox" + (".exe" if os.name == "nt" else "")
ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
BG, PANEL, FG, MUTED, ACCENT, OK, ERR = "#14161c", "#1d2029", "#e6e8ee", "#8b90a0", "#4f8cff", "#3ecf8e", "#ff6b6b"


def find_engine():
    here = [getattr(sys, "_MEIPASS", ""), os.path.dirname(os.path.abspath(sys.argv[0])), os.getcwd()]
    for d in here:
        p = os.path.join(d, ENGINE)
        if d and os.path.isfile(p):
            return p
    return None


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Asset Replacer for Roblox")
        self.geometry("820x760")
        self.minsize(700, 640)
        self.configure(bg=BG)
        self.proc = None
        self.q = queue.Queue()
        self.vars = {k: tk.StringVar() for k in ("cookie", "api", "file", "out", "group")}
        self.vars["threads"] = tk.StringVar(value="5")
        self.types = {t: tk.BooleanVar(value=False) for t in ("animation", "audio", "image", "model", "video", "mesh")}
        self.flags = {k: tk.BooleanVar(value=False) for k in ("unformatted", "names", "dry")}
        self.show = tk.BooleanVar(value=False)
        self._style()
        self._build()
        self.after(100, self._drain)
        if not find_engine():
            self.log(f"Engine '{ENGINE}' not found next to this app. Run build.bat first.\n", ERR)

    def _style(self):
        s = ttk.Style(self)
        s.theme_use("clam")
        s.configure(".", background=BG, foreground=FG, fieldbackground=PANEL, bordercolor=PANEL, font=("Segoe UI", 10))
        s.configure("Card.TFrame", background=PANEL)
        s.configure("TLabel", background=PANEL, foreground=FG)
        s.configure("Muted.TLabel", background=PANEL, foreground=MUTED, font=("Segoe UI", 9))
        s.configure("H.TLabel", background=BG, font=("Segoe UI", 18, "bold"))
        s.configure("Sub.TLabel", background=BG, foreground=MUTED)
        s.configure("TEntry", fieldbackground=BG, foreground=FG, insertcolor=FG, padding=6)
        s.configure("TCheckbutton", background=PANEL, foreground=FG)
        s.map("TCheckbutton", background=[("active", PANEL)])
        s.configure("TButton", background="#2a2f3d", foreground=FG, padding=(10, 6), borderwidth=0)
        s.map("TButton", background=[("active", "#353b4d")])
        s.configure("Run.TButton", background=ACCENT, foreground="white", font=("Segoe UI", 11, "bold"), padding=(18, 9))
        s.map("Run.TButton", background=[("active", "#3a78eb"), ("disabled", "#2a2f3d")])
        s.configure("Stop.TButton", background="#3a2226", foreground=ERR, padding=(14, 9))
        s.configure("Horizontal.TProgressbar", troughcolor=PANEL, background=ACCENT, thickness=4)

    def card(self, parent, title):
        wrap = ttk.Frame(parent, style="Card.TFrame", padding=14)
        wrap.pack(fill="x", pady=(0, 10))
        ttk.Label(wrap, text=title.upper(), style="Muted.TLabel").grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 8))
        wrap.columnconfigure(1, weight=1)
        return wrap

    def row(self, card, r, label, key, browse=None, secret=False, width=None):
        ttk.Label(card, text=label).grid(row=r, column=0, sticky="w", padx=(0, 12), pady=4)
        e = ttk.Entry(card, textvariable=self.vars[key], show="•" if secret else "", width=width or 40)
        e.grid(row=r, column=1, sticky="ew" if not width else "w", pady=4)
        if secret:
            self.secret_entries = getattr(self, "secret_entries", []) + [e]
        if browse:
            ttk.Button(card, text="Browse", command=browse).grid(row=r, column=2, padx=(8, 0))

    def _build(self):
        root = ttk.Frame(self, padding=18)
        root.pack(fill="both", expand=True)
        ttk.Label(root, text="Asset Replacer", style="H.TLabel").pack(anchor="w")
        ttk.Label(root, text="Re-upload the assets in a Roblox place file to your own account or group.", style="Sub.TLabel").pack(anchor="w", pady=(0, 12))

        c = self.card(root, "Authentication")
        self.row(c, 1, ".ROBLOSECURITY cookie", "cookie", secret=True)
        self.row(c, 2, "Open Cloud API key", "api", secret=True)
        ttk.Checkbutton(c, text="Show secrets", variable=self.show, command=self._toggle).grid(row=3, column=1, sticky="w")
        ttk.Label(c, text="Held in memory only and never saved. Use an alt account if you can.", style="Muted.TLabel").grid(row=4, column=1, sticky="w", pady=(4, 0))

        c = self.card(root, "Files")
        self.row(c, 1, "Place / model file", "file", browse=self._pick_in)
        self.row(c, 2, "Output file", "out", browse=self._pick_out)

        c = self.card(root, "Options")
        self.row(c, 1, "Group ID (optional)", "group", width=14)
        self.row(c, 2, "Threads", "threads", width=14)
        ttk.Label(c, text="Only these types").grid(row=3, column=0, sticky="nw", pady=6)
        f = ttk.Frame(c, style="Card.TFrame"); f.grid(row=3, column=1, sticky="w")
        for i, (t, v) in enumerate(self.types.items()):
            ttk.Checkbutton(f, text=t, variable=v).grid(row=i // 3, column=i % 3, sticky="w", padx=(0, 14))
        ttk.Label(c, text="Leave all unchecked to reupload everything.", style="Muted.TLabel").grid(row=4, column=1, sticky="w")
        f = ttk.Frame(c, style="Card.TFrame"); f.grid(row=5, column=1, sticky="w", pady=(8, 0))
        ttk.Checkbutton(f, text="Scan unformatted IDs", variable=self.flags["unformatted"]).pack(side="left", padx=(0, 14))
        ttk.Checkbutton(f, text="Fetch original names", variable=self.flags["names"]).pack(side="left", padx=(0, 14))
        ttk.Checkbutton(f, text="Dry run", variable=self.flags["dry"]).pack(side="left")

        bar = ttk.Frame(root); bar.pack(fill="x", pady=(2, 8))
        self.run_btn = ttk.Button(bar, text="Start", style="Run.TButton", command=self.start)
        self.run_btn.pack(side="left")
        self.stop_btn = ttk.Button(bar, text="Stop", style="Stop.TButton", command=self.stop, state="disabled")
        self.stop_btn.pack(side="left", padx=8)
        self.status = ttk.Label(bar, text="Idle", style="Sub.TLabel"); self.status.pack(side="right")
        self.prog = ttk.Progressbar(root, mode="indeterminate"); self.prog.pack(fill="x", pady=(0, 8))

        self.logbox = tk.Text(root, bg="#0d0f14", fg=FG, insertbackground=FG, relief="flat", height=10, font=("Consolas", 9), wrap="word", state="disabled")
        self.logbox.pack(fill="both", expand=True)
        for tag, col in (("ok", OK), ("err", ERR), ("muted", MUTED)):
            self.logbox.tag_config(tag, foreground=col)

    def _toggle(self):
        for e in getattr(self, "secret_entries", []):
            e.configure(show="" if self.show.get() else "•")

    def _pick_in(self):
        p = filedialog.askopenfilename(filetypes=[("Roblox files", "*.rbxl *.rbxlx *.rbxm *.rbxmx"), ("All", "*.*")])
        if p:
            self.vars["file"].set(p)
            base, ext = os.path.splitext(p)
            if not self.vars["out"].get():
                self.vars["out"].set(f"{base}_output{ext}")

    def _pick_out(self):
        p = filedialog.asksaveasfilename(defaultextension=".rbxl", filetypes=[("Roblox files", "*.rbxl *.rbxlx *.rbxm *.rbxmx")])
        if p:
            self.vars["out"].set(p)

    def log(self, text, tag=None):
        self.logbox.configure(state="normal")
        self.logbox.insert("end", text, tag or "")
        self.logbox.see("end")
        self.logbox.configure(state="disabled")

    def build_cmd(self):
        g = {k: v.get().strip() for k, v in self.vars.items()}
        dry = self.flags["dry"].get()
        if not g["cookie"] or not g["api"] or not g["file"]:
            raise ValueError("Cookie, API key and input file are required.")
        if not os.path.isfile(g["file"]):
            raise ValueError("Input file does not exist.")
        if not g["out"] and not dry:
            raise ValueError("Pick an output file (protects your original from corruption).")
        if g["group"] and not g["group"].isdigit():
            raise ValueError("Group ID must be a number.")
        if not g["threads"].isdigit() or int(g["threads"]) < 1:
            raise ValueError("Threads must be a positive number.")
        exe = find_engine()
        if not exe:
            raise ValueError(f"{ENGINE} not found next to the app.")
        cmd = [exe, "--cookie", g["cookie"], "--api-key", g["api"], "--file", g["file"], "--threads", g["threads"]]
        if g["out"]:
            cmd += ["--output", g["out"]]
        if g["group"]:
            cmd += ["--group", g["group"]]
        chosen = [t for t, v in self.types.items() if v.get()]
        if chosen:
            cmd += ["--only", ",".join(chosen)]
        if self.flags["unformatted"].get(): cmd.append("--unformatted-ids")
        if self.flags["names"].get(): cmd.append("--fetch-names")
        if dry: cmd.append("--dry-run")
        return cmd

    def start(self):
        try:
            cmd = self.build_cmd()
        except ValueError as e:
            messagebox.showerror("Missing info", str(e)); return
        secrets = [self.vars["cookie"].get().strip(), self.vars["api"].get().strip()]
        self.log("\n▶ Starting…\n", "muted")
        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        try:
            self.proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                         encoding="utf-8", errors="replace", creationflags=flags, cwd=os.path.dirname(cmd[0]))
        except OSError as e:
            self.log(f"Could not launch engine: {e}\n", "err"); return
        self.run_btn.configure(state="disabled"); self.stop_btn.configure(state="normal")
        self.status.configure(text="Running…"); self.prog.start(12)
        threading.Thread(target=self._reader, args=(self.proc, secrets), daemon=True).start()

    def _reader(self, proc, secrets):
        for line in proc.stdout:
            line = ANSI.sub("", line)
            for s in secrets:
                if s: line = line.replace(s, "***")
            self.q.put(("line", line))
        self.q.put(("done", proc.wait()))

    def _drain(self):
        try:
            while True:
                kind, val = self.q.get_nowait()
                if kind == "line":
                    low = val.lower()
                    self.log(val, "err" if ("error" in low or "failed" in low) else None)
                else:
                    ok = val == 0
                    self.log(f"\n{'✔ Finished' if ok else f'✖ Exited with code {val}'}\n", "ok" if ok else "err")
                    self.status.configure(text="Done" if ok else "Stopped / failed")
                    self.prog.stop(); self.run_btn.configure(state="normal"); self.stop_btn.configure(state="disabled")
                    self.proc = None
        except queue.Empty:
            pass
        self.after(100, self._drain)

    def stop(self):
        if self.proc:
            self.proc.terminate()
            self.log("Stopping…\n", "muted")


if __name__ == "__main__":
    App().mainloop()
