"""LocalWhispr daemon: listens for commands via Unix socket."""

from __future__ import annotations

import asyncio
import os
import signal
import sys
from pathlib import Path

SOCKET_PATH = Path(os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")) / "localwhispr.sock"


class LocalWhisprDaemon:
    """Daemon that listens for commands via Unix socket and orchestrates pipelines."""

    def __init__(self, app: "LocalWhisprApp") -> None:
        self._app = app
        self._server: asyncio.AbstractServer | None = None

    async def handle_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        """Process a command received via socket."""
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
        """Dispatch command to the correct action."""
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
                return f"ERR unknown command: {command}"

    def _shutdown(self) -> None:
        """Shut down the daemon."""
        print("[localwhispr] Shutting down daemon...")
        if self._server:
            self._server.close()
        asyncio.get_event_loop().stop()

    async def start(self) -> None:
        """Start the Unix socket server."""
        # Remove stale socket if it exists
        if SOCKET_PATH.exists():
            SOCKET_PATH.unlink()

        self._server = await asyncio.start_unix_server(
            self.handle_client, path=str(SOCKET_PATH)
        )
        # Permission: current user only
        SOCKET_PATH.chmod(0o600)

        print(f"[localwhispr] Daemon listening on {SOCKET_PATH}")
        print("[localwhispr] Ready! Configure GNOME shortcuts to send commands.")
        print("[localwhispr]   Dictation:  localwhispr ctl dictate")
        print("[localwhispr]   Screenshot: localwhispr ctl screenshot")
        print("[localwhispr]   Meeting:    localwhispr ctl meeting")
        print()

        async with self._server:
            await self._server.serve_forever()

    async def cleanup(self) -> None:
        """Clean up resources on shutdown."""
        if self._server:
            self._server.close()
            await self._server.wait_closed()
        if SOCKET_PATH.exists():
            SOCKET_PATH.unlink()


def _merge_segments(
    mic_segments: list[tuple[float, float, str]],
    monitor_segments: list[tuple[float, float, str]],
) -> str:
    """Interleave mic and monitor segments by timestamp into a single text."""
    all_segments: list[tuple[float, str]] = []
    for start, _end, text in mic_segments:
        all_segments.append((start, text))
    for start, _end, text in monitor_segments:
        all_segments.append((start, text))

    # Sort by timestamp
    all_segments.sort(key=lambda x: x[0])

    return " ".join(text for _, text in all_segments)


class LocalWhisprApp:
    """Application logic: manages state and pipelines."""

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
        self._mode: str = ""  # "dictate", "screenshot", or "meeting"
        self._meeting_recorder = None
        self._dual_recorder = None  # DualRecorder for dictate with monitor

    def toggle_dictation(self) -> str:
        """Toggle dictation recording."""
        if self._processing:
            return "BUSY processing"

        if self._recording and self._mode == "dictate":
            # Stop recording and process
            return self._stop_and_process_dictation()
        elif not self._recording:
            # Start recording
            self._mode = "dictate"
            self._recording = True

            if self._capture_monitor:
                from localwhispr.recorder import DualRecorder
                self._dual_recorder = DualRecorder(
                    config=type("C", (), {"sample_rate": self._recorder.sample_rate, "channels": self._recorder.channels})()
                )
                self._dual_recorder.start()
                print("[localwhispr] ● Recording dictation (mic + headset)...")
            else:
                self._recorder.start()
                print("[localwhispr] ● Recording dictation...")

            from localwhispr.notifier import notify_recording_start
            notify_recording_start(self._notif)

            return "OK recording"
        else:
            return f"BUSY mode={self._mode}"

    def toggle_screenshot(self) -> str:
        """Toggle recording for screenshot command."""
        if self._processing:
            return "BUSY processing"

        if self._recording and self._mode == "screenshot":
            return self._stop_and_process_screenshot()
        elif not self._recording:
            self._mode = "screenshot"
            self._recording = True
            self._recorder.start()

            from localwhispr.notifier import notify_recording_start
            notify_recording_start(self._notif)

            print("[localwhispr] ◉ Recording command + screenshot...")
            return "OK recording"
        else:
            return f"BUSY mode={self._mode}"

    def toggle_meeting(self) -> str:
        """Toggle meeting recording."""
        if self._processing:
            return "BUSY processing"

        if self._recording and self._mode == "meeting":
            return self._stop_and_process_meeting()
        elif not self._recording:
            return self._start_meeting()
        else:
            return f"BUSY mode={self._mode}"

    def get_status(self) -> str:
        """Return current status."""
        if self._processing:
            return f"STATUS processing mode={self._mode}"
        if self._recording:
            return f"STATUS recording mode={self._mode}"
        return "STATUS idle"

    def force_stop(self) -> str:
        """Stop recording without processing."""
        if self._recording and self._mode == "meeting" and self._meeting_recorder:
            self._meeting_recorder.stop()
            self._meeting_recorder = None
            self._recording = False
            self._mode = ""
            print("[localwhispr] ■ Meeting cancelled.")
            return "OK stopped"
        elif self._recording:
            if self._dual_recorder:
                self._dual_recorder.stop()
                self._dual_recorder = None
            else:
                self._recorder.stop()
            self._recording = False
            self._mode = ""
            print("[localwhispr] ■ Recording cancelled.")
            return "OK stopped"
        return "OK already_idle"

    def _stop_and_process_dictation(self) -> str:
        """Stop recording and start dictation pipeline in a thread."""
        import threading

        from localwhispr.notifier import notify_recording_stop
        notify_recording_stop(self._notif)

        print("[localwhispr] ■ Stopping recording...")

        if self._dual_recorder:
            mic_bytes, monitor_bytes = self._dual_recorder.stop()
            self._dual_recorder = None
            self._recording = False

            if (not mic_bytes or len(mic_bytes) < 1000) and (not monitor_bytes or len(monitor_bytes) < 1000):
                print("[localwhispr] Recording too short, ignoring.")
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
                print("[localwhispr] Recording too short, ignoring.")
                self._mode = ""
                return "OK too_short"

            self._processing = True
            threading.Thread(
                target=self._process_dictation, args=(wav_bytes,), daemon=True
            ).start()

        return "OK processing"

    def _process_dictation(self, wav_bytes: bytes) -> None:
        """Simple pipeline: transcription -> AI cleanup -> type."""
        from localwhispr.notifier import notify_done, notify_error

        try:
            print("[localwhispr] Transcribing...")
            raw_text = self._transcriber.transcribe(wav_bytes)
            if not raw_text:
                print("[localwhispr] No speech detected.")
                notify_error("No speech detected", self._notif)
                return

            print("[localwhispr] Polishing with AI...")
            cleaned_text = self._cleanup.cleanup(raw_text)

            print(f"[localwhispr] Typing: {cleaned_text[:80]}...")
            self._typer.type_text(cleaned_text)
            notify_done(cleaned_text, self._notif)

        except Exception as e:
            print(f"[localwhispr] ERROR in pipeline: {e}")
            notify_error(str(e), self._notif)
        finally:
            self._processing = False
            self._mode = ""

    def _process_dictation_dual(self, mic_bytes: bytes, monitor_bytes: bytes) -> None:
        """Dual pipeline: transcribe mic + monitor separately, merge by timestamp, cleanup, type."""
        from localwhispr.notifier import notify_done, notify_error

        try:
            print("[localwhispr] Transcribing mic...")
            mic_segments = self._transcriber.transcribe_with_timestamps(mic_bytes) if mic_bytes and len(mic_bytes) > 1000 else []

            print("[localwhispr] Transcribing headset...")
            monitor_segments = self._transcriber.transcribe_with_timestamps(monitor_bytes) if monitor_bytes and len(monitor_bytes) > 1000 else []

            if not mic_segments and not monitor_segments:
                print("[localwhispr] No speech detected.")
                notify_error("No speech detected", self._notif)
                return

            # Merge interleaved by timestamp (no labels)
            merged_text = _merge_segments(mic_segments, monitor_segments)
            print(f"[localwhispr] Merged text: {merged_text[:120]}...")

            # AI cleanup (standard, no labels)
            print("[localwhispr] Polishing with AI...")
            cleaned_text = self._cleanup.cleanup(merged_text)

            print(f"[localwhispr] Typing: {cleaned_text[:80]}...")
            self._typer.type_text(cleaned_text)
            notify_done(cleaned_text, self._notif)

        except Exception as e:
            print(f"[localwhispr] ERROR in dual pipeline: {e}")
            notify_error(str(e), self._notif)
        finally:
            self._processing = False
            self._mode = ""

    def _stop_and_process_screenshot(self) -> str:
        """Stop recording and start screenshot pipeline in a thread."""
        import threading

        from localwhispr.notifier import notify_recording_stop
        notify_recording_stop(self._notif)

        print("[localwhispr] ■ Stopping command recording...")
        wav_bytes = self._recorder.stop()
        self._recording = False

        if not wav_bytes or len(wav_bytes) < 1000:
            print("[localwhispr] Recording too short, ignoring.")
            self._mode = ""
            return "OK too_short"

        self._processing = True
        threading.Thread(
            target=self._process_screenshot, args=(wav_bytes,), daemon=True
        ).start()
        return "OK processing"

    def _process_screenshot(self, wav_bytes: bytes) -> None:
        """Pipeline: transcription -> screenshot + multimodal LLM -> type."""
        from localwhispr.notifier import notify_done, notify_error

        try:
            print("[localwhispr] Transcribing command...")
            command_text = self._transcriber.transcribe(wav_bytes)
            if not command_text:
                print("[localwhispr] No command detected.")
                notify_error("No command detected", self._notif)
                return

            print(f"[localwhispr] Executing: {command_text[:80]}...")
            result = self._screenshot_cmd.execute(command_text)

            if result:
                print(f"[localwhispr] Typing response: {result[:80]}...")
                self._typer.type_text(result)
                notify_done(result, self._notif)
            else:
                notify_error("AI returned no response", self._notif)

        except Exception as e:
            print(f"[localwhispr] ERROR in screenshot pipeline: {e}")
            notify_error(str(e), self._notif)
        finally:
            self._processing = False
            self._mode = ""

    # -- Meeting mode --------------------------------------------------------

    def _start_meeting(self) -> str:
        """Start meeting recording."""
        from localwhispr.meeting import MeetingRecorder
        from localwhispr.notifier import notify, play_sound

        if not self._meeting_config:
            return "ERR meeting_config missing"

        try:
            self._meeting_recorder = MeetingRecorder(self._meeting_config)
            output_dir = self._meeting_recorder.start()
        except RuntimeError as e:
            print(f"[localwhispr] ERROR starting meeting: {e}")
            return f"ERR {e}"

        self._mode = "meeting"
        self._recording = True

        play_sound("device-added", self._notif)
        print(f"[localwhispr] ● Recording meeting in {output_dir}")
        return "OK meeting_recording"

    def _stop_and_process_meeting(self) -> str:
        """Stop meeting recording and start post-processing."""
        import threading
        from localwhispr.notifier import play_sound

        if not self._meeting_recorder:
            self._recording = False
            self._mode = ""
            return "ERR no_meeting_recorder"

        print("[localwhispr] ■ Stopping meeting recording...")
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
        """Pipeline: chunked transcription + AI meeting minutes."""
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
                    msg_parts.append(f"Transcription: {results['transcription']}")
                if "summary" in results:
                    msg_parts.append(f"Summary: {results['summary']}")

                notify(
                    "Meeting processed ✅",
                    "\n".join(msg_parts) if msg_parts else str(files.output_dir),
                    self._notif,
                )
                play_sound("complete", self._notif)
            else:
                notify_error("No content generated from meeting", self._notif)

        except Exception as e:
            print(f"[localwhispr] ERROR in meeting pipeline: {e}")
            notify_error(f"Meeting error: {e}", self._notif)
        finally:
            self._processing = False
            self._mode = ""
            self._meeting_recorder = None
