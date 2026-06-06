import os
import sys
import subprocess
import threading
import shutil
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

def get_timecode(filepath):
    """Liest den Timecode einer Videodatei mittels ffprobe aus."""
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
        # Nimmt den ersten gefundenen, gültigen Timecode-Eintrag
        for tc in timecodes:
            if tc and len(tc) >= 8: 
                return tc
    except subprocess.CalledProcessError:
        pass
    return None

def process_files(hd_dir, fourk_dir, temp_dir=None, check_only=False):
    hd_path = Path(hd_dir)
    fourk_path = Path(fourk_dir)

    # Gängige Videoformate, die berücksichtigt werden sollen
    video_extensions = {'.mp4', '.mov', '.mxf', '.avi', '.m4v'}
    processed_4k_files = set()
    
    # Statistik für Nur-Prüfen Modus
    total_checked = 0
    identical_tc = 0
    different_tc = 0
    differing_files = []

    # Gehe alle Dateien im HD-Ordner (inkl. Unterordner) durch
    for hd_file in hd_path.rglob('*'):
        if hd_file.is_file() and hd_file.suffix.lower() in video_extensions:
            
            # Ermittle den relativen Pfad, um die Struktur im 4K-Ordner abzugleichen
            rel_path = hd_file.relative_to(hd_path)
            expected_4k_dir = fourk_path / rel_path.parent

            if not expected_4k_dir.exists():
                print(f"Überspringe: Zielordner {expected_4k_dir} existiert nicht.")
                continue

            # Suche die passende 4K-Datei anhand des Dateinamens (ohne Endung)
            fourk_file = None
            for f in expected_4k_dir.iterdir():
                if f.is_file() and f.stem == hd_file.stem and f.suffix.lower() in video_extensions:
                    fourk_file = f
                    break

            if not fourk_file:
                print(f"Nicht gefunden: Kein 4K-Pendant für {hd_file.name}")
                continue
            
            processed_4k_files.add(fourk_file.resolve())

            # Timecode aus HD-Datei auslesen
            tc = get_timecode(hd_file)
            
            # Falls kein Timecode gefunden wird, setzen wir als Fallback 00:00:00:00
            if not tc:
                tc = "00:00:00:00"
                if not check_only:
                    print(f"[Fallback] Kein TC in {hd_file.name} gefunden. Setze 00:00:00:00.")

            # Prüfe, ob der 4K Clip den Timecode nicht schon hat
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
                print(f"[{fourk_file.name}] Timecode ist bereits identisch ({tc}). Überspringe...")
                continue

            print(f"Kopiere Timecode [{tc}] auf 4K-Datei: {fourk_file.name}...")
            
            # Temporäre Datei für FFmpeg Output (Lokal oder auf dem Server)
            if temp_dir:
                temp_output = Path(temp_dir) / (fourk_file.stem + '.temp' + fourk_file.suffix)
            else:
                temp_output = fourk_file.with_suffix('.temp' + fourk_file.suffix)
            
            # FFmpeg Befehl zum verlustfreien Kopieren (-c copy) und Hinzufügen des Timecodes
            ffmpeg_cmd = [
                "ffmpeg",
                "-y",                      # Bestehende Dateien ungefragt überschreiben
                "-i", str(fourk_file),     # Input: 4K Datei
                "-map", "0",               # Kopiere ALLE Streams (Video, Audio(s), etc.)
                "-map_metadata", "0",      # Globale Metadaten erhalten
                "-map_metadata:s:v", "0:s:v", # Video-Metadaten erhalten (z.B. Gamma/Color)
                "-map_metadata:s:a", "0:s:a", # Audio-Metadaten erhalten
                "-c", "copy",              # Stream Copy (kein Neu-Rendern!)
                "-timecode", tc,           # Den ausgelesenen Timecode setzen
                str(temp_output)           # Output: Temporäre 4K Datei
            ]
            
            server_temp = None
            try:
                subprocess.run(ffmpeg_cmd, capture_output=True, text=True, check=True)
                
                # --- SICHERHEITS-CHECKS ---
                # 1. Dateigrößen-Check (erlaube max. 2% Abweichung nach unten)
                orig_size = fourk_file.stat().st_size
                temp_size = temp_output.stat().st_size
                
                if temp_size < orig_size * 0.98:
                    print(f"[RED]-> ABBRUCH bei {fourk_file.name}: Neue Datei ist ungewöhnlich klein! (Original: {orig_size}, Neu: {temp_size})\n")
                    temp_output.unlink(missing_ok=True)
                    continue

                # 2. Timecode-Check in der neuen Datei
                new_tc = get_timecode(temp_output)
                if new_tc != tc:
                    print(f"[RED]-> ABBRUCH bei {fourk_file.name}: Timecode wurde nicht korrekt geschrieben! (Erwartet: {tc}, Gelesen: {new_tc})\n")
                    temp_output.unlink(missing_ok=True)
                    continue

                # Wenn erfolgreich: Sicherer Rücktransport oder direktes Ersetzen
                if temp_dir:
                    print("Schiebe verifizierte Datei sicher zurück auf den Server...")
                    server_temp = fourk_file.with_suffix('.network_temp' + fourk_file.suffix)
                    shutil.copy2(temp_output, server_temp)
                    server_temp.replace(fourk_file)
                    temp_output.unlink(missing_ok=True)
                    print(f"[GREEN]-> Erfolg! (Über SSD gecached & verifiziert)\n")
                else:
                    temp_output.replace(fourk_file)
                    print(f"[GREEN]-> Erfolg! (Größe & TC verifiziert)\n")
            except subprocess.CalledProcessError as e:
                print(f"[RED]-> FEHLER (FFmpeg) bei {fourk_file.name}: {e.stderr}\n")
                temp_output.unlink(missing_ok=True)
            except Exception as e:
                print(f"[RED]-> FEHLER (System/Zugriff) bei {fourk_file.name}: {str(e)}\n")
                temp_output.unlink(missing_ok=True)
                if server_temp:
                    server_temp.unlink(missing_ok=True)

    # Nach Durchlauf: Prüfe welche 4K Dateien keinen HD-Pendant hatten
    print("\n--- Überprüfung auf unberührte 4K-Dateien ---")
    missing_hd = []
    for f in fourk_path.rglob('*'):
        if f.is_file() and f.suffix.lower() in video_extensions:
            if f.resolve() not in processed_4k_files:
                missing_hd.append(f)
    
    if missing_hd:
        print("[RED]ACHTUNG: Für folgende 4K-Dateien wurde kein HD-Pendant gefunden:")
        for f in missing_hd:
            print(f"[RED]❌ {f.relative_to(fourk_path)}")
        print("\n")
    else:
        print("[GREEN]Perfekt: Alle 4K-Dateien hatten ein passendes HD-Pendant.\n")

    if check_only:
        print("--- PRÜFBERICHT ---")
        print(f"Gesamt geprüft: {total_checked}")
        print(f"[GREEN]Identische Timecodes: {identical_tc}")
        if different_tc > 0:
            print(f"[RED]Abweichende Timecodes: {different_tc}")
            print("\nFolgende Dateien haben abweichende Timecodes:")
            for f_rel, expected_tc, actual_tc in differing_files:
                print(f"[RED]- {f_rel} (HD: {expected_tc} | 4K: {actual_tc})")
        else:
            print(f"[GREEN]Abweichende Timecodes: 0 (Alles perfekt synchron!)")
        print("-------------------\n")

class PrintLogger:
    def __init__(self, text_widget):
        self.text_widget = text_widget
        self.text_widget.tag_config("error", foreground="red", font=("Consolas", 9, "bold"))
        self.text_widget.tag_config("success", foreground="green", font=("Consolas", 9, "bold"))

    def write(self, message):
        def _insert():
            if "[RED]" in message:
                self.text_widget.insert(tk.END, message.replace("[RED]", ""), "error")
            elif "[GREEN]" in message:
                self.text_widget.insert(tk.END, message.replace("[GREEN]", ""), "success")
            else:
                self.text_widget.insert(tk.END, message)
            self.text_widget.see(tk.END)
        
        # Thread-safe Update des UI (ausgelöst vom Worker-Thread)
        self.text_widget.after(0, _insert)

    def flush(self):
        pass

class TimecodeApp:
    def __init__(self, root):
        self.root = root
        self.root.title("TCMatcher")
        self.root.geometry("650x600")
        self.root.minsize(500, 400)
        
        # UI Setup
        self.setup_ui()
        
        # Redirect stdout (damit print()-Befehle im Log-Fenster landen)
        sys.stdout = PrintLogger(self.log_text)

    def setup_ui(self):
        main_frame = ttk.Frame(self.root, padding="15")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # HD Ordner
        ttk.Label(main_frame, text="HD Material Ordner (Quelle):", font=("Segoe UI", 10, "bold")).pack(anchor=tk.W, pady=(0, 5))
        hd_frame = ttk.Frame(main_frame)
        hd_frame.pack(fill=tk.X, pady=(0, 15))
        self.hd_var = tk.StringVar()
        ttk.Entry(hd_frame, textvariable=self.hd_var, width=50).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))
        ttk.Button(hd_frame, text="Durchsuchen", command=self.browse_hd).pack(side=tk.RIGHT)

        # 4K Ordner
        ttk.Label(main_frame, text="4K Material Ordner (Ziel):", font=("Segoe UI", 10, "bold")).pack(anchor=tk.W, pady=(0, 5))
        fourk_frame = ttk.Frame(main_frame)
        fourk_frame.pack(fill=tk.X, pady=(0, 20))
        self.fourk_var = tk.StringVar()
        ttk.Entry(fourk_frame, textvariable=self.fourk_var, width=50).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))
        ttk.Button(fourk_frame, text="Durchsuchen", command=self.browse_fourk).pack(side=tk.RIGHT)

        # Temp Ordner (Optional)
        ttk.Label(main_frame, text="Lokaler SSD Zwischenspeicher (Optional):", font=("Segoe UI", 10, "bold")).pack(anchor=tk.W, pady=(0, 5))
        temp_frame = ttk.Frame(main_frame)
        temp_frame.pack(fill=tk.X, pady=(0, 20))
        self.temp_var = tk.StringVar()
        ttk.Entry(temp_frame, textvariable=self.temp_var, width=50).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))
        ttk.Button(temp_frame, text="Durchsuchen", command=self.browse_temp).pack(side=tk.RIGHT)

        # Buttons
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X, pady=(0, 20))
        
        self.start_btn = ttk.Button(button_frame, text="Timecode Übertragung Starten", command=self.start_processing)
        self.start_btn.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5), ipady=5)

        self.check_btn = ttk.Button(button_frame, text="Nur Timecodes Prüfen (Dry-Run)", command=self.start_checking)
        self.check_btn.pack(side=tk.RIGHT, fill=tk.X, expand=True, padx=(5, 0), ipady=5)

        # Log Text Widget
        ttk.Label(main_frame, text="Log-Ausgabe:").pack(anchor=tk.W, pady=(0, 5))
        text_frame = ttk.Frame(main_frame)
        text_frame.pack(fill=tk.BOTH, expand=True)
        
        self.log_text = tk.Text(text_frame, wrap=tk.WORD, font=("Consolas", 9), bg="#f5f5f5")
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        scrollbar = ttk.Scrollbar(text_frame, command=self.log_text.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_text.config(yscrollcommand=scrollbar.set)

    def browse_hd(self):
        folder = filedialog.askdirectory(title="Wähle den Ordner mit dem HD Material")
        if folder:
            self.hd_var.set(folder)

    def browse_fourk(self):
        folder = filedialog.askdirectory(title="Wähle den Ordner mit dem 4K Material")
        if folder:
            self.fourk_var.set(folder)

    def browse_temp(self):
        folder = filedialog.askdirectory(title="Wähle einen lokalen Zwischenspeicher (SSD)")
        if folder:
            self.temp_var.set(folder)

    def check_dependencies(self):
        """Prüft, ob ffmpeg und ffprobe im Systempfad verfügbar sind."""
        for tool in ["ffmpeg", "ffprobe"]:
            if shutil.which(tool) is None:
                messagebox.showerror("Fehlende Abhängigkeit", f"Das Tool '{tool}' wurde nicht gefunden.\nBitte installiere FFmpeg und füge es dem System-PATH hinzu.")
                return False
        return True

    def start_processing(self):
        self._start_task(check_only=False)

    def start_checking(self):
        self._start_task(check_only=True)

    def _start_task(self, check_only):
        if not self.check_dependencies():
            return

        hd_dir = self.hd_var.get().strip()
        fourk_dir = self.fourk_var.get().strip()
        temp_dir = self.temp_var.get().strip() or None

        if not hd_dir or not fourk_dir:
            messagebox.showwarning("Fehlende Pfade", "Bitte wähle sowohl den HD- als auch den 4K-Ordner aus.")
            return
            
        if not os.path.exists(hd_dir) or not os.path.exists(fourk_dir):
            messagebox.showerror("Fehler", "Einer der ausgewählten HD/4K-Ordner existiert nicht.")
            return
            
        if not check_only and temp_dir and not os.path.exists(temp_dir):
            messagebox.showerror("Fehler", "Der gewählte lokale Zwischenspeicher existiert nicht.")
            return

        # Disable buttons during processing
        self.start_btn.config(state=tk.DISABLED)
        self.check_btn.config(state=tk.DISABLED)
        self.log_text.delete(1.0, tk.END)
        
        if check_only:
            print("Starte Timecode-Prüfung (Dry-Run)...\n")
        else:
            print("Starte Timecode-Übertragung...\n")
            if temp_dir:
                print(f"Nutze lokalen SSD Cache: {temp_dir}\n")

        # Run in separate thread so UI doesn't freeze
        threading.Thread(target=self.run_process, args=(hd_dir, fourk_dir, temp_dir, check_only), daemon=True).start()

    def run_process(self, hd_dir, fourk_dir, temp_dir, check_only):
        try:
            process_files(hd_dir, fourk_dir, temp_dir, check_only)
            print("[GREEN]✅ Vorgang erfolgreich abgeschlossen.\n")
            if check_only:
                messagebox.showinfo("Fertig", "Die Timecode-Prüfung wurde abgeschlossen.")
            else:
                messagebox.showinfo("Fertig", "Die Timecode-Übertragung wurde abgeschlossen.")
        except Exception as e:
            print(f"[RED]\n❌ Ein unerwarteter Fehler ist aufgetreten:\n{str(e)}")
            messagebox.showerror("Fehler", f"Ein Fehler ist aufgetreten:\n{str(e)}")
        finally:
            # Re-enable buttons (thread-safe UI update)
            def enable_buttons():
                self.start_btn.config(state=tk.NORMAL)
                self.check_btn.config(state=tk.NORMAL)
            self.root.after(0, enable_buttons)

if __name__ == "__main__":
    root = tk.Tk()
    
    # Der DPI Awareness Call von Windows wurde absichtlich entfernt!
    # Auf Monitoren mit z.B. 150% Skalierung führt dies dazu, dass Windows
    # das Fenster automatisch vergrößert. Das UI ist dadurch exakt so groß
    # wie es sein soll und nicht mehr winzig.
        
    app = TimecodeApp(root)
    root.mainloop()