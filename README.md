# LocalWhispr

Multimodal voice dictation with AI for Linux (GNOME Wayland).
Open-source alternative to [Wispr Flow](https://wisprflow.ai), combining the best of
[VibeVoice](https://github.com/mpaepper/vibevoice) and [vibe-local](https://github.com/craigvc/vibe-local).

## Features

- **AI-powered dictation**: speak naturally, AI removes hesitations, adds punctuation and formats text
- **Dual mic + headset capture**: transcribes your voice and the audio you hear, merged into a single text
- **Screenshot + Voice Command**: speak a command, the AI sees your screen and responds
- **Meeting Recording**: captures mic + system audio, transcribes and generates minutes with AI
- **Multi-language**: automatic language detection (supports mixing languages in the same session)
- **CUDA accelerated**: faster-whisper with float16 on GPU for ultra-fast transcription
- **100% local**: Ollama for AI, no data sent to the cloud
- **Native Wayland**: uses ydotool/wtype to type into any app
- **Native GNOME shortcuts**: uses GNOME custom shortcuts, no special permissions needed
- **Systemd service**: runs as a background daemon, auto-starts on boot

## Requirements

### Hardware

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| **GPU** | NVIDIA with 4GB+ VRAM (CUDA) | NVIDIA with 8GB+ VRAM |
| **RAM** | 8 GB | 16 GB+ |
| **CPU** | Any x86_64 | - |

> LocalWhispr works on CPU (`device: "cpu"` in config), but transcription will be **much slower**. With CUDA, a 1-minute transcription takes ~3s; on CPU it can take 30s+.

### Software

| Requirement | Version | Notes |
|-------------|---------|-------|
| **Linux** | Kernel 5.x+ | Tested on CachyOS and Arch Linux |
| **GNOME** | 45+ | With Wayland (does not work with X11/Xorg) |
| **Python** | 3.12+ | - |
| **PipeWire** | 0.3+ | Already included in most modern distros |
| **NVIDIA Driver** | 535+ | With CUDA support |
| **CUDA Toolkit** | 12.x | For GPU acceleration |
| **Ollama** | 0.3+ | For local AI |

## Installation

### 1. System dependencies

#### Arch Linux / CachyOS / Manjaro

```bash
# Wayland tools (required)
sudo pacman -S ydotool wl-clipboard wtype

# Audio (required)
sudo pacman -S portaudio pipewire pipewire-pulse

# Screenshot (at least one)
sudo pacman -S grim           # or use GNOME's native PrintScreen

# Sound notifications
sudo pacman -S libcanberra

# CUDA (if you have an NVIDIA GPU)
sudo pacman -S cuda cudnn
```

#### Ubuntu / Debian (22.04+)

```bash
# Wayland tools
sudo apt install ydotool wl-clipboard wtype

# Audio
sudo apt install portaudio19-dev pipewire pipewire-pulse

# Screenshot
sudo apt install grim

# Sound notifications
sudo apt install libcanberra0

# CUDA - follow the official guide:
# https://developer.nvidia.com/cuda-downloads
```

#### Fedora

```bash
# Wayland tools
sudo dnf install ydotool wl-clipboard wtype

# Audio
sudo dnf install portaudio-devel pipewire pipewire-pulseaudio

# Screenshot
sudo dnf install grim

# Sound notifications
sudo dnf install libcanberra

# CUDA - follow the RPM Fusion guide:
# https://rpmfusion.org/Howto/CUDA
```

### 2. Enable the ydotool daemon

`ydotool` needs a daemon running to simulate keyboard input on Wayland:

```bash
systemctl --user enable --now ydotool
```

Verify it's working:

```bash
systemctl --user status ydotool
# Should show "active (running)"
```

### 3. Install Ollama

```bash
curl -fsSL https://ollama.com/install.sh | sh
sudo systemctl enable --now ollama
```

Download the required models:

```bash
# For text polishing (dictation) and meeting minutes (~2GB)
ollama pull llama3.2

# For screenshot + AI mode (multimodal, ~8GB)
ollama pull gemma3:12b
```

> **Tip**: If you have limited VRAM, use `llama3.2:1b` for cleanup and `llava:7b` for vision. Edit `config.yaml` afterwards.

### 4. Clone and install LocalWhispr

```bash
git clone https://github.com/guibastosm/ai-meeting-notes.git
cd ai-meeting-notes

# Create virtual environment and install
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

Or with `uv` (faster):

```bash
git clone https://github.com/guibastosm/ai-meeting-notes.git
cd ai-meeting-notes

uv venv && source .venv/bin/activate
uv pip install -e .
```

### 5. Configure

Copy and edit the configuration file:

```bash
cp config.yaml config.local.yaml   # (optional) create your local copy
```

Edit `config.yaml` according to your needs:

```yaml
shortcuts:
  dictate: "<Ctrl><Super>d"      # dictation shortcut
  screenshot: "<Ctrl><Shift>s"   # screenshot + AI shortcut
  meeting: "<Ctrl><Super>m"      # meeting recording shortcut

whisper:
  model: "large-v3"              # or "base", "small", "medium" (less VRAM)
  language: ""                   # empty = auto-detect (supports multiple languages)
  device: "cuda"                 # or "cpu" if no NVIDIA GPU
  compute_type: "float16"        # or "int8" for less VRAM

ollama:
  base_url: "http://localhost:11434"
  cleanup_model: "llama3.2"      # model for text polishing
  vision_model: "gemma3:12b"     # multimodal model for screenshot

dictate:
  capture_monitor: true          # capture headset audio in addition to mic

meeting:
  output_dir: "~/LocalWhispr/meetings"
  summary_model: "llama3.2"
```

**Whisper Models vs VRAM:**

| Model | VRAM Required | Quality | Speed |
|-------|--------------|---------|-------|
| `base` | ~1 GB | Good | Very fast |
| `small` | ~2 GB | Better | Fast |
| `medium` | ~5 GB | Great | Medium |
| `large-v3` | ~10 GB | Excellent | Slower |

### 6. Register GNOME shortcuts

```bash
source .venv/bin/activate
localwhispr setup-shortcuts
```

This registers the shortcuts defined in `config.yaml` as GNOME custom shortcuts.

### 7. Start LocalWhispr

#### Option A: Direct in terminal (for testing)

```bash
source .venv/bin/activate
localwhispr serve --preload-model
```

#### Option B: As a systemd service (recommended)

The systemd service auto-starts on boot and runs in the background.

**Important**: Edit `localwhispr.service` before copying, replacing paths for your user:

```bash
# Edit the file with your paths
sed -i "s|/home/morcegod|$HOME|g" localwhispr.service
sed -i "s|/run/user/1000|/run/user/$(id -u)|g" localwhispr.service

# Copy to user systemd
mkdir -p ~/.config/systemd/user
cp localwhispr.service ~/.config/systemd/user/

# Enable and start
systemctl --user daemon-reload
systemctl --user enable --now localwhispr

# Verify it's running
systemctl --user status localwhispr
```

To view logs in real-time:

```bash
journalctl --user -u localwhispr -f
```

## Usage

| Action | Shortcut (default) | What it does |
|--------|-------------------|--------------|
| **Dictation** | `Ctrl+Super+D` | Press to record. Press again to transcribe, polish and type. |
| **Screenshot + AI** | `Ctrl+Shift+S` | Press to record voice command. Press again to capture screen and send to LLM. |
| **Meeting** | `Ctrl+Super+M` | Press to start recording. Press again to stop, transcribe and generate minutes. |

### Usage examples

1. **Dictation**: Open any editor, press `Ctrl+Super+D`, speak, press again. The polished text appears where the cursor is.
2. **Dual dictation**: With `capture_monitor: true`, LocalWhispr captures your voice AND headset audio, merging everything into a single transcription.
3. **Screenshot**: With code on screen, press `Ctrl+Shift+S`, say "explain this code", press again. The AI analyzes the screen and types the explanation.
4. **Meeting**: Join a call, press `Ctrl+Super+M`. When done, press again. Find the transcription and minutes in `~/LocalWhispr/meetings/`.

### Sound feedback

| Sound | Meaning |
|-------|---------|
| "device connected" sound | Recording started |
| "device removed" sound | Recording stopped, processing... |
| "complete" sound | Text typed / meeting processed |

### Meeting output structure

```
~/LocalWhispr/meetings/2026-02-12_17-30/
  mic.wav              # Microphone audio (your voice)
  system.wav           # System audio (what you hear)
  combined.wav         # Mix of both channels
  transcription.md     # Full transcription with timestamps
  summary.md           # AI-generated meeting minutes
```

### Daemon commands

```bash
localwhispr ctl dictate      # Toggle dictation
localwhispr ctl screenshot   # Toggle screenshot + AI
localwhispr ctl meeting      # Toggle meeting recording
localwhispr ctl status       # Check status
localwhispr ctl stop         # Cancel recording
localwhispr ctl ping         # Check if daemon is alive
localwhispr ctl quit         # Shut down the daemon
```

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│  GNOME Shortcuts                                                 │
│  Ctrl+Super+D │ Ctrl+Shift+S │ Ctrl+Super+M                     │
│       │              │              │                             │
│       ▼              ▼              ▼                             │
│  ctl dictate    ctl screenshot  ctl meeting                      │
│       │              │              │                             │
│       └──────────────┼──────────────┘                             │
│                      ▼                                            │
│              Unix Socket → Daemon                                 │
│              ┌───────┼────────┐                                   │
│              ▼       ▼        ▼                                   │
│          Dictation Screenshot Meeting                             │
│           │        │          │                                   │
│   Mic+Monitor   Mic→Whisper  parecord (mic + monitor)            │
│    →Whisper    +Print→Ollama   →Whisper→Ollama                   │
│     →Ollama     multimodal     minutes/summary                   │
│      cleanup      │          │                                   │
│           │        ▼          ▼                                   │
│           ▼    wl-copy→App  ~/LocalWhispr/meetings/               │
│       wl-copy→App                                                │
└──────────────────────────────────────────────────────────────────┘
```

## Pipelines

**Dictation (simple):**
```
Shortcut → mic → faster-whisper (CUDA) → Ollama cleanup → wl-copy → Ctrl+V → App
```

**Dictation (dual mic + headset):**
```
Shortcut → mic + parecord monitor → faster-whisper ×2 → merge by timestamp → Ollama cleanup → wl-copy → Ctrl+V → App
```

**Screenshot + AI:**
```
Shortcut → mic → faster-whisper → PrintScreen → wl-paste → base64 → Ollama multimodal → wl-copy → Ctrl+V → App
```

**Meeting:**
```
Shortcut → parecord (mic) + parecord (monitor) → [record to disk]
      → Shortcut (stop) → mix audio → faster-whisper chunked → Ollama minutes → ~/LocalWhispr/meetings/
```

## Troubleshooting

**"Daemon is not running"**
```bash
localwhispr serve --preload-model
# or
systemctl --user restart localwhispr
```

**"ydotoold is not running"**
```bash
systemctl --user enable --now ydotool
```

**"Could not connect to Ollama"**
```bash
sudo systemctl start ollama
ollama list   # check if models are downloaded
```

**Slow transcription or VRAM error**
- Use a smaller model: `model: "small"` or `model: "medium"` in config.yaml
- Use `compute_type: "int8"` to reduce VRAM usage
- Check if CUDA is active: `nvidia-smi`

**Text not typed / clipboard not working**
```bash
# Check if wl-clipboard is installed
wl-copy "test" && wl-paste

# Check if ydotool can simulate key presses
ydotool key 29:1 47:1 47:0 29:0   # simulates Ctrl+V
```

**Headset audio not captured**
```bash
# List audio devices
pactl list sources short

# Look for a .monitor containing "usb" (USB headset/dongle)
# Edit config.yaml and set monitor_source explicitly if needed
```

**No sound feedback**
```bash
# Test if canberra works
canberra-gtk-play -i device-added
```

## License

MIT
