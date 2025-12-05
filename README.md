# youtube-music-sync
Script and docker that runs periodically and syncs youtube playlists with local folders, and edits the metadata of each song as required by your music client of choice.


# The Problem:
1. I would like to maintain a local copy of my youtube playlists for serving on my NAS as a backup in case youtube decides to remove any of the songs in that playlist or the creator makes the video private.
2. I want this collection to remain in sync with my youtube music and do not want to take the manual effort to download each playlist and check which song is new, then update its metadata. 
3. I may want to apply some post processing on this music
4. Downloading too many songs at a time could result in errors. This should be fixed as the script runs the next time, but we shouldnt re download the same songs, so continuity must be maintained. 

# How to use
1. Open your youtube music account and go to your library. use some Scraper extension to get the urls of all your playlists (I use easy web data scraper). put them in playlists.txt
2. Edit config.yml as you please. Importantly fill in the path of this playlist file, the mode in which you wanna run this script, the output format for your audio, the path to yt-dlp and ffmpeg (optional).
3. run the script.

# Thanks to 
1. The kind developers and the community of yt-dlp.
2. claude.ai
