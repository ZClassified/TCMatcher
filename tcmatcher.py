import os
import sys
import subprocess
import threading
import shutil
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox
import customtkinter as ctk

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

def get_timecode(filepath):
    """Reads the timecode of a video file using ffprobe."""
    command = [
        "ffprobe",
        "-v", "error",
        "-show_entries", "stream_tags=timecode:format_tags=timecode",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(filepath)
    ]
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=True)
        timecodes = result.stdout.strip().split('\n')
        for tc in timecodes:
            if tc and len(tc) >= 8: 
                return tc
    except subprocess.CalledProcessError:
        pass
    return None

def process_files(hd_dir, fourk_dir, temp_dir=None, check_only=False):
    hd_path = Path(hd_dir)
    fourk_path = Path(fourk_dir)

    video_extensions = {'.mp4', '.mov', '.mxf', '.avi', '.m4v'}
    processed_4k_files = set()
    
    total_checked = 0
    identical_tc = 0
    different_tc = 0
    differing_files = []

    for hd_file in hd_path.rglob('*'):
        if hd_file.is_file() and hd_file.suffix.lower() in video_extensions:
            rel_path = hd_file.relative_to(hd_path)
            expected_4k_dir = fourk_path / rel_path.parent

            if not expected_4k_dir.exists():
                print(f"Skipping: Target folder {expected_4k_dir} does not exist.")
                continue

            fourk_file = None
            for f in expected_4k_dir.iterdir():
                if f.is_file() and f.stem == hd_file.stem and f.suffix.lower() in video_extensions:
                    fourk_file = f
                    break

            if not fourk_file:
                print(f"Not found: No 4K counterpart for {hd_file.name}")
                continue
            
            processed_4k_files.add(fourk_file.resolve())

            tc = get_timecode(hd_file)
            if not tc:
                tc = "00:00:00:00"
                if not check_only:
                    print(f"[Fallback] No TC found in {hd_file.name}. Setting 00:00:00:00.")

            fourk_tc = get_timecode(fourk_file)
            
            if check_only:
                total_checked += 1
                if fourk_tc == tc:
                    identical_tc += 1
                else:
                    different_tc += 1
                    differing_files.append((fourk_file.relative_to(fourk_path), tc, fourk_tc))
                continue

            if fourk_tc == tc:
                print(f"[{fourk_file.name}] Timecode is already identical ({tc}). Skipping...")
                continue

            print(f"Copying Timecode [{tc}] to 4K file: {fourk_file.name}...")
            
            if temp_dir:
                temp_output = Path(temp_dir) / (fourk_file.stem + '.temp' + fourk_file.suffix)
            else:
                temp_output = fourk_file.with_suffix('.temp' + fourk_file.suffix)
            
            ffmpeg_cmd = [
                "ffmpeg",
                "-y",
                "-i", str(fourk_file),
                "-map", "0",
                "-map_metadata", "0",
                "-map_metadata:s:v", "0:s:v",
                "-map_metadata:s:a", "0:s:a",
                "-c", "copy",
                "-timecode", tc,
                str(temp_output)
            ]
            
            server_temp = None
            try:
                subprocess.run(ffmpeg_cmd, capture_output=True, text=True, check=True)
                
                orig_size = fourk_file.stat().st_size
                temp_size = temp_output.stat().st_size
                
                if temp_size < orig_size * 0.98:
                    print(f"[RED]-> ABORT for {fourk_file.name}: New file is unusually small! (Original: {orig_size}, New: {temp_size})\n")
                    temp_output.unlink(missing_ok=True)
                    continue

                new_tc = get_timecode(temp_output)
                if new_tc != tc:
                    print(f"[RED]-> ABORT for {fourk_file.name}: Timecode was not written correctly! (Expected: {tc}, Read: {new_tc})\n")
                    temp_output.unlink(missing_ok=True)
                    continue

                if temp_dir:
                    print("Pushing verified file safely back to the server...")
                    server_temp = fourk_file.with_suffix('.network_temp' + fourk_file.suffix)
                    shutil.copy2(temp_output, server_temp)
                    server_temp.replace(fourk_file)
                    temp_output.unlink(missing_ok=True)
                    print(f"[GREEN]-> Success! (Cached via SSD & verified)\n")
                else:
                    temp_output.replace(fourk_file)
                    print(f"[GREEN]-> Success! (Size & TC verified)\n")
            except subprocess.CalledProcessError as e:
                print(f"[RED]-> ERROR (FFmpeg) for {fourk_file.name}: {e.stderr}\n")
                temp_output.unlink(missing_ok=True)
            except Exception as e:
                print(f"[RED]-> ERROR (System/Access) for {fourk_file.name}: {str(e)}\n")
                temp_output.unlink(missing_ok=True)
                if server_temp:
                    server_temp.unlink(missing_ok=True)

    print("\n--- Check for untouched 4K files ---")
    missing_hd = []
    for f in fourk_path.rglob('*'):
        if f.is_file() and f.suffix.lower() in video_extensions:
            if f.resolve() not in processed_4k_files:
                missing_hd.append(f)
    
    if missing_hd:
        print("[RED]WARNING: No HD counterpart found for the following 4K files:")
        for f in missing_hd:
            print(f"[RED]❌ {f.relative_to(fourk_path)}")
        print("\n")
    else:
        print("[GREEN]Perfect: All 4K files had a matching HD counterpart.\n")

    if check_only:
        print("--- CHECK REPORT ---")
        print(f"Total checked: {total_checked}")
        print(f"[GREEN]Identical timecodes: {identical_tc}")
        if different_tc > 0:
            print(f"[RED]Differing timecodes: {different_tc}")
            print("\nThe following files have differing timecodes:")
            for f_rel, expected_tc, actual_tc in differing_files:
                print(f"[RED]- {f_rel} (HD: {expected_tc} | 4K: {actual_tc})")
        else:
            print(f"[GREEN]Differing timecodes: 0 (Everything perfectly in sync!)")
        print("-------------------\n")

class PrintLogger:
    def __init__(self, text_widget):
        self.text_widget = text_widget

    def write(self, message):
        def _insert():
            self.text_widget.configure(state="normal")
            if "[RED]" in message:
                self.text_widget.insert(tk.END, message.replace("[RED]", ""), "error")
            elif "[GREEN]" in message:
                self.text_widget.insert(tk.END, message.replace("[GREEN]", ""), "success")
            else:
                self.text_widget.insert(tk.END, message)
            self.text_widget.see(tk.END)
            self.text_widget.configure(state="disabled")
        
        self.text_widget.after(0, _insert)

    def flush(self):
        pass

class TCMatcherApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        
        self.i18n = {
            "DE": {
                "window_title": "TCMatcher",
                "tab_transfer": "Timecode Übertragen",
                "tab_check": "Timecodes Prüfen",
                "hd_label": "Original Material Ordner (Quelle):",
                "4k_label": "Bearbeitetes Material Ordner (Ziel):",
                "temp_label": "Lokaler SSD Cache (Optional):",
                "browse_btn": "...",
                "start_btn_transfer": "TIMECODE ÜBERTRAGUNG STARTEN",
                "start_btn_check": "TIMECODES PRÜFEN (DRY-RUN)",
                "log_label": "Log-Ausgabe:",
                "info_btn": "Info & Anleitung",
                "info_title": "Information",
                "info_text": "TCMatcher Anleitung:\n\n1. Original Material Ordner: Wähle den Ordner mit den Originaldateien (mit korrektem Timecode).\n2. Bearbeitetes Material Ordner: Wähle den Ordner mit den veränderten Dateien. Die Dateinamen und Ordnerstruktur müssen exakt mit dem Original-Ordner übereinstimmen!\n3. SSD Cache: Wenn deine Dateien auf einem Netzwerkspeicher liegen, wähle einen lokalen SSD-Ordner. TCMatcher kopiert die Dateien zum Bearbeiten auf die SSD und schiebt sie danach sicher zurück.\n\nPrüfen (Dry-Run):\nSimuliert den Vorgang und zeigt, welche Dateien abweichende Timecodes haben, ohne etwas zu verändern.\n\n---\nCredits:\nErstellt mit Python & CustomTkinter.\nVideoverarbeitung durch FFmpeg.",
                "lang_label": "Sprache / Language:",
                "err_deps_title": "Fehlende Abhängigkeit",
                "err_deps_msg": "Das Tool '{}' wurde nicht gefunden.\nBitte installiere FFmpeg und füge es dem System-PATH hinzu.",
                "err_paths_title": "Fehlende Pfade",
                "err_paths_msg": "Bitte wähle sowohl den Original- als auch den Bearbeiteten-Ordner aus.",
                "err_exist_title": "Fehler",
                "err_exist_msg": "Ein ausgewählter Ordner existiert nicht.",
                "done_title": "Fertig",
                "done_check_msg": "Die Timecode-Prüfung wurde abgeschlossen.",
                "done_trans_msg": "Die Timecode-Übertragung wurde abgeschlossen."
            },
            "EN": {
                "window_title": "TCMatcher",
                "tab_transfer": "Transfer Timecode",
                "tab_check": "Check Timecodes",
                "hd_label": "Original Material Folder (Source):",
                "4k_label": "Processed Material Folder (Destination):",
                "temp_label": "Local SSD Cache (Optional):",
                "browse_btn": "...",
                "start_btn_transfer": "START TIMECODE TRANSFER",
                "start_btn_check": "CHECK TIMECODES (DRY-RUN)",
                "log_label": "Log Output:",
                "info_btn": "Info & Manual",
                "info_title": "Information",
                "info_text": "TCMatcher Manual:\n\n1. Original Material Folder: Select the folder with the original files (containing correct timecode).\n2. Processed Material Folder: Select the folder with the modified files. Filenames and folder structure must match the Original folder exactly!\n3. SSD Cache: If your files are on a network drive, select a local SSD folder. TCMatcher will process the files locally and safely push them back.\n\nCheck (Dry-Run):\nSimulates the process and shows which files have differing timecodes without modifying anything.\n\n---\nCredits:\nBuilt with Python & CustomTkinter.\nVideo processing powered by FFmpeg.",
                "lang_label": "Sprache / Language:",
                "err_deps_title": "Missing Dependency",
                "err_deps_msg": "The tool '{}' was not found.\nPlease install FFmpeg and add it to the system PATH.",
                "err_paths_title": "Missing Paths",
                "err_paths_msg": "Please select both the Original and Processed folders.",
                "err_exist_title": "Error",
                "err_exist_msg": "A selected folder does not exist.",
                "done_title": "Done",
                "done_check_msg": "The timecode check has been completed.",
                "done_trans_msg": "The timecode transfer has been completed."
            }
        }
        
        self.current_lang = "EN"
        self.title(self.i18n[self.current_lang]["window_title"])
        self.geometry("900x650")
        self.minsize(800, 500)
        
        self.hd_var = tk.StringVar()
        self.fourk_var = tk.StringVar()
        self.temp_var = tk.StringVar()
        
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1) # For log area
        
        self.setup_ui()
        self.show_tab("transfer")
        
        self.log_text.tag_config("error", foreground="#ff4d4d")
        self.log_text.tag_config("success", foreground="#00cc66")
        sys.stdout = PrintLogger(self.log_text)

    def setup_ui(self):
        # Sidebar
        self.sidebar = ctk.CTkFrame(self, width=200, corner_radius=0)
        self.sidebar.grid(row=0, column=0, rowspan=2, sticky="nsew")
        self.sidebar.grid_rowconfigure(3, weight=1)

        self.btn_tab_transfer = ctk.CTkButton(self.sidebar, text=self.i18n[self.current_lang]["tab_transfer"], 
                                       command=lambda: self.show_tab("transfer"), corner_radius=0, height=40)
        self.btn_tab_transfer.pack(side="top", fill="x", padx=0, pady=(20, 0))

        self.btn_tab_check = ctk.CTkButton(self.sidebar, text=self.i18n[self.current_lang]["tab_check"], 
                                       command=lambda: self.show_tab("check"), corner_radius=0, height=40)
        self.btn_tab_check.pack(side="top", fill="x", padx=0, pady=0)
        
        self.info_button = ctk.CTkButton(self.sidebar, 
                                        text=self.i18n[self.current_lang]["info_btn"], 
                                        command=self.show_info,
                                        fg_color="transparent",
                                        border_width=1,
                                        border_color="#cccccc",
                                        text_color="white")
        self.info_button.pack(side="bottom", padx=20, pady=(0, 20))
        
        self.lang_menu = ctk.CTkComboBox(self.sidebar, 
                                        values=["English", "Deutsch"], 
                                        command=self.change_language,
                                        fg_color="#1f538d",
                                        button_color="#14375e",
                                        border_color="#1f538d")
        self.lang_menu.pack(side="bottom", padx=20, pady=(0, 10))
        self.lang_menu.set("English")
        
        self.lang_label = ctk.CTkLabel(self.sidebar, text=self.i18n[self.current_lang]["lang_label"], font=ctk.CTkFont(size=12, weight="bold"))
        self.lang_label.pack(side="bottom", padx=20, pady=(0, 10))

        # Main Area Frames
        self.frame_transfer = ctk.CTkFrame(self, fg_color="transparent")
        self.frame_check = ctk.CTkFrame(self, fg_color="transparent")

        self.setup_transfer_view()
        self.setup_check_view()
        
        # Log Output Frame
        self.log_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.log_frame.grid(row=1, column=1, padx=20, pady=(0, 20), sticky="nsew")
        self.log_frame.grid_columnconfigure(0, weight=1)
        self.log_frame.grid_rowconfigure(1, weight=1)
        
        self.log_label_widget = ctk.CTkLabel(self.log_frame, text=self.i18n[self.current_lang]["log_label"], font=ctk.CTkFont(size=12, weight="bold"))
        self.log_label_widget.grid(row=0, column=0, sticky="w", pady=(0, 5))
        
        self.log_text = ctk.CTkTextbox(self.log_frame, wrap="word", font=ctk.CTkFont(family="Consolas", size=12), state="disabled")
        self.log_text.grid(row=1, column=0, sticky="nsew")

    def setup_transfer_view(self):
        self.frame_transfer.grid_columnconfigure(0, weight=1)
        
        self.label_hd_t = ctk.CTkLabel(self.frame_transfer, text=self.i18n[self.current_lang]["hd_label"], font=ctk.CTkFont(size=13, weight="bold"))
        self.label_hd_t.grid(row=0, column=0, padx=20, pady=(20, 5), sticky="w")
        
        f1 = ctk.CTkFrame(self.frame_transfer, fg_color="transparent")
        f1.grid(row=1, column=0, padx=20, pady=5, sticky="ew")
        f1.grid_columnconfigure(0, weight=1)
        ctk.CTkEntry(f1, textvariable=self.hd_var, state="readonly").grid(row=0, column=0, sticky="ew", padx=(0, 10))
        self.btn_browse_hd_t = ctk.CTkButton(f1, text=self.i18n[self.current_lang]["browse_btn"], width=40, command=lambda: self.select("hd"))
        self.btn_browse_hd_t.grid(row=0, column=1)

        self.label_4k_t = ctk.CTkLabel(self.frame_transfer, text=self.i18n[self.current_lang]["4k_label"], font=ctk.CTkFont(size=13, weight="bold"))
        self.label_4k_t.grid(row=2, column=0, padx=20, pady=(15, 5), sticky="w")
        
        f2 = ctk.CTkFrame(self.frame_transfer, fg_color="transparent")
        f2.grid(row=3, column=0, padx=20, pady=5, sticky="ew")
        f2.grid_columnconfigure(0, weight=1)
        ctk.CTkEntry(f2, textvariable=self.fourk_var, state="readonly").grid(row=0, column=0, sticky="ew", padx=(0, 10))
        self.btn_browse_4k_t = ctk.CTkButton(f2, text=self.i18n[self.current_lang]["browse_btn"], width=40, command=lambda: self.select("4k"))
        self.btn_browse_4k_t.grid(row=0, column=1)

        self.label_temp_t = ctk.CTkLabel(self.frame_transfer, text=self.i18n[self.current_lang]["temp_label"], font=ctk.CTkFont(size=13, weight="bold"))
        self.label_temp_t.grid(row=4, column=0, padx=20, pady=(15, 5), sticky="w")
        
        f3 = ctk.CTkFrame(self.frame_transfer, fg_color="transparent")
        f3.grid(row=5, column=0, padx=20, pady=5, sticky="ew")
        f3.grid_columnconfigure(0, weight=1)
        ctk.CTkEntry(f3, textvariable=self.temp_var, state="readonly").grid(row=0, column=0, sticky="ew", padx=(0, 10))
        self.btn_browse_temp_t = ctk.CTkButton(f3, text=self.i18n[self.current_lang]["browse_btn"], width=40, command=lambda: self.select("temp"))
        self.btn_browse_temp_t.grid(row=0, column=1)

        self.btn_start_transfer = ctk.CTkButton(self.frame_transfer, text=self.i18n[self.current_lang]["start_btn_transfer"], 
                                      command=lambda: self.start_task(check_only=False), 
                                      fg_color="#28a745", hover_color="#218838",
                                      font=ctk.CTkFont(size=14, weight="bold"), height=50)
        self.btn_start_transfer.grid(row=6, column=0, padx=40, pady=(20, 10), sticky="ew")

    def setup_check_view(self):
        self.frame_check.grid_columnconfigure(0, weight=1)
        
        self.label_hd_c = ctk.CTkLabel(self.frame_check, text=self.i18n[self.current_lang]["hd_label"], font=ctk.CTkFont(size=13, weight="bold"))
        self.label_hd_c.grid(row=0, column=0, padx=20, pady=(20, 5), sticky="w")
        
        f1 = ctk.CTkFrame(self.frame_check, fg_color="transparent")
        f1.grid(row=1, column=0, padx=20, pady=5, sticky="ew")
        f1.grid_columnconfigure(0, weight=1)
        ctk.CTkEntry(f1, textvariable=self.hd_var, state="readonly").grid(row=0, column=0, sticky="ew", padx=(0, 10))
        self.btn_browse_hd_c = ctk.CTkButton(f1, text=self.i18n[self.current_lang]["browse_btn"], width=40, command=lambda: self.select("hd"))
        self.btn_browse_hd_c.grid(row=0, column=1)

        self.label_4k_c = ctk.CTkLabel(self.frame_check, text=self.i18n[self.current_lang]["4k_label"], font=ctk.CTkFont(size=13, weight="bold"))
        self.label_4k_c.grid(row=2, column=0, padx=20, pady=(15, 5), sticky="w")
        
        f2 = ctk.CTkFrame(self.frame_check, fg_color="transparent")
        f2.grid(row=3, column=0, padx=20, pady=5, sticky="ew")
        f2.grid_columnconfigure(0, weight=1)
        ctk.CTkEntry(f2, textvariable=self.fourk_var, state="readonly").grid(row=0, column=0, sticky="ew", padx=(0, 10))
        self.btn_browse_4k_c = ctk.CTkButton(f2, text=self.i18n[self.current_lang]["browse_btn"], width=40, command=lambda: self.select("4k"))
        self.btn_browse_4k_c.grid(row=0, column=1)

        self.btn_start_check = ctk.CTkButton(self.frame_check, text=self.i18n[self.current_lang]["start_btn_check"], 
                                      command=lambda: self.start_task(check_only=True), 
                                      fg_color="#28a745", hover_color="#218838",
                                      font=ctk.CTkFont(size=14, weight="bold"), height=50)
        self.btn_start_check.grid(row=4, column=0, padx=40, pady=(30, 10), sticky="ew")

    def show_tab(self, name):
        self.frame_transfer.grid_forget()
        self.frame_check.grid_forget()
        
        self.btn_tab_transfer.configure(fg_color="transparent")
        self.btn_tab_check.configure(fg_color="transparent")

        if name == "transfer":
            self.frame_transfer.grid(row=0, column=1, padx=20, pady=10, sticky="nsew")
            self.btn_tab_transfer.configure(fg_color=("#3B8ED0", "#1f6aa5"))
        elif name == "check":
            self.frame_check.grid(row=0, column=1, padx=20, pady=10, sticky="nsew")
            self.btn_tab_check.configure(fg_color=("#3B8ED0", "#1f6aa5"))

    def change_language(self, choice):
        self.current_lang = "DE" if choice == "Deutsch" else "EN"
        lang_data = self.i18n[self.current_lang]
        
        self.title(lang_data["window_title"])
        self.btn_tab_transfer.configure(text=lang_data["tab_transfer"])
        self.btn_tab_check.configure(text=lang_data["tab_check"])
        
        self.label_hd_t.configure(text=lang_data["hd_label"])
        self.label_4k_t.configure(text=lang_data["4k_label"])
        self.label_temp_t.configure(text=lang_data["temp_label"])
        
        self.label_hd_c.configure(text=lang_data["hd_label"])
        self.label_4k_c.configure(text=lang_data["4k_label"])
        
        self.btn_browse_hd_t.configure(text=lang_data["browse_btn"])
        self.btn_browse_4k_t.configure(text=lang_data["browse_btn"])
        self.btn_browse_temp_t.configure(text=lang_data["browse_btn"])
        self.btn_browse_hd_c.configure(text=lang_data["browse_btn"])
        self.btn_browse_4k_c.configure(text=lang_data["browse_btn"])
        
        self.btn_start_transfer.configure(text=lang_data["start_btn_transfer"])
        self.btn_start_check.configure(text=lang_data["start_btn_check"])
        
        self.log_label_widget.configure(text=lang_data["log_label"])
        self.info_button.configure(text=lang_data["info_btn"])
        self.lang_label.configure(text=lang_data["lang_label"])

    def show_info(self):
        info_win = ctk.CTkToplevel(self)
        info_win.title(self.i18n[self.current_lang]["info_title"])
        info_win.geometry("500x350")
        info_win.attributes("-topmost", True)
        
        label = ctk.CTkLabel(info_win, text=self.i18n[self.current_lang]["info_text"], 
                             wraplength=450, justify="left", padx=20, pady=20)
        label.pack(expand=True, fill="both")

    def select(self, mode):
        path = filedialog.askdirectory()
        if path:
            norm_path = os.path.normpath(path)
            if mode == "hd":
                self.hd_var.set(norm_path)
            elif mode == "4k":
                self.fourk_var.set(norm_path)
            elif mode == "temp":
                self.temp_var.set(norm_path)

    def check_dependencies(self):
        for tool in ["ffmpeg", "ffprobe"]:
            if shutil.which(tool) is None:
                title = self.i18n[self.current_lang]["err_deps_title"]
                msg = self.i18n[self.current_lang]["err_deps_msg"].format(tool)
                messagebox.showerror(title, msg)
                return False
        return True

    def start_task(self, check_only):
        if not self.check_dependencies():
            return

        hd_dir = self.hd_var.get().strip()
        fourk_dir = self.fourk_var.get().strip()
        temp_dir = self.temp_var.get().strip() or None

        if not hd_dir or not fourk_dir:
            title = self.i18n[self.current_lang]["err_paths_title"]
            msg = self.i18n[self.current_lang]["err_paths_msg"]
            messagebox.showwarning(title, msg)
            return
            
        if not os.path.exists(hd_dir) or not os.path.exists(fourk_dir):
            title = self.i18n[self.current_lang]["err_exist_title"]
            msg = self.i18n[self.current_lang]["err_exist_msg"]
            messagebox.showerror(title, msg)
            return
            
        if not check_only and temp_dir and not os.path.exists(temp_dir):
            title = self.i18n[self.current_lang]["err_exist_title"]
            msg = self.i18n[self.current_lang]["err_exist_msg"]
            messagebox.showerror(title, msg)
            return

        self.btn_start_transfer.configure(state="disabled")
        self.btn_start_check.configure(state="disabled")
        
        self.log_text.configure(state="normal")
        self.log_text.delete(1.0, tk.END)
        self.log_text.configure(state="disabled")
        
        if check_only:
            print("Starting Timecode Check (Dry-Run)...\n")
        else:
            print("Starting Timecode Transfer...\n")
            if temp_dir:
                print(f"Using local SSD cache: {temp_dir}\n")

        threading.Thread(target=self.run_process, args=(hd_dir, fourk_dir, temp_dir, check_only), daemon=True).start()

    def run_process(self, hd_dir, fourk_dir, temp_dir, check_only):
        try:
            process_files(hd_dir, fourk_dir, temp_dir, check_only)
            print("[GREEN]✅ Process completed successfully.\n")
            title = self.i18n[self.current_lang]["done_title"]
            msg = self.i18n[self.current_lang]["done_check_msg"] if check_only else self.i18n[self.current_lang]["done_trans_msg"]
            self.after(0, lambda t=title, m=msg: messagebox.showinfo(t, m))
        except Exception as e:
            print(f"[RED]\n❌ An unexpected error occurred:\n{str(e)}")
            err_title = self.i18n[self.current_lang]["err_exist_title"]
            err_msg = f"An error occurred:\n{str(e)}"
            self.after(0, lambda t=err_title, m=err_msg: messagebox.showerror(t, m))
        finally:
            def enable_buttons():
                self.btn_start_transfer.configure(state="normal")
                self.btn_start_check.configure(state="normal")
            self.after(0, enable_buttons)

if __name__ == "__main__":
    app = TCMatcherApp()
    app.mainloop()