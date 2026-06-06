import os
import sys
import subprocess
import threading
import shutil
import math
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox
import customtkinter as ctk

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

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
        kwargs = {"capture_output": True, "text": True, "check": True, "stdin": subprocess.DEVNULL}
        if sys.platform == "win32":
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        result = subprocess.run(command, **kwargs)
        timecodes = result.stdout.strip().split('\n')
        for tc in timecodes:
            if tc and len(tc) >= 8: 
                return tc
    except subprocess.CalledProcessError:
        pass
    return None

def get_framerate(filepath):
    """Reads the framerate of a video file using ffprobe and rounds it to the nearest integer base."""
    command = [
        "ffprobe",
        "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=r_frame_rate",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(filepath)
    ]
    try:
        kwargs = {"capture_output": True, "text": True, "check": True, "stdin": subprocess.DEVNULL}
        if sys.platform == "win32":
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        result = subprocess.run(command, **kwargs)
        fps_str = result.stdout.strip()
        if fps_str:
            parts = fps_str.split('/')
            if len(parts) == 2:
                fps = float(parts[0]) / float(parts[1])
            else:
                fps = float(fps_str)
            return int(round(fps))
    except (subprocess.CalledProcessError, ValueError, ZeroDivisionError):
        pass
    return 25 # Fallback

def tc_to_seconds(tc_str, fps):
    """Converts a timecode string to absolute seconds based on given fps."""
    parts = tc_str.replace(';', ':').split(':')
    if len(parts) < 4:
        return 0.0
    h, m, s, f = map(int, parts)
    return h * 3600 + m * 60 + s + (f / fps)

def seconds_to_tc(seconds, fps):
    """Converts absolute seconds to a timecode string based on target fps."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    f = int(round((seconds - int(seconds)) * fps))
    if f >= fps:
        f = 0
        s += 1
        if s >= 60:
            s = 0
            m += 1
            if m >= 60:
                m = 0
                h += 1
    return f"{h:02d}:{m:02d}:{s:02d}:{f:02d}"

def process_files(hd_dir, fourk_dir, temp_dir=None, check_only=False, mode="standard", progress_callback=None, check_stop_callback=None):
    hd_path = Path(hd_dir)
    fourk_path = Path(fourk_dir)

    print(f"Scanning original files in: {hd_path}")
    print(f"Matching with processed files in: {fourk_path}")
    if mode == "mismatch":
        print("Mode: FPS Mismatch Only (Timecode Recalculation)\n")
    else:
        print("Mode: Standard (Skips FPS Mismatches)\n")

    video_extensions = {'.mp4', '.mov', '.mxf', '.avi', '.m4v'}
    processed_4k_files = set()
    
    total_checked = 0
    identical_tc = 0
    different_tc = 0
    differing_files = []

    # Transfer statistics
    total_found = 0
    no_counterpart = 0
    already_identical = 0
    successful_updates = 0
    failed_updates = 0
    failed_files = []
    
    skipped_mismatch = []
    skipped_normal = 0
    found_fps_mismatch = []

    # Pre-scan for progress tracking
    print("Pre-scanning files to count total...")
    all_hd_files = [f for f in hd_path.rglob('*') if f.is_file() and f.suffix.lower() in video_extensions and not f.name.startswith('.')]
    total_files = len(all_hd_files)
    print(f"Found {total_files} original video files to process.\n")

    for index, hd_file in enumerate(all_hd_files):
        if check_stop_callback and check_stop_callback():
            print("\n[RED]=== PROCESS CANCELLED BY USER ===")
            print("[RED]Already finished files are saved. Resuming later will skip them.")
            break
            
        if progress_callback:
            progress_callback(index + 1, total_files)
        total_found += 1
        rel_path = hd_file.relative_to(hd_path)
        expected_4k_dir = fourk_path / rel_path.parent

        if not expected_4k_dir.exists():
            print(f"Skipping: Target folder {expected_4k_dir} does not exist.")
            no_counterpart += 1
            continue

        fourk_file = None
        for f in expected_4k_dir.iterdir():
            if f.is_file() and f.stem == hd_file.stem and f.suffix.lower() in video_extensions and not f.name.startswith('.'):
                fourk_file = f
                break

        if not fourk_file:
            print(f"Not found: No Processed counterpart for {hd_file.name}")
            no_counterpart += 1
            continue
        
        processed_4k_files.add(fourk_file.resolve())

        tc = get_timecode(hd_file)
        hd_fps = get_framerate(hd_file)
        
        fourk_tc = get_timecode(fourk_file)
        fourk_fps = get_framerate(fourk_file)
        
        if not tc:
            tc = "00:00:00:00"
            if not check_only:
                print(f"[Fallback] No TC found in {hd_file.name}. Setting 00:00:00:00.")

        is_mismatch = (hd_fps != fourk_fps)
        
        if mode == "standard" and is_mismatch:
            if check_only:
                found_fps_mismatch.append((hd_file.name, hd_fps, fourk_fps))
            else:
                print(f"[RED]Skipped: {hd_file.name} (FPS Mismatch: Orig {hd_fps}fps vs Target {fourk_fps}fps)")
                skipped_mismatch.append((hd_file.name, hd_fps, fourk_fps))
                continue
            
        if mode == "mismatch" and not is_mismatch:
            print(f"Skipped: {hd_file.name} (Framerates match, handled by standard mode)")
            skipped_normal += 1
            continue
            
        if mode == "mismatch" and check_only:
            total_checked += 1
            found_fps_mismatch.append((hd_file.name, hd_fps, fourk_fps))
            print(f"[RED]Found FPS Mismatch: {hd_file.name} (Orig: {hd_fps}fps | Processed: {fourk_fps}fps)")
            continue
            
        target_tc = tc
        if mode == "mismatch" and is_mismatch:
            abs_seconds = tc_to_seconds(tc, hd_fps)
            target_tc = seconds_to_tc(abs_seconds, fourk_fps)
            print(f"[{hd_file.name}] Recalculated TC: {tc} ({hd_fps}fps) -> {target_tc} ({fourk_fps}fps)")
        
        if check_only:
            total_checked += 1
            if fourk_tc == target_tc:
                identical_tc += 1
                print(f"Checked: {rel_path} -> [GREEN]Match ({target_tc})")
            else:
                different_tc += 1
                print(f"[RED]Checked: {rel_path} -> Mismatch! (Original/Target: {target_tc} | Processed: {fourk_tc})")
                differing_files.append((fourk_file.relative_to(fourk_path), target_tc, fourk_tc))
            continue

        if fourk_tc == target_tc:
            print(f"[{fourk_file.name}] Timecode is already identical ({target_tc}). Skipping...")
            already_identical += 1
            continue

        print(f"Copying Timecode [{target_tc}] to Processed file: {fourk_file.name}...")
        
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
            "-timecode", target_tc,
            str(temp_output)
        ]
        
        server_temp = None
        try:
            kwargs = {"capture_output": True, "text": True, "check": True, "stdin": subprocess.DEVNULL}
            if sys.platform == "win32":
                kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
            subprocess.run(ffmpeg_cmd, **kwargs)
            
            orig_size = fourk_file.stat().st_size
            temp_size = temp_output.stat().st_size
            
            if temp_size < orig_size * 0.98:
                print(f"[RED]-> ABORT for {fourk_file.name}: New file is unusually small! (Original: {orig_size}, New: {temp_size})\n")
                temp_output.unlink(missing_ok=True)
                failed_updates += 1
                failed_files.append((fourk_file.name, "File too small after writing"))
                continue

            new_tc = get_timecode(temp_output)
            if new_tc != target_tc:
                print(f"[RED]-> ABORT for {fourk_file.name}: Timecode was not written correctly! (Expected: {target_tc}, Read: {new_tc})\n")
                temp_output.unlink(missing_ok=True)
                failed_updates += 1
                failed_files.append((fourk_file.name, "Timecode verification failed"))
                continue

            if temp_dir:
                print("Pushing verified file safely back to the server...")
                server_temp = fourk_file.with_suffix('.network_temp' + fourk_file.suffix)
                shutil.copy2(temp_output, server_temp)
                server_temp.replace(fourk_file)
                temp_output.unlink(missing_ok=True)
                print(f"[GREEN]-> Success! (Cached via SSD & verified)\n")
                successful_updates += 1
            else:
                temp_output.replace(fourk_file)
                print(f"[GREEN]-> Success! (Size & TC verified)\n")
                successful_updates += 1
        except subprocess.CalledProcessError as e:
            print(f"[RED]-> ERROR (FFmpeg) for {fourk_file.name}: {e.stderr}\n")
            temp_output.unlink(missing_ok=True)
            failed_updates += 1
            failed_files.append((fourk_file.name, f"FFmpeg error: {e.stderr.strip() if e.stderr else 'Unknown'}"))
        except Exception as e:
            print(f"[RED]-> ERROR (System/Access) for {fourk_file.name}: {str(e)}\n")
            temp_output.unlink(missing_ok=True)
            if server_temp:
                server_temp.unlink(missing_ok=True)
            failed_updates += 1
            failed_files.append((fourk_file.name, f"System/Access error: {str(e)}"))

    print("\n--- Check for untouched Processed files ---")
    missing_hd = []
    for f in fourk_path.rglob('*'):
        if f.is_file() and f.suffix.lower() in video_extensions and not f.name.startswith('.'):
            if f.resolve() not in processed_4k_files:
                missing_hd.append(f)
    
    if missing_hd:
        print("[RED]WARNING: No Original counterpart found for the following Processed files:")
        for f in missing_hd:
            print(f"[RED]❌ {f.relative_to(fourk_path)}")
        print("\n")
    else:
        print("[GREEN]Perfect: All Processed files had a matching Original counterpart.\n")

    # Details
    if check_only:
        if different_tc > 0:
            print("\n[RED]The following files have differing timecodes:")
            for f_rel, expected_tc, actual_tc in differing_files:
                print(f"[RED]- {f_rel} (Original/Target: {expected_tc} | Processed: {actual_tc})")
        if mode == "standard" and found_fps_mismatch:
            print("\n[RED]The following files have a Framerate Mismatch:")
            for name, h_fps, f_fps in found_fps_mismatch:
                print(f"[RED]- {name} (Orig: {h_fps}fps | Target: {f_fps}fps)")
    else:
        if failed_updates > 0:
            print("\n[RED]The following files could not be updated:")
            for name, reason in failed_files:
                print(f"[RED]- {name} (Reason: {reason})")

    if skipped_mismatch:
        print("\n[RED]The following files have a Framerate Mismatch (Skipped):")
        for name, h_fps, f_fps in skipped_mismatch:
            print(f"[RED]- {name} (Orig: {h_fps}fps | Target: {f_fps}fps)")
            
    print("\n")

    # Summary
    if check_only:
        if mode == "mismatch":
            print("--- FPS MISMATCH REPORT ---")
            print(f"Total files scanned: {total_found}")
            print(f"Skipped (Standard files): {skipped_normal}")
            if found_fps_mismatch:
                print(f"[RED]Found FPS Mismatches: {len(found_fps_mismatch)}")
            else:
                print(f"[GREEN]Found FPS Mismatches: 0 (All framerates match!)")
            print("---------------------------\n")
        else:
            print("--- TIMECODE CHECK REPORT ---")
            print(f"Total checked: {total_checked}")
            print(f"[GREEN]Identical timecodes: {identical_tc}")
            if different_tc > 0:
                print(f"[RED]Differing timecodes: {different_tc}")
            else:
                print(f"[GREEN]Differing timecodes: 0 (Everything perfectly in sync!)")
                
            if found_fps_mismatch:
                print(f"[RED]FPS mismatches found: {len(found_fps_mismatch)}")
            elif skipped_mismatch:
                print(f"[RED]Skipped (FPS Mismatch): {len(skipped_mismatch)}")
            print("-----------------------------\n")
    else:
        print("--- TRANSFER REPORT ---")
        print(f"Total Original files processed: {total_found}")
        if mode == "mismatch":
            print(f"Skipped (Standard files): {skipped_normal}")
        print(f"[GREEN]Successfully updated: {successful_updates}")
        print(f"Already in sync (skipped): {already_identical}")
        
        if failed_updates > 0:
            print(f"[RED]Failed to update: {failed_updates}")
        else:
            print(f"[GREEN]Failed to update: 0")
            
        if skipped_mismatch:
            print(f"[RED]Skipped (FPS Mismatch): {len(skipped_mismatch)}")
            
        if no_counterpart > 0:
            print(f"[RED]Missing counterparts: {no_counterpart} original files had no counterpart in the target folder.")
        print("-----------------------\n")

class PrintLogger:
    def __init__(self, text_widget, is_stderr=False):
        self.text_widget = text_widget
        self.is_stderr = is_stderr

    def write(self, message):
        if not message:
            return
        def _insert():
            self.text_widget.configure(state="normal")
            if self.is_stderr:
                self.text_widget.insert(tk.END, message, "error")
            elif "[RED]" in message:
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
                "tab_transfer_mm": "Transfer (FPS Mismatch)",
                "tab_check_mm": "Check (FPS Mismatch)",
                "hd_label": "Original Material Ordner (Quelle):",
                "4k_label": "Bearbeitetes Material Ordner (Ziel):",
                "temp_label": "Lokaler SSD Cache (Optional):",
                "browse_btn": "...",
                "start_btn_transfer": "TIMECODE ÜBERTRAGUNG STARTEN",
                "start_btn_check": "TIMECODES PRÜFEN (DRY-RUN)",
                "start_btn_transfer_mm": "MISMATCH TIMECODES UMRECHNEN",
                "start_btn_check_mm": "MISMATCH PRÜFEN (DRY-RUN)",
                "log_label": "Log-Ausgabe:",
                "info_btn": "Info & Anleitung",
                "info_title": "Information",
                "info_text": "TCMatcher Anleitung:\n\n1. Original Material Ordner: Wähle den Ordner mit den Originaldateien (mit korrektem Timecode).\n2. Bearbeitetes Material Ordner: Wähle den Ordner mit den veränderten Dateien. Die Dateinamen und Ordnerstruktur müssen exakt mit dem Original-Ordner übereinstimmen!\n3. SSD Cache: Wenn deine Dateien auf einem Netzwerkspeicher liegen, wähle einen lokalen SSD-Ordner. TCMatcher kopiert die Dateien zum Bearbeiten auf die SSD und schiebt sie danach sicher zurück.\n\nPrüfen (Dry-Run):\nSimuliert den Vorgang und zeigt, welche Dateien abweichende Timecodes haben, ohne etwas zu verändern. Im Standard-Modus werden auch abweichende Framerates (FPS Mismatches) in der Statistik ausgewiesen.\n\nFPS Mismatch:\nWenn Original und Bearbeitung unterschiedliche Framerates haben (z.B. 30p zu 25p), werden diese bei der Standard-Übertragung zum Schutz übersprungen. Nutze stattdessen die '(FPS Mismatch)' Tabs. Diese übersetzen den Timecode mathematisch exakt, sodass der In-Point im Schnittprogramm trotz Framerate-Wechsel perfekt erhalten bleibt.\n\n---\nCredits:\nErstellt mit Python & CustomTkinter.\nVideoverarbeitung durch FFmpeg.",
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
                "tab_transfer_mm": "Transfer (FPS Mismatch)",
                "tab_check_mm": "Check (FPS Mismatch)",
                "hd_label": "Original Material Folder (Source):",
                "4k_label": "Processed Material Folder (Destination):",
                "temp_label": "Local SSD Cache (Optional):",
                "browse_btn": "...",
                "start_btn_transfer": "START TIMECODE TRANSFER",
                "start_btn_check": "CHECK TIMECODES (DRY-RUN)",
                "start_btn_transfer_mm": "RECALCULATE MISMATCH TIMECODES",
                "start_btn_check_mm": "CHECK MISMATCH (DRY-RUN)",
                "log_label": "Log Output:",
                "info_btn": "Info & Manual",
                "info_title": "Information",
                "info_text": "TCMatcher Manual:\n\n1. Original Material Folder: Select the folder with the original files (containing correct timecode).\n2. Processed Material Folder: Select the folder with the modified files. Filenames and folder structure must match the Original folder exactly!\n3. SSD Cache: If your files are on a network drive, select a local SSD folder. TCMatcher will process the files locally and safely push them back.\n\nCheck (Dry-Run):\nSimulates the process and shows which files have differing timecodes without modifying anything. In Standard mode, files with different framerates (FPS mismatches) are also actively reported in the final statistics.\n\nFPS Mismatch:\nIf Original and Processed files have different framerates (e.g. 30p to 25p), standard transfers will skip them for safety. Instead, use the '(FPS Mismatch)' tabs. These will mathematically recalculate the exact timecode base so that the in-point remains perfectly linked in your NLE.\n\n---\nCredits:\nBuilt with Python & CustomTkinter.\nVideo processing powered by FFmpeg.",
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
        self.geometry("1000x800")
        self.minsize(900, 600)
        
        try:
            self.iconbitmap(resource_path("tcmatcher_logo.ico"))
        except Exception:
            pass
        
        self.hd_var = tk.StringVar()
        self.fourk_var = tk.StringVar()
        self.temp_var = tk.StringVar()
        self.stop_requested = False
        
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=0)
        self.grid_rowconfigure(1, weight=1) # Give log area all extra space
        
        self.setup_ui()
        self.show_tab("transfer")
        
        self.log_text.tag_config("error", foreground="#ff4d4d")
        self.log_text.tag_config("success", foreground="#00cc66")
        sys.stdout = PrintLogger(self.log_text, is_stderr=False)
        sys.stderr = PrintLogger(self.log_text, is_stderr=True)

    def setup_ui(self):
        # Sidebar
        self.sidebar = ctk.CTkFrame(self, width=200, corner_radius=0)
        self.sidebar.grid(row=0, column=0, rowspan=2, sticky="nsew")
        self.sidebar.grid_rowconfigure(5, weight=1)

        self.btn_tab_transfer = ctk.CTkButton(self.sidebar, text=self.i18n[self.current_lang]["tab_transfer"], 
                                       command=lambda: self.show_tab("transfer"), corner_radius=0, height=40)
        self.btn_tab_transfer.pack(side="top", fill="x", padx=0, pady=(20, 0))

        self.btn_tab_check = ctk.CTkButton(self.sidebar, text=self.i18n[self.current_lang]["tab_check"], 
                                       command=lambda: self.show_tab("check"), corner_radius=0, height=40)
        self.btn_tab_check.pack(side="top", fill="x", padx=0, pady=0)
        
        self.btn_tab_transfer_mm = ctk.CTkButton(self.sidebar, text=self.i18n[self.current_lang]["tab_transfer_mm"], 
                                       command=lambda: self.show_tab("transfer_mm"), corner_radius=0, height=40)
        self.btn_tab_transfer_mm.pack(side="top", fill="x", padx=0, pady=0)

        self.btn_tab_check_mm = ctk.CTkButton(self.sidebar, text=self.i18n[self.current_lang]["tab_check_mm"], 
                                       command=lambda: self.show_tab("check_mm"), corner_radius=0, height=40)
        self.btn_tab_check_mm.pack(side="top", fill="x", padx=0, pady=0)
        
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
        self.frame_transfer_mm = ctk.CTkFrame(self, fg_color="transparent")
        self.frame_check_mm = ctk.CTkFrame(self, fg_color="transparent")

        self.setup_transfer_view()
        self.setup_check_view()
        self.setup_transfer_mm_view()
        self.setup_check_mm_view()
        
        # Log Output Frame
        self.log_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.log_frame.grid(row=1, column=1, padx=20, pady=(0, 20), sticky="nsew")
        self.log_frame.grid_columnconfigure(0, weight=1)
        self.log_frame.grid_rowconfigure(1, weight=0)
        self.log_frame.grid_rowconfigure(2, weight=1)
        
        self.log_label_widget = ctk.CTkLabel(self.log_frame, text=self.i18n[self.current_lang]["log_label"], font=ctk.CTkFont(size=12, weight="bold"))
        self.log_label_widget.grid(row=0, column=0, sticky="w", pady=(0, 5))
        
        # Progress Bar Frame (Row 1)
        self.progress_frame = ctk.CTkFrame(self.log_frame, fg_color="transparent")
        self.progress_frame.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        self.progress_frame.grid_columnconfigure(0, weight=1)
        self.progress_frame.grid_remove() # Hide initially
        
        self.progress_bar = ctk.CTkProgressBar(self.progress_frame)
        self.progress_bar.grid(row=0, column=0, sticky="ew", padx=(0, 10))
        self.progress_bar.set(0)
        
        self.progress_label = ctk.CTkLabel(self.progress_frame, text="0 / 0", font=ctk.CTkFont(size=12, weight="bold"))
        self.progress_label.grid(row=0, column=1)

        self.btn_stop = ctk.CTkButton(self.progress_frame, text="STOP", width=60, fg_color="#ff4d4d", hover_color="#cc0000", command=self.request_stop)
        self.btn_stop.grid(row=0, column=2, padx=(10, 0))
        
        # Textbox (Row 2)
        self.log_text = ctk.CTkTextbox(self.log_frame, wrap="word", font=ctk.CTkFont(family="Consolas", size=12), state="disabled")
        self.log_text.grid(row=2, column=0, sticky="nsew")

    def setup_transfer_view(self):
        self._setup_transfer_like_view(self.frame_transfer, "start_btn_transfer", check_only=False, mode="standard")

    def setup_transfer_mm_view(self):
        self._setup_transfer_like_view(self.frame_transfer_mm, "start_btn_transfer_mm", check_only=False, mode="mismatch")

    def _setup_transfer_like_view(self, frame, btn_text_key, check_only, mode):
        frame.grid_columnconfigure(0, weight=1)
        
        label_hd = ctk.CTkLabel(frame, text=self.i18n[self.current_lang]["hd_label"], font=ctk.CTkFont(size=13, weight="bold"))
        label_hd.grid(row=0, column=0, padx=20, pady=(10, 2), sticky="w")
        setattr(self, f"label_hd_{frame._name}", label_hd) # Keep ref for language updates
        
        f1 = ctk.CTkFrame(frame, fg_color="transparent")
        f1.grid(row=1, column=0, padx=20, pady=2, sticky="ew")
        f1.grid_columnconfigure(0, weight=1)
        ctk.CTkEntry(f1, textvariable=self.hd_var, state="readonly").grid(row=0, column=0, sticky="ew", padx=(0, 10))
        btn_browse_hd = ctk.CTkButton(f1, text=self.i18n[self.current_lang]["browse_btn"], width=40, command=lambda: self.select("hd"))
        btn_browse_hd.grid(row=0, column=1)
        setattr(self, f"btn_browse_hd_{frame._name}", btn_browse_hd)

        label_4k = ctk.CTkLabel(frame, text=self.i18n[self.current_lang]["4k_label"], font=ctk.CTkFont(size=13, weight="bold"))
        label_4k.grid(row=2, column=0, padx=20, pady=(10, 2), sticky="w")
        setattr(self, f"label_4k_{frame._name}", label_4k)
        
        f2 = ctk.CTkFrame(frame, fg_color="transparent")
        f2.grid(row=3, column=0, padx=20, pady=2, sticky="ew")
        f2.grid_columnconfigure(0, weight=1)
        ctk.CTkEntry(f2, textvariable=self.fourk_var, state="readonly").grid(row=0, column=0, sticky="ew", padx=(0, 10))
        btn_browse_4k = ctk.CTkButton(f2, text=self.i18n[self.current_lang]["browse_btn"], width=40, command=lambda: self.select("4k"))
        btn_browse_4k.grid(row=0, column=1)
        setattr(self, f"btn_browse_4k_{frame._name}", btn_browse_4k)

        label_temp = ctk.CTkLabel(frame, text=self.i18n[self.current_lang]["temp_label"], font=ctk.CTkFont(size=13, weight="bold"))
        label_temp.grid(row=4, column=0, padx=20, pady=(10, 2), sticky="w")
        setattr(self, f"label_temp_{frame._name}", label_temp)
        
        f3 = ctk.CTkFrame(frame, fg_color="transparent")
        f3.grid(row=5, column=0, padx=20, pady=2, sticky="ew")
        f3.grid_columnconfigure(0, weight=1)
        ctk.CTkEntry(f3, textvariable=self.temp_var, state="readonly").grid(row=0, column=0, sticky="ew", padx=(0, 10))
        btn_browse_temp = ctk.CTkButton(f3, text=self.i18n[self.current_lang]["browse_btn"], width=40, command=lambda: self.select("temp"))
        btn_browse_temp.grid(row=0, column=1)
        setattr(self, f"btn_browse_temp_{frame._name}", btn_browse_temp)

        btn_start = ctk.CTkButton(frame, text=self.i18n[self.current_lang][btn_text_key], 
                                      command=lambda: self.start_task(check_only=check_only, mode=mode), 
                                      fg_color="#28a745", hover_color="#218838",
                                      font=ctk.CTkFont(size=14, weight="bold"), height=50)
        btn_start.grid(row=6, column=0, padx=40, pady=(15, 10), sticky="ew")
        setattr(self, f"btn_start_{frame._name}", btn_start)
        
        if mode == "mismatch":
            self.btn_start_transfer_mm = btn_start
        else:
            self.btn_start_transfer = btn_start

    def setup_check_view(self):
        self._setup_check_like_view(self.frame_check, "start_btn_check", check_only=True, mode="standard")

    def setup_check_mm_view(self):
        self._setup_check_like_view(self.frame_check_mm, "start_btn_check_mm", check_only=True, mode="mismatch")

    def _setup_check_like_view(self, frame, btn_text_key, check_only, mode):
        frame.grid_columnconfigure(0, weight=1)
        
        label_hd = ctk.CTkLabel(frame, text=self.i18n[self.current_lang]["hd_label"], font=ctk.CTkFont(size=13, weight="bold"))
        label_hd.grid(row=0, column=0, padx=20, pady=(10, 2), sticky="w")
        setattr(self, f"label_hd_{frame._name}", label_hd)
        
        f1 = ctk.CTkFrame(frame, fg_color="transparent")
        f1.grid(row=1, column=0, padx=20, pady=2, sticky="ew")
        f1.grid_columnconfigure(0, weight=1)
        ctk.CTkEntry(f1, textvariable=self.hd_var, state="readonly").grid(row=0, column=0, sticky="ew", padx=(0, 10))
        btn_browse_hd = ctk.CTkButton(f1, text=self.i18n[self.current_lang]["browse_btn"], width=40, command=lambda: self.select("hd"))
        btn_browse_hd.grid(row=0, column=1)
        setattr(self, f"btn_browse_hd_{frame._name}", btn_browse_hd)

        label_4k = ctk.CTkLabel(frame, text=self.i18n[self.current_lang]["4k_label"], font=ctk.CTkFont(size=13, weight="bold"))
        label_4k.grid(row=2, column=0, padx=20, pady=(10, 2), sticky="w")
        setattr(self, f"label_4k_{frame._name}", label_4k)
        
        f2 = ctk.CTkFrame(frame, fg_color="transparent")
        f2.grid(row=3, column=0, padx=20, pady=2, sticky="ew")
        f2.grid_columnconfigure(0, weight=1)
        ctk.CTkEntry(f2, textvariable=self.fourk_var, state="readonly").grid(row=0, column=0, sticky="ew", padx=(0, 10))
        btn_browse_4k = ctk.CTkButton(f2, text=self.i18n[self.current_lang]["browse_btn"], width=40, command=lambda: self.select("4k"))
        btn_browse_4k.grid(row=0, column=1)
        setattr(self, f"btn_browse_4k_{frame._name}", btn_browse_4k)

        btn_start = ctk.CTkButton(frame, text=self.i18n[self.current_lang][btn_text_key], 
                                      command=lambda: self.start_task(check_only=check_only, mode=mode), 
                                      fg_color="#28a745", hover_color="#218838",
                                      font=ctk.CTkFont(size=14, weight="bold"), height=50)
        btn_start.grid(row=4, column=0, padx=40, pady=(20, 10), sticky="ew")
        setattr(self, f"btn_start_{frame._name}", btn_start)
        
        if mode == "mismatch":
            self.btn_start_check_mm = btn_start
        else:
            self.btn_start_check = btn_start

    def show_tab(self, name):
        self.frame_transfer.grid_forget()
        self.frame_check.grid_forget()
        self.frame_transfer_mm.grid_forget()
        self.frame_check_mm.grid_forget()
        
        self.btn_tab_transfer.configure(fg_color="transparent")
        self.btn_tab_check.configure(fg_color="transparent")
        self.btn_tab_transfer_mm.configure(fg_color="transparent")
        self.btn_tab_check_mm.configure(fg_color="transparent")

        active_color = ("#3B8ED0", "#1f6aa5")

        if name == "transfer":
            self.frame_transfer.grid(row=0, column=1, padx=20, pady=10, sticky="nsew")
            self.btn_tab_transfer.configure(fg_color=active_color)
        elif name == "check":
            self.frame_check.grid(row=0, column=1, padx=20, pady=10, sticky="nsew")
            self.btn_tab_check.configure(fg_color=active_color)
        elif name == "transfer_mm":
            self.frame_transfer_mm.grid(row=0, column=1, padx=20, pady=10, sticky="nsew")
            self.btn_tab_transfer_mm.configure(fg_color=active_color)
        elif name == "check_mm":
            self.frame_check_mm.grid(row=0, column=1, padx=20, pady=10, sticky="nsew")
            self.btn_tab_check_mm.configure(fg_color=active_color)

    def change_language(self, choice):
        self.current_lang = "DE" if choice == "Deutsch" else "EN"
        lang_data = self.i18n[self.current_lang]
        
        self.title(lang_data["window_title"])
        self.btn_tab_transfer.configure(text=lang_data["tab_transfer"])
        self.btn_tab_check.configure(text=lang_data["tab_check"])
        self.btn_tab_transfer_mm.configure(text=lang_data["tab_transfer_mm"])
        self.btn_tab_check_mm.configure(text=lang_data["tab_check_mm"])
        
        for frame in [self.frame_transfer, self.frame_check, self.frame_transfer_mm, self.frame_check_mm]:
            if hasattr(self, f"label_hd_{frame._name}"):
                getattr(self, f"label_hd_{frame._name}").configure(text=lang_data["hd_label"])
            if hasattr(self, f"label_4k_{frame._name}"):
                getattr(self, f"label_4k_{frame._name}").configure(text=lang_data["4k_label"])
            if hasattr(self, f"label_temp_{frame._name}"):
                getattr(self, f"label_temp_{frame._name}").configure(text=lang_data["temp_label"])
            
            if hasattr(self, f"btn_browse_hd_{frame._name}"):
                getattr(self, f"btn_browse_hd_{frame._name}").configure(text=lang_data["browse_btn"])
            if hasattr(self, f"btn_browse_4k_{frame._name}"):
                getattr(self, f"btn_browse_4k_{frame._name}").configure(text=lang_data["browse_btn"])
            if hasattr(self, f"btn_browse_temp_{frame._name}"):
                getattr(self, f"btn_browse_temp_{frame._name}").configure(text=lang_data["browse_btn"])

        self.btn_start_transfer.configure(text=lang_data["start_btn_transfer"])
        self.btn_start_check.configure(text=lang_data["start_btn_check"])
        self.btn_start_transfer_mm.configure(text=lang_data["start_btn_transfer_mm"])
        self.btn_start_check_mm.configure(text=lang_data["start_btn_check_mm"])
        
        self.log_label_widget.configure(text=lang_data["log_label"])
        self.info_button.configure(text=lang_data["info_btn"])
        self.lang_label.configure(text=lang_data["lang_label"])

    def show_info(self):
        info_win = ctk.CTkToplevel(self)
        info_win.title(self.i18n[self.current_lang]["info_title"])
        info_win.geometry("600x480")
        info_win.attributes("-topmost", True)
        
        label = ctk.CTkLabel(info_win, text=self.i18n[self.current_lang]["info_text"], 
                             wraplength=550, justify="left", padx=20, pady=20)
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

    def request_stop(self):
        self.stop_requested = True
        self.btn_stop.configure(state="disabled", text="Stopping...")

    def check_dependencies(self):
        for tool in ["ffmpeg", "ffprobe"]:
            if shutil.which(tool) is None:
                title = self.i18n[self.current_lang]["err_deps_title"]
                msg = self.i18n[self.current_lang]["err_deps_msg"].format(tool)
                messagebox.showerror(title, msg)
                return False
        return True

    def start_task(self, check_only, mode="standard"):
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
        self.btn_start_transfer_mm.configure(state="disabled")
        self.btn_start_check_mm.configure(state="disabled")
        
        self.log_text.configure(state="normal")
        self.log_text.delete(1.0, tk.END)
        self.log_text.configure(state="disabled")
        
        if check_only:
            if mode == "mismatch":
                print("Starting FPS Mismatch Check (Dry-Run)...\n")
            else:
                print("Starting Timecode Check (Dry-Run)...\n")
        else:
            if mode == "mismatch":
                print("Starting FPS Mismatch Timecode Transfer...\n")
            else:
                print("Starting Timecode Transfer...\n")
            if temp_dir:
                print(f"Using local SSD cache: {temp_dir}\n")

        self.stop_requested = False
        if hasattr(self, 'btn_stop'):
            self.btn_stop.configure(state="normal", text="STOP")

        threading.Thread(target=self.run_process, args=(hd_dir, fourk_dir, temp_dir, check_only, mode), daemon=True).start()

    def run_process(self, hd_dir, fourk_dir, temp_dir, check_only, mode):
        def update_progress(current, total):
            def _ui_update():
                if not self.progress_frame.winfo_ismapped():
                    self.progress_frame.grid()
                
                if total > 0:
                    self.progress_bar.set(current / total)
                self.progress_label.configure(text=f"{current} / {total}")
            self.after(0, _ui_update)

        try:
            process_files(hd_dir, fourk_dir, temp_dir, check_only, mode=mode, progress_callback=update_progress, check_stop_callback=lambda: self.stop_requested)
            if self.stop_requested:
                print("[RED]⚠️ Process stopped by user.\n")
            else:
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
                self.progress_frame.grid_remove()
                self.btn_start_transfer.configure(state="normal")
                self.btn_start_check.configure(state="normal")
                self.btn_start_transfer_mm.configure(state="normal")
                self.btn_start_check_mm.configure(state="normal")
            self.after(0, enable_buttons)

if __name__ == "__main__":
    app = TCMatcherApp()
    app.mainloop()