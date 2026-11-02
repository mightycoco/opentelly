param(
    [Parameter(Mandatory = $true)]
    [string]$RuntimeDirectory,
    [Parameter(Mandatory = $true)]
    [string]$SevenZipPath
)

$ErrorActionPreference = "Stop"
$repository = "zhongfly/mpv-winbuild"
$headers = @{
    Accept = "application/vnd.github+json"
    "User-Agent" = "OpenTelly-release"
}
if ($env:GITHUB_TOKEN) {
    $headers.Authorization = "Bearer $env:GITHUB_TOKEN"
}

$release = Invoke-RestMethod `
    -Headers $headers `
    -Uri "https://api.github.com/repos/$repository/releases/latest"
$mpvAsset = $release.assets |
    Where-Object { $_.name -match '^mpv-dev-lgpl-x86_64-\d{8}-git-[a-f0-9]+\.7z$' } |
    Select-Object -First 1
$ffmpegAsset = $release.assets |
    Where-Object { $_.name -match '^ffmpeg-lgpl-x86_64-git-[a-f0-9]+\.7z$' } |
    Select-Object -First 1
$checksumAsset = $release.assets |
    Where-Object { $_.name -eq "sha256.txt" } |
    Select-Object -First 1
if (-not $mpvAsset -or -not $ffmpegAsset -or -not $checksumAsset) {
    throw "The upstream release does not contain the expected LGPL assets and checksums."
}

$runtimePath = [System.IO.Path]::GetFullPath($RuntimeDirectory)
$licensePath = Join-Path $runtimePath "licenses"
$mpvLicensePath = Join-Path $licensePath "mpv"
$ffmpegLicensePath = Join-Path $licensePath "ffmpeg"
$sourcePath = Join-Path $licensePath "source"
New-Item -ItemType Directory -Force -Path $runtimePath, $mpvLicensePath, $ffmpegLicensePath, $sourcePath | Out-Null

$checksumFile = Join-Path $env:TEMP "mpv-runtime-sha256.txt"
Invoke-WebRequest -Headers $headers -Uri $checksumAsset.browser_download_url -OutFile $checksumFile
$checksums = Get-Content $checksumFile

foreach ($asset in @($mpvAsset, $ffmpegAsset)) {
    $archive = Join-Path $env:TEMP $asset.name
    Invoke-WebRequest -Headers $headers -Uri $asset.browser_download_url -OutFile $archive
    $checksumLine = $checksums |
        Where-Object { $_ -match ("^([0-9a-fA-F]{64})\s+\*?" + [regex]::Escape($asset.name) + "$") } |
        Select-Object -First 1
    if (-not $checksumLine) {
        throw "No SHA-256 checksum was published for $($asset.name)."
    }
    $expectedHash = ($checksumLine -split "\s+")[0].ToLowerInvariant()
    $actualHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $archive).Hash.ToLowerInvariant()
    if ($actualHash -ne $expectedHash) {
        throw "SHA-256 mismatch for $($asset.name): expected $expectedHash, got $actualHash."
    }
    if ($asset.name -eq $mpvAsset.name) {
        $mpvHash = $actualHash
    } else {
        $ffmpegHash = $actualHash
    }
}

$mpvArchive = Join-Path $env:TEMP $mpvAsset.name
& $SevenZipPath x $mpvArchive "-o$runtimePath" -y | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "Could not extract $($mpvAsset.name)."
}

$mpvCommitMatch = [regex]::Match($release.body, 'mpv-player/mpv/commit/([a-f0-9]{40})')
$buildRunMatch = [regex]::Match($release.body, 'actions/runs/(\d+)')
$ffmpegCommitMatch = [regex]::Match($ffmpegAsset.name, 'git-([a-f0-9]+)\.7z$')
if (-not $mpvCommitMatch.Success -or -not $buildRunMatch.Success -or -not $ffmpegCommitMatch.Success) {
    throw "Could not determine exact mpv, FFmpeg, and build workflow revisions."
}

$buildRun = Invoke-RestMethod `
    -Headers $headers `
    -Uri "https://api.github.com/repos/$repository/actions/runs/$($buildRunMatch.Groups[1].Value)"
$builderCommit = $buildRun.head_sha
$ffmpegCommit = (Invoke-RestMethod `
    -Headers $headers `
    -Uri "https://api.github.com/repos/FFmpeg/FFmpeg/commits/$($ffmpegCommitMatch.Groups[1].Value)").sha
$mpvCommit = $mpvCommitMatch.Groups[1].Value

$sourceArchives = @(
    @{
        Uri = "https://github.com/mpv-player/mpv/archive/$mpvCommit.zip"
        Path = Join-Path $sourcePath "mpv-source.zip"
    },
    @{
        Uri = "https://github.com/FFmpeg/FFmpeg/archive/$ffmpegCommit.zip"
        Path = Join-Path $sourcePath "ffmpeg-source.zip"
    },
    @{
        Uri = "https://github.com/$repository/archive/$builderCommit.zip"
        Path = Join-Path $sourcePath "mpv-build-scripts-source.zip"
    }
)
foreach ($sourceArchive in $sourceArchives) {
    Invoke-WebRequest -Headers $headers -Uri $sourceArchive.Uri -OutFile $sourceArchive.Path
}

$downloads = @(
    @{
        Uri = "https://raw.githubusercontent.com/mpv-player/mpv/$mpvCommit/Copyright"
        Path = Join-Path $mpvLicensePath "Copyright"
    },
    @{
        Uri = "https://raw.githubusercontent.com/mpv-player/mpv/$mpvCommit/LICENSE.LGPL"
        Path = Join-Path $mpvLicensePath "LICENSE.LGPL"
    },
    @{
        Uri = "https://raw.githubusercontent.com/FFmpeg/FFmpeg/$ffmpegCommit/COPYING.LGPLv3"
        Path = Join-Path $ffmpegLicensePath "COPYING.LGPLv3"
    }
)
foreach ($download in $downloads) {
    Invoke-WebRequest -Headers $headers -Uri $download.Uri -OutFile $download.Path
}

$provenance = @"
mpv runtime package: $($mpvAsset.name)
mpv package SHA-256: $mpvHash
mpv source revision: https://github.com/mpv-player/mpv/commit/$mpvCommit
FFmpeg package: $($ffmpegAsset.name)
FFmpeg package SHA-256: $ffmpegHash
FFmpeg source revision: https://github.com/FFmpeg/FFmpeg/commit/$ffmpegCommit
Build workflow source revision: https://github.com/$repository/tree/$builderCommit
Build workflow run: https://github.com/$repository/actions/runs/$($buildRunMatch.Groups[1].Value)
Upstream release: $($release.html_url)
"@
Set-Content -LiteralPath (Join-Path $licensePath "BUILD-PROVENANCE.txt") -Value $provenance -Encoding utf8

$notices = @"
Open Telly source distribution - third-party runtime notices

This distribution includes the libmpv runtime from the mpv-winbuild LGPL
variant. The upstream project describes mpv as LGPLv2.1+ when built with
-Dgpl=false and states that its LGPL variant statically links FFmpeg under
LGPLv3. The included LGPL texts, corresponding mpv/FFmpeg source archives, and
build revision references are in this directory. The binary and its
dependencies remain replaceable files under runtime/.

The mpv-winbuild maintainers caution that they cannot guarantee every package
in their build is LGPL-compatible. This bundle therefore records the selected
upstream build and licenses but is not a legal certification. Review all
transitive dependency licenses before publishing or redistributing it.

Open Telly's own source is not relicensed by this notice. Qt for Python and
other Python dependencies are installed separately from requirements.txt and
have their own license terms.
"@
Set-Content -LiteralPath (Join-Path $licensePath "THIRD_PARTY_NOTICES.md") -Value $notices -Encoding utf8

$library = Get-ChildItem -LiteralPath $runtimePath -Filter "libmpv-2.dll" -Recurse |
    Select-Object -First 1
if (-not $library) {
    throw "The selected archive does not contain libmpv-2.dll."
}
Write-Output "Runtime ready: $($mpvAsset.name)"
Write-Output "libmpv: $($library.FullName)"
