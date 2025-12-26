from src.ConfigManager import ConfigManager
import subprocess
import re
from pathlib import Path
from utils.vtt_to_lrc import vtt_to_lrc


class DownloadEngine:
    """
    Wraps yt-dlp execution and manages audio + optional lyric downloads.
    """

    def __init__(self, config: ConfigManager):
        self.config = config

    def clean_filename(self, name: str) -> str:
        regex = r'[<>:"/\\|?*]' if self.config.os_type == "windows" else r"[/\0]"
        cleaned = re.sub(regex, "", name).strip(". ")
        return cleaned[:200]

    def download(self, playlist_info: dict) -> bool:
        clean_title = self.clean_filename(playlist_info["title"])
        dest_dir = self.config.root_path / clean_title
        dest_dir.mkdir(parents=True, exist_ok=True)

        archive_file = "download_archive.txt"

        cmd = [
            self.config.ytdlp_path,
            "--extract-audio",
            "--audio-format", self.config.audio_format,
            "--audio-quality", self.config.audio_quality,
            "--embed-thumbnail",
            "--embed-metadata",
            "--add-metadata",
            "--download-archive", str(archive_file),
            "--no-overwrites",
            "--ignore-errors",
        ]


        # ---- Lyrics / captions support ----
        if getattr(self.config, "download_lyrics", False):
            cmd.extend(
                [
                    "--write-subs",
                    "--write-auto-subs",
                    "--sub-langs",
                    "en",
                    "--sub-format",
                    "vtt",
                ]
            )

        if getattr(self.config, "lyrics_only", False):
            cmd.append("--skip-download")

        # ---- Output & URL ----
        cmd.extend(
            [
                "--output",
                str(dest_dir / "%(title)s.%(ext)s"),
                playlist_info["url"],
            ]
        )

        if self.config.extra_args:
            cmd.extend(self.config.extra_args.split())

        print(f"[DEBUG] Executing: {' '.join(cmd)}")

        download_started = False
        error_occurred = False

        try:
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                shell=self.config.os_type == "windows",
                encoding="utf-8",
                errors="replace",
            )

            for line in process.stdout:
                line = line.strip()
                if not line:
                    continue

                print(f"[yt-dlp] {line}")

                if "[download]" in line.lower() or "extractaudio" in line.lower():
                    download_started = True

                if "error" in line.lower() and "ignore" not in line.lower():
                    error_occurred = True

            process.wait()

            success = process.returncode == 0 or (
                download_started and not error_occurred
            )

            if not success:
                print("[WARNING] Download may have failed.")
                return False

            # ---- Post-process: VTT → LRC ----
            if getattr(self.config, "download_lyrics", False):
                for vtt_file in dest_dir.glob("*.vtt"):
                    lrc_file = vtt_file.with_suffix(".lrc")
                    try:
                        vtt_to_lrc(vtt_file, lrc_file)
                        print(f"[LYRICS] Converted {vtt_file.name} → {lrc_file.name}")
                    except Exception as e:
                        print(f"[LYRICS] Failed to convert {vtt_file.name}: {e}")

            return True

        except Exception as e:
            print(f"[EXCEPTION] Download failed: {e}")
            return False
