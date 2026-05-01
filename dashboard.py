import streamlit as st
import time
import subprocess
import os
import shutil
from pathlib import Path
from datetime import datetime
import json

from src.ConfigManager import ConfigManager
from src.StateManager import StateManager
from src.PlaylistResolver import PlaylistResolver
from src.DownloadEngine import DownloadEngine
from src.WhisperLyricsEngine import WhisperLyricsEngine
from src.YtdlpManager import YtdlpManager

# --- Streamlit Page Config ---
st.set_page_config(
    page_title="YT Music Sync",
    page_icon="🎵",
    layout="wide",
    initial_sidebar_state="expanded",
)

# --- Custom Styling ---
st.markdown(
    """
    <style>
    .main { background-color: #0e1117; }
    .stMetric { 
        background-color: #161b22; 
        padding: 15px; 
        border-radius: 10px; 
        border: 1px solid #30363d;
        box-shadow: 0 2px 8px rgba(0,0,0,0.2);
    }
    .playlist-card {
        background-color: #161b22;
        padding: 20px;
        border-radius: 12px;
        border: 1px solid #30363d;
        margin-bottom: 15px;
        transition: all 0.3s ease;
        box-shadow: 0 2px 8px rgba(0,0,0,0.2);
    }
    .playlist-card:hover {
        border-color: #58a6ff;
        transform: translateY(-2px);
        box-shadow: 0 4px 16px rgba(88,166,255,0.2);
    }
    .status-badge {
        padding: 4px 12px;
        border-radius: 20px;
        font-size: 0.75rem;
        font-weight: 600;
        text-transform: uppercase;
        display: inline-block;
    }
    .status-completed { background-color: #238636; color: white; }
    .status-pending { background-color: #af8500; color: white; }
    .status-failed { background-color: #da3633; color: white; }
    .channel-info {
        background: linear-gradient(135deg, #1a1f2e 0%, #161b22 100%);
        padding: 20px;
        border-radius: 12px;
        border: 1px solid #30363d;
        margin-bottom: 20px;
    }
    .stat-card {
        background-color: #1a1f2e;
        padding: 15px;
        border-radius: 8px;
        border-left: 4px solid #58a6ff;
    }
    </style>
""",
    unsafe_allow_html=True,
)


# --- Helper Functions ---
@st.cache_data(ttl=300)  # Cache for 5 minutes
def get_ytdlp_version(path):
    try:
        res = subprocess.run(
            [path, "--version"], capture_output=True, text=True, shell=False, timeout=5
        )
        return res.stdout.strip()
    except Exception:
        return "Not found"


@st.cache_data(ttl=60)  # Cache for 1 minute
def get_disk_usage(path):
    try:
        total, used, free = shutil.disk_usage(path)
        return {
            "used_gb": used // (2**30),
            "total_gb": total // (2**30),
            "free_gb": free // (2**30),
            "percent": (used / total) * 100,
        }
    except Exception:
        return None


def count_download_archives(root_path):
    """Count total archive files and entries."""
    try:
        archive_files = list(Path(root_path).rglob("download_archive.txt"))
        total_entries = 0
        for archive in archive_files:
            with open(archive, "r", encoding="utf-8") as f:
                total_entries += len([line for line in f if line.strip()])
        return len(archive_files), total_entries
    except Exception:
        return 0, 0


def clear_download_archives(root_path):
    """Remove all download_archive.txt files."""
    try:
        archive_files = list(Path(root_path).rglob("download_archive.txt"))
        for archive in archive_files:
            archive.unlink()
        return len(archive_files)
    except Exception as e:
        st.error(f"Failed to clear archives: {e}")
        return 0


@st.cache_resource
def init_engines():
    """Initializes components once to handle state effectively."""
    try:
        config = ConfigManager()
        ytdlp_manager = YtdlpManager(config)
        ytdlp_manager.ensure_ready()
        state = StateManager()
        resolver = PlaylistResolver(config, state)
        engine = DownloadEngine(config)
        lyrics = WhisperLyricsEngine()
        return config, state, resolver, engine, lyrics, ytdlp_manager
    except Exception as e:
        st.error(f"Initialization Error: {e}")
        return None, None, None, None, None, None


def run_sync(p, config, state, engine, lyrics_engine):
    """Encapsulated sync logic for robustness."""
    with st.status(f"Syncing: {p['title']}", expanded=True) as status:
        status.write("📡 Fetching updates from YouTube...")
        success = engine.download(p)

        if not success:
            status.update(label=f"❌ Failed: {p['title']}", state="error")
            return False

        # Lyrics Step
        playlist_dir = config.root_path / engine.clean_filename(p["title"])
        status.write("🎤 Checking for missing lyrics...")

        audio_files = list(playlist_dir.glob("*.opus")) + list(
            playlist_dir.glob("*.mp3")
        )
        for audio_file in audio_files:
            lrc_file = audio_file.with_suffix(".lrc")
            if not lrc_file.exists():
                status.write(f"Transcribing: {audio_file.name}")
                try:
                    lyrics_engine.generate_lrc(audio_file)
                except Exception as e:
                    status.write(f"⚠️ Failed lyrics for {audio_file.name}: {e}")

        state.mark_completed(p["id"])
        status.update(label=f"✅ Completed: {p['title']}", state="complete")
        return True


# --- Main App ---
def main():
    config, state, resolver, engine, lyrics, ytdlp_manager = init_engines()
    if not config:
        return

    # Initialize session state
    if "playlists" not in st.session_state:
        st.session_state.playlists = None
    if "last_refresh" not in st.session_state:
        st.session_state.last_refresh = None

    # --- Sidebar ---
    with st.sidebar:
        st.title("🎵 YT Music Sync")
        st.caption("v2.0 - Enhanced Dashboard")

        st.divider()

        st.subheader("🖥️ System Status")

        # yt-dlp version
        ytdlp_version = get_ytdlp_version(config.ytdlp_path)
        st.metric("yt-dlp Version", ytdlp_version)

        if st.button(
            "Update yt-dlp Now",
            use_container_width=True,
            help="Check the latest stable release and replace the managed yt-dlp binary if needed",
        ):
            with st.spinner("Checking yt-dlp release..."):
                result = ytdlp_manager.ensure_ready(force_update=True)
                st.info(result["message"] or "yt-dlp update check completed")
                st.cache_data.clear()
                st.cache_resource.clear()
                time.sleep(1)
                st.rerun()

        # Disk usage with visual
        disk = get_disk_usage(config.root_path)
        if disk:
            st.metric(
                "Storage Used",
                f"{disk['used_gb']}GB / {disk['total_gb']}GB",
                delta=f"{disk['free_gb']}GB free",
            )
            st.progress(disk["percent"] / 100)

        # Archive stats
        archive_count, entry_count = count_download_archives(config.root_path)
        st.metric(
            "Archive Files", f"{archive_count} files", delta=f"{entry_count} entries"
        )

        st.divider()
        st.subheader("⚡ Quick Actions")

        # Refresh playlists
        if st.button(
            "🔄 Refresh Playlists",
            use_container_width=True,
            help="Reload playlist data from source",
        ):
            st.session_state.playlists = None
            st.session_state.last_refresh = datetime.now()
            st.rerun()

        # Sync all
        if st.button("🚀 Sync All Pending", use_container_width=True, type="primary"):
            st.session_state.sync_all = True

        # Clear archives
        if st.button(
            "📦 Clear Download Archives",
            use_container_width=True,
            help="Remove all download_archive.txt files (forces re-check of all songs)",
        ):
            with st.spinner("Clearing archives..."):
                cleared = clear_download_archives(config.root_path)
                if cleared > 0:
                    st.success(f"✅ Cleared {cleared} archive files!")
                    time.sleep(1)
                    st.rerun()
                else:
                    st.info("No archives found to clear")

        # Clear state
        if st.button(
            "🗑️ Reset Download State",
            use_container_width=True,
            help="Clear completion tracking (doesn't delete files)",
        ):
            if os.path.exists("download_state.json"):
                os.remove("download_state.json")
                st.success("State cleared!")
                time.sleep(1)
                st.rerun()

        st.divider()

        # Last refresh time
        if st.session_state.last_refresh:
            st.caption(
                f"Last refresh: {st.session_state.last_refresh.strftime('%H:%M:%S')}"
            )

    # --- Header ---
    st.title("📊 Playlist Synchronization Dashboard")

    # --- Load Playlists (with caching) ---
    if st.session_state.playlists is None:
        with st.spinner("🔍 Resolving playlists..."):
            start_time = time.time()

            if config.input_method == "channel":
                playlists = resolver.from_channel()
            elif config.input_method == "playlist_file":
                playlists = resolver.from_file()
            else:
                playlists = [
                    resolver.get_playlist_info(url) for url in config.playlist_urls
                ]

            playlists = [p for p in playlists if p]
            st.session_state.playlists = playlists
            st.session_state.last_refresh = datetime.now()

            load_time = time.time() - start_time
            st.toast(
                f"✅ Loaded {len(playlists)} playlists in {load_time:.2f}s", icon="⚡"
            )

    playlists = st.session_state.playlists

    # --- Channel Info Display ---
    channel_info = state.get_channel_info()
    if channel_info and channel_info.get("channel"):
        st.markdown(
            f"""
            <div class="channel-info">
                <h3>🎭 Channel: {channel_info.get('channel', 'Unknown')}</h3>
                <p style="color: #8b949e; margin: 5px 0;">
                    <strong>Channel ID:</strong> {channel_info.get('channel_id', 'N/A')} | 
                    <strong>Total Playlists:</strong> {channel_info.get('playlist_count', len(playlists))}
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )

    # --- Stats Cards ---
    completed_ids = [p["id"] for p in playlists if state.is_completed(p["id"])]
    pending = [p for p in playlists if p["id"] not in completed_ids]

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("📚 Total Playlists", len(playlists), help="All tracked playlists")

    with col2:
        st.metric(
            "✅ Up to Date",
            len(completed_ids),
            delta=(
                f"{(len(completed_ids)/len(playlists)*100):.1f}%" if playlists else "0%"
            ),
            help="Playlists already synced",
        )

    with col3:
        st.metric(
            "⏳ Pending",
            len(pending),
            delta=f"-{len(pending)}" if pending else "0",
            delta_color="inverse",
            help="Playlists needing sync",
        )

    with col4:
        stats = state.get_stats()
        st.metric(
            "💾 Cached Info",
            stats.get("total_playlists", 0),
            help="Playlists with cached metadata",
        )

    st.divider()

    # --- Tabs ---
    tab_overview, tab_pending, tab_completed, tab_settings = st.tabs(
        ["📊 All Playlists", "⏳ Pending Sync", "✅ Completed", "⚙️ Settings"]
    )

    with tab_overview:
        # Search and filters
        col_search, col_sort = st.columns([3, 1])

        with col_search:
            search = st.text_input(
                "🔍 Search Playlists",
                placeholder="Type to filter playlists...",
                key="search_all",
            )

        with col_sort:
            sort_option = st.selectbox(
                "Sort by",
                [
                    "Name (A-Z)",
                    "Name (Z-A)",
                    "Status (Pending First)",
                    "Status (Completed First)",
                ],
                key="sort_all",
            )

        # Apply filters and sorting
        filtered = playlists.copy()
        if search:
            filtered = [p for p in filtered if search.lower() in p["title"].lower()]

        if "Z-A" in sort_option:
            filtered.sort(key=lambda x: x["title"], reverse=True)
        elif "A-Z" in sort_option:
            filtered.sort(key=lambda x: x["title"])
        elif "Pending First" in sort_option:
            filtered.sort(key=lambda x: (state.is_completed(x["id"]), x["title"]))
        elif "Completed First" in sort_option:
            filtered.sort(key=lambda x: (not state.is_completed(x["id"]), x["title"]))

        st.caption(f"Showing {len(filtered)} of {len(playlists)} playlists")

        # Playlist cards in grid
        cols = st.columns(2)
        for i, p in enumerate(filtered):
            is_done = state.is_completed(p["id"])
            col_idx = i % 2

            with cols[col_idx]:
                st.markdown(
                    f"""
                    <div class="playlist-card">
                        <span class="status-badge status-{'completed' if is_done else 'pending'}">
                            {'✓ Synced' if is_done else '⏳ Pending'}
                        </span>
                        <h3 style="margin: 10px 0 5px 0;">{p['title']}</h3>
                        <code style="font-size: 0.7rem; color: #8b949e;">{p['id']}</code>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

                btn_col1, btn_col2, btn_col3 = st.columns([2, 2, 1])

                if btn_col1.button(
                    "🔄 Sync" if is_done else "⬇️ Download",
                    key=f"btn_all_{p['id']}",
                    use_container_width=True,
                    type="secondary" if is_done else "primary",
                ):
                    run_sync(p, config, state, engine, lyrics)
                    st.session_state.playlists = None  # Force refresh
                    st.rerun()

                btn_col2.link_button("🔗 YouTube", p["url"], use_container_width=True)

                if btn_col3.button("ℹ️", key=f"info_{p['id']}", help="Show details"):
                    st.session_state[f"show_info_{p['id']}"] = not st.session_state.get(
                        f"show_info_{p['id']}", False
                    )

                # Expandable info
                if st.session_state.get(f"show_info_{p['id']}", False):
                    with st.expander("Details", expanded=True):
                        st.json(p)

    with tab_pending:
        st.subheader(f"⏳ Pending Sync ({len(pending)} playlists)")

        if not pending:
            st.info("🎉 All playlists are up to date!")
        else:
            if st.button("🚀 Sync All Pending Playlists", type="primary"):
                progress_bar = st.progress(0)
                for idx, p in enumerate(pending):
                    run_sync(p, config, state, engine, lyrics)
                    progress_bar.progress((idx + 1) / len(pending))
                st.success("✅ All playlists synced!")
                st.session_state.playlists = None
                time.sleep(1)
                st.rerun()

            for p in pending:
                with st.container():
                    col1, col2 = st.columns([4, 1])
                    col1.write(f"**{p['title']}**")
                    if col2.button("Sync", key=f"btn_pending_{p['id']}"):
                        run_sync(p, config, state, engine, lyrics)
                        st.session_state.playlists = None
                        st.rerun()

    with tab_completed:
        st.subheader(f"✅ Completed ({len(completed_ids)} playlists)")

        completed_playlists = [p for p in playlists if state.is_completed(p["id"])]

        for p in completed_playlists:
            with st.container():
                col1, col2, col3 = st.columns([3, 1, 1])
                col1.write(f"**{p['title']}**")
                if col2.button("Re-sync", key=f"btn_completed_{p['id']}"):
                    run_sync(p, config, state, engine, lyrics)
                    st.rerun()
                col3.link_button("View", p["url"], key=f"link_completed_{p['id']}")

    with tab_settings:
        col1, col2 = st.columns(2)

        with col1:
            st.subheader("📁 Project Configuration")
            st.caption("Current settings from `config.yml`")

            with st.expander("View Configuration", expanded=False):
                st.json(config.data)

        with col2:
            st.subheader("💾 Internal State")
            st.caption("Download tracking from `download_state.json`")

            stats = state.get_stats()
            st.markdown(
                f"""
                <div class="stat-card">
                    <strong>Total Playlists:</strong> {stats['total_playlists']}<br>
                    <strong>Completed:</strong> {stats['completed_playlists']}<br>
                    <strong>Partial Downloads:</strong> {stats['partial_downloads']}<br>
                    <strong>Channel Cached:</strong> {'Yes ✓' if stats['channel_cached'] else 'No ✗'}
                </div>
                """,
                unsafe_allow_html=True,
            )

            with st.expander("View Raw State", expanded=False):
                st.json(state.state)

    # --- Background Sync All Logic ---
    if st.session_state.get("sync_all", False):
        st.session_state.sync_all = False
        if not pending:
            st.toast("ℹ️ Nothing to sync - all playlists are up to date!", icon="ℹ️")
        else:
            progress_bar = st.progress(0)
            status_text = st.empty()

            for idx, p in enumerate(pending):
                status_text.text(f"Syncing {idx + 1}/{len(pending)}: {p['title']}")
                run_sync(p, config, state, engine, lyrics)
                progress_bar.progress((idx + 1) / len(pending))

            st.success("🎉 All playlists synced successfully!")
            st.session_state.playlists = None
            time.sleep(2)
            st.rerun()


if __name__ == "__main__":
    main()
