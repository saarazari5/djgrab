# djgrab

Downloads a song from a link into `~/djgrab/`. Spec: `docs/SPEC.md`. Decisions: `docs/DECISIONS.md`.

## Binaries

`yt-dlp` and `ffmpeg` are required. `flac` and `fpcalc` are reported by `djgrab doctor` and are not used by this build.

Audio the tool downloads itself is an allowed input. Web downloads are flagged lossy. A Soulseek flac, wav, or aiff is flagged lossless.

## Commands

```
uv run djgrab doctor
uv run djgrab <url>
uv run djgrab clear
uv run djgrab config soulseek.username <name>
```

`config <section.key> <value>` writes a string into the config file, creating `~/.djgrab/djgrab.toml` when none exists.

The database and staging live in `~/.djgrab/` unless `--data` or `DJGRAB_DATA` is set. Config is `./djgrab.toml` when that file exists, otherwise `~/.djgrab/djgrab.toml`.

## Errors

A word that is not `doctor`, `clear`, `config`, or a URL is refused before yt-dlp runs. A yt-dlp failure marks that job failed and retryable, or sends it to the buy list when `fallback_to_buylist` is set. A Soulseek download failure tries the next file. Other jobs in the batch still run.
