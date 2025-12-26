import streamlit as st
import time
import subprocess
from pathlib import Path

from src.ConfigManager import ConfigManager
from src.StateManager import StateManager
from src.PlaylistResolver import PlaylistResolver
from src.DownloadEngine import DownloadEngine
from src.WhisperLyricsEngine import WhisperLyricsEngine


# --- Streamlit Page Config ---
st.set_page_config(
    page_title="YT Music Sync Dashboard",
    page_icon="🎵",
    layout="wide",
    initial_sidebar_state="expanded",
)


def get_ytdlp_version(path):
    try:
        res = subprocess.run(
            [path, "--version"],
            capture_output=True,
            text=True,
            shell=True,
        )
        return res.stdout.strip()
    except Exception:
        return "Not found"


def main():
    st.title("🎵 YouTube Music Sync Dashboard")

    # --- Initialize core components ---
    try:
        config = ConfigManager()
        state = StateManager()
        resolver = PlaylistResolver(config, state)
        engine = DownloadEngine(config)
        lyrics_engine = WhisperLyricsEngine()
    except Exception as e:
        st.error(f"Failed to initialize components: {e}")
        return

    # --- Sidebar ---
    with st.sidebar:
        st.header("⚙️ System Status")
        st.metric("yt-dlp version", get_ytdlp_version(config.ytdlp_path))
        st.write(f"**OS Type:** `{config.os_type.capitalize()}`")
        st.write(f"**Root Path:** `{config.root_path}`")

        st.divider()
        if st.button("🔄 Refresh Data", use_container_width=True):
            st.rerun()

    # --- Tabs ---
    tab_progress, tab_logs, tab_settings = st.tabs(
        ["📊 Progress", "📝 Activity Logs", "⚙️ Config & State"]
    )

    # =====================
    # Progress Tab
    # =====================
    with tab_progress:
        with st.spinner("Loading playlist metadata..."):
            if config.input_method == "channel":
                playlists = resolver.from_channel()
            elif config.input_method == "playlist_file":
                playlists = resolver.from_file()
            else:
                playlists = [
                    resolver.get_playlist_info(url) for url in config.playlist_urls
                ]

        playlists = [p for p in playlists if p]

        if not playlists:
            st.warning("No playlists found.")
            return

        completed = [p for p in playlists if state.is_completed(p["id"])]
        pending = [p for p in playlists if not state.is_completed(p["id"])]

        c1, c2, c3 = st.columns(3)
        c1.metric("Total", len(playlists))
        c2.metric("Completed", len(completed))
        c3.metric("Pending", len(pending), delta_color="inverse")

        progress = len(completed) / len(playlists)
        st.progress(progress, text=f"{int(progress * 100)}% synced")

        st.divider()
        st.subheader("Playlist Catalog")

        search = st.text_input("🔍 Search playlists...", "")

        for p in playlists:
            if search.lower() not in p["title"].lower():
                continue

            is_done = state.is_completed(p["id"])
            label = "✅ COMPLETED" if is_done else "⏳ PENDING"

            with st.expander(f"{label} | {p['title']}"):
                col_info, col_action = st.columns([3, 1])

                with col_info:
                    st.write(f"**Playlist ID:** `{p['id']}`")
                    st.write(f"[Open on YouTube]({p['url']})")

                with col_action:
                    btn = "Re-sync" if is_done else "Start Sync"
                    if st.button(btn, key=f"sync_{p['id']}", use_container_width=True):

                        with st.status(
                            f"Syncing {p['title']}...",
                            expanded=True,
                        ) as status:

                            success = engine.download(p)

                            if not success:
                                status.update(
                                    label="Download failed",
                                    state="error",
                                )
                                st.error("Download failed.")
                                return

                            # ---- Whisper lyrics step ----
                            playlist_dir = config.root_path / engine.clean_filename(
                                p["title"]
                            )

                            audio_ext = f"*.opus"

                            missing_tracks = [
                                f
                                for f in playlist_dir.glob(audio_ext)
                                if not f.with_suffix(".lrc").exists()
                            ]

                            if missing_tracks:
                                status.write(
                                    f"🎤 Generating lyrics for {len(missing_tracks)} tracks..."
                                )

                            for audio_file in missing_tracks:
                                try:
                                    lyrics_engine.generate_lrc(audio_file)
                                    status.write(f"✓ Lyrics: {audio_file.name}")
                                except Exception as e:
                                    status.write(f"⚠️ Lyrics failed: {audio_file.name}")

                            state.mark_completed(p["id"])
                            status.update(
                                label="Sync complete",
                                state="complete",
                            )

                            st.toast(
                                f"Finished {p['title']}",
                                icon="✅",
                            )
                            time.sleep(1)
                            st.rerun()

    # =====================
    # Logs Tab
    # =====================
    with tab_logs:
        st.subheader("Activity Logs")
        st.info("Per-playlist logs appear during sync.")

    # =====================
    # Settings Tab
    # =====================
    with tab_settings:
        c1, c2 = st.columns(2)
        with c1:
            st.subheader("config.yml")
            st.json(config.data)
        with c2:
            st.subheader("download_state.json")
            st.json(state.state)


if __name__ == "__main__":
    main()
