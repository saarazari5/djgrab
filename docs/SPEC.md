# djgrab

Personal tool. A keeper with no free source gets a lossy YouTube or SoundCloud copy. Buy links stay the lossless upgrade. This build does not recognize audio, stream, or talk to a store.

## Inputs

### Single

`djgrab keep <track_id>` sets keeper. When `singles` is `auto_keepers`, that also downloads. `djgrab grab <track_id|job_id>` downloads even when the track is not a keeper.

`djgrab grab <spotify-track-url>` reads the public title, artist, and duration from the Spotify embed page, then the artist's first genre when the artist page has one. It stores that track and runs the same search. The Spotify URL is not downloaded. A Spotify playlist URL belongs to `djgrab playlist`.

A filed track is `{genre folder}/{artist} - {title}.m4a` under `djgrab/` in the home folder. A blank genre is filled from Spotify's artist search before the file is written: the artist whose name matches, otherwise the first result that has a genre. `A feat. B` searches the full credit, then the first name. The folder is `library.genres` when that genre is listed, otherwise the genre text. No credentials, no match, or an artist with no genre uses `library.fallback_genre`. An existing file with the same name gets the track id added.

A free link is filed with `acquired_via=free`. Search does not run. A local free file is tagged and filed. A free URL is recorded as the inbox path.

No free link: if the same artist, title, and mix are already filed and the file is still there, that file is kept and nothing is searched. Otherwise search metadata on each configured source, then match. A YouTube or SoundCloud download embeds the source thumbnail when the site provides one.

- One usable candidate: download it into staging and file it with that track id. A lossless Soulseek file is filed as `quality=lossless`. Other files stay `quality=lossy`. Inbox does not match again. `acquired_via=web`.
- More than one usable file: the best one is downloaded. A DRM, unavailable, or private failure tries the next file.
- No usable file: job `buylist` when `fallback_to_buylist` is true, otherwise `needs_review` with the candidates stored.
- yt-dlp hard failure: job `buylist` when `fallback_to_buylist` is true, otherwise `failed` and `retryable`. The rest of a batch still runs.

`download.enabled=false` fails the job and names `enabled`.

### Playlist

`djgrab playlist <url>`. Entries already identify the tracks. Each entry URL is downloaded and filed the same way as a web single. No search, no match, no cutting. An entry with no URL is skipped and recorded on the playlist job. One entry failing does not stop the others.

`djgrab playlist <spotify-playlist-url>` reads the public embed track list. Each `spotify:track` entry is stored as a keeper with a blank genre and searched the same way as `djgrab grab <spotify-track-url>`. The Spotify URL is not downloaded. An entry that is not a track is skipped and named on the playlist job. The embed page is the whole list. One entry failing does not stop the others. The parent job reports how many were filed and which were skipped or not acquired.

### Set

`djgrab set <url>` reads a tracklist from one long video, then searches and downloads each song on its own. The set audio is not downloaded. Chapters are used when the video has them. Otherwise timestamp lines in the description (`12:34 Artist - Title`, `1:02:03 Artist - Title`) are used. If the description has no times, lines like `Artist - Title` are used. If those are missing too, the first of 100 comments with at least two timestamp lines is used. No chapters, description names, or comment times stops with `video has no tracklist` and does not search. Each song is stored with no duration, because the time it plays in the mix is not the studio length. One song that is not found or fails does not stop the others.

`djgrab cut <set_url> <timeline.json>` still cuts from a JSON list of `{start_s, end_s, track_id}` plus optional `id_clip`.

Track segments are trimmed inward by `trim_s` seconds. A segment shorter than 60 seconds after that trim is skipped. Each remaining cut is filed as `{artist} - {title}` under `djgrab/` in the home folder. One bad cut is recorded and the rest continue.

`id_clip: true` cuts 12 seconds from `start_s` of the same audio, with no trim and no 60 second minimum. Clips are saved under `library/ids/` and do not replace the track file.

## Match

A candidate is usable when, after dropping the words remaster, official, audio, video, lyric, hd, and a 4-digit year, every title word is in the candidate title and every artist word is in the candidate artist. Accents are ignored for that comparison. When the track has a duration, the length must be within 15 seconds. A track with no duration skips that check, and length is not used to rank those candidates. When the track has a mix, the candidate's trailing parenthetical must be that mix. The closest length wins, then the title with no extra words, then an uploader that matches the artist. A lossless Soulseek file that passes is preferred. That file is downloaded. If the download fails because it is DRM, unavailable, or private, the next usable file is tried. Nothing usable, or every file failing that way, goes to the buy list when `fallback_to_buylist` is set.

The search sent to YouTube, SoundCloud, and Soulseek is the artist and title with those words removed. Soulseek runs only when `[soulseek]` `username` and `password` are set.

## Config

`djgrab.toml`, table `download`:

- `enabled` (bool)
- `sources` (youtube, soundcloud)
- `format` (`m4a` or `mp3`)
- `bitrate` (`256k`)
- `trim_s` (seconds)
- `singles` (`auto_keepers` or `on_demand`)
- `fallback_to_buylist` (bool)

Table `library`:

- `fallback_genre` (folder when the track has no genre)
- `genres` (map of genre text to folder name, matched without case)

Table `spotify`: `client_id` and `client_secret`. `SPOTIFY_CLIENT_ID` and `SPOTIFY_CLIENT_SECRET` override the file. When the artist page has no genre, those credentials are used to read the first genre from Spotify's artist API. The same credentials search Spotify by artist name whenever a track is filed with a blank genre. Empty credentials leave the genre blank.

Missing file uses those defaults. The database and staging stay in `data/`, or `--data`, or `DJGRAB_DATA`. Songs are `djgrab/` in the home folder, or inside that data directory when `--data` or `DJGRAB_DATA` is set.

## Storage

SQLite `data/djgrab.sqlite`.

- `tracks.acquired_via`: `inbox` (default), `free`, `web`, `purchase`
- `jobs.status`: `pending`, `acquired`, `needs_review`, `buylist`, `failed`
- `inbox_files`: staged file already matched to a track, then `filed`
- `spend`: one row per successful yt-dlp download, `provider=ytdlp`

## Commands

- `djgrab doctor` — `yt-dlp` and `ffmpeg` are required. `flac` and `fpcalc` are reported and do not block this build. Missing required tools include an install line.
- `djgrab add` — create a track.
- `djgrab keep`, `djgrab grab`, `djgrab playlist`, `djgrab set`, `djgrab cut`.
- `djgrab clear` — delete the database. Song files stay.

## Binaries

`yt-dlp` for search, track download, playlist listing, and set audio. One process at a time, a timeout, then three tries with backoff. `ffmpeg` tags inbox files and cuts sets.
