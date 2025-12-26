from src.ConfigManager import ConfigManager
import subprocess
import re
import sys
from pathlib import Path


class DownloadEngine:
    """Wraps the yt-dlp execution and manages the download process."""

    def __init__(self, config: ConfigManager):
        self.config = config

    def clean_filename(self, name):
        regex = r'[<>:"/\\|?*]' if self.config.os_type == "windows" else r"[/\0]"
        cleaned = re.sub(regex, "", name).strip(". ")
        return cleaned[:200]

    def download(self, playlist_info):
        clean_title = self.clean_filename(playlist_info["title"])
        dest_dir = self.config.root_path / clean_title
        dest_dir.mkdir(parents=True, exist_ok=True)

        cmd = [
            self.config.ytdlp_path,
            "--extract-audio",
            "--audio-format",
            self.config.audio_format,
            "--audio-quality",
            self.config.audio_quality,
            "--embed-thumbnail",
            "--embed-metadata",
            "--add-metadata",
            "--no-overwrites",
            "--ignore-errors",
            "--output",
            str(dest_dir / "%(title)s.%(ext)s"),
            playlist_info["url"],
        ]

        if self.config.extra_args:
            cmd.extend(self.config.extra_args.split())

        print(f"Executing command: {' '.join(cmd)}")
        print(f"Destination: {dest_dir}")
        print(f"[DEBUG] yt-dlp path: {self.config.ytdlp_path}")
        print(f"[DEBUG] yt-dlp path exists: {Path(self.config.ytdlp_path).exists()}")
        print(f"[DEBUG] Command as list: {cmd}")

        download_started = False
        has_output = False
        error_occurred = False

        try:
            # Use shell=True only on Windows for better compatibility
            # On Linux, direct execution is more reliable
            use_shell = self.config.os_type == "windows"

            print(f"[DEBUG] OS: {self.config.os_type}, Using shell: {use_shell}")

            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                bufsize=1,
                universal_newlines=True,
                shell=use_shell,
                encoding="utf-8",
                errors="replace",
            )

            for line in process.stdout:
                line = line.strip()
                if not line:
                    continue

                has_output = True

                # Print ALL output for debugging
                print(f"[YTDLP] {line}")

                # Check for configuration errors
                if any(
                    indicator in line.lower()
                    for indicator in [
                        "invalid",
                        "unrecognized",
                        "unknown format",
                        "usage:",
                        "error: argument",
                    ]
                ):
                    error_occurred = True
                    print(f"\n[CONFIG ERROR] {line}")

                # Check for various success indicators
                if any(
                    indicator in line.lower()
                    for indicator in [
                        "[download]",
                        "downloading",
                        "extracting audio",
                        "[extractaudio]",
                        "has already been downloaded",
                        "destination:",
                        "downloading playlist",
                    ]
                ):
                    download_started = True

                # Print progress lines on same line
                if "[download]" in line and "%" in line:
                    print(f"\r{line}", end="", flush=True)
                # Print other important lines on new lines
                elif any(
                    x in line.lower()
                    for x in [
                        "destination:",
                        "error",
                        "warning",
                        "extractaudio",
                        "has already been downloaded",
                        "downloading playlist",
                        "downloading video",
                    ]
                ):
                    if "sabr streaming" not in line.lower():
                        print(f"\n{line}")

                # Check for errors
                if "error" in line.lower() and "ignore" not in line.lower():
                    error_occurred = True
                    print(f"\n[ERROR] {line}")

            process.wait()
            return_code = process.returncode

            print(f"\n[DEBUG] Process completed with return code: {return_code}")
            print(
                f"[DEBUG] Download started: {download_started}, Has output: {has_output}, Error: {error_occurred}"
            )

            # Consider it successful if:
            # 1. Return code is 0, OR
            # 2. Download actually started (even if some files failed due to --ignore-errors)
            # Note: We DON'T consider it successful just because it had output -
            # yt-dlp can output errors without downloading anything
            success = (return_code == 0) or (download_started and not error_occurred)

            if not success:
                print(f"[WARNING] Download may have failed. Check the output above.")

            return success

        except Exception as e:
            print(f"\n[EXCEPTION] Error during download: {e}")
            import traceback

            traceback.print_exc()
            return False
