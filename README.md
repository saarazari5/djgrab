# djgrab

Download a song from a link. The file lands in your home folder:

```text
~/djgrab/{genre}/{artist} - {title}.m4a
```

You are responsible for what you download. djgrab does not unlock Spotify audio or SoundCloud Go+.

## Install

There is no `brew install djgrab`. Homebrew installs the three programs djgrab runs on. uv then installs the `djgrab` command.

On a Mac:

```bash
brew install uv yt-dlp ffmpeg
uv tool install git+https://github.com/saarazari5/djgrab
djgrab doctor
```

`doctor` exits with an error when `yt-dlp` or `ffmpeg` is missing. Quote URLs in zsh so `?` is not treated as a pattern.

```bash
djgrab "https://www.youtube.com/watch?v=..."
```

The song is saved under `~/djgrab/`. The database and temporary files are in `~/.djgrab/`. No account is required for YouTube or SoundCloud.

To install a newer copy later:

```bash
uv tool upgrade djgrab
```

On Linux, install `ffmpeg` with your package manager and install [uv](https://docs.astral.sh/uv/getting-started/installation/) and `yt-dlp`, then run the same `uv tool install` line.

To work on the code instead of installing the command:

```bash
uv sync --extra dev
uv run pytest
uv run djgrab doctor
```

## Commands

```bash
djgrab doctor
djgrab "https://www.youtube.com/watch?v=..."
djgrab "https://soundcloud.com/artist/track"
djgrab "https://soundcloud.com/artist/sets/..."
djgrab "https://open.spotify.com/track/..."
djgrab "https://open.spotify.com/playlist/..."
djgrab clear
```

`--config` and `--data` can go before or after the link. A word that is not `doctor`, `clear`, or a URL is refused.

Songs are saved in `~/djgrab/`. The database and temporary files are in `~/.djgrab/`. `--data somewhere` stores the database in `somewhere/` and the songs in `somewhere/djgrab/`. `DJGRAB_DATA` does the same.

`djgrab clear` deletes `~/.djgrab/djgrab.sqlite`. The audio files stay. After a clear, djgrab no longer knows which songs were already downloaded, so the next link fetches them again.

The last line of a download is `status: message`. Exit code 1 means that download failed. Exit code 2 means the link was refused.

## What a link does

A YouTube or SoundCloud page that names one recording is downloaded from that URL.

A YouTube or SoundCloud playlist, including a SoundCloud URL with `/sets/`, downloads each recording from its own URL. One failure does not stop the rest.

A Spotify track or playlist is only a list of names. Spotify audio is locked. djgrab reads the public title, artist, and duration, then searches YouTube and SoundCloud.

One video is a DJ set when the page names at least two songs. Those songs are searched and downloaded one by one. The mix itself is not saved. A video that names no songs is downloaded as that one file.

Names are read from YouTube chapters, then timestamp lines in the description, then `Artist - Title` lines, then the first comment that lists at least two timestamps. Bracket notes such as `[ Unreleased ]` are dropped.

A song already filed with the same artist, title, and mix is kept. A different mix is a different song. If the file has been deleted, it is downloaded again.

## Search

The query is the artist and title with these words removed: remaster, remastered, official, audio, video, lyric, lyrics, hd, hq, and a 4-digit year.

A candidate is usable when every title word is in its title and every artist word is in its artist. When the track has a length, the candidate must be within 15 seconds. A DJ-set song has no length, so that check is skipped. When the track has a mix, the candidate's trailing parenthetical must be that mix.

Ranking: a lossless Soulseek file, then the closest length, then fewer extra title words, then an uploader that matches the artist.

DRM, unavailable, and private errors try the next file. A Soulseek user who never sends the file is skipped and the next file is tried. Nothing usable is reported as `buylist`.

YouTube and SoundCloud downloads are AAC in m4a at 256 kbps and are marked lossy. A Soulseek flac, wav, or aiff that matches is filed as lossless. The source picture is embedded when the site provides one. A missing picture does not stop the download.

Genre comes from an iTunes artist search. The folder is `library.genres` when that genre is listed, otherwise the genre text. No genre uses `fallback_genre` (`Unknown`).

## Configure

You can skip this. With no config file, YouTube and SoundCloud are searched and songs go to `~/djgrab/`.

Soulseek is the optional extra. It searches other people's shared files and prefers a lossless match. Create the account in the Soulseek app first, then save this file as `~/.djgrab/djgrab.toml`:

```toml
[download]
enabled = true
sources = ["youtube", "soundcloud"]
format = "m4a"
bitrate = "256k"

[library]
fallback_genre = "Unknown"

[library.genres]
pop = "Pop"
"dance pop" = "Pop"

[spotify]
client_id = ""
client_secret = ""

[soulseek]
username = "your-soulseek-username"
password = "your-soulseek-password"
```

Leave `username` and `password` empty to keep Soulseek off. Both must be set for it to run.

Spotify keys are optional. The genre folder comes from an iTunes artist search and does not need them. `SPOTIFY_CLIENT_ID` and `SPOTIFY_CLIENT_SECRET` override the file when they are set.

A `djgrab.toml` in the current directory is used first. `--config /path/to/djgrab.toml` picks a file directly.

| Key | Meaning |
| --- | --- |
| `sources` | `youtube` and `soundcloud` |
| `format` | `m4a` or `mp3` |
| `bitrate` | audio bitrate, default `256k` |
| `fallback_genre` | folder used when no genre is found |
| `genres` | map a genre string to a folder name, ignoring case |

## Tests

```bash
uv sync --extra dev
uv run pytest
```

Tests are offline except one that serves a wav on localhost and runs `yt-dlp` and `ffmpeg`.

## What this does not do

It does not play a stream, buy from a store, or listen to the audio to name a song. It does not cut a DJ mix into songs. It does not sync a DJ app.
