# djgrab

Personal lossy downloads from YouTube and SoundCloud. Spec: `docs/SPEC.md`. Decisions: `docs/DECISIONS.md`.

## Binaries

`yt-dlp` and `ffmpeg` are required. `flac` and `fpcalc` are reported by `djgrab doctor` and are not used by this build.

Audio the tool downloads itself (single-track rips and set audio for cutting) is an allowed input. Personal use. Always flagged lossy.

## Commands

```
uv run djgrab doctor
uv run djgrab add --artist A --title T --duration 180
uv run djgrab keep <track_id>
uv run djgrab grab <track_id|job_id|spotify-track-url>
uv run djgrab playlist <youtube-or-soundcloud-url|spotify-playlist-url>
uv run djgrab set <url>
uv run djgrab cut <set_url> <timeline.json>
uv run djgrab clear
```

## Errors

A yt-dlp failure marks that job failed and retryable, or sends it to the buy list when `fallback_to_buylist` is set. Other jobs in the batch still run.
