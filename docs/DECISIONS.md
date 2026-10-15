# Decisions

## 2026-10-15 — Personal format-shifting

YouTube downloads break YouTube's terms. Accepted for a personal copy of a track you are keeping. Not a store client and not a lossless claim.

## 2026-10-15 — m4a, not a fake lossless rip

Web and set-cut files are AAC in m4a at 256 kbps and tagged `quality=lossy`. A rip is never stored as lossless.

## 2026-10-15 — Auto-download keepers

`singles=auto_keepers` downloads when a track becomes a keeper and it has no free link. `djgrab grab` downloads on demand either way. `on_demand` leaves `keep` as a flag only.

## 2026-10-15 — trim_s=2

A set cut starts and ends two seconds inside the timeline so a transition bleeds less. It does not remove the bleed. Segments under 60 seconds after that trim are dropped.

## 2026-10-15 — Playlist skips recognition

A playlist entry is already a track. Download its URL. Do not search, match, or cut. A DJ set is the path that needs a timeline.

## 2026-10-15 — Spotify playlist is a search list

A Spotify playlist is metadata. `djgrab playlist` stores each track and searches YouTube or SoundCloud. It does not download the Spotify URL. A YouTube or SoundCloud playlist entry is still downloaded by its URL.
