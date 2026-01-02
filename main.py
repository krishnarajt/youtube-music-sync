import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from src.ConfigManager import ConfigManager
from src.StateManager import StateManager
from src.PlaylistResolver import PlaylistResolver
from src.DownloadEngine import DownloadEngine
from src.WhisperLyricsEngine import WhisperLyricsEngine
from utils.LyricsEmbedder import LyricsEmbedder
from src.logging_utils import get_logger
from utils.name_album_from_folders import NameAlbumFromFolders

logger = get_logger(__name__)


class YouTubeApp:
    """
    Orchestrates the components to run the application automatically
    on a 12-hour schedule.
    """

    def __init__(self):
        try:
            logger.info("Initializing components...")
            self.config = ConfigManager()
            logger.info(f"Config loaded (Method: {self.config.input_method})")
            logger.info(f"yt-dlp path: {self.config.ytdlp_path}")
            logger.info(f"Root path: {self.config.root_path}")

            self.state = StateManager()
            self.lyrics_engine = WhisperLyricsEngine()
            self.lyrics_embedder = LyricsEmbedder()
            self.resolver = PlaylistResolver(self.config, self.state)
            self.engine = DownloadEngine(self.config)
            logger.info("All components initialized")
        except Exception as e:
            logger.error(f"Failed to initialize components: {e}", exc_info=True)
            sys.exit(1)

    def run_album_naming(self) -> None:
        """
        Executes name_album_from_folders.py on the root download directory.
        This automatically tags all MP3 files with proper album/artist metadata.
        """
        try:
            from utils.name_album_from_folders import NameAlbumFromFolders

            logger.info(f"Running album naming on: {self.config.root_path}")
            namer = NameAlbumFromFolders(self.config.root_path)
            namer.run()
            logger.info("Album naming completed")
        except ImportError:
            logger.warning(
                "name_album_from_folders module not found; skipping album naming"
            )
        except Exception as e:
            logger.error(f"Album naming failed: {e}", exc_info=True)

    def process_playlist_lyrics_and_embedding(self, playlist_dir: Path) -> None:
        """
        Generate lyrics for audio files without LRC and embed existing LRC files.

        Args:
            playlist_dir: Path to the playlist directory
        """
        # Supported audio extensions
        audio_extensions = ["*.mp3", "*.opus", "*.m4a", "*.flac"]

        # Step 1: Generate missing lyrics using Whisper
        logger.info(f"Checking for missing lyrics in: {playlist_dir.name}")
        lyrics_generated = 0

        for ext in audio_extensions:
            for audio_file in playlist_dir.glob(ext):
                lrc_file = audio_file.with_suffix(".lrc")

                # Generate lyrics if LRC doesn't exist
                if not lrc_file.exists():
                    try:
                        logger.info(f"Generating lyrics for: {audio_file.name}")
                        self.lyrics_engine.generate_lrc(audio_file)
                        logger.info(f"✓ Lyrics generated for {audio_file.name}")
                        lyrics_generated += 1
                    except Exception as e:
                        logger.warning(
                            f"Failed to generate lyrics for {audio_file.name}: {e}"
                        )

        if lyrics_generated > 0:
            logger.info(f"Generated {lyrics_generated} new lyrics files")

        # Step 2: Embed LRC files into audio files
        logger.info(f"Embedding lyrics into audio files in: {playlist_dir.name}")

        try:
            stats = self.lyrics_embedder.embed_lyrics_for_directory(
                playlist_dir,
                recursive=False,  # Only process current directory
                skip_if_exists=True,  # Skip files that already have embedded lyrics
            )

            if stats["embedded"] > 0:
                logger.info(
                    f"✓ Embedded lyrics into {stats['embedded']} files "
                    f"({stats['skipped']} skipped, {stats['failed']} failed)"
                )
            else:
                logger.debug("No new lyrics to embed")

        except Exception as e:
            logger.error(f"Failed to embed lyrics for {playlist_dir.name}: {e}")

    def perform_sync(self):
        """Single sync pass logic."""
        logger.info(f"Sync started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        # 1. Resolve Target Playlists (Fetches latest songs from URLs/Channels)
        logger.info(f"Input Method: {self.config.input_method}")
        if self.config.input_method == "channel":
            playlists = self.resolver.from_channel()
        elif self.config.input_method == "playlist_file":
            playlists = self.resolver.from_file()
        else:
            playlists = [
                self.resolver.get_playlist_info(url)
                for url in self.config.playlist_urls
            ]

        playlists = [p for p in playlists if p]
        if not playlists:
            logger.warning(
                "No playlists found! Check your config or internet connection."
            )
            return

        logger.info(f"Found {len(playlists)} playlists to check.")

        # 2. Processing Loop
        # Note: We no longer filter by 'self.state.is_completed' here.
        # This allows yt-dlp to check the playlist for new songs every 12 hours.
        success_count = 0
        fail_count = 0

        for i, p in enumerate(playlists, 1):
            playlist_id = p["id"]
            playlist_title = p["title"]

            logger.info(
                f"[{i}/{len(playlists)}] Checking for updates: {playlist_title}"
            )

            try:
                # DownloadEngine handles skipping existing files via download_archive.txt
                success = self.engine.download(p)

                if success:
                    playlist_dir = self.config.root_path / self.engine.clean_filename(
                        playlist_title
                    )

                    # Process lyrics generation and embedding
                    self.process_playlist_lyrics_and_embedding(playlist_dir)

                    # Run album naming for this specific playlist
                    logger.info(f"Running album naming for: {playlist_title}")
                    try:
                        namer = NameAlbumFromFolders(self.config.root_path)
                        namer.run()
                        logger.info(f"✓ Album naming completed for: {playlist_title}")
                    except ImportError:
                        logger.warning("name_album_from_folders module not found")
                    except Exception as e:
                        logger.warning(f"Album naming failed for {playlist_title}: {e}")

                    # Mark playlist as completed after successful download
                    self.state.mark_completed(playlist_id)
                    logger.info(f"✓ Marked playlist as completed: {playlist_title}")
                    success_count += 1
                else:
                    logger.warning(f"✗ Download failed for: {playlist_title}")
                    fail_count += 1

            except Exception as e:
                logger.error(
                    f"Exception during sync of {playlist_title}: {e}", exc_info=True
                )
                fail_count += 1

        logger.info(
            f"Sync Cycle Finished! Successful: {success_count}, Failed: {fail_count}"
        )

    def run_forever(self):
        """Runs the sync every 12 hours."""
        INTERVAL = 12 * 60 * 60  # 12 Hours in seconds

        logger.info("YouTube Music Sync (Automated Mode) started")
        logger.info(f"Cycle Interval: 12 Hours")

        while True:
            try:
                self.perform_sync()
            except Exception as e:
                logger.error(f"Unexpected error in main loop: {e}", exc_info=True)

            next_run = datetime.now() + timedelta(seconds=INTERVAL)
            logger.info(
                f"Sleeping. Next sync scheduled for: {next_run.strftime('%Y-%m-%d %H:%M:%S')}"
            )
            time.sleep(INTERVAL)


if __name__ == "__main__":
    try:
        app = YouTubeApp()
        app.run_forever()
    except KeyboardInterrupt:
        logger.info("Interrupted by user. Exiting...")
        sys.exit(0)
    except Exception as e:
        logger.error(f"A fatal error occurred: {e}", exc_info=True)
        sys.exit(1)
