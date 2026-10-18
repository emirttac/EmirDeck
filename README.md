# EmirDeck

Lightweight Windows Stream Deck / hotkey media player.

Runs in the system tray. Press an assigned key → fullscreen video, audio, or image.

**Author:** [github.com/emirttac](https://github.com/emirttac)

## Features

- Global hotkeys (including numpad)
- Fullscreen always-on-top playback (video / mp3 / images)
- ESC or click to close
- JSON config + settings UI
- Languages: English, Deutsch, Türkçe, 中文
- Native PyQt6 — no Electron
- Shared app mark (`assets/emirdeck.ico`) used for tray, windows, and installer

## Install (end users)

Download **`EmirDeck-Setup.exe`** from [Releases](https://github.com/emirttac/EmirDeck/releases) and run it.

- Modern Inno Setup wizard (English / Deutsch / Türkçe)
- **No Python install, no console windows, no online dependency download during setup**
- Everything needed is inside the installer
- Creates Start Menu + optional Desktop shortcut
- Launch EmirDeck at the end of setup

Install path: `%LOCALAPPDATA%\EmirDeck`

## Run from source (developers)

```powershell
git clone https://github.com/emirttac/EmirDeck.git
cd EmirDeck
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python main.py
```

Copy `config.example.json` → `config.json` if needed.

## Build installer (developers)

Requires Python + [Inno Setup 6](https://jrsoftware.org/isinfo.php).

```powershell
cd installer
.\build_setup.ps1
```

This builds:

1. Self-contained `EmirDeck.exe` (PyInstaller, PyQt6 + pynput bundled)
2. `EmirDeck-Setup.exe` (Inno Setup packages that folder)

## Config

`config.json` (next to `EmirDeck.exe` after install):

```json
{
  "language": "auto",
  "macros": [
    {
      "trigger_key": "numpad1",
      "video_path": "C:\\Videos\\clip.mp4",
      "loop": false
    }
  ]
}
```

`language`: `auto` | `en` | `de` | `tr` | `zh`

## License

MIT — see [LICENSE](LICENSE).
