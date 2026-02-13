"""Pós-processamento de reuniões: transcrição chunked + ata com IA."""

from __future__ import annotations

import io
import time
import wave
from datetime import timedelta
from pathlib import Path
from typing import TYPE_CHECKING

import httpx
import numpy as np

if TYPE_CHECKING:
    from visionflow.config import MeetingConfig, OllamaConfig, WhisperConfig
    from visionflow.meeting import MeetingFiles
    from visionflow.transcriber import Transcriber

# Tamanho de cada chunk para transcrição (5 minutos em samples a 16kHz)
CHUNK_DURATION_S = 300  # 5 minutos
# Limiar de palavras para resumo incremental
SUMMARY_WORD_LIMIT = 3000


def process_meeting(
    files: "MeetingFiles",
    whisper_config: "WhisperConfig",
    ollama_config: "OllamaConfig",
    meeting_config: "MeetingConfig",
    transcriber: "Transcriber | None" = None,
) -> dict[str, Path]:
    """Pipeline completo: transcrição + ata. Retorna paths dos arquivos gerados."""
    output_dir = files.output_dir
    results: dict[str, Path] = {}

    # 1. Transcrição
    print("[visionflow] Iniciando transcrição da reunião...")
    t0 = time.time()
    transcription = transcribe_meeting(files.combined_wav, whisper_config, transcriber)
    elapsed = time.time() - t0

    if not transcription:
        print("[visionflow] Nenhum áudio transcrito na reunião.")
        return results

    # Salva transcrição
    transcription_path = output_dir / "transcription.md"
    header = (
        f"# Transcrição da Reunião\n\n"
        f"**Data**: {files.started_at.strftime('%d/%m/%Y %H:%M')}\n"
        f"**Duração**: {_format_duration(files.duration_seconds)}\n"
        f"**Tempo de transcrição**: {elapsed:.1f}s\n\n---\n\n"
    )
    transcription_path.write_text(header + transcription, encoding="utf-8")
    results["transcription"] = transcription_path
    print(f"[visionflow] Transcrição salva: {transcription_path}")

    # 2. Ata / Resumo com IA
    print("[visionflow] Gerando ata da reunião com IA...")
    summary = generate_summary(transcription, ollama_config, meeting_config)

    if summary:
        summary_path = output_dir / "summary.md"
        summary_header = (
            f"# Ata da Reunião\n\n"
            f"**Data**: {files.started_at.strftime('%d/%m/%Y %H:%M')}\n"
            f"**Duração**: {_format_duration(files.duration_seconds)}\n\n---\n\n"
        )
        summary_path.write_text(summary_header + summary, encoding="utf-8")
        results["summary"] = summary_path
        print(f"[visionflow] Ata salva: {summary_path}")
    else:
        print("[visionflow] AVISO: não foi possível gerar ata.")

    return results


def transcribe_meeting(
    wav_path: Path,
    whisper_config: "WhisperConfig",
    transcriber: "Transcriber | None" = None,
) -> str:
    """Transcreve áudio longo em chunks com timestamps."""
    if not wav_path.exists() or wav_path.stat().st_size < 1000:
        return ""

    # Lê o áudio inteiro
    with wave.open(str(wav_path), "rb") as wf:
        sample_rate = wf.getframerate()
        n_frames = wf.getnframes()
        raw_data = wf.readframes(n_frames)

    audio = np.frombuffer(raw_data, dtype=np.int16)
    total_duration = len(audio) / sample_rate
    chunk_samples = CHUNK_DURATION_S * sample_rate

    print(f"[visionflow] Áudio: {total_duration:.0f}s ({total_duration/60:.1f} min)")

    # Reutiliza modelo já carregado pelo daemon, ou carrega novo
    if transcriber:
        model = transcriber._ensure_model()
        print("[visionflow] Reutilizando modelo Whisper do daemon")
    else:
        from faster_whisper import WhisperModel
        print(f"[visionflow] Carregando Whisper '{whisper_config.model}'...")
        model = WhisperModel(
            whisper_config.model,
            device=whisper_config.device,
            compute_type=whisper_config.compute_type,
        )

    # Transcreve em chunks
    parts: list[str] = []
    n_chunks = max(1, int(np.ceil(len(audio) / chunk_samples)))

    for i in range(n_chunks):
        start_sample = i * chunk_samples
        end_sample = min((i + 1) * chunk_samples, len(audio))
        chunk = audio[start_sample:end_sample]

        chunk_start_time = start_sample / sample_rate
        timestamp = _format_duration(chunk_start_time)

        print(f"[visionflow] Transcrevendo chunk {i+1}/{n_chunks} [{timestamp}]...")

        # Converte chunk para WAV em memória
        wav_buf = io.BytesIO()
        with wave.open(wav_buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            wf.writeframes(chunk.tobytes())
        wav_buf.seek(0)

        segments, _info = model.transcribe(
            wav_buf,
            language=whisper_config.language if whisper_config.language else None,
            beam_size=5,
            vad_filter=True,
            vad_parameters=dict(
                min_silence_duration_ms=500,
                speech_pad_ms=300,
            ),
        )

        chunk_text_parts: list[str] = []
        for segment in segments:
            # Timestamp absoluto = offset do chunk + timestamp do segmento
            abs_start = chunk_start_time + segment.start
            ts_str = _format_duration(abs_start)
            chunk_text_parts.append(f"[{ts_str}] {segment.text.strip()}")

        if chunk_text_parts:
            parts.extend(chunk_text_parts)

    return "\n\n".join(parts)


def generate_summary(
    transcription: str,
    ollama_config: "OllamaConfig",
    meeting_config: "MeetingConfig",
) -> str:
    """Gera ata/resumo da reunião via Ollama."""
    word_count = len(transcription.split())
    print(f"[visionflow] Transcrição: {word_count} palavras")

    if word_count <= SUMMARY_WORD_LIMIT:
        # Cabe numa única chamada
        return _ollama_summarize(transcription, ollama_config, meeting_config)
    else:
        # Resumo incremental: divide em blocos, resume cada, depois meta-resumo
        return _incremental_summary(transcription, ollama_config, meeting_config)


def _ollama_summarize(
    text: str,
    ollama_config: "OllamaConfig",
    meeting_config: "MeetingConfig",
) -> str:
    """Envia texto ao Ollama para gerar resumo."""
    base_url = ollama_config.base_url.rstrip("/")
    model = meeting_config.summary_model
    prompt = meeting_config.summary_prompt

    try:
        response = httpx.post(
            f"{base_url}/api/generate",
            json={
                "model": model,
                "prompt": f"{prompt}\n\nTranscrição da reunião:\n\n{text}",
                "stream": False,
                "options": {
                    "temperature": 0.3,
                    "num_predict": 4096,
                },
            },
            timeout=120.0,
        )
        response.raise_for_status()
        data = response.json()
        return data.get("response", "").strip()

    except httpx.ConnectError:
        print("[visionflow] ERRO: Não foi possível conectar ao Ollama.")
        return ""
    except Exception as e:
        print(f"[visionflow] ERRO na geração de ata: {e}")
        return ""


def _incremental_summary(
    transcription: str,
    ollama_config: "OllamaConfig",
    meeting_config: "MeetingConfig",
) -> str:
    """Resume transcrições longas em blocos e depois faz meta-resumo."""
    # Divide em blocos de ~2500 palavras
    words = transcription.split()
    block_size = 2500
    blocks: list[str] = []

    for i in range(0, len(words), block_size):
        block = " ".join(words[i:i + block_size])
        blocks.append(block)

    print(f"[visionflow] Resumo incremental: {len(blocks)} blocos")

    # Resume cada bloco
    partial_summaries: list[str] = []
    for idx, block in enumerate(blocks):
        print(f"[visionflow] Resumindo bloco {idx+1}/{len(blocks)}...")
        summary = _ollama_summarize(block, ollama_config, meeting_config)
        if summary:
            partial_summaries.append(f"## Parte {idx+1}\n\n{summary}")

    if not partial_summaries:
        return ""

    # Se só tem um bloco, retorna direto
    if len(partial_summaries) == 1:
        return partial_summaries[0]

    # Meta-resumo: combina os resumos parciais
    combined = "\n\n---\n\n".join(partial_summaries)
    print("[visionflow] Gerando meta-resumo...")

    meta_prompt = (
        "Você recebeu resumos parciais de uma reunião longa. "
        "Combine-os em um resumo único e coerente, mantendo o formato:\n"
        "1. RESUMO\n2. DECISÕES\n3. ACTION ITEMS\n4. TÓPICOS\n"
        "Elimine redundâncias e organize cronologicamente."
    )

    base_url = ollama_config.base_url.rstrip("/")
    try:
        response = httpx.post(
            f"{base_url}/api/generate",
            json={
                "model": meeting_config.summary_model,
                "prompt": f"{meta_prompt}\n\nResumos parciais:\n\n{combined}",
                "stream": False,
                "options": {
                    "temperature": 0.3,
                    "num_predict": 4096,
                },
            },
            timeout=120.0,
        )
        response.raise_for_status()
        data = response.json()
        return data.get("response", "").strip()
    except Exception as e:
        print(f"[visionflow] ERRO no meta-resumo: {e}")
        # Retorna os resumos parciais como fallback
        return combined


def _format_duration(seconds: float) -> str:
    """Formata segundos como HH:MM:SS."""
    td = timedelta(seconds=int(seconds))
    total_seconds = int(td.total_seconds())
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    secs = total_seconds % 60
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"
