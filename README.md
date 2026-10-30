# Open Telly

A simple Windows IPTV desktop client built with Python 3.12+ and PySide6. It loads an Extended M3U playlist, embeds mpv in a Qt window and lets the user switch channels via an overlay list.

## Features

- Open an M3U/Extended M3U playlist
- Parse channel metadata (`tvg-id`, `group-title`, `tvg-logo`, etc.)
- Ignore player-specific M3U comments such as `#EXTVLCOPT`
- Embed mpv into the Qt application window using the native Windows HWND
- Switch channels with `loadfile` while keeping the same mpv process alive
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
- mpv installed (the standard Winget install location is detected automatically)
- PySide6 dependencies installed via `pip`

## Install mpv on Windows

The simplest way is to install mpv from the official project or via winget:

```powershell
winget install --id=shinchiro.mpv --source winget
```

Verify the binary is available:

```powershell
mpv --version
```

If mpv is installed elsewhere, add it to `PATH` or configure the executable in
`MpvSettings(executable=r"C:\path\to\mpv.exe")`.

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

## Notes

The implementation is intentionally modular so the playlist parser, GUI logic and mpv controller remain separate.
Preferences are stored in the operating system's per-user application settings.
Favourite entries include their stream URLs so they remain available even when
their original playlist is not loaded.
