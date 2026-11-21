import tkinter as tk
from pathlib import Path
from threading import Thread
from tkinter import filedialog, messagebox

from config import AUDIO1, AUDIO2, CUTS_JSON, OUTPUT, VIDEO, VIDEO2
from pipeline import process_project


class PodPyApp:
    def __init__(self, root):
        self.root = root
        root.title("PodPy — Podcast Video Editor")
        root.minsize(760, 650)

        self.audio_mode = tk.StringVar(value="separate_audio")
        self.output_mode = tk.StringVar(value="render")
        self.fields = {}
        self._build_form()
        self._update_audio_fields()
        self._update_output_fields()

    def _build_form(self):
        container = tk.Frame(self.root, padx=18, pady=18)
        container.pack(fill="both", expand=True)
        container.columnconfigure(1, weight=1)

        tk.Label(
            container,
            text="Choose two camera videos and an output workflow.",
            font=("TkDefaultFont", 12, "bold"),
        ).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 10))

        tk.Label(container, text="Audio source", font=("TkDefaultFont", 10, "bold")).grid(
            row=1, column=0, columnspan=3, sticky="w"
        )
        tk.Radiobutton(
            container, text="Use two separate audio tracks", variable=self.audio_mode,
            value="separate_audio", command=self._update_audio_fields,
        ).grid(row=2, column=0, columnspan=3, sticky="w")
        tk.Radiobutton(
            container, text="Videos only (use embedded audio)", variable=self.audio_mode,
            value="videos_only", command=self._update_audio_fields,
        ).grid(row=3, column=0, columnspan=3, sticky="w", pady=(0, 8))

        tk.Label(container, text="Output", font=("TkDefaultFont", 10, "bold")).grid(
            row=4, column=0, columnspan=3, sticky="w"
        )
        for row, label, value in (
            (5, "Render MP4", "render"),
            (6, "Create Resolve XML only", "resolve"),
            (7, "Both MP4 and Resolve XML", "both"),
        ):
            tk.Radiobutton(
                container, text=label, variable=self.output_mode, value=value,
                command=self._update_output_fields,
            ).grid(row=row, column=0, columnspan=3, sticky="w")

        rows = [
            ("Video 1 (sync reference)", "video1", VIDEO, "file"),
            ("Video 2", "video2", VIDEO2, "file"),
            ("Audio track 1", "audio1", AUDIO1, "file"),
            ("Audio track 2", "audio2", AUDIO2, "file"),
            ("Rendered MP4", "output", OUTPUT, "save_video"),
            ("Resolve XML", "resolve_xml", "podpy_timeline.fcpxml", "save_xml"),
            ("Cut-list JSON", "cuts", CUTS_JSON, "save_json"),
        ]
        self.audio_widgets = []
        self.output_widgets = {"render": [], "resolve": []}
        for row, (label, key, initial, picker) in enumerate(rows, start=8):
            label_widget = tk.Label(container, text=label)
            label_widget.grid(row=row, column=0, sticky="w", padx=(0, 10), pady=4)
            value = tk.StringVar(value=initial)
            self.fields[key] = value
            entry = tk.Entry(container, textvariable=value)
            entry.grid(row=row, column=1, sticky="ew", pady=4)
            button = tk.Button(
                container, text="Browse…",
                command=lambda field=key, kind=picker: self._browse(field, kind),
            )
            button.grid(row=row, column=2, padx=(8, 0), pady=4)
            widgets = (label_widget, entry, button)
            if key in ("audio1", "audio2"):
                self.audio_widgets.extend(widgets)
            elif key == "output":
                self.output_widgets["render"].extend(widgets)
            elif key == "resolve_xml":
                self.output_widgets["resolve"].extend(widgets)

        self.process_button = tk.Button(
            container, text="Process", command=self._start_processing
        )
        self.process_button.grid(row=15, column=0, columnspan=3, sticky="ew", pady=(12, 8))
        tk.Label(container, text="Progress").grid(
            row=16, column=0, columnspan=3, sticky="w", pady=(4, 4)
        )
        self.status = tk.StringVar(value="Ready")
        tk.Label(container, textvariable=self.status, anchor="w").grid(
            row=17, column=0, columnspan=3, sticky="ew", pady=(0, 8)
        )
        self.log = tk.Text(container, height=7, wrap="word", state="disabled")
        self.log.grid(row=18, column=0, columnspan=3, sticky="nsew")
        container.rowconfigure(18, weight=1)

    def _update_audio_fields(self):
        state = "normal" if self.audio_mode.get() == "separate_audio" else "disabled"
        for widget in self.audio_widgets:
            widget.configure(state=state)

    def _update_output_fields(self):
        mode = self.output_mode.get()
        render_state = "normal" if mode in ("render", "both") else "disabled"
        resolve_state = "normal" if mode in ("resolve", "both") else "disabled"
        for widget in self.output_widgets["render"]:
            widget.configure(state=render_state)
        for widget in self.output_widgets["resolve"]:
            widget.configure(state=resolve_state)

    def _browse(self, field, kind):
        current = self.fields[field].get()
        initial_dir = str(Path(current).expanduser().parent) if current else str(Path.home())
        if kind == "file":
            selected = filedialog.askopenfilename(
                title="Select media file",
                initialdir=initial_dir,
                filetypes=[
                    ("Media files", "*.mp4 *.mov *.mkv *.avi *.mp3 *.wav *.m4a *.aac *.flac"),
                    ("All files", "*.*"),
                ],
            )
        else:
            options = {
                "save_video": ("Save rendered MP4 as", ".mp4", "MP4 video", "*.mp4"),
                "save_xml": ("Save Resolve XML as", ".fcpxml", "Final Cut Pro XML", "*.fcpxml"),
                "save_json": ("Save camera cut list as", ".json", "JSON files", "*.json"),
            }
            title, extension, filetype, pattern = options[kind]
            selected = filedialog.asksaveasfilename(
                title=title,
                initialdir=initial_dir,
                initialfile=Path(current).name if current else f"podpy_output{extension}",
                defaultextension=extension,
                filetypes=[(filetype, pattern)],
            )
        if selected:
            self.fields[field].set(selected)

    def _append_log(self, message):
        self.log.configure(state="normal")
        self.log.insert("end", message + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")
        self.status.set(message)

    def _start_processing(self):
        values = {key: value.get().strip() for key, value in self.fields.items()}
        audio_mode = self.audio_mode.get()
        output_mode = self.output_mode.get()
        missing = [key for key in ("video1", "video2", "cuts") if not values[key]]
        if audio_mode == "separate_audio":
            missing.extend(key for key in ("audio1", "audio2") if not values[key])
        if output_mode in ("render", "both") and not values["output"]:
            missing.append("output")
        if output_mode in ("resolve", "both") and not values["resolve_xml"]:
            missing.append("resolve_xml")
        if missing:
            messagebox.showerror(
                "Missing file or destination",
                "Select both videos and the required audio/output destinations.",
            )
            return

        self.process_button.configure(state="disabled")
        self._append_log("Starting PodPy…")

        def report(message):
            self.root.after(0, self._append_log, message)

        def worker():
            try:
                process_project(
                    video1=values["video1"],
                    video2=values["video2"],
                    audio1=None if audio_mode == "videos_only" else values["audio1"],
                    audio2=None if audio_mode == "videos_only" else values["audio2"],
                    output=values["output"] or None,
                    cuts_json=values["cuts"],
                    resolve_xml=values["resolve_xml"] or None,
                    output_mode=output_mode,
                    on_progress=report,
                )
            except Exception as exc:
                report(f"Error: {exc}")
                self.root.after(
                    0, lambda error=exc: messagebox.showerror("Processing failed", str(error))
                )
            finally:
                self.root.after(0, lambda: self.process_button.configure(state="normal"))

        Thread(target=worker, daemon=True).start()


def main():
    root = tk.Tk()
    PodPyApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
