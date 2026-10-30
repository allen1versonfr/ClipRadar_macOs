# Changelog

All notable changes to Clip Radar for macOS are documented here. The macOS port follows the Windows
version's numbers: 4.36.0 here is Clip Radar 4.36.0 ([its changes](docs/CHANGELOG-windows.md)) running on a Mac.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [4.36.0] - 2026-10-30

The first macOS release: Clip Radar 4.36.0, ported to the Mac, for Apple silicon and Intel.

### Added
- **Clip Radar.app** in a drag-to-Applications disk image, one per chip (`ClipRadar-macOS-arm64.dmg`, `ClipRadar-macOS-x86_64.dmg`), with FFmpeg, yt-dlp and TwitchDownloaderCLI inside. macOS 11 or later.
- **Rendering on the Mac's video engine (VideoToolbox)** for H.264 and H.265, with the CPU as the fallback as on Windows. Intel Macs use a bitrate mode, since their VideoToolbox has no constant-quality mode.
- **Updates in the app**: a new version is downloaded from this repository's releases, and after Clip Radar quits, the new Clip Radar.app replaces the old one and opens. It needs Clip Radar to be in a folder you can write to, like Applications.
- **Tool downloads for the Mac** (Settings › Downloads and tools): FFmpeg from Martin Riedl's signed builds (evermeet.cx as a fallback), yt-dlp's macOS build and TwitchDownloader's MacOS build, each for your chip. FFmpeg and yt-dlp installed with Homebrew are found too, even though apps opened from Finder don't see Homebrew's folder on the `PATH`.
- **Saved sign-ins are encrypted** with a random key kept in your login Keychain.
- **The clip hotkey is ⌃⌥C** (Control+Option+C), from any app while Clip Radar's window is open. No Accessibility permission needed.
- **Tools end with Clip Radar** even after a Force Quit: a small watcher stops FFmpeg, yt-dlp and TwitchDownloader when Clip Radar ends for any reason.
- "Couldn't delete: in use" names the program holding the file (from `lsof`); Settings › Performance shows the Mac's free memory; system sounds for a queued and a finished clip; Finder's file dialogs; Safari as a browser to take cookies from.
- `scripts/install.sh`, `scripts/run.sh` and `scripts/build_app.sh` (with optional Developer ID signing and notarization), and a GitHub Actions workflow that tests, builds on both chips, self-tests each build and publishes releases.

### Changed
- Clips and projects live in `~/Movies/Clip Radar`; settings, tools, models and logs in `~/Library/Application Support/ClipRadar`.
- Wording for the Mac: Finder instead of File Explorer, "Keep the Mac responsive", and Keychain instead of "your Windows account". "Keep the Mac responsive" runs FFmpeg at a lower priority (`nice`).
- Whisper runs on the CPU on a Mac (CTranslate2 has no Metal support), so the NVIDIA GPU-support download isn't offered.
