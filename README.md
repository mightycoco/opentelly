# Open Telly

A simple Windows IPTV desktop client built with Python 3.12+ and PySide6. It loads an Extended M3U playlist, embeds mpv in a Qt window and lets the user switch channels via an overlay list.

## Features

- Open an M3U/Extended M3U playlist
- Parse channel metadata (`tvg-id`, `group-title`, `tvg-logo`, etc.)
- Ignore player-specific M3U comments such as `#EXTVLCOPT`
- Render video inside Qt through libmpv; the legacy subprocess backend embeds
  mpv using the native Windows HWND
- Switch channels with `loadfile` while keeping the same mpv process alive
- Show previous, stop/play, mute/unmute, and next controls when hovering over the bottom-left video area; channel navigation wraps around the playlist
- Show an audio-track selector when a channel has multiple audio streams
- Mark the selected audio track and switch streams from the bottom-right control
- Remember window placement, maximized/minimized/fullscreen state, and always-on-top preference
- Resume the last successfully played channel when its playlist is loaded again
- Remember the selected audio track per channel
- Save favourite channels across playlists and application restarts
- Switch between playlist and favourites in the channel overlay; click a row's star to toggle its favourite
- Confirm channel switches using mpv playback events and report failed loads
- Use UDP for RTSP by default (TCP and other transports are configurable)
- Hover/move mouse to show the channel overlay and auto-hide it after inactivity
- Clean application shutdown when closing the window, using Alt+F4, or selecting Exit
- Supports UTF-8 with BOM and Windows/Unix line endings

## Prerequisites

- Python 3.12 or newer recommended
- Windows 10 or 11 (64-bit)
- An mpv runtime; the release source ZIP includes libmpv, while a plain source
  checkout uses an installed libmpv or `mpv.exe`
- PySide6 dependencies installed via `pip`

## Install mpv on Windows

For a plain source checkout, install mpv, for example:

```powershell
winget install --id=shinchiro.mpv --source winget
```

Open Telly uses libmpv when its shared library (`mpv-2.dll` or
`libmpv-2.dll`) is installed, and automatically falls back to the mpv process
when the DLL is absent. Some mpv distributions, including the Winget package,
only contain `mpv.exe`. If you have a separate libmpv DLL, set `MPV_LIBRARY`
to its full path to use it. The release source ZIP includes an LGPL-labelled
libmpv runtime under `runtime/`, which is discovered automatically.

The environment variable applies to the current PowerShell session. Backend
selection can be overridden with `OPEN_TELLY_BACKEND=libmpv` or
`OPEN_TELLY_BACKEND=process`; the process backend locates mpv on `PATH` or in
the standard Winget installation folder.

## Setup

```powershell
cd <project-root>
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

## Run

```powershell
python main.py
```

Optional file argument:

```powershell
python main.py path\to\your_playlist.m3u
# or
python main.py path\to\playlist.m3u
```

VLC-specific directives in an M3U file are ignored; mpv playback options are
configured by the application instead. The player uses RTSP over UDP by
default for FRITZ!Box streams; set `MpvSettings(rtsp_transport="tcp")` to use
TCP if needed.

## Testing

```powershell
pytest
```

## Releases

See [docs/RELEASING.md](docs/RELEASING.md) for the manual GitHub Actions release
workflow and selectable semantic-version increments.
The source bundle and its mpv licensing/provenance notes are described in
[docs/MPV_RUNTIME_DISTRIBUTION.md](docs/MPV_RUNTIME_DISTRIBUTION.md).

## Notes

The implementation is intentionally modular so the playlist parser, GUI logic and mpv controller remain separate.
Preferences are stored in the operating system's per-user application settings.
Favourite entries include their stream URLs so they remain available even when
their original playlist is not loaded.
