"""Daemon LocalWhispr: escuta comandos via Unix socket."""

from __future__ import annotations

import asyncio
import os
import signal
import sys
from pathlib import Path

SOCKET_PATH = Path(os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")) / "localwhispr.sock"


class LocalWhisprDaemon:
    """Daemon que escuta comandos via Unix socket e orquestra os pipelines."""

    def __init__(self, app: "LocalWhisprApp") -> None:
        self._app = app
        self._server: asyncio.AbstractServer | None = None

    async def handle_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        """Processa um comando recebido via socket."""
        try:
            data = await asyncio.wait_for(reader.read(1024), timeout=5.0)
            command = data.decode().strip()

            response = self._dispatch(command)
            writer.write(response.encode())
            await writer.drain()
        except asyncio.TimeoutError:
            writer.write(b"ERR timeout")
            await writer.drain()
        except Exception as e:
            writer.write(f"ERR {e}".encode())
            await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()

    def _dispatch(self, command: str) -> str:
        """Despacha o comando para a ação correta."""
        match command:
            case "dictate":
                return self._app.toggle_dictation()
            case "screenshot":
                return self._app.toggle_screenshot()
            case "meeting":
                return self._app.toggle_meeting()
            case "status":
                return self._app.get_status()
            case "stop":
                return self._app.force_stop()
            case "ping":
                return "pong"
            case "quit":
                asyncio.get_event_loop().call_soon(self._shutdown)
                return "OK bye"
            case _:
                return f"ERR comando desconhecido: {command}"

    def _shutdown(self) -> None:
        """Encerra o daemon."""
        print("[localwhispr] Encerrando daemon...")
        if self._server:
            self._server.close()
        asyncio.get_event_loop().stop()

    async def start(self) -> None:
        """Inicia o servidor Unix socket."""
        # Remove socket antigo se existir
        if SOCKET_PATH.exists():
            SOCKET_PATH.unlink()

        self._server = await asyncio.start_unix_server(
            self.handle_client, path=str(SOCKET_PATH)
        )
        # Permissão: apenas o usuário atual
        SOCKET_PATH.chmod(0o600)

        print(f"[localwhispr] Daemon escutando em {SOCKET_PATH}")
        print("[localwhispr] Pronto! Configure atalhos do GNOME para enviar comandos.")
        print("[localwhispr]   Ditado:     localwhispr ctl dictate")
        print("[localwhispr]   Screenshot: localwhispr ctl screenshot")
        print("[localwhispr]   Reunião:    localwhispr ctl meeting")
        print()

        async with self._server:
            await self._server.serve_forever()

    async def cleanup(self) -> None:
        """Limpa recursos ao encerrar."""
        if self._server:
            self._server.close()
            await self._server.wait_closed()
        if SOCKET_PATH.exists():
            SOCKET_PATH.unlink()


def _merge_speaker_segments(
    mic_segments: list[tuple[float, float, str]],
    monitor_segments: list[tuple[float, float, str]],
) -> str:
    """Intercala segmentos de mic e monitor por timestamp com labels [Eu]/[Outro]."""
    tagged: list[tuple[float, str, str]] = []
    for start, _end, text in mic_segments:
        tagged.append((start, "[Eu]", text))
    for start, _end, text in monitor_segments:
        tagged.append((start, "[Outro]", text))

    # Ordena por timestamp
    tagged.sort(key=lambda x: x[0])

    # Agrupa segmentos consecutivos do mesmo falante
    parts: list[str] = []
    current_speaker = ""
    current_texts: list[str] = []
    for _, speaker, text in tagged:
        if speaker != current_speaker:
            if current_texts:
                parts.append(f"{current_speaker} {' '.join(current_texts)}")
            current_speaker = speaker
            current_texts = [text]
        else:
            current_texts.append(text)
    if current_texts:
        parts.append(f"{current_speaker} {' '.join(current_texts)}")

    return "\n".join(parts)


class LocalWhisprApp:
    """Lógica da aplicação: gerencia estado e pipelines."""

    def __init__(
        self,
        recorder: "AudioRecorder",
        transcriber: "Transcriber",
        cleanup: "AICleanup",
        screenshot_cmd: "ScreenshotCommand",
        typer: "Typer",
        notif_config: "NotificationConfig",
        meeting_config: "MeetingConfig | None" = None,
        whisper_config: "WhisperConfig | None" = None,
        ollama_config: "OllamaConfig | None" = None,
        capture_monitor: bool = False,
    ) -> None:
        self._recorder = recorder
        self._transcriber = transcriber
        self._cleanup = cleanup
        self._screenshot_cmd = screenshot_cmd
        self._typer = typer
        self._notif = notif_config
        self._meeting_config = meeting_config
        self._whisper_config = whisper_config
        self._ollama_config = ollama_config
        self._capture_monitor = capture_monitor
        self._recording = False
        self._processing = False
        self._mode: str = ""  # "dictate", "screenshot", ou "meeting"
        self._meeting_recorder = None
        self._dual_recorder = None  # DualRecorder para dictate com monitor

    def toggle_dictation(self) -> str:
        """Toggle gravação de ditado."""
        if self._processing:
            return "BUSY processando"

        if self._recording and self._mode == "dictate":
            # Parar gravação e processar
            return self._stop_and_process_dictation()
        elif not self._recording:
            # Iniciar gravação
            self._mode = "dictate"
            self._recording = True

            if self._capture_monitor:
                from localwhispr.recorder import DualRecorder
                self._dual_recorder = DualRecorder(
                    config=type("C", (), {"sample_rate": self._recorder.sample_rate, "channels": self._recorder.channels})()
                )
                self._dual_recorder.start()
                print("[localwhispr] ● Gravando ditado (mic + headset)...")
            else:
                self._recorder.start()
                print("[localwhispr] ● Gravando ditado...")

            from localwhispr.notifier import notify_recording_start
            notify_recording_start(self._notif)

            return "OK recording"
        else:
            return f"BUSY modo={self._mode}"

    def toggle_screenshot(self) -> str:
        """Toggle gravação para comando com screenshot."""
        if self._processing:
            return "BUSY processando"

        if self._recording and self._mode == "screenshot":
            return self._stop_and_process_screenshot()
        elif not self._recording:
            self._mode = "screenshot"
            self._recording = True
            self._recorder.start()

            from localwhispr.notifier import notify_recording_start
            notify_recording_start(self._notif)

            print("[localwhispr] ◉ Gravando comando + screenshot...")
            return "OK recording"
        else:
            return f"BUSY modo={self._mode}"

    def toggle_meeting(self) -> str:
        """Toggle gravação de reunião."""
        if self._processing:
            return "BUSY processando"

        if self._recording and self._mode == "meeting":
            return self._stop_and_process_meeting()
        elif not self._recording:
            return self._start_meeting()
        else:
            return f"BUSY modo={self._mode}"

    def get_status(self) -> str:
        """Retorna status atual."""
        if self._processing:
            return f"STATUS processing mode={self._mode}"
        if self._recording:
            return f"STATUS recording mode={self._mode}"
        return "STATUS idle"

    def force_stop(self) -> str:
        """Para gravação sem processar."""
        if self._recording and self._mode == "meeting" and self._meeting_recorder:
            self._meeting_recorder.stop()
            self._meeting_recorder = None
            self._recording = False
            self._mode = ""
            print("[localwhispr] ■ Reunião cancelada.")
            return "OK stopped"
        elif self._recording:
            if self._dual_recorder:
                self._dual_recorder.stop()
                self._dual_recorder = None
            else:
                self._recorder.stop()
            self._recording = False
            self._mode = ""
            print("[localwhispr] ■ Gravação cancelada.")
            return "OK stopped"
        return "OK already_idle"

    def _stop_and_process_dictation(self) -> str:
        """Para gravação e inicia pipeline de ditado em thread."""
        import threading

        from localwhispr.notifier import notify_recording_stop
        notify_recording_stop(self._notif)

        print("[localwhispr] ■ Parando gravação...")

        if self._dual_recorder:
            mic_bytes, monitor_bytes = self._dual_recorder.stop()
            self._dual_recorder = None
            self._recording = False

            if (not mic_bytes or len(mic_bytes) < 1000) and (not monitor_bytes or len(monitor_bytes) < 1000):
                print("[localwhispr] Gravação muito curta, ignorando.")
                self._mode = ""
                return "OK too_short"

            self._processing = True
            threading.Thread(
                target=self._process_dictation_dual, args=(mic_bytes, monitor_bytes), daemon=True
            ).start()
        else:
            wav_bytes = self._recorder.stop()
            self._recording = False

            if not wav_bytes or len(wav_bytes) < 1000:
                print("[localwhispr] Gravação muito curta, ignorando.")
                self._mode = ""
                return "OK too_short"

            self._processing = True
            threading.Thread(
                target=self._process_dictation, args=(wav_bytes,), daemon=True
            ).start()

        return "OK processing"

    def _process_dictation(self, wav_bytes: bytes) -> None:
        """Pipeline simples: transcrição → IA cleanup → digitar."""
        from localwhispr.notifier import notify_done, notify_error

        try:
            print("[localwhispr] Transcrevendo...")
            raw_text = self._transcriber.transcribe(wav_bytes)
            if not raw_text:
                print("[localwhispr] Nenhum texto detectado.")
                notify_error("Nenhuma fala detectada", self._notif)
                return

            print("[localwhispr] Polindo com IA...")
            cleaned_text = self._cleanup.cleanup(raw_text)

            print(f"[localwhispr] Digitando: {cleaned_text[:80]}...")
            self._typer.type_text(cleaned_text)
            notify_done(cleaned_text, self._notif)

        except Exception as e:
            print(f"[localwhispr] ERRO no pipeline: {e}")
            notify_error(str(e), self._notif)
        finally:
            self._processing = False
            self._mode = ""

    def _process_dictation_dual(self, mic_bytes: bytes, monitor_bytes: bytes) -> None:
        """Pipeline dual: transcreve mic + monitor separadamente, merge com labels, cleanup, digitar."""
        from localwhispr.notifier import notify_done, notify_error

        try:
            # Transcreve mic (Eu)
            print("[localwhispr] Transcrevendo mic...")
            mic_segments = self._transcriber.transcribe_with_timestamps(mic_bytes) if mic_bytes and len(mic_bytes) > 1000 else []

            # Transcreve monitor (Outro)
            print("[localwhispr] Transcrevendo headset...")
            monitor_segments = self._transcriber.transcribe_with_timestamps(monitor_bytes) if monitor_bytes and len(monitor_bytes) > 1000 else []

            if not mic_segments and not monitor_segments:
                print("[localwhispr] Nenhuma fala detectada.")
                notify_error("Nenhuma fala detectada", self._notif)
                return

            # Merge intercalado por timestamp com labels
            labeled_text = _merge_speaker_segments(mic_segments, monitor_segments)
            print(f"[localwhispr] Conversa mesclada: {labeled_text[:120]}...")

            # AI cleanup com suporte a labels
            print("[localwhispr] Polindo com IA...")
            cleaned_text = self._cleanup.cleanup_conversation(labeled_text)

            print(f"[localwhispr] Digitando: {cleaned_text[:80]}...")
            self._typer.type_text(cleaned_text)
            notify_done(cleaned_text, self._notif)

        except Exception as e:
            print(f"[localwhispr] ERRO no pipeline dual: {e}")
            notify_error(str(e), self._notif)
        finally:
            self._processing = False
            self._mode = ""

    def _stop_and_process_screenshot(self) -> str:
        """Para gravação e inicia pipeline de screenshot em thread."""
        import threading

        from localwhispr.notifier import notify_recording_stop
        notify_recording_stop(self._notif)

        print("[localwhispr] ■ Parando gravação de comando...")
        wav_bytes = self._recorder.stop()
        self._recording = False

        if not wav_bytes or len(wav_bytes) < 1000:
            print("[localwhispr] Gravação muito curta, ignorando.")
            self._mode = ""
            return "OK too_short"

        self._processing = True
        threading.Thread(
            target=self._process_screenshot, args=(wav_bytes,), daemon=True
        ).start()
        return "OK processing"

    def _process_screenshot(self, wav_bytes: bytes) -> None:
        """Pipeline: transcrição → screenshot + LLM multimodal → digitar."""
        from localwhispr.notifier import notify_done, notify_error

        try:
            print("[localwhispr] Transcrevendo comando...")
            command_text = self._transcriber.transcribe(wav_bytes)
            if not command_text:
                print("[localwhispr] Nenhum comando detectado.")
                notify_error("Nenhum comando detectado", self._notif)
                return

            print(f"[localwhispr] Executando: {command_text[:80]}...")
            result = self._screenshot_cmd.execute(command_text)

            if result:
                print(f"[localwhispr] Digitando resposta: {result[:80]}...")
                self._typer.type_text(result)
                notify_done(result, self._notif)
            else:
                notify_error("IA não retornou resposta", self._notif)

        except Exception as e:
            print(f"[localwhispr] ERRO no pipeline screenshot: {e}")
            notify_error(str(e), self._notif)
        finally:
            self._processing = False
            self._mode = ""

    # ── Meeting mode ────────────────────────────────────────────────────

    def _start_meeting(self) -> str:
        """Inicia gravação de reunião."""
        from localwhispr.meeting import MeetingRecorder
        from localwhispr.notifier import notify, play_sound

        if not self._meeting_config:
            return "ERR meeting_config ausente"

        try:
            self._meeting_recorder = MeetingRecorder(self._meeting_config)
            output_dir = self._meeting_recorder.start()
        except RuntimeError as e:
            print(f"[localwhispr] ERRO ao iniciar meeting: {e}")
            return f"ERR {e}"

        self._mode = "meeting"
        self._recording = True

        play_sound("device-added", self._notif)
        print(f"[localwhispr] ● Gravando reunião em {output_dir}")
        return "OK meeting_recording"

    def _stop_and_process_meeting(self) -> str:
        """Para gravação de reunião e inicia pós-processamento."""
        import threading
        from localwhispr.notifier import play_sound

        if not self._meeting_recorder:
            self._recording = False
            self._mode = ""
            return "ERR no_meeting_recorder"

        print("[localwhispr] ■ Parando gravação da reunião...")
        play_sound("device-removed", self._notif)

        files = self._meeting_recorder.stop()
        self._recording = False

        if not files:
            self._mode = ""
            self._meeting_recorder = None
            return "ERR meeting_no_files"

        self._processing = True
        threading.Thread(
            target=self._process_meeting, args=(files,), daemon=True
        ).start()
        return "OK meeting_processing"

    def _process_meeting(self, files) -> None:
        """Pipeline: transcrição chunked + ata IA."""
        from localwhispr.meeting_processor import process_meeting
        from localwhispr.notifier import notify, notify_error, play_sound

        try:
            results = process_meeting(
                files=files,
                whisper_config=self._whisper_config,
                ollama_config=self._ollama_config,
                meeting_config=self._meeting_config,
                transcriber=self._transcriber,
            )

            if results:
                msg_parts = []
                if "transcription" in results:
                    msg_parts.append(f"Transcrição: {results['transcription']}")
                if "summary" in results:
                    msg_parts.append(f"Ata: {results['summary']}")

                notify(
                    "Reunião processada ✅",
                    "\n".join(msg_parts) if msg_parts else str(files.output_dir),
                    self._notif,
                )
                play_sound("complete", self._notif)
            else:
                notify_error("Nenhum conteúdo gerado da reunião", self._notif)

        except Exception as e:
            print(f"[localwhispr] ERRO no pipeline de meeting: {e}")
            notify_error(f"Erro no meeting: {e}", self._notif)
        finally:
            self._processing = False
            self._mode = ""
            self._meeting_recorder = None
