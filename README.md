# VisionFlow

Ditado por voz multimodal com IA para Linux (GNOME Wayland).
Alternativa open-source ao [Wispr Flow](https://wisprflow.ai), combinando o melhor do
[VibeVoice](https://github.com/mpaepper/vibevoice) e [vibe-local](https://github.com/craigvc/vibe-local).

## Features

- **Ditado com IA**: fale naturalmente, a IA remove hesitações, pontua e formata o texto
- **Screenshot + Comando de Voz**: fale um comando, a IA vê sua tela e responde
- **Gravação de Reuniões**: captura mic + áudio do sistema, transcreve e gera ata com IA
- **CUDA acelerado**: faster-whisper com float16 na GPU para transcrição ultra-rápida
- **100% local**: Ollama para IA, sem enviar dados para nuvem
- **Wayland nativo**: usa ydotool/wtype para digitar em qualquer app
- **Atalhos GNOME nativos**: usa os custom shortcuts do GNOME, sem necessidade de permissões especiais
- **Systemd service**: roda como daemon em background

## Arquitetura

```
┌──────────────────────────────────────────────────────────────────┐
│  GNOME Shortcuts                                                 │
│  Ctrl+Shift+D │ Ctrl+Shift+S │ Ctrl+Shift+M                     │
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
│     Mic→Whisper  Mic→Whisper  pw-record (mic + monitor)          │
│      →Ollama    +grim→Ollama   →Whisper→Ollama                   │
│       cleanup    multimodal     ata/resumo                       │
│           │        │          │                                   │
│           ▼        ▼          ▼                                   │
│       ydotool → App      ~/VisionFlow/meetings/                  │
└──────────────────────────────────────────────────────────────────┘
```

## Requisitos

- **Sistema**: Linux com GNOME + Wayland (testado no CachyOS/GNOME 49)
- **GPU**: NVIDIA com CUDA (recomendado, funciona em CPU também)
- **Python**: 3.12+
- **Ollama**: rodando localmente

## Instalação

### 1. Dependências do sistema (CachyOS/Arch)

```bash
# Ferramentas Wayland
sudo pacman -S ydotool wl-clipboard grim

# Audio
sudo pacman -S portaudio pipewire

# CUDA (se ainda não tem)
sudo pacman -S cuda cudnn

# Notificações
sudo pacman -S libnotify

# ydotool daemon
systemctl --user enable --now ydotool
```

### 2. Ollama

```bash
curl -fsSL https://ollama.com/install.sh | sh
sudo systemctl enable --now ollama
ollama pull llama3.2           # para polimento de texto
ollama pull gemma3:12b         # para modo screenshot (multimodal)
```

### 3. VisionFlow

```bash
cd ai-meeting-notes
uv venv && source .venv/bin/activate
uv pip install -e .
```

### 4. Configurar atalhos GNOME

```bash
# Registra atalhos automaticamente (padrão: Ctrl+Shift+D, Ctrl+Shift+S, Ctrl+Shift+M)
visionflow setup-shortcuts

# Ou com atalhos customizados:
visionflow setup-shortcuts --dictate "<Super>d" --screenshot "<Super>s" --meeting "<Super>m"
```

### 5. Iniciar o daemon

```bash
# Direto no terminal
visionflow serve --preload-model

# Ou como serviço systemd (background)
cp visionflow.service ~/.config/systemd/user/
systemctl --user enable --now visionflow
```

## Uso

| Ação | Atalho (padrão) | O que faz |
|------|-----------------|-----------|
| **Ditado** | `Ctrl+Shift+D` | Pressione uma vez para começar a gravar. Pressione de novo para parar, transcrever, polir e digitar. |
| **Screenshot + IA** | `Ctrl+Shift+S` | Pressione uma vez para gravar comando de voz. Pressione de novo para capturar a tela, enviar comando + screenshot para o LLM multimodal e digitar a resposta. |
| **Reunião** | `Ctrl+Shift+M` | Pressione para iniciar gravação (mic + áudio do sistema). Pressione de novo para parar, transcrever e gerar ata com IA. |

### Exemplos de uso

1. **Ditado**: Abra qualquer editor, pressione `Ctrl+Shift+D`, fale, pressione de novo. O texto polido aparece.
2. **Screenshot**: Com código na tela, pressione `Ctrl+Shift+S`, diga "explique esse código", pressione de novo. A IA analisa a tela e digita a explicação.
3. **Reunião**: Entre numa call, pressione `Ctrl+Shift+M`. Ao final da reunião, pressione de novo. Encontre a transcrição e ata em `~/VisionFlow/meetings/`.

### Estrutura de saída da reunião

```
~/VisionFlow/meetings/2026-02-12_17-30/
  mic.wav              # Áudio do microfone (sua voz)
  system.wav           # Áudio do sistema (o que você ouve)
  combined.wav         # Mix dos dois canais
  transcription.md     # Transcrição completa com timestamps
  summary.md           # Ata/resumo gerado por IA
```

### Comandos do daemon

```bash
visionflow ctl dictate      # Toggle ditado
visionflow ctl screenshot   # Toggle screenshot + IA
visionflow ctl meeting      # Toggle gravação de reunião
visionflow ctl status       # Verifica status
visionflow ctl stop         # Cancela gravação
visionflow ctl ping         # Verifica se daemon está vivo
visionflow ctl quit         # Encerra o daemon
```

## Configuração

Edite `config.yaml` (ou `~/.config/visionflow/config.yaml`):

```yaml
shortcuts:
  dictate: "<Ctrl><Shift>d"
  screenshot: "<Ctrl><Shift>s"
  meeting: "<Ctrl><Shift>m"

whisper:
  model: "large-v3"        # ou "base", "small", "medium"
  language: "pt"
  device: "cuda"           # ou "cpu"
  compute_type: "float16"

ollama:
  cleanup_model: "llama3.2"
  vision_model: "gemma3:12b"

typing:
  method: "clipboard"      # ou "ydotool"

meeting:
  output_dir: "~/VisionFlow/meetings"
  mic_source: "auto"         # "auto" detecta automaticamente
  monitor_source: "auto"     # ou nome explícito do PipeWire source
  sample_rate: 16000
  summary_model: "llama3.2"  # modelo Ollama para gerar ata
```

## Pipelines

**Ditado:**
```
Atalho GNOME → ctl dictate → Gravar áudio → faster-whisper (CUDA) → Ollama cleanup → clipboard → App focado
```

**Screenshot + IA:**
```
Atalho GNOME → ctl screenshot → Gravar áudio + grim screenshot → faster-whisper → Ollama multimodal → clipboard → App focado
```

**Reunião:**
```
Atalho GNOME → ctl meeting → pw-record (mic) + pw-record (monitor) → [grava em disco]
            → ctl meeting (stop) → mix audio → faster-whisper chunked → Ollama ata → salva em ~/VisionFlow/meetings/
```

## Troubleshooting

**"Daemon não está rodando"**
```bash
visionflow serve --preload-model
```

**"ydotoold não está rodando"**
```bash
systemctl --user enable --now ydotool
```

**"Não foi possível conectar ao Ollama"**
```bash
sudo systemctl start ollama
```

**Transcrição lenta**
- Use modelo menor: `model: "base"` ou `model: "small"` no config.yaml
- Verifique se CUDA está ativo: `nvidia-smi`

## Licença

MIT
