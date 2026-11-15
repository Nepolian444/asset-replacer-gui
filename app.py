"""Asset Replacer - Windows 11 style front end for shibahex/asset-replacer-roblox."""
import ctypes, json, os, queue, re, subprocess, sys, threading, time, tkinter as tk
from tkinter import ttk, filedialog, messagebox
try:
    import sv_ttk
except ImportError:  # falls back to the default look
    sv_ttk = None

ENGINE = "animation-replace-roblox" + (".exe" if os.name == "nt" else "")
ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
PROG = re.compile(r"\[(\d+)/(\d+)\]")
SETTINGS = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "AssetReplacer", "settings.json")
TYPES = ("animation", "audio", "image", "model", "video", "mesh")
if os.name == "nt":
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)  # crisp text on scaled displays
    except Exception:
        pass


def find_engine():
    for d in (getattr(sys, "_MEIPASS", ""), os.path.dirname(os.path.abspath(sys.argv[0])), os.getcwd()):
        p = os.path.join(d, ENGINE)
        if d and os.path.isfile(p):
            return p


def dark_titlebar(win):
    try:
        win.update()
        hwnd = ctypes.windll.user32.GetParent(win.winfo_id())
        for attr in (20, 19):
            if ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(ctypes.c_int(1)), 4) == 0:
                break
    except Exception:
        pass


def fmt(sec):
    sec = int(sec)
    h, r = divmod(sec, 3600)
    m, s = divmod(r, 60)
    return f"{h}h {m:02d}m" if h else f"{m}m {s:02d}s"


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Asset Replacer")
        if sv_ttk:
            sv_ttk.set_theme("dark")
        k = self.winfo_fpixels("1i") / 96
        self.geometry(f"{int(780 * k)}x{int(900 * k)}")
        self.minsize(int(700 * k), int(760 * k))
        self.proc, self.q, self.t0, self.p0 = None, queue.Queue(), 0, None
        self.v = {n: tk.StringVar() for n in ("cookie", "api", "file", "out", "group")}
        self.v["threads"] = tk.StringVar(value="5")
        self.types = {t: tk.BooleanVar() for t in TYPES}
        self.flags = {n: tk.BooleanVar() for n in ("unformatted", "names", "dry")}
        self.show = tk.BooleanVar()
        self._load()
        self._build()
        dark_titlebar(self)
        self.protocol("WM_DELETE_WINDOW", self._close)
        self.after(100, self._drain)
        if not find_engine():
            self.log(f"Engine '{ENGINE}' not found next to this app.\n", "err")

    # ---------- UI ----------
    def _build(self):
        root = ttk.Frame(self, padding=20)
        root.pack(fill="both", expand=True)
        ttk.Label(root, text="Asset Replacer", font=("Segoe UI Semibold", 20)).pack(anchor="w")
        ttk.Label(root, text="Re-upload the assets in a Roblox place file to your own account or group.",
                  foreground="#9a9a9a").pack(anchor="w", pady=(0, 14))

        # bottom first so the log always keeps its space
        self.logbox = tk.Text(root, bg="#1c1c1c", fg="#e6e6e6", relief="flat", height=11, wrap="word",
                              font=("Cascadia Mono", 9), state="disabled", padx=10, pady=8, borderwidth=0)
        sb = ttk.Scrollbar(root, command=self.logbox.yview)
        self.logbox.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y", pady=(6, 0))
        self.logbox.pack(side="bottom", fill="both", expand=True, pady=(6, 0))
        for tag, col in (("ok", "#6ccb5f"), ("err", "#ff7b72"), ("muted", "#8b8b8b")):
            self.logbox.tag_config(tag, foreground=col)
        info = ttk.Frame(root); info.pack(side="bottom", fill="x")
        self.prog_text = ttk.Label(info, text="", foreground="#9a9a9a"); self.prog_text.pack(side="left")
        self.status = ttk.Label(info, text="Idle"); self.status.pack(side="right")
        self.prog = ttk.Progressbar(root, mode="determinate", maximum=100)
        self.prog.pack(side="bottom", fill="x", pady=(8, 4))
        bar = ttk.Frame(root); bar.pack(side="bottom", fill="x", pady=(12, 0))
        self.run_btn = ttk.Button(bar, text="Start", style="Accent.TButton", width=14, command=self.start)
        self.run_btn.pack(side="left")
        self.stop_btn = ttk.Button(bar, text="Stop", width=10, command=self.stop, state="disabled")
        self.stop_btn.pack(side="left", padx=8)
        self.open_btn = ttk.Button(bar, text="Show output", command=self.show_output, state="disabled")
        self.open_btn.pack(side="left")

        c = self.card(root, "Account")
        self.entry(c, 0, "Roblox cookie", "cookie", secret=True)
        self.entry(c, 1, "API key", "api", secret=True)
        ttk.Checkbutton(c, text="Show secrets", variable=self.show, command=self._toggle).grid(row=2, column=1, sticky="w", pady=(4, 0))
        ttk.Label(c, text="Kept in memory only and never saved. Use an alt account.", foreground="#9a9a9a").grid(row=3, column=1, sticky="w")

        c = self.card(root, "Files")
        self.entry(c, 0, "Place file", "file", browse=self._pick_in)
        self.entry(c, 1, "Output file", "out", browse=self._pick_out)

        c = self.card(root, "Options")
        self.entry(c, 0, "Group ID", "group", width=16)
        self.entry(c, 1, "Threads", "threads", width=16)
        ttk.Label(c, text="Only upload").grid(row=2, column=0, sticky="nw", pady=8)
        f = ttk.Frame(c); f.grid(row=2, column=1, columnspan=2, sticky="w")
        for i, t in enumerate(TYPES):
            ttk.Checkbutton(f, text=t.capitalize(), variable=self.types[t]).grid(row=i // 3, column=i % 3, sticky="w", padx=(0, 22), pady=2)
        ttk.Label(c, text="Nothing ticked = everything.", foreground="#9a9a9a").grid(row=3, column=1, sticky="w")
        f = ttk.Frame(c); f.grid(row=4, column=1, columnspan=2, sticky="w", pady=(10, 0))
        for i, (key, text) in enumerate((("unformatted", "Scan unformatted IDs"), ("names", "Fetch original names"), ("dry", "Dry run (upload nothing)"))):
            ttk.Checkbutton(f, text=text, variable=self.flags[key], style="Switch.TCheckbutton").grid(row=i, column=0, sticky="w", pady=2)

    def card(self, parent, title):
        f = ttk.LabelFrame(parent, text=title, padding=14)
        f.pack(fill="x", pady=(0, 12))
        f.columnconfigure(1, weight=1)
        return f

    def entry(self, card, r, label, key, browse=None, secret=False, width=None):
        ttk.Label(card, text=label).grid(row=r, column=0, sticky="w", padx=(0, 16), pady=5)
        e = ttk.Entry(card, textvariable=self.v[key], show="•" if secret else "", width=width or 40)
        e.grid(row=r, column=1, sticky="w" if width else "ew", pady=5)
        if secret:
            self.__dict__.setdefault("secrets", []).append(e)
        if browse:
            ttk.Button(card, text="Browse…", command=browse).grid(row=r, column=2, padx=(8, 0))

    def _toggle(self):
        for e in self.secrets:
            e.configure(show="" if self.show.get() else "•")

    def log(self, text, tag=None):
        self.logbox.configure(state="normal")
        self.logbox.insert("end", text, tag or "")
        self.logbox.see("end")
        self.logbox.configure(state="disabled")

    # ---------- file pickers / settings ----------
    def _pick_in(self):
        p = filedialog.askopenfilename(filetypes=[("Roblox files", "*.rbxl *.rbxlx *.rbxm *.rbxmx"), ("All files", "*.*")])
        if p:
            self.v["file"].set(p)
            base, ext = os.path.splitext(p)
            self.v["out"].set(f"{base}_output{ext}")

    def _pick_out(self):
        p = filedialog.asksaveasfilename(defaultextension=".rbxl", filetypes=[("Roblox files", "*.rbxl *.rbxlx *.rbxm *.rbxmx")])
        if p:
            self.v["out"].set(p)

    def _load(self):
        try:
            d = json.load(open(SETTINGS, encoding="utf-8"))
            for k in ("file", "out", "group", "threads"):
                self.v[k].set(d.get(k, self.v[k].get()))
            for t in TYPES:
                self.types[t].set(t in d.get("types", []))
            for k in self.flags:
                self.flags[k].set(d.get(k, False))
        except Exception:
            pass

    def _save(self):  # never stores cookie or API key
        try:
            os.makedirs(os.path.dirname(SETTINGS), exist_ok=True)
            d = {k: self.v[k].get() for k in ("file", "out", "group", "threads")}
            d["types"] = [t for t, v in self.types.items() if v.get()]
            d.update({k: v.get() for k, v in self.flags.items()})
            json.dump(d, open(SETTINGS, "w", encoding="utf-8"))
        except Exception:
            pass

    def show_output(self):
        p = self.v["out"].get().strip()
        if os.name == "nt" and p:
            subprocess.Popen(["explorer", "/select,", os.path.normpath(p)])

    # ---------- running ----------
    def build_cmd(self):
        g = {k: x.get().strip() for k, x in self.v.items()}
        dry = self.flags["dry"].get()
        if not (g["cookie"] and g["api"] and g["file"]):
            raise ValueError("Cookie, API key and place file are required.")
        if not os.path.isfile(g["file"]):
            raise ValueError("The place file does not exist.")
        if not g["out"] and not dry:
            raise ValueError("Choose an output file so your original is never overwritten.")
        if g["group"] and not g["group"].isdigit():
            raise ValueError("Group ID must be a number.")
        if not g["threads"].isdigit() or int(g["threads"]) < 1:
            raise ValueError("Threads must be a positive number.")
        exe = find_engine()
        if not exe:
            raise ValueError(f"{ENGINE} was not found next to the app.")
        cmd = [exe, "--cookie", g["cookie"], "--api-key", g["api"], "--file", g["file"], "--threads", g["threads"]]
        if g["out"]: cmd += ["--output", g["out"]]
        if g["group"]: cmd += ["--group", g["group"]]
        chosen = [t for t, x in self.types.items() if x.get()]
        if chosen: cmd += ["--only", ",".join(chosen)]
        if self.flags["unformatted"].get(): cmd.append("--unformatted-ids")
        if self.flags["names"].get(): cmd.append("--fetch-names")
        if dry: cmd.append("--dry-run")
        return cmd

    def start(self):
        try:
            cmd = self.build_cmd()
        except ValueError as e:
            messagebox.showerror("Missing info", str(e)); return
        self._save()
        secrets = [self.v["cookie"].get().strip(), self.v["api"].get().strip()]
        shown = " ".join("***" if a in secrets else (f'"{a}"' if " " in a else a) for a in cmd[1:])
        self.log(f"\n▶ {os.path.basename(cmd[0])} {shown}\n", "muted")
        try:
            self.proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                                         errors="replace", creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), cwd=os.path.dirname(cmd[0]))
        except OSError as e:
            self.log(f"Could not launch the engine: {e}\n", "err"); return
        self.run_btn.configure(state="disabled"); self.stop_btn.configure(state="normal"); self.open_btn.configure(state="disabled")
        self.prog.configure(mode="indeterminate"); self.prog.start(12)
        self.prog_text.configure(text="Scanning…"); self.t0 = time.time(); self.p0 = None
        self._tick()
        threading.Thread(target=self._reader, args=(self.proc, secrets), daemon=True).start()

    def _tick(self):
        if self.proc:
            self.status.configure(text=f"Running · {fmt(time.time() - self.t0)}")
            self.after(1000, self._tick)

    def _reader(self, proc, secrets):
        for line in proc.stdout:
            line = ANSI.sub("", line)
            for s in secrets:
                if s: line = line.replace(s, "***")
            self.q.put(("line", line))
        self.q.put(("done", proc.wait()))

    def _progress(self, n, total):
        if self.p0 is None:
            self.p0 = (time.time(), n)
            self.prog.stop(); self.prog.configure(mode="determinate", maximum=total)
        self.prog.configure(value=n)
        t, n0 = self.p0
        rate = (n - n0) / (time.time() - t) if time.time() > t and n > n0 else 0
        eta = f" · about {fmt((total - n) / rate)} left" if rate else ""
        self.prog_text.configure(text=f"{n} / {total}  ({n * 100 / total:.1f}%){eta}")

    def _drain(self):
        try:
            while True:
                kind, val = self.q.get_nowait()
                if kind == "line":
                    m = PROG.search(val)
                    if m and int(m.group(2)) > 0:
                        self._progress(int(m.group(1)), int(m.group(2)))
                    low = val.lower()
                    self.log(val, "err" if ("error" in low or "failed" in low) else None)
                else:
                    ok = val == 0
                    self.log("\n✔ Finished\n" if ok else f"\n✖ Stopped (exit code {val})\n", "ok" if ok else "err")
                    self.status.configure(text="Done" if ok else "Stopped")
                    self.prog.stop()
                    if ok and self.p0:
                        self.prog.configure(mode="determinate", value=self.prog["maximum"])
                    self.run_btn.configure(state="normal"); self.stop_btn.configure(state="disabled")
                    self.open_btn.configure(state="normal" if ok and os.path.isfile(self.v["out"].get().strip()) else "disabled")
                    self.proc = None
        except queue.Empty:
            pass
        self.after(100, self._drain)

    def stop(self):
        if self.proc:
            self.proc.terminate()
            self.log("Stopping…\n", "muted")

    def _close(self):
        if self.proc and not messagebox.askyesno("Still running", "A run is in progress. Stop it and exit?"):
            return
        if self.proc:
            self.proc.terminate()
        self._save()
        self.destroy()


if __name__ == "__main__":
    App().mainloop()
