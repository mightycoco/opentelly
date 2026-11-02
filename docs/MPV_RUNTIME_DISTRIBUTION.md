# Bundled mpv runtime

The manual Release workflow creates a source ZIP that contains the source tree
and a replaceable Windows `libmpv` runtime under `runtime/`. The backend looks
there automatically. The source ZIP remains a Python source distribution;
users install the Python requirements and start it with `python main.py`.

The workflow currently obtains the x86-64 LGPL-labelled `mpv-dev` package from
[zhongfly/mpv-winbuild](https://github.com/zhongfly/mpv-winbuild). It verifies
the upstream SHA-256 manifest and records the exact package, mpv and FFmpeg
revisions, license texts, and corresponding mpv/FFmpeg/build-repository source
archives inside `runtime/licenses/`.

The upstream project describes its LGPL mpv build as using `-Dgpl=false` and
statically linking LGPLv3 FFmpeg. It also explicitly cautions that it cannot
guarantee every package in the build is LGPL-compatible. Consequently this
packaging path provides notices and provenance, but is **not a legal
certification**. Review all transitive libraries and their licenses before
publishing the bundle or representing it as compliant. The LGPL-tagged build
is selected to avoid the default GPL mpv build; do not replace it with a
non-LGPL build without revisiting the application's distribution terms.

The mpv DLL is distributed as a separate replaceable file, not statically
linked into Open Telly. This does not relicense Open Telly's own source. The
repository currently does not declare an Open Telly license, so this change
does not grant recipients additional rights to Open Telly source.

The generated source ZIP does not bundle Python or PySide6. Those dependencies
are installed separately using `requirements.txt` and retain their own license
terms. This is a source ZIP, not a standalone installer.
