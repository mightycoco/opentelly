# macOS and Linux Portability Roadmap

This document describes the work needed to make Open Telly available on macOS
and Linux while preserving its existing Windows behavior. It is a roadmap, not a
claim that either platform is currently supported.

## Implementation status

The worker now consumes the `MpvBackend` protocol, and the existing subprocess
implementation conforms through its adapter methods. This is an incremental
seam only: the current contract still accepts a Windows window handle and
forwards mpv-shaped event dictionaries. Playback operations now have named
backend methods, with raw mpv commands isolated in the subprocess adapter. A
platform-neutral render target and normalized event model remain to be
implemented before a portable renderer can be added. The subprocess backend is
still the only production backend.

## Current platform-specific constraints

- `src/iptv_player/player/mpv_ipc.py` communicates with mpv through Windows named
  pipes using `pywin32`.
- `src/iptv_player/settings.py` builds mpv arguments containing a Windows named
  pipe path and embeds playback using mpv's `--wid` option.
- `src/iptv_player/video_widget.py` exposes a native Qt window handle for mpv.
  Whether `--wid` can embed video depends on the platform and display system.
- `src/iptv_player/main_window.py` uses Win32 `SetWindowPos` for the
  always-on-top preference.
- mpv executable discovery has a Windows-specific Winget installation fallback.
- `requirements.txt` already limits `pywin32` to Windows.

Playlist parsing, playback/channel models, most widgets, and preferences via
`QSettings` are not inherently Windows-specific.

## Recommended implementation direction

Use mpv's **libmpv render API** with Qt for in-window video on all operating
systems. This avoids relying on embedding another process's native window,
which is particularly problematic to support consistently on macOS and
Wayland-based Linux desktops.

Keep the current mpv subprocess backend as the Windows implementation during
the migration. Introduce explicit platform/backend interfaces so changes can
be validated incrementally. If libmpv packaging or rendering proves too costly,
a separate mpv window can be offered as a fallback, with the trade-off that it
does not provide the current embedded-video experience.

## Work plan

### 1. Define the support targets

- Pick and document minimum supported macOS and Linux versions.
- Choose supported Linux display targets. Test Wayland and X11 separately;
  success on one does not establish support on the other.
- Decide which CPU architectures and Python versions will be packaged.
- Confirm that the selected mpv/libmpv builds include the required RTSP,
  codec, audio, and rendering support.

**Exit criteria:** a platform matrix identifies supported OS versions,
architectures, display systems, Python versions, and mpv distribution methods.

### 2. Separate platform services from application behavior

- Define small interfaces for mpv process/rendering, IPC transport, window
  pinning, and executable discovery.
- Keep playlist parsing, channel selection, favorites, audio-track behavior,
  and preferences independent of those implementations.
- Select implementations through a single platform/backend factory rather than
  scattering operating-system checks throughout the UI.
- Retain the current Windows backend until the alternative backend has passed
  the same playback and lifecycle tests.

**Exit criteria:** platform-specific implementations can be tested independently
and existing Windows behavior remains covered by regression tests.

### 3. Replace subprocess window embedding for macOS and Linux

- Add a libmpv binding/rendering backend and integrate its render context with a
  Qt widget using the graphics APIs supported by the chosen PySide6/platform
  combination.
- Handle render updates, resize, device/context lifetime, and teardown on the
  appropriate Qt/graphics thread.
- Ensure input and window focus continue to behave correctly while the video
  surface is active.
- If an in-process render backend is deferred, implement and document a
  separate-window fallback rather than assuming `--wid` works everywhere.

**Exit criteria:** playback is visibly embedded in the application on each
target OS/display system, resizing works, and closing the application leaves no
orphaned player process or graphics resources.

### 4. Add portable mpv IPC

- Keep the Windows named-pipe transport for Windows.
- Add a Unix-domain-socket transport for macOS and Linux, using a unique socket
  path in a per-user runtime/temp directory with appropriate permissions.
- Factor common JSON request/response parsing and event dispatch away from
  transport-specific connect/read/write/close logic.
- Avoid blocking the Qt GUI thread for IPC operations.
- Remove socket files during normal shutdown and handle stale paths, player
  startup failures, and interrupted shutdown explicitly.

**Exit criteria:** the same worker tests pass for each transport, including
command replies, property events, timeouts, concurrent activity, and shutdown.

### 5. Replace Win32-only window and executable handling

- Use Qt's `WindowStaysOnTopHint` for the always-on-top preference where the
  desktop environment supports it. Report or document environments that ignore
  the request rather than silently claiming the window is pinned.
- Discover `mpv` or `libmpv` through normal platform package locations and `PATH`;
  preserve explicit executable/library configuration.
- Keep Windows Winget discovery in the Windows-specific implementation.
- Review subprocess flags, signal handling, and process termination behavior on
  POSIX systems.
- Check that frameless tool overlays and their stacking/focus behavior work on
  each target window manager.

**Exit criteria:** no macOS/Linux code path imports Win32 APIs or assumes
Windows paths, and window pinning/overlays have documented platform behavior.

### 6. Package dependencies and installation

- Keep `pywin32` conditional on Windows.
- Add and validate platform-specific libmpv dependencies only if the selected
  rendering backend requires them.
- Document installing mpv/libmpv through supported macOS and Linux package
  sources, including any runtime-library requirements.
- Add reproducible development setup instructions for each platform.
- Decide on distribution formats, such as a signed/notarized macOS app and
  Linux AppImage/Flatpak/system package, only after the runtime dependencies are
  settled.

**Exit criteria:** a clean machine can install the documented dependencies,
launch the app, and resolve the required mpv components without relying on a
developer's local PATH or library setup.

### 7. Build a cross-platform validation matrix

For every supported target, automate or document checks for:

- Startup, playlist loading, channel switching, audio-track enumeration and
  selection, favorites, and saved preferences.
- RTSP over UDP and TCP, including representative FRITZ!Box streams where
  available.
- Window resize/fullscreen/always-on-top behavior and overlay interaction.
- Close during startup, close during playback, network failure, and recovery
  without hanging or leaving child processes.
- Clean installation and launch from a packaged build.

Use CI runners for platform-independent tests and native runners/devices for
video rendering, audio output, and desktop-window behavior. A passing test run
on Windows alone does not establish macOS or Linux support.

**Exit criteria:** each advertised OS/display target has passing automated tests
and recorded native playback evidence.

## Suggested milestones

1. **Portability foundation:** support matrix, backend interfaces, and
   platform-independent tests.
2. **Linux preview:** Unix-socket IPC and libmpv rendering; validate X11 and
   Wayland as separate targets.
3. **macOS preview:** libmpv rendering, runtime packaging, and native window
   behavior.
4. **Release readiness:** installation packages, clean-machine checks, and
   documented platform limitations.

## Main risks and decisions

- **Video rendering is the largest risk.** Native child-window embedding is not
  a portable contract; validate the Qt/libmpv render integration early.
- **Linux is not one desktop target.** X11 and Wayland have different embedding,
  stacking, and input constraints.
- **libmpv distribution is platform-specific.** Its shared libraries, codecs,
  rendering backends, licensing obligations, and signing/notarization
  requirements must be resolved for each package.
- **RTSP behavior can vary by build.** Verify that each distributed mpv build
  supports the application's needed RTSP transports and codecs.
- **Always-on-top is advisory on some desktops.** The application can request
  the behavior, but the window manager may control whether it is honored.

## Definition of done

macOS or Linux should be advertised as supported only after the application has
a documented installation path and passes the validation matrix on every
promised OS/display target, including embedded playback, channel/audio
switching, persistent preferences, and clean shutdown.
