import sys
import time
from datetime import datetime, timedelta
from src.ConfigManager import ConfigManager
from src.StateManager import StateManager
from src.PlaylistResolver import PlaylistResolver
from src.DownloadEngine import DownloadEngine
from src.WhisperLyricsEngine import WhisperLyricsEngine


class YouTubeApp:
    """
    Orchestrates the components to run the application automatically
    on a 12-hour schedule.
    """

    def __init__(self):
        try:
            print("Initializing components...")
            self.config = ConfigManager()
            print(f"✓ Config loaded (Method: {self.config.input_method})")
            print(f"✓ yt-dlp path: {self.config.ytdlp_path}")
            print(f"✓ Root path: {self.config.root_path}")

            self.state = StateManager()
            self.lyrics_engine = WhisperLyricsEngine()
            self.resolver = PlaylistResolver(self.config, self.state)
            self.engine = DownloadEngine(self.config)
            print("✓ All components initialized\n")
        except Exception as e:
            print(f"Failed to initialize components: {e}")
            import traceback

            traceback.print_exc()
            sys.exit(1)

    def perform_sync(self):
        """Single sync pass logic."""
        print(f"\n🔄 Sync started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 60)

        # 1. Resolve Target Playlists (Fetches latest songs from URLs/Channels)
        print(f"Input Method: {self.config.input_method}")
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
            print("❌ No playlists found! Check your config or internet connection.")
            return

        print(f"📊 Found {len(playlists)} playlists to check.")

        # 2. Processing Loop
        # Note: We no longer filter by 'self.state.is_completed' here.
        # This allows yt-dlp to check the playlist for new songs every 12 hours.
        success_count = 0
        fail_count = 0

        for i, p in enumerate(playlists, 1):
            print(f"\n[{i}/{len(playlists)}] Checking for updates: {p['title']}")

            try:
                # DownloadEngine handles skipping existing files via download_archive.txt
                success = self.engine.download(p)

                if success:
                    # Whisper lyrics fallback for any new songs
                    playlist_dir = self.config.root_path / self.engine.clean_filename(
                        p["title"]
                    )
                    for audio_file in playlist_dir.glob("*.opus"):
                        lrc_file = audio_file.with_suffix(".lrc")
                        if not lrc_file.exists():
                            try:
                                self.lyrics_engine.generate_lrc(audio_file)
                                print(f"   ✓ Lyrics generated for {audio_file.name}")
                            except Exception as e:
                                print(f"   ⚠️ Failed lyrics for {audio_file.name}: {e}")

                    success_count += 1
                else:
                    fail_count += 1

            except Exception as e:
                print(f"\n💥 EXCEPTION during sync of {p['title']}: {e}")
                fail_count += 1

        print("\n" + "=" * 60)
        print(f"✨ Sync Cycle Finished!")
        print(f"   Successful/Up-to-date: {success_count}")
        print(f"   Failed: {fail_count}")
        print("=" * 60)

    def run_forever(self):
        """Runs the sync every 12 hours."""
        INTERVAL = 12 * 60 * 60  # 12 Hours in seconds

        print("\n" + "=" * 60)
        print("🎵 YouTube Music Sync (Automated Mode)")
        print(f"Cycle Interval: 12 Hours")
        print("=" * 60 + "\n")

        while True:
            try:
                self.perform_sync()
            except Exception as e:
                print(f"⚠️ Unexpected error in main loop: {e}")

            next_run = datetime.now() + timedelta(seconds=INTERVAL)
            print(
                f"\n💤 Sleeping. Next sync scheduled for: {next_run.strftime('%Y-%m-%d %H:%M:%S')}"
            )
            time.sleep(INTERVAL)


if __name__ == "__main__":
    try:
        app = YouTubeApp()
        app.run_forever()
    except KeyboardInterrupt:
        print("\n\n🛑 Interrupted by user. Exiting...")
        sys.exit(0)
    except Exception as e:
        print(f"\n💥 A fatal error occurred: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
