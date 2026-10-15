from __future__ import annotations

import asyncio
import logging
import threading
from pathlib import Path

from djgrab.acquire.webdl import DownloadError, WebCandidate

# shortcut: one login for the process and an 8s result wait, upgrade if a long playlist gets the account banned
_WAIT_S = 8
_IDLE_S = 15
_LOSSLESS = {".flac", ".wav", ".aiff", ".aif"}


def _duration_s(attributes) -> int:
    for attr in attributes or []:
        code = getattr(attr, "key", None)
        if code == 1:
            return int(getattr(attr, "value", 0) or 0)
    return 0


def candidates_from_results(results) -> list[WebCandidate]:
    found: list[WebCandidate] = []
    for result in results:
        for item in result.shared_items:
            filename = item.filename
            suffix = Path(filename.replace("\\", "/")).suffix.casefold()
            found.append(
                WebCandidate(
                    source="soulseek",
                    url=f"{result.username}\x1f{filename}",
                    title=Path(filename.replace("\\", "/")).name,
                    uploader=result.username,
                    duration_s=_duration_s(item.attributes),
                    lossless=suffix in _LOSSLESS,
                )
            )
    return found


class SoulseekSource:
    def __init__(self, username: str, password: str):
        self.username = username
        self.password = password
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._client = None
        self._ready = threading.Lock()

    def search(self, query: str) -> list[WebCandidate]:
        try:
            results = self._call(self._search(query))
        except Exception as exc:
            raise DownloadError(str(exc)) from exc
        return candidates_from_results(results)

    def fetch(self, url: str, dest_dir: Path) -> Path:
        username, filename = url.split("\x1f", 1)
        try:
            path = self._call(self._fetch(username, filename, dest_dir))
        except TimeoutError as exc:
            raise DownloadError("soulseek timed out") from exc
        except Exception as exc:
            raise DownloadError(str(exc) or "soulseek failed") from exc
        if not isinstance(path, Path) or not path.is_file():
            raise DownloadError("soulseek wrote no file")
        return path

    def _call(self, coro):
        self._ensure()
        assert self._loop is not None
        return asyncio.run_coroutine_threadsafe(coro, self._loop).result(timeout=180)

    def _ensure(self) -> None:
        with self._ready:
            if self._client is not None:
                return
            if self._loop is None:
                self._loop = asyncio.new_event_loop()
                self._thread = threading.Thread(target=self._loop.run_forever, daemon=True)
                self._thread.start()
            asyncio.run_coroutine_threadsafe(self._login(), self._loop).result(timeout=60)

    async def _login(self) -> None:
        from aioslsk.client import SoulSeekClient
        from aioslsk.settings import CredentialsSettings, Settings, SharesSettings

        logging.getLogger("aioslsk").setLevel(logging.ERROR)
        logging.getLogger("async_upnp_client").setLevel(logging.CRITICAL)
        settings = Settings(
            credentials=CredentialsSettings(username=self.username, password=self.password),
            shares=SharesSettings(scan_on_start=False, directories=[]),
        )
        client = SoulSeekClient(settings)
        await client.start()
        await client.login()
        self._client = client

    async def _search(self, query: str):
        assert self._client is not None
        request = await self._client.searches.search(query)
        await asyncio.sleep(_WAIT_S)
        return list(request.results)

    async def _fetch(self, username: str, filename: str, dest_dir: Path) -> Path:
        assert self._client is not None
        dest_dir.mkdir(parents=True, exist_ok=True)
        self._client.settings.shares.download = str(dest_dir)
        transfer = await self._client.transfers.download(username, filename)
        idle = 0
        last = -1
        for _ in range(180):
            name = getattr(getattr(transfer.state, "VALUE", None), "name", "")
            if name in {"FAILED", "ABORTED"}:
                raise DownloadError(transfer.fail_reason or transfer.abort_reason or f"soulseek {name}")
            local = getattr(transfer, "local_path", None)
            if name == "COMPLETE" and local and Path(local).is_file():
                return Path(local)
            got = int(getattr(transfer, "bytes_transfered", 0) or 0)
            idle, reason = _idle_error(name, got != last, idle)
            last = got
            if reason:
                try:
                    await self._client.transfers.abort(transfer)
                except Exception:
                    pass
                raise DownloadError(reason)
            await asyncio.sleep(1)
        raise DownloadError("soulseek timed out")


def _idle_error(name: str, moved: bool, idle: int) -> tuple[int, str]:
    if name == "DOWNLOADING" and moved:
        return 0, ""
    idle += 1
    if idle < _IDLE_S:
        return idle, ""
    if name == "DOWNLOADING":
        return idle, "soulseek stalled"
    return idle, "soulseek peer did not start"
