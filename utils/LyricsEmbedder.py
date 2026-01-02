import os
from pathlib import Path
from mutagen.flac import FLAC
from mutagen.mp4 import MP4
from mutagen.id3 import ID3, USLT, ID3NoHeaderError
from src.logging_utils import get_logger

logger = get_logger(__name__)


class LyricsEmbedder:
    """
    Embeds LRC files into audio files (MP3, FLAC, M4A, OPUS) for compatibility
    with music servers like Navidrome.

    Usage:
        embedder = LyricsEmbedder()
        embedder.embed_lyrics_for_file(audio_file_path)
        # or
        embedder.embed_lyrics_for_directory(directory_path)
    """

    def __init__(self):
        """Initialize the LyricsEmbedder."""
        pass

    def has_embedded_lyrics(self, audio_path: Path) -> bool:
        """
        Check if an audio file already has embedded lyrics.

        Args:
            audio_path: Path to the audio file

        Returns:
            True if lyrics are already embedded, False otherwise
        """
        try:
            if audio_path.suffix.lower() == ".flac":
                audio = FLAC(str(audio_path))
                return "LYRICS" in audio or "UNSYNCEDLYRICS" in audio

            elif audio_path.suffix.lower() in [".m4a", ".mp4"]:
                audio = MP4(str(audio_path))
                return "\xa9lyr" in audio.tags if audio.tags else False

            elif audio_path.suffix.lower() in [".mp3", ".opus"]:
                try:
                    audio = ID3(str(audio_path))
                    # Check for USLT (Unsynchronized Lyrics) frames
                    for key in audio.keys():
                        if key.startswith("USLT"):
                            return True
                    return False
                except ID3NoHeaderError:
                    return False

        except Exception as e:
            logger.warning(f"Error checking embedded lyrics for {audio_path.name}: {e}")
            return False

    def embed_lrc_to_file(self, audio_path: Path, skip_if_exists: bool = True) -> bool:
        """
        Embed LRC file content into a single audio file.

        Args:
            audio_path: Path to the audio file
            skip_if_exists: If True, skip files that already have embedded lyrics

        Returns:
            True if lyrics were successfully embedded, False otherwise
        """
        # Check for corresponding LRC file
        lrc_path = audio_path.with_suffix(".lrc")

        if not lrc_path.exists():
            logger.debug(f"No LRC file found for: {audio_path.name}")
            return False

        # Skip if lyrics already embedded and skip_if_exists is True
        if skip_if_exists and self.has_embedded_lyrics(audio_path):
            logger.debug(f"Lyrics already embedded, skipping: {audio_path.name}")
            return False

        try:
            # Read LRC content
            with open(lrc_path, "r", encoding="utf-8") as f:
                lrc_content = f.read()

            # Embed based on file type
            if audio_path.suffix.lower() == ".flac":
                audio = FLAC(str(audio_path))
                audio["LYRICS"] = lrc_content
                audio.save()
                logger.info(f"✓ Embedded lyrics into FLAC: {audio_path.name}")
                return True

            elif audio_path.suffix.lower() in [".m4a", ".mp4"]:
                audio = MP4(str(audio_path))
                if audio.tags is None:
                    audio.add_tags()
                audio.tags["\xa9lyr"] = lrc_content
                audio.save()
                logger.info(f"✓ Embedded lyrics into M4A: {audio_path.name}")
                return True

            elif audio_path.suffix.lower() in [".mp3", ".opus"]:
                try:
                    audio = ID3(str(audio_path))
                except ID3NoHeaderError:
                    # Create new ID3 tag if none exists
                    audio = ID3()

                # Add USLT frame (Unsynchronized Lyrics)
                # Using language code 'eng' and empty description
                audio.add(USLT(encoding=3, lang="eng", desc="", text=lrc_content))
                audio.save(str(audio_path), v2_version=3)
                logger.info(f"✓ Embedded lyrics into MP3/OPUS: {audio_path.name}")
                return True

            else:
                logger.warning(f"Unsupported audio format: {audio_path.suffix}")
                return False

        except Exception as e:
            logger.error(f"Failed to embed lyrics for {audio_path.name}: {e}")
            return False

    def embed_lyrics_for_directory(
        self, directory: Path, recursive: bool = True, skip_if_exists: bool = True
    ) -> dict:
        """
        Embed LRC files for all audio files in a directory.

        Args:
            directory: Path to the directory
            recursive: If True, process subdirectories
            skip_if_exists: If True, skip files that already have embedded lyrics

        Returns:
            Dictionary with statistics: total, embedded, skipped, failed
        """
        stats = {"total": 0, "embedded": 0, "skipped": 0, "failed": 0}

        # Supported audio extensions
        audio_extensions = [".mp3", ".flac", ".m4a", ".mp4", ".opus"]

        # Collect all audio files
        audio_files = []
        if recursive:
            for ext in audio_extensions:
                audio_files.extend(directory.rglob(f"*{ext}"))
        else:
            for ext in audio_extensions:
                audio_files.extend(directory.glob(f"*{ext}"))

        stats["total"] = len(audio_files)

        if not audio_files:
            logger.info(f"No audio files found in: {directory}")
            return stats

        logger.info(f"Processing {stats['total']} audio files in: {directory}")

        for audio_path in audio_files:
            lrc_path = audio_path.with_suffix(".lrc")

            if not lrc_path.exists():
                stats["skipped"] += 1
                continue

            if skip_if_exists and self.has_embedded_lyrics(audio_path):
                stats["skipped"] += 1
                continue

            if self.embed_lrc_to_file(audio_path, skip_if_exists=False):
                stats["embedded"] += 1
            else:
                stats["failed"] += 1

        logger.info(
            f"Lyrics embedding complete - "
            f"Total: {stats['total']}, "
            f"Embedded: {stats['embedded']}, "
            f"Skipped: {stats['skipped']}, "
            f"Failed: {stats['failed']}"
        )

        return stats


if __name__ == "__main__":
    # Standalone usage example
    import sys

    if len(sys.argv) < 2:
        print("Usage: python LyricsEmbedder.py <directory_path>")
        sys.exit(1)

    directory = Path(sys.argv[1])

    if not directory.exists() or not directory.is_dir():
        print(f"Error: Invalid directory path: {directory}")
        sys.exit(1)

    embedder = LyricsEmbedder()
    stats = embedder.embed_lyrics_for_directory(directory)

    print(f"\n=== Lyrics Embedding Summary ===")
    print(f"Total audio files: {stats['total']}")
    print(f"Lyrics embedded: {stats['embedded']}")
    print(f"Skipped: {stats['skipped']}")
    print(f"Failed: {stats['failed']}")

    if stats["total"] > 0:
        percentage = (stats["embedded"] / stats["total"]) * 100
        print(f"Success rate: {percentage:.2f}%")
