import sys
import time
from src.ConfigManager import ConfigManager
from src.StateManager import StateManager
from src.PlaylistResolver import PlaylistResolver
from src.DownloadEngine import DownloadEngine


class YouTubeApp:
    """
    Orchestrates the components to run the application via Command Line.
    This uses the same logic as dashboard.py but formatted for terminal output.
    """

    def __init__(self):
        try:
            print("Initializing components...")
            self.config = ConfigManager()
            print(f"✓ Config loaded (Method: {self.config.input_method})")
            print(f"✓ yt-dlp path: {self.config.ytdlp_path}")
            print(f"✓ Root path: {self.config.root_path}")
            print(f"✓ Audio format: {self.config.audio_format}")
            print(f"✓ Audio quality: {self.config.audio_quality}")

            self.state = StateManager()
            self.resolver = PlaylistResolver(self.config, self.state)
            self.engine = DownloadEngine(self.config)
            print("✓ All components initialized\n")
        except Exception as e:
            print(f"Failed to initialize components: {e}")
            import traceback

            traceback.print_exc()
            sys.exit(1)

    def run(self):
        print("\n" + "=" * 60)
        print("🎵 YouTube Music Sync (CLI Mode)")
        print("=" * 60 + "\n")

        # 1. Resolve Target Playlists based on Config Method
        print(f"Input Method: {self.config.input_method}")

        # Logic for resolving playlists
        if self.config.input_method == "channel":
            playlists = self.resolver.from_channel()
        elif self.config.input_method == "playlist_file":
            playlists = self.resolver.from_file()
        else:
            playlists = [
                self.resolver.get_playlist_info(url)
                for url in self.config.playlist_urls
            ]

        # Filter out failed metadata fetches
        playlists = [p for p in playlists if p]
        if not playlists:
            print("❌ No playlists found! Check your config or internet connection.")
            return

        # 2. Filtering and Reporting
        remaining = [p for p in playlists if not self.state.is_completed(p["id"])]

        print(f"\n📊 Summary:")
        print(f"   Total Playlists: {len(playlists)}")
        print(f"   Already Synced:  {len(playlists) - len(remaining)}")
        print(f"   Pending Sync:    {len(remaining)}")

        if not remaining:
            print("\n✅ All playlists are up to date!")
            return

        # Ask for confirmation
        print(f"\n⚠️  About to sync {len(remaining)} playlists.")
        response = input("Continue? (y/n): ").lower().strip()
        if response not in ["y", "yes"]:
            print("Cancelled by user.")
            return

        # 3. Processing Loop
        print("\n🚀 Starting Sync...")
        print("=" * 60)

        success_count = 0
        fail_count = 0

        for i, p in enumerate(remaining, 1):
            print(f"\n{'='*60}")
            print(f"[{i}/{len(remaining)}] Processing: {p['title']}")
            print(f"ID: {p['id']}")
            print(f"URL: {p['url']}")
            print(f"{'='*60}")

            try:
                success = self.engine.download(p)

                if success:
                    self.state.mark_completed(p["id"])
                    print(f"\n✅ SUCCESS: {p['title']} completed and marked as done")
                    success_count += 1
                    # Brief pause to be polite to the API
                    time.sleep(2)
                else:
                    print(
                        f"\n❌ FAILED: {p['title']} - download did not complete successfully"
                    )
                    fail_count += 1

            except Exception as e:
                print(f"\n💥 EXCEPTION during sync of {p['title']}: {e}")
                import traceback

                traceback.print_exc()
                fail_count += 1

        print("\n" + "=" * 60)
        print("✨ All tasks finished!")
        print(f"   Successful: {success_count}")
        print(f"   Failed: {fail_count}")
        print("=" * 60 + "\n")


if __name__ == "__main__":
    try:
        app = YouTubeApp()
        app.run()
    except KeyboardInterrupt:
        print("\n\n🛑 Interrupted by user. Progress up to this point has been saved.")
        sys.exit(0)
    except Exception as e:
        print(f"\n💥 A fatal error occurred: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
