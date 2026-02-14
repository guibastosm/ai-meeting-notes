# LocalWhispr

Ditado por voz multimodal com IA para Linux (GNOME Wayland).
Alternativa open-source ao [Wispr Flow](https://wisprflow.ai), combinando o melhor do
[VibeVoice](https://github.com/mpaepper/vibevoice) e [vibe-local](https://github.com/craigvc/vibe-local).

## Features

- **Ditado com IA**: fale naturalmente, a IA remove hesitações, pontua e formata o texto
- **Captura dual mic + headset**: transcreve sua voz e o áudio que você ouve, com labels `[Eu]` / `[Outro]`
- **Screenshot + Comando de Voz**: fale um comando, a IA vê sua tela e responde
- **Gravação de Reuniões**: captura mic + áudio do sistema, transcreve e gera ata com IA
- **Multi-idioma**: detecção automática de idioma (suporta misturar português e inglês na mesma sessão)
- **CUDA acelerado**: faster-whisper com float16 na GPU para transcrição ultra-rápida
- **100% local**: Ollama para IA, sem enviar dados para nuvem
- **Wayland nativo**: usa ydotool/wtype para digitar em qualquer app
- **Atalhos GNOME nativos**: usa os custom shortcuts do GNOME, sem necessidade de permissões especiais
- **Systemd service**: roda como daemon em background, inicia automaticamente no boot

## Requisitos

### Hardware

| Componente | Mínimo | Recomendado |
|-----------|--------|-------------|
| **GPU** | NVIDIA com 4GB+ VRAM (CUDA) | NVIDIA com 8GB+ VRAM |
| **RAM** | 8 GB | 16 GB+ |
| **CPU** | Qualquer x86_64 | - |

> O LocalWhispr funciona em CPU (`device: "cpu"` no config), mas a transcrição será **muito mais lenta**. Com CUDA, uma transcrição de 1 minuto leva ~3s; em CPU pode levar 30s+.

### Software

| Requisito | Versão | Notas |
|-----------|--------|-------|
| **Linux** | Kernel 5.x+ | Testado em CachyOS e Arch Linux |
| **GNOME** | 45+ | Com Wayland (não funciona com X11/Xorg) |
| **Python** | 3.12+ | - |
| **PipeWire** | 0.3+ | Já vem na maioria das distros modernas |
| **NVIDIA Driver** | 535+ | Com suporte CUDA |
| **CUDA Toolkit** | 12.x | Para aceleração GPU |
| **Ollama** | 0.3+ | Para IA local |

## Instalacao

### 1. Dependencias do sistema

#### Arch Linux / CachyOS / Manjaro

```bash
# Ferramentas Wayland (obrigatório)
sudo pacman -S ydotool wl-clipboard wtype

# Áudio (obrigatório)
sudo pacman -S portaudio pipewire pipewire-pulse

# Screenshot (pelo menos um)
sudo pacman -S grim           # ou use o PrintScreen nativo do GNOME

# Notificações sonoras
sudo pacman -S libcanberra

# CUDA (se tiver GPU NVIDIA)
sudo pacman -S cuda cudnn
```

#### Ubuntu / Debian (22.04+)

```bash
# Ferramentas Wayland
sudo apt install ydotool wl-clipboard wtype

# Áudio
sudo apt install portaudio19-dev pipewire pipewire-pulse

# Screenshot
sudo apt install grim

# Notificações sonoras
sudo apt install libcanberra0

# CUDA - siga o guia oficial:
# https://developer.nvidia.com/cuda-downloads
```

#### Fedora

```bash
# Ferramentas Wayland
sudo dnf install ydotool wl-clipboard wtype

# Áudio
sudo dnf install portaudio-devel pipewire pipewire-pulseaudio

# Screenshot
sudo dnf install grim

# Notificações sonoras
sudo dnf install libcanberra

# CUDA - siga o guia RPM Fusion:
# https://rpmfusion.org/Howto/CUDA
```

### 2. Ativar o ydotool daemon

O `ydotool` precisa de um daemon rodando para simular teclado no Wayland:

```bash
systemctl --user enable --now ydotool
```

Verifique se está funcionando:

```bash
systemctl --user status ydotool
# Deve mostrar "active (running)"
```

### 3. Instalar o Ollama

```bash
curl -fsSL https://ollama.com/install.sh | sh
sudo systemctl enable --now ollama
```

Baixe os modelos necessários:

```bash
# Para polimento de texto (ditado) e atas de reunião (~2GB)
ollama pull llama3.2

# Para modo screenshot + IA (multimodal, ~8GB)
ollama pull gemma3:12b
```

> **Dica**: Se tiver pouca VRAM, use `llama3.2:1b` para cleanup e `llava:7b` para vision. Edite o `config.yaml` depois.

### 4. Clonar e instalar o LocalWhispr

```bash
git clone https://github.com/guibastosm/ai-meeting-notes.git
cd ai-meeting-notes

# Criar ambiente virtual e instalar
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

Ou com `uv` (mais rápido):

```bash
git clone https://github.com/guibastosm/ai-meeting-notes.git
cd ai-meeting-notes

uv venv && source .venv/bin/activate
uv pip install -e .
```

### 5. Configurar

Copie e edite o arquivo de configuração:

```bash
cp config.yaml config.local.yaml   # (opcional) crie sua cópia local
```

Edite o `config.yaml` conforme sua necessidade:

```yaml
shortcuts:
  dictate: "<Ctrl><Super>d"      # atalho para ditado
  screenshot: "<Ctrl><Shift>s"   # atalho para screenshot + IA
  meeting: "<Ctrl><Super>m"      # atalho para gravar reunião

whisper:
  model: "large-v3"              # ou "base", "small", "medium" (menos VRAM)
  language: ""                   # vazio = auto-detect (suporta múltiplos idiomas)
  device: "cuda"                 # ou "cpu" se não tiver GPU NVIDIA
  compute_type: "float16"        # ou "int8" para menos VRAM

ollama:
  base_url: "http://localhost:11434"
  cleanup_model: "llama3.2"      # modelo para polir texto
  vision_model: "gemma3:12b"     # modelo multimodal para screenshot

dictate:
  capture_monitor: true          # captura áudio do headset além do mic

meeting:
  output_dir: "~/LocalWhispr/meetings"
  summary_model: "llama3.2"
```

**Modelos Whisper vs VRAM:**

| Modelo | VRAM necessária | Qualidade | Velocidade |
|--------|----------------|-----------|------------|
| `base` | ~1 GB | Boa | Muito rápida |
| `small` | ~2 GB | Melhor | Rápida |
| `medium` | ~5 GB | Ótima | Média |
| `large-v3` | ~10 GB | Excelente | Mais lenta |

### 6. Registrar atalhos do GNOME

```bash
source .venv/bin/activate
localwhispr setup-shortcuts
```

Isso registra os atalhos definidos no `config.yaml` como custom shortcuts do GNOME.

### 7. Iniciar o LocalWhispr

#### Opção A: Direto no terminal (para testar)

```bash
source .venv/bin/activate
localwhispr serve --preload-model
```

#### Opção B: Como serviço systemd (recomendado)

O serviço systemd inicia automaticamente no boot e roda em background.

**Importante**: Edite o `localwhispr.service` antes de copiar, substituindo os caminhos para o seu usuário:

```bash
# Edite o arquivo com seus caminhos
sed -i "s|/home/morcegod|$HOME|g" localwhispr.service
sed -i "s|/run/user/1000|/run/user/$(id -u)|g" localwhispr.service

# Copie para o systemd do usuário
mkdir -p ~/.config/systemd/user
cp localwhispr.service ~/.config/systemd/user/

# Ative e inicie
systemctl --user daemon-reload
systemctl --user enable --now localwhispr

# Verifique se está rodando
systemctl --user status localwhispr
```

Para ver os logs em tempo real:

```bash
journalctl --user -u localwhispr -f
```

## Uso

| Ação | Atalho (padrão) | O que faz |
|------|-----------------|-----------|
| **Ditado** | `Ctrl+Super+D` | Pressione para gravar. Pressione de novo para transcrever, polir e digitar. |
| **Screenshot + IA** | `Ctrl+Shift+S` | Pressione para gravar comando de voz. Pressione de novo para capturar a tela e enviar ao LLM. |
| **Reunião** | `Ctrl+Super+M` | Pressione para iniciar gravação. Pressione de novo para parar, transcrever e gerar ata. |

### Exemplos de uso

1. **Ditado**: Abra qualquer editor, pressione `Ctrl+Super+D`, fale, pressione de novo. O texto polido aparece onde o cursor estiver.
2. **Ditado dual**: Com `capture_monitor: true`, o LocalWhispr captura sua voz E o áudio do headset, rotulando `[Eu]` e `[Outro]`.
3. **Screenshot**: Com código na tela, pressione `Ctrl+Shift+S`, diga "explique esse codigo", pressione de novo. A IA analisa a tela e digita a explicação.
4. **Reunião**: Entre numa call, pressione `Ctrl+Super+M`. Ao final, pressione de novo. Encontre a transcrição e ata em `~/LocalWhispr/meetings/`.

### Feedback sonoro

| Som | Significado |
|-----|-------------|
| Som de "device connected" | Gravação iniciada |
| Som de "device removed" | Gravação parada, processando... |
| Som de "complete" | Texto digitado / reunião processada |

### Estrutura de saída da reunião

```
~/LocalWhispr/meetings/2026-02-12_17-30/
  mic.wav              # Áudio do microfone (sua voz)
  system.wav           # Áudio do sistema (o que você ouve)
  combined.wav         # Mix dos dois canais
  transcription.md     # Transcrição completa com timestamps
  summary.md           # Ata/resumo gerado por IA
```

### Comandos do daemon

```bash
localwhispr ctl dictate      # Toggle ditado
localwhispr ctl screenshot   # Toggle screenshot + IA
localwhispr ctl meeting      # Toggle gravação de reunião
localwhispr ctl status       # Verifica status
localwhispr ctl stop         # Cancela gravação
localwhispr ctl ping         # Verifica se daemon está vivo
localwhispr ctl quit         # Encerra o daemon
```

## Arquitetura

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
│          Ditado  Screenshot  Reunião                              │
│           │        │          │                                   │
│   Mic+Monitor   Mic→Whisper  parecord (mic + monitor)            │
│    →Whisper    +Print→Ollama   →Whisper→Ollama                   │
│     →Ollama     multimodal     ata/resumo                        │
│      cleanup      │          │                                   │
│           │        ▼          ▼                                   │
│           ▼    wl-copy→App  ~/LocalWhispr/meetings/               │
│       wl-copy→App                                                │
└──────────────────────────────────────────────────────────────────┘
```

## Pipelines

**Ditado (simples):**
```
Atalho → mic → faster-whisper (CUDA) → Ollama cleanup → wl-copy → Ctrl+V → App
```

**Ditado (dual mic + headset):**
```
Atalho → mic + parecord monitor → faster-whisper ×2 → merge [Eu]/[Outro] → Ollama cleanup → wl-copy → Ctrl+V → App
```

**Screenshot + IA:**
```
Atalho → mic → faster-whisper → PrintScreen → wl-paste → base64 → Ollama multimodal → wl-copy → Ctrl+V → App
```

**Reunião:**
```
Atalho → parecord (mic) + parecord (monitor) → [grava em disco]
      → Atalho (stop) → mix áudio → faster-whisper chunked → Ollama ata → ~/LocalWhispr/meetings/
```

## Troubleshooting

**"Daemon não está rodando"**
```bash
localwhispr serve --preload-model
# ou
systemctl --user restart localwhispr
```

**"ydotoold não está rodando"**
```bash
systemctl --user enable --now ydotool
```

**"Não foi possível conectar ao Ollama"**
```bash
sudo systemctl start ollama
ollama list   # verifica se os modelos estão baixados
```

**Transcrição lenta ou erro de VRAM**
- Use modelo menor: `model: "small"` ou `model: "medium"` no config.yaml
- Use `compute_type: "int8"` para reduzir uso de VRAM
- Verifique se CUDA está ativo: `nvidia-smi`

**Texto não é digitado / clipboard não funciona**
```bash
# Verifique se wl-clipboard está instalado
wl-copy "teste" && wl-paste

# Verifique se ydotool consegue simular teclas
ydotool key 29:1 47:1 47:0 29:0   # simula Ctrl+V
```

**Áudio do headset não é capturado**
```bash
# Liste os dispositivos de áudio
pactl list sources short

# Procure por um .monitor que contenha "usb" (headset USB/dongle)
# Edite config.yaml e defina monitor_source explicitamente se necessário
```

**Sem feedback sonoro**
```bash
# Teste se canberra funciona
canberra-gtk-play -i device-added
```

## Licença

MIT
