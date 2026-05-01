import json
import os
import shutil
import stat
import subprocess
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

from src.ConfigManager import ConfigManager
from src.logging_utils import get_logger

logger = get_logger(__name__)


class YtdlpManager:
    """Handles yt-dlp version checks, updates, and JS runtime configuration."""

    RELEASE_API_URL = "https://api.github.com/repos/yt-dlp/yt-dlp/releases/latest"
    DEFAULT_TIMEOUT = 30

    def __init__(self, config: ConfigManager):
        self.config = config

    def get_current_version(self) -> str | None:
        """Return the installed yt-dlp version, or None if it cannot be read."""
        try:
            result = subprocess.run(
                [self.config.ytdlp_path, "--version"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=10,
                check=True,
                shell=False,
            )
            version = result.stdout.strip()
            return version or None
        except Exception as exc:
            logger.warning(f"Unable to read yt-dlp version from {self.config.ytdlp_path}: {exc}")
            return None

    def get_js_runtime_args(self) -> list[str]:
        """Return CLI args needed for yt-dlp's external JS runtime support."""
        configured = (self.config.js_runtimes or "").strip()
        if configured:
            return ["--js-runtimes", configured]

        candidates = [
            ("deno", "deno"),
            ("node", "node"),
            ("bun", "bun"),
            ("qjs", "quickjs"),
            ("quickjs", "quickjs"),
        ]

        for binary_name, runtime_name in candidates:
            binary_path = shutil.which(binary_name)
            if binary_path:
                value = runtime_name
                if runtime_name != "deno":
                    value = f"{runtime_name}:{binary_path}"
                return ["--js-runtimes", value]

        return []

    def build_command(self, *args: str) -> list[str]:
        """Build a yt-dlp command with JS runtime support when available."""
        return [self.config.ytdlp_path, *self.get_js_runtime_args(), *args]

    def ensure_ready(self, force_update: bool = False) -> dict:
        """
        Optionally update yt-dlp, then report the current executable state.
        Returns a small status dict suitable for logging/UI.
        """
        update_result = {
            "updated": False,
            "checked": False,
            "current_version": self.get_current_version(),
            "latest_version": None,
            "message": "",
        }

        if self.config.auto_update_ytdlp:
            update_result = self.update_if_needed(force=force_update)

        js_args = self.get_js_runtime_args()
        if js_args:
            logger.info(f"yt-dlp JS runtime enabled via: {js_args[-1]}")
        else:
            logger.warning(
                "No supported JS runtime detected for yt-dlp. Install Deno or ensure Node is in PATH."
            )

        return update_result

    def update_if_needed(self, force: bool = False) -> dict:
        """Check the latest stable release and replace the managed binary if newer."""
        result = {
            "updated": False,
            "checked": False,
            "current_version": self.get_current_version(),
            "latest_version": None,
            "message": "",
        }

        if not self._is_managed_binary():
            result["message"] = "Skipping yt-dlp auto-update because the executable is managed outside this project."
            logger.info(result["message"])
            return result

        if not force and not self._should_check_for_update():
            result["message"] = "Skipping yt-dlp update check until the next scheduled window."
            logger.debug(result["message"])
            return result

        try:
            release = self._fetch_latest_release()
            latest_version = release["tag_name"]
            result["checked"] = True
            result["latest_version"] = latest_version

            needs_update = force or self._version_tuple(result["current_version"]) < self._version_tuple(
                latest_version
            )

            if not needs_update:
                result["message"] = f"yt-dlp is already up to date ({latest_version})."
                logger.info(result["message"])
                self._write_update_state(
                    {
                        "last_checked_utc": self._now_iso(),
                        "current_version": result["current_version"],
                        "latest_version": latest_version,
                    }
                )
                return result

            asset = self._select_release_asset(release)
            self._download_binary(asset["browser_download_url"])
            result["updated"] = True
            result["current_version"] = self.get_current_version() or latest_version
            result["message"] = f"Updated yt-dlp to {result['current_version']}."
            logger.info(result["message"])
            self._write_update_state(
                {
                    "last_checked_utc": self._now_iso(),
                    "current_version": result["current_version"],
                    "latest_version": latest_version,
                }
            )
            return result

        except Exception as exc:
            result["message"] = f"yt-dlp update check failed: {exc}"
            logger.warning(result["message"])
            self._write_update_state(
                {
                    "last_checked_utc": self._now_iso(),
                    "current_version": result["current_version"],
                    "latest_version": result["latest_version"],
                    "last_error": str(exc),
                }
            )
            return result

    def _fetch_latest_release(self) -> dict:
        response = requests.get(
            self.RELEASE_API_URL,
            headers={"Accept": "application/vnd.github+json", "User-Agent": "youtube-music-sync"},
            timeout=self.DEFAULT_TIMEOUT,
        )
        response.raise_for_status()
        return response.json()

    def _select_release_asset(self, release: dict) -> dict:
        target_name = "yt-dlp.exe" if self.config.os_type == "windows" else "yt-dlp"
        for asset in release.get("assets", []):
            if asset.get("name") == target_name:
                return asset
        raise RuntimeError(f"Release asset '{target_name}' not found in latest yt-dlp release")

    def _download_binary(self, url: str) -> None:
        target = Path(self.config.ytdlp_path)
        target.parent.mkdir(parents=True, exist_ok=True)

        with requests.get(url, stream=True, timeout=self.DEFAULT_TIMEOUT) as response:
            response.raise_for_status()
            with tempfile.NamedTemporaryFile(
                delete=False,
                dir=target.parent,
                prefix=f"{target.name}.",
                suffix=".download",
            ) as temp_file:
                for chunk in response.iter_content(chunk_size=1024 * 256):
                    if chunk:
                        temp_file.write(chunk)
                temp_path = Path(temp_file.name)

        if self.config.os_type != "windows":
            current_mode = temp_path.stat().st_mode
            temp_path.chmod(current_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

        os.replace(temp_path, target)

    def _is_managed_binary(self) -> bool:
        configured_path = getattr(self.config, "ytdlp_path_input", self.config.ytdlp_path)
        return bool(configured_path) and ("/" in configured_path or "\\" in configured_path)

    def _should_check_for_update(self) -> bool:
        state_path = self._state_path()
        if not state_path.exists():
            return True

        try:
            with open(state_path, "r", encoding="utf-8") as handle:
                state = json.load(handle)
            last_checked_raw = state.get("last_checked_utc")
            if not last_checked_raw:
                return True

            last_checked = datetime.fromisoformat(last_checked_raw)
            next_check = last_checked + timedelta(hours=self.config.ytdlp_update_interval_hours)
            return datetime.now(timezone.utc) >= next_check
        except Exception:
            return True

    def _write_update_state(self, state: dict) -> None:
        state_path = self._state_path()
        try:
            state_path.parent.mkdir(parents=True, exist_ok=True)
            with open(state_path, "w", encoding="utf-8") as handle:
                json.dump(state, handle, indent=2)
        except OSError as exc:
            logger.warning(f"Unable to persist yt-dlp update state to {state_path}: {exc}")

    def _state_path(self) -> Path:
        target = Path(self.config.ytdlp_path)
        state_dir = self.config.root_path / ".youtube-music-sync"
        return state_dir / f"{target.stem}.version.json"

    def _now_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _version_tuple(self, version: str | None) -> tuple[int, ...]:
        if not version:
            return tuple()

        version = version.strip()
        parts = []
        for piece in version.split("."):
            if piece.isdigit():
                parts.append(int(piece))
            else:
                digits = "".join(ch for ch in piece if ch.isdigit())
                if digits:
                    parts.append(int(digits))
        return tuple(parts)
