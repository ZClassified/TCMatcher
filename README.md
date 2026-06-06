# TCMatcher
[English](#english) | [Deutsch](#deutsch)

---

<a name="english"></a>
## English

**TCMatcher** is a graphical utility tool designed to safely and quickly transfer timecodes from your original video files into your processed/upscaled files when timecode was reset or changed during the upscaling/processing. 

When processing, transcoding, or modifying video files, the original timecode track is often stripped or inadvertently reset to `00:00:00:00`. This creates a massive problem for video editors who need to relink the modified files back into their timelines. TCMatcher solves this by comparing the folder structures of your original and processed files and safely injecting the original timecode back into the modified files.

### Features
- **Lossless Stream Copy**: TCMatcher uses `ffmpeg -c copy` to inject the timecode. It does **not** re-encode your video, meaning 100% of the visual quality is preserved and the process is blazingly fast.
- **Metadata Preservation**: It explicitly maps all global, video, and audio metadata (including vital color space and gamma tags) from the original upscaled file to the new file.
- **Dry-Run Mode (Check Only)**: Want to see how many files are missing their timecode before doing anything? Use the "Check Only" mode to safely scan your directories and output a statistical report without modifying any files.
- **Safe Network Transfers**: If your files are stored on a NAS or server, you can select a local SSD as a temporary cache. TCMatcher will process the files locally and use an atomic replacement strategy to safely push the files back to the server, preventing data corruption during network drops.
- **File Validation**: It verifies that the written file size is correct and explicitly reads the timecode back from the newly created file to ensure absolute sync before finalizing the process.

### Prerequisites
- **Python 3.7+**
- **FFmpeg & FFprobe**: These must be installed on your system and accessible via the system `PATH`. You can download FFmpeg from [the official website](https://ffmpeg.org/download.html).

### Installation
1. Clone or download this repository.
2. Install the required Python packages:
   ```bash
   pip install customtkinter
   ```

### How to Use

1. Run the application:
   ```bash
   python tcmatcher.py
   ```
2. **Original Material Folder (Source)**: Select the root folder containing your original video files with the correct timecodes.
3. **Processed Material Folder (Destination)**: Select the root folder containing your processed/upscaled video files. *Note: The folder structure inside the Processed folder must match the Original folder.*
4. **Local SSD Cache (Optional)**: If you are working over a network, select a folder on a fast, local drive to ensure safe processing.
5. **Start**: 
   - Click **Check Only Timecodes (Dry-Run)** to generate a report of mismatched files.
   - Click **Start Timecode Transfer** to begin the automated injection process.

### Supported Formats
Currently, the tool scans for the following video extensions:
`.mp4`, `.mov`, `.mxf`, `.avi`, `.m4v`

### Important Notes
- **Identical Filenames**: The processed files must have the exact same filename (without extension) and be located in the exact same sub-folder structure relative to their root folder as the Original files.
- **Backup**: While the script is designed with multiple safety checks (like size validation and atomic replacement), it is always recommended to have a backup of your files before running batch metadata operations.

---

<a name="deutsch"></a>
## Deutsch

**TCMatcher** ist ein grafisches Tool, das entwickelt wurde, um Timecodes sicher und schnell von deinen Original-Videodateien auf bearbeitete (oder upgescalte) Dateien zu übertragen, wenn der Timecode während der Bearbeitung zurückgesetzt oder verändert wurde.

Bei der Verarbeitung, Konvertierung oder Modifikation von Videodateien geht häufig der ursprüngliche Timecode-Track verloren oder wird ungewollt auf `00:00:00:00` zurückgesetzt. Dies stellt ein großes Problem für Video-Cutter dar, die die bearbeiteten Dateien in ihren Timelines neu verlinken müssen. TCMatcher löst dies, indem es die Ordnerstrukturen deiner Original- und Ziel-Dateien abgleicht und den ursprünglichen Timecode sicher wieder in die bearbeiteten Dateien injiziert.

### Features
- **Verlustfreier Stream-Copy**: TCMatcher nutzt `ffmpeg -c copy`, um den Timecode zu injizieren. Das Video wird **nicht** neu kodiert, d.h. 100% der visuellen Qualität bleibt erhalten und der Prozess ist blitzschnell.
- **Metadaten-Erhalt**: Das Tool mappt explizit alle globalen, Video- und Audio-Metadaten (inkl. wichtiger Farbraum- und Gamma-Tags) von der bearbeiteten Originaldatei in die neue Datei.
- **Dry-Run Modus (Nur Prüfen)**: Du willst sehen, wie vielen Dateien der Timecode fehlt, bevor du etwas tust? Nutze den Modus "Timecodes Prüfen", um deine Verzeichnisse sicher zu scannen und einen statistischen Bericht auszugeben, ohne Dateien zu verändern.
- **Sichere Netzwerk-Transfers**: Wenn deine Dateien auf einem NAS oder Server liegen, kannst du eine lokale SSD als Zwischenspeicher wählen. TCMatcher verarbeitet die Dateien lokal und nutzt eine atomare Ersetzungsstrategie, um die Dateien sicher auf den Server zurückzuschieben (verhindert Datenkorruption bei Netzwerkabbrüchen).
- **Dateivalidierung**: Es wird überprüft, ob die geschriebene Dateigröße korrekt ist, und der Timecode wird explizit aus der neu erstellten Datei zurückgelesen, um eine absolute Synchronität vor dem Abschluss sicherzustellen.

### Voraussetzungen
- **Python 3.7+**
- **FFmpeg & FFprobe**: Diese müssen auf deinem System installiert und über den System-`PATH` erreichbar sein. Du kannst FFmpeg auf [der offiziellen Website](https://ffmpeg.org/download.html) herunterladen.

### Installation
1. Klone oder lade dieses Repository herunter.
2. Installiere die benötigten Python-Pakete:
   ```bash
   pip install customtkinter
   ```

### Nutzung
1. Starte die Anwendung:
   ```bash
   python tcmatcher.py
   ```
2. **Original Material Ordner (Quelle)**: Wähle das Hauptverzeichnis mit deinen Original-Videodateien (mit den korrekten Timecodes).
3. **Bearbeitetes Material Ordner (Ziel)**: Wähle das Hauptverzeichnis mit deinen bearbeiteten/upgescalten Videodateien. *Hinweis: Die Ordnerstruktur im Ziel-Ordner muss exakt mit der des Original-Ordners übereinstimmen.*
4. **Lokaler SSD Cache (Optional)**: Wenn du über ein Netzwerk arbeitest, wähle einen Ordner auf einer schnellen, lokalen Festplatte, um eine sichere Verarbeitung zu gewährleisten.
5. **Start**: 
   - Gehe zum Tab **Timecodes Prüfen** und klicke auf den Button, um einen Bericht über abweichende Dateien zu generieren.
   - Gehe zum Tab **Timecode Übertragen** und klicke auf den Start-Button, um den automatisierten Injektionsprozess zu beginnen.

### Unterstützte Formate
Aktuell scannt das Tool nach folgenden Video-Erweiterungen:
`.mp4`, `.mov`, `.mxf`, `.avi`, `.m4v`

### Wichtige Hinweise
- **Identische Dateinamen**: Die bearbeiteten Dateien müssen exakt denselben Dateinamen (ohne Erweiterung) haben und sich in exakt derselben Unterordner-Struktur relativ zu ihrem Hauptverzeichnis befinden wie die Originaldateien.
- **Backup**: Obwohl das Skript mit mehreren Sicherheitsprüfungen (wie Größenvalidierung und atomarer Ersetzung) ausgestattet ist, wird immer empfohlen, ein Backup deiner Dateien zu haben, bevor du Batch-Metadaten-Operationen durchführst.
