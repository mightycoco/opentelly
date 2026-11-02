# Releasing Open Telly

Releases are created manually from the GitHub Actions **Release** workflow.
Run it from the repository's default branch and select a semantic-version
increment:

- `patch`: `0.1.0` becomes `0.1.1`
- `minor`: `0.1.0` becomes `0.2.0`
- `major`: `0.1.0` becomes `1.0.0`

The workflow installs the application dependencies and runs the test suite
before changing the version. On success it updates `src/iptv_player/__init__.py`,
commits that change to the selected branch, creates the corresponding `vX.Y.Z`
tag, and publishes a GitHub Release with generated notes. The workflow token
needs permission to push commits and tags to that branch; repository branch
protection must allow this or the workflow will fail explicitly.
To avoid reliance on remotely resolved workflow actions, it checks out the
selected branch with the runner's Git installation and uses Python 3.12 from
the Windows runner tool cache.

The repository does not yet build platform installers. Releases therefore use
GitHub's automatically generated source archives and an additional
`OpenTelly-X.Y.Z-source.zip`. The latter contains the Python sources and the
verified, replaceable LGPL-labelled libmpv runtime with its notices,
provenance, and source archives. It is still a source distribution and
requires Python dependencies to be installed; it is not a standalone
application installer. See [MPV_RUNTIME_DISTRIBUTION.md](MPV_RUNTIME_DISTRIBUTION.md)
for the upstream build's licensing caveats.
