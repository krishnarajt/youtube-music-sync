import yaml
import os
import sys
from pathlib import Path
from shutil import which


class ConfigManager:
    """Handles loading and validating the application configuration."""

    def __init__(self, config_path="config.yml"):
        self.path = config_path
        self.data = self._load()
        self._setup_properties()

    def _load(self):
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f)
        except FileNotFoundError:
            print(f"Error: Config file '{self.path}' not found!")
            sys.exit(1)
        except yaml.YAMLError as e:
            print(f"Error: Failed to parse config file: {e}")
            sys.exit(1)

    def _setup_properties(self):
        self.os_type = self.data.get("os_type", "windows").lower()
        self.input_method = self.data.get("input_method", "channel")
        self.channel_url = self.data.get("channel_url", "")
        self.playlist_urls = self.data.get("playlist_urls", [])
        self.playlist_file = self.data.get("playlist_file", "")

        # Path resolution
        root = self.data.get("root_path", "./downloads")
        if self.os_type == "linux" and root.startswith("~"):
            root = os.path.expanduser(root)
        self.root_path = Path(root)
        self.root_path.mkdir(parents=True, exist_ok=True)

        self.ytdlp_path = self._resolve_exe(self.data.get("ytdlp_path", "yt-dlp"))
        self.ffmpeg_path = self._resolve_exe(self.data.get("ffmpeg_path", ""))

        # Handle audio format - normalize "auto" to "best" for yt-dlp compatibility
        audio_format_raw = self.data.get("audio_format", "best")
        if audio_format_raw is None or str(audio_format_raw).lower() in ["", "auto"]:
            self.audio_format = "best"
        else:
            self.audio_format = str(audio_format_raw).lower()

        self.audio_quality = str(self.data.get("audio_quality", "0"))
        self.extra_args = self.data.get("extra_args", "")

    def _resolve_exe(self, path):
        """Resolve executable path, finding it in PATH if needed"""
        if not path:
            return ""

        # If it looks like a bare command name (no path separators)
        if "/" not in path and "\\" not in path:
            # Try to find it in PATH
            found = which(path)
            if found:
                return found
            # If not found in PATH, return as-is (might still work with shell=True)
            return path

        # It's a path - expand home directory if needed
        if self.os_type == "linux" and path.startswith("~"):
            path = os.path.expanduser(path)

        return str(Path(path).resolve())
