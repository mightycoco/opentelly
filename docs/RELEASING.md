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

The repository does not yet build platform installers. Releases therefore use
GitHub's automatically generated source archives and do not claim to be
standalone application packages.
