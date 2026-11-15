"""Asset Replacer - dashboard front end for shibahex/asset-replacer-roblox (native window via pywebview)."""
import base64, ctypes, ctypes.wintypes as wt, json, os, queue, re, subprocess, sys, threading, time
import webview

ENGINE = "animation-replace-roblox" + (".exe" if os.name == "nt" else "")
ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
DIR = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "AssetReplacer")
SETTINGS = os.path.join(DIR, "settings.json")
FD = getattr(webview, "FileDialog", None)
OPEN, SAVE = (FD.OPEN, FD.SAVE) if FD else (webview.OPEN_DIALOG, webview.SAVE_DIALOG)
FILTER = ("Roblox files (*.rbxl;*.rbxlx;*.rbxm;*.rbxmx)", "All files (*.*)")


class BLOB(ctypes.Structure):
    _fields_ = [("cbData", wt.DWORD), ("pbData", ctypes.c_void_p)]


def _crypt(data: bytes, encrypt: bool) -> bytes:
    """Windows DPAPI: only this Windows user on this PC can decrypt."""
    buf = ctypes.create_string_buffer(data, len(data))
    src, out = BLOB(len(data), ctypes.cast(buf, ctypes.c_void_p)), BLOB()
    fn = ctypes.windll.crypt32.CryptProtectData if encrypt else ctypes.windll.crypt32.CryptUnprotectData
    if not fn(ctypes.byref(src), None, None, None, None, 0, ctypes.byref(out)):
        raise OSError("DPAPI failed")
    res = ctypes.string_at(out.pbData, out.cbData)
    ctypes.windll.kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    ctypes.windll.kernel32.LocalFree(out.pbData)
    return res


def protect(s): return base64.b64encode(_crypt(s.encode(), True)).decode() if s else ""
def unprotect(s): return _crypt(base64.b64decode(s), False).decode() if s else ""


def find_engine():
    for d in (getattr(sys, "_MEIPASS", ""), os.path.dirname(os.path.abspath(sys.argv[0])), os.getcwd()):
        p = os.path.join(d, ENGINE)
        if d and os.path.isfile(p):
            return p


class Api:
    def __init__(self):
        self._win, self._proc, self._q = None, None, queue.Queue()

    # ----- settings -----
    def init(self):
        try:
            d = json.load(open(SETTINGS, encoding="utf-8"))
        except Exception:
            return {}
        if d.get("remember"):
            try:
                d["cookie"], d["api"] = unprotect(d.get("cookie", "")), unprotect(d.get("api", ""))
            except Exception:
                d["cookie"] = d["api"] = ""
        else:
            d.pop("cookie", None); d.pop("api", None)
        return d

    def save(self, c):
        d = {k: c.get(k, "") for k in ("file", "out", "group", "threads")}
        d.update(types=c.get("types", []), flags=c.get("flags", {}), remember=bool(c.get("remember")))
        try:
            if d["remember"]:
                d["cookie"], d["api"] = protect(c.get("cookie", "")), protect(c.get("api", ""))
            os.makedirs(DIR, exist_ok=True)
            json.dump(d, open(SETTINGS, "w", encoding="utf-8"))
        except Exception:
            pass

    # ----- dialogs -----
    def pick(self, kind, current=""):
        if kind == "in":
            r = self._win.create_file_dialog(OPEN, file_types=FILTER)
        else:
            r = self._win.create_file_dialog(SAVE, save_filename="output.rbxl", file_types=FILTER)
        r = r[0] if isinstance(r, (list, tuple)) and r else r
        return r or ""

    def reveal(self, path):
        if os.name == "nt" and path and os.path.isfile(path):
            subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])

    # ----- engine -----
    def run(self, c, dry=False):
        if self._proc:
            return {"error": "A run is already in progress."}
        g = {k: str(c.get(k, "")).strip() for k in ("cookie", "api", "file", "out", "group", "threads")}
        exe = find_engine()
        if not exe: return {"error": f"{ENGINE} was not found next to the app."}
        if not (g["cookie"] and g["api"] and g["file"]): return {"error": "Cookie, API key and place file are required."}
        if not os.path.isfile(g["file"]): return {"error": "The place file does not exist."}
        if not g["out"] and not dry: return {"error": "Choose an output file so your original is never overwritten."}
        if g["group"] and not g["group"].isdigit(): return {"error": "Group ID must be a number."}
        if not g["threads"].isdigit() or int(g["threads"]) < 1: return {"error": "Threads must be a positive number."}
        cmd = [exe, "--cookie", g["cookie"], "--api-key", g["api"], "--file", g["file"], "--threads", g["threads"]]
        if g["out"]: cmd += ["--output", g["out"]]
        if g["group"]: cmd += ["--group", g["group"]]
        if c.get("types"): cmd += ["--only", ",".join(c["types"])]
        fl = c.get("flags", {})
        if fl.get("unformatted"): cmd.append("--unformatted-ids")
        if fl.get("names"): cmd.append("--fetch-names")
        if dry: cmd.append("--dry-run")
        self.save(c)
        secrets = [g["cookie"], g["api"]]
        shown = " ".join("***" if a in secrets else (f'"{a}"' if " " in a else a) for a in cmd[1:])
        try:
            self._proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                                          errors="replace", creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), cwd=os.path.dirname(exe))
        except OSError as e:
            return {"error": f"Could not launch the engine: {e}"}
        threading.Thread(target=self._read, args=(self._proc, secrets), daemon=True).start()
        return {"cmd": os.path.basename(exe) + " " + shown}

    def stop(self):
        if self._proc:
            self._proc.terminate()

    def _read(self, proc, secrets):
        for line in proc.stdout:
            line = ANSI.sub("", line)
            for s in secrets:
                if s: line = line.replace(s, "***")
            self._q.put({"k": "line", "t": line})
        self._q.put({"k": "done", "code": proc.wait()})
        self._proc = None

    def _flush(self):  # batch events so a chatty scan can't flood the UI
        try:
            hwnd = self._win.native.Handle.ToInt64()
            ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(ctypes.c_int(1)), 4)
        except Exception:
            pass
        while True:
            time.sleep(0.15)
            batch = []
            while not self._q.empty():
                batch.append(self._q.get())
            if batch:
                self._win.evaluate_js(f"window.onEvents({json.dumps(batch)})")


if __name__ == "__main__":
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    api = Api()
    api._win = webview.create_window("Asset Replacer", os.path.join(base, "ui", "index.html"), js_api=api,
                                     width=1260, height=840, min_size=(1100, 720), background_color="#14151a")
    webview.start(api._flush)
