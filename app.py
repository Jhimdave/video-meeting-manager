"""Meeting video -> transcript -> AI summary -> Notion: paste a video path (or folder), click the button."""
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import config
from paths import APP_DIR
import pipeline

import os
import sys


os.chdir(APP_DIR)


def _icon_path() -> str:
    """icon.ico: bundled inside the exe (PyInstaller --add-data) or next to app.py when run from source."""
    base = getattr(sys, "_MEIPASS", str(APP_DIR))
    return os.path.join(base, "icon.ico")


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Meeting to Notion")
        try:  # window + taskbar icon
            self.iconbitmap(default=_icon_path())
        except Exception:
            pass
        self.geometry("760x640")
        self.q: queue.Queue = queue.Queue()
        self.vars = {k: tk.StringVar() for k in ("path", "title", "video_link", "time_finished")}
        self._build()
        self.after(150, self._drain)

    def _build(self):
        pad = {"padx": 10, "pady": 4}
        frm = ttk.Frame(self)
        frm.pack(fill="x", padx=6, pady=6)
        frm.columnconfigure(1, weight=1)

        ttk.Label(frm, text="Meeting video file or folder *").grid(row=0, column=0, sticky="w", **pad)
        ttk.Entry(frm, textvariable=self.vars["path"]).grid(row=0, column=1, sticky="ew", **pad)
        btns = ttk.Frame(frm)
        btns.grid(row=0, column=2, **pad)
        ttk.Button(btns, text="File...", command=self._pick_file).pack(side="left", padx=2)
        ttk.Button(btns, text="Folder...", command=self._pick_dir).pack(side="left", padx=2)

        rows = [
            ("Title (blank = AI title)", "title", ""),
            ("Video Link", "video_link", "https://..."),
            ("Time finished (blank = file date)", "time_finished", "YYYY-MM-DD HH:MM"),
        ]
        for i, (label, key, hint) in enumerate(rows, start=1):
            ttk.Label(frm, text=label).grid(row=i, column=0, sticky="w", **pad)
            ttk.Entry(frm, textvariable=self.vars[key]).grid(row=i, column=1, columnspan=2, sticky="ew", **pad)
            if hint:
                ttk.Label(frm, text=hint, foreground="#888").grid(row=i, column=3, sticky="w")

        self.refresh = tk.BooleanVar()
        ttk.Checkbutton(self, text="Refresh Notion people/projects cache now (it also refreshes weekly)",
                        variable=self.refresh).pack(anchor="w", padx=16, pady=(8, 0))
        self.btn = ttk.Button(self, text="Transcribe, Summarize and Add to Notion", command=self._start)
        self.btn.pack(fill="x", padx=16, pady=(8, 4), ipady=8)
        self.bar = ttk.Progressbar(self, mode="indeterminate")
        self.bar.pack(fill="x", padx=16, pady=4)

        self.log = tk.Text(self, height=18, state="disabled", wrap="word", font=("Consolas", 10))
        self.log.pack(fill="both", expand=True, padx=16, pady=(4, 12))

    def _pick_file(self):
        p = filedialog.askopenfilename(title="Select meeting video",
                                       filetypes=[("Video/Audio", "*.mp4 *.mov *.mkv *.webm *.avi *.m4v *.mp3 *.m4a *.wav"), ("All", "*.*")])
        if p:
            self.vars["path"].set(p)

    def _pick_dir(self):
        p = filedialog.askdirectory(title="Select folder with meeting videos")
        if p:
            self.vars["path"].set(p)

    def _write(self, text: str):
        self.log.configure(state="normal")
        self.log.insert("end", text + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _drain(self):
        try:
            while True:
                kind, payload = self.q.get_nowait()
                if kind == "log":
                    self._write(payload)
                elif kind == "done":
                    self.bar.stop()
                    self.btn.configure(state="normal")
                    ok = len(payload)
                    self._write(f"\nFinished. {ok} page(s) created in Notion.")
                    if ok:
                        messagebox.showinfo("Done", f"{ok} meeting page(s) added to Notion.")
        except queue.Empty:
            pass
        self.after(150, self._drain)

    def _start(self):
        path = self.vars["path"].get().strip()
        if not path:
            messagebox.showwarning("Missing", "Enter the video file or folder path first.")
            return
        s = config.load_settings()
        errors = config.validate(s)
        if errors:
            messagebox.showerror("Check your .env", "\n".join(errors))
            return
        form = {k: v.get() for k, v in self.vars.items() if k != "path"}
        form["refresh_cache"] = self.refresh.get()
        self.btn.configure(state="disabled")
        self.bar.start(12)
        self._write("Starting...")

        def work():
            try:
                urls = pipeline.run(path, form, s, lambda m: self.q.put(("log", m)))
            except Exception as e:
                self.q.put(("log", f"ERROR: {e}"))
                urls = []
            self.q.put(("done", urls))

        threading.Thread(target=work, daemon=True).start()


if __name__ == "__main__":
    App().mainloop()