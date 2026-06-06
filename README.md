# TCMatcher

**TCMatcher** is a graphical utility tool designed to safely and quickly transfer timecodes from your original HD video files into your upscaled files when timecode was reset or changed during the upscaling process. 

When using AI video upscaling software, the original timecode track is often stripped or reset to `00:00:00:00`. This creates a massive problem for video editors who need to relink the high-resolution files back into their timelines. TCMatcher solves this by comparing the folder structures of your original and upscaled files and injecting the original timecode back into the upscaled files.

## Features
- **Lossless Stream Copy**: TCMatcher uses `ffmpeg -c copy` to inject the timecode. It does **not** re-encode your video, meaning 100% of the visual quality is preserved and the process is blazingly fast.
- **Metadata Preservation**: It explicitly maps all global, video, and audio metadata (including vital color space and gamma tags) from the original upscaled file to the new file.
- **Dry-Run Mode (Check Only)**: Want to see how many files are missing their timecode before doing anything? Use the "Check Only" mode to safely scan your directories and output a statistical report without modifying any files.
- **Safe Network Transfers**: If your files are stored on a NAS or server, you can select a local SSD as a temporary cache. TCMatcher will process the files locally and use an atomic replacement strategy to safely push the files back to the server, preventing data corruption during network drops.
- **File Validation**: It verifies that the written file size is correct and explicitly reads the timecode back from the newly created file to ensure absolute sync before finalizing the process.

## Prerequisites
- **Python 3.7+**
- **FFmpeg & FFprobe**: These must be installed on your system and accessible via the system `PATH`. You can download FFmpeg from [the official website](https://ffmpeg.org/download.html).

## How to Use

1. Run the application:
   ```bash
   python tc_copy.py
   ```
2. **HD Material Folder (Source)**: Select the root folder containing your original video files with the correct timecodes.
3. **4K Material Folder (Destination)**: Select the root folder containing your upscaled video files. *Note: The folder structure inside the 4K folder must match the HD folder.*
4. **Local SSD Cache (Optional)**: If you are working over a network, select a folder on a fast, local drive to ensure safe processing.
5. **Start**: 
   - Click **Nur Timecodes Prüfen (Dry-Run)** to generate a report of mismatched files.
   - Click **Timecode Übertragung Starten** to begin the automated injection process.

## Supported Formats
Currently, the tool scans for the following video extensions:
`.mp4`, `.mov`, `.mxf`, `.avi`, `.m4v`

## Important Notes
- **Identical Filenames**: The upscaled files must have the exact same filename (without extension) and be located in the exact same sub-folder structure relative to their root folder as the HD files.
- **Backup**: While the script is designed with multiple safety checks (like size validation and atomic replacement), it is always recommended to have a backup of your files before running batch metadata operations.
