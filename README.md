# djgrab

Personal downloader for tracks you already decided to keep. You give it a name, a Spotify link, a playlist, or one long DJ-set video. It searches YouTube and SoundCloud, and Soulseek when you configure it, then files one audio file per song.

Songs are saved in your home folder:

```text
~/djgrab/{genre}/{artist} - {title}.m4a
```

The database and temporary downloads stay in `data/` inside this project. `djgrab clear` deletes only the database. The audio files stay.

Rekordbox does not copy a file when you drag it in from `~/djgrab/`. It remembers that path. Deleting the folder makes those tracks missing in Rekordbox.

## Install

You need Python 3.11+, [uv](https://docs.astral.sh/uv/), `yt-dlp`, and `ffmpeg`.

```bash
uv sync --extra dev
uv run djgrab doctor
```

`doctor` exits with an error when `yt-dlp` or `ffmpeg` is missing. `flac` and `fpcalc` are reported and are not used.

## Configure

```bash
cp djgrab.example.toml djgrab.toml
```

`djgrab.toml` is gitignored. Put your own values there. Nothing in this repository contains a Spotify secret or a Soulseek password.

`SPOTIFY_CLIENT_ID` and `SPOTIFY_CLIENT_SECRET` override the file when they are set. An empty environment variable does not override a value in the file.

### Download

| Key | Meaning |
| --- | --- |
| `enabled` | `false` stops every download and names `enabled` in the error |
| `sources` | `youtube` and `soundcloud` |
| `format` | `m4a` or `mp3` |
| `bitrate` | audio bitrate, default `256k` |
| `trim_s` | seconds cut off each end of a hand-written set timeline |
| `singles` | `auto_keepers` downloads when you `keep` a track. `on_demand` only marks it |
| `fallback_to_buylist` | a miss or a hard failure goes to the buy list |

### Library

| Key | Meaning |
| --- | --- |
| `fallback_genre` | folder used when no genre is found. Default `Unknown` |
| `genres` | map a Spotify genre string to a folder name, ignoring case |

Example: `"dance pop" = "Pop"` files that genre under `Pop/`.

### Spotify

The Spotify link is never the audio. Spotify audio is locked. djgrab reads the public title, artist, and duration, then searches elsewhere.

Create an app at the Spotify developer dashboard with the Web API enabled. Put the client id and client secret in `djgrab.toml`. Those credentials are used for two things:

- The artist's first genre, from the artist page or the artist API.
- A search by artist name when a track is filed with a blank genre, including songs named in a DJ set.

Empty credentials leave the genre blank, and the file goes to `fallback_genre`.

### Soulseek

Set both `username` and `password`. The account has to exist in the Soulseek app first. Empty fields skip Soulseek.

Soulseek is searched at the same time as YouTube and SoundCloud. A lossless file (flac, wav, aiff) that matches is preferred. One login is reused for the process. Sharing a folder is a Soulseek app prompt, not something djgrab asks for. Point the Soulseek app at `~/djgrab/` if you choose to share.

YouTube and SoundCloud need no account.

## Commands

Run these from the project directory.

```bash
uv run djgrab doctor
uv run djgrab add --artist "Nova Ridge" --title "Solar Drift" --mix "Original Mix" --duration 180
uv run djgrab keep 1
uv run djgrab grab 1
uv run djgrab grab "https://open.spotify.com/track/..."
uv run djgrab playlist "https://soundcloud.com/..."
uv run djgrab playlist "https://open.spotify.com/playlist/..."
uv run djgrab set "https://www.youtube.com/watch?v=..."
uv run djgrab cut "https://www.youtube.com/watch?v=..." timeline.json
uv run djgrab clear
```

`--config` and `--data` go after the subcommand. `--data somewhere` stores the database in `somewhere/` and the songs in `somewhere/djgrab/`. `DJGRAB_DATA` does the same.

The last line of a command is `status: message`. Exit code 1 means the job failed. Exit code 2 means the command itself was refused, such as a missing track or a video with no tracklist.

### One song

`add` stores a track and prints its id. `keep` marks it as a keeper. With `singles = "auto_keepers"` that also downloads it.

`grab` takes a track id, a job id, or a Spotify track URL. A Spotify URL is looked up, stored, and then searched. A free URL stored on the track is filed as-is and is not searched.

A song that is already filed with the same artist, title, and mix is kept. The search does not run again. A different mix is a different song. If the file has been deleted from disk, it is downloaded again.

### Playlists

A YouTube or SoundCloud playlist is a list of separate videos. Each URL is downloaded whole. There is no search and no cutting. One failure does not stop the rest.

A Spotify playlist is a list of names. Each track is stored and searched the same way as `grab` on a Spotify track URL.

### DJ sets

`djgrab set` treats one video as a tracklist, then downloads each song on its own. It does not save the mix and it does not cut slices out of it.

It reads names in this order:

1. YouTube chapters.
2. Timestamp lines in the description, such as `12:34 Artist - Title` or `1:02:03 Artist - Title`.
3. Description lines like `Artist - Title` when there are no timestamps.
4. The first of 100 comments that contains at least two timestamp lines.

Bracket notes such as `[ Unreleased ]` are dropped. If none of those sources name at least two songs, the command stops with `video has no tracklist` and does not search.

The time a song plays inside the mix is not stored as its length, because a DJ does not play the studio recording for the same number of seconds. Matching then uses the artist and title.

`djgrab cut` is the other path. You pass a JSON list you already wrote:

```json
[{ "start_s": 0, "end_s": 180, "track_id": 1 }]
```

The set audio is downloaded once and cut. Each piece is trimmed inward by `trim_s` seconds. A piece shorter than 60 seconds after that trim is skipped. `"id_clip": true` saves 12 seconds from `start_s` under `ids/` and does not replace the track file.

### Clear

`djgrab clear` deletes `data/djgrab.sqlite`, including the `-wal` and `-shm` files. Songs in `~/djgrab/` stay. After a clear, djgrab no longer knows which songs were already downloaded, so the next set fetches them again.

## How a search picks a file

The query is the artist and title with these words removed: remaster, remastered, official, audio, video, lyric, lyrics, hd, hq, and a 4-digit year. Accents are ignored while comparing. The saved filename keeps the original spelling.

A candidate is usable when every title word is in its title and every artist word is in its artist. When the track has a length, the candidate must be within 15 seconds. A track with no length skips that check. When the track has a mix, the candidate's trailing parenthetical must be that mix.

YouTube and SoundCloud are searched together. Soulseek runs at the same time when it is configured. Downloads stay one song at a time.

Ranking:

1. A lossless Soulseek file wins over a lossy file.
2. Closest length, when the track has a length.
3. Fewer extra words in the title.
4. An uploader that matches the artist.

DRM, unavailable, and private errors drop that file and try the next one. Any other download error stops that song. Nothing usable goes to the buy list when `fallback_to_buylist` is true.

A title-only name whose artist is `Unknown` has to match the title exactly, so `Luna` does not grab a longer filename that merely contains that word.

## Files and tags

YouTube and SoundCloud downloads are AAC in m4a at the configured bitrate and are marked lossy. A Soulseek flac, wav, or aiff that matches is filed as lossless.

The source thumbnail is embedded in the file when YouTube or SoundCloud provides one. Finder and Rekordbox read that picture from inside the file. A missing picture does not stop the download. A Soulseek file keeps the cover it already has.

Genre comes from Spotify when credentials are set. The folder is `library.genres` when that genre is listed, otherwise the genre text. No genre uses `fallback_genre`.

An existing file with the same name gets the track id added: `Artist - Title (12).m4a`.

## Database

SQLite file: `data/djgrab.sqlite`.

- `tracks.acquired_via`: `inbox`, `free`, `web`, `purchase`
- `jobs.status`: `pending`, `acquired`, `needs_review`, `buylist`, `failed`
- `inbox_files`: the filed path for a track
- `spend`: one row per successful yt-dlp download

Staging files live in `data/staging/` until they are filed.

## Tests

```bash
uv sync --extra dev
uv run pytest
```

Tests are offline. They use recorded search results and do not call YouTube, SoundCloud, Spotify, or Soulseek.

## What this build does not do

It does not play a stream, buy from a store, or listen to the audio to name a song. A DJ mix overlaps tracks, so silence detection and fingerprinting name the wrong recording. It does not unlock SoundCloud Go+ or Spotify audio. It does not sync a DJ app library.
