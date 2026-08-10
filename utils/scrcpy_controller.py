"""scrcpy-based device controller.

Replaces ADB `input` / `screencap` with the scrcpy control protocol and the
live H.264 video stream (see SCRCPY_BOT_REFERENCE.md).

The device-side scrcpy server is started headlessly (video + control, no
audio). The video socket provides real-time frames which are decoded into BGR
images with a persistent ffmpeg process, and the control socket injects taps,
swipes, pinch-zoom gestures and key events.
"""

import os
import random
import re
import socket
import struct
import subprocess
import threading
import time
from collections.abc import Callable

import cv2
import numpy as np

import config
from utils.device import select_device
from utils.template_detector import TemplateDetector

# --- scrcpy control protocol constants (reference §4, §5) --------------------

MSG_INJECT_TOUCH_EVENT = 2
MSG_INJECT_SCROLL_EVENT = 3

# Pointer IDs (reference §5.3)
POINTER_ID_GENERIC_FINGER = -2
POINTER_ID_VIRTUAL_FINGER = -3

# Motion event actions (reference §7.4)
ACTION_DOWN = 0
ACTION_UP = 1
ACTION_MOVE = 2

# Video stream wire format (reference §10.2, scrcpy demuxer.c)
VIDEO_CODEC_H264 = 0x68323634  # "h264"
DEVICE_NAME_FIELD_LENGTH = 64
PACKET_HEADER_SIZE = 12


def _recv_exact(sock: socket.socket, n: int) -> bytes:
    buf = bytearray()
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise ConnectionError("socket closed")
        buf.extend(chunk)
    return bytes(buf)


def _float_to_u16fp(value: float) -> int:
    return max(0, min(65535, round(value * 65536)))


def _to_annex_b(data: bytes) -> bytes:
    """Convert AVCC (length-prefixed NAL units) H.264 data to Annex B.

    Passes through data that is already in Annex B (starts with a start code).
    """
    if data[:4] == b"\x00\x00\x00\x01" or data[:3] == b"\x00\x00\x01":
        return data

    out = bytearray()
    i = 0
    while i + 4 <= len(data):
        size = struct.unpack(">I", data[i : i + 4])[0]
        i += 4
        if size == 0 or i + size > len(data):
            break
        out += b"\x00\x00\x00\x01"
        out += data[i : i + size]
        i += size
    return bytes(out)


class _FfmpegDecoder:
    """Decodes the H.264 video socket into BGR frames via a persistent ffmpeg."""

    def __init__(self, width: int, height: int):
        self.width = width
        self.height = height
        self.frame_size = width * height * 3
        self._latest: np.ndarray | None = None
        self._lock = threading.Lock()
        self._proc = subprocess.Popen(
            [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-fflags",
                "nobuffer",
                "-f",
                "h264",
                "-i",
                "pipe:0",
                "-f",
                "rawvideo",
                "-pix_fmt",
                "bgr24",
                "pipe:1",
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
        self._restarted = False
        self._thread = threading.Thread(target=self._read_frames, daemon=True)
        self._thread.start()

    def _read_frames(self) -> None:
        out = self._proc.stdout
        if out is None:
            return
        try:
            while True:
                raw = out.read(self.frame_size)
                if not raw or len(raw) < self.frame_size:
                    break
                frame = np.frombuffer(raw, dtype=np.uint8).reshape(
                    self.height, self.width, 3
                )
                with self._lock:
                    self._latest = frame
        except (OSError, ValueError):
            pass

    def feed(self, data: bytes) -> None:
        stdin = self._proc.stdin
        if stdin is None:
            return
        try:
            stdin.write(_to_annex_b(data))
            stdin.flush()
        except (BrokenPipeError, OSError):
            pass

    def alive(self) -> bool:
        return self._proc.poll() is None

    def latest(self) -> np.ndarray | None:
        with self._lock:
            return self._latest

    def close(self) -> None:
        stdin = self._proc.stdin
        if stdin is not None:
            try:
                stdin.close()
            except (BrokenPipeError, OSError):
                pass
        try:
            self._proc.terminate()
        except OSError:
            pass


class _VideoStream(threading.Thread):
    """Reads the scrcpy video socket and keeps the latest decoded frame."""

    def __init__(self, sock: socket.socket, on_size: Callable[[int, int], None]):
        super().__init__(daemon=True)
        self._sock = sock
        self._on_size = on_size
        self._running = True
        self._restarted = False
        self._decoder: _FfmpegDecoder | None = None
        self.size = (0, 0)

    @property
    def latest_frame(self) -> np.ndarray | None:
        decoder = self._decoder
        return decoder.latest() if decoder else None

    def _update_size(self, width: int, height: int) -> None:
        if (width, height) != self.size:
            self.size = (width, height)
            self._on_size(width, height)

    def run(self) -> None:
        try:
            # Device name field, then the codec id (reference §10.2)
            _recv_exact(self._sock, DEVICE_NAME_FIELD_LENGTH)
            codec_id = struct.unpack(">I", _recv_exact(self._sock, 4))[0]
            if codec_id != VIDEO_CODEC_H264:
                print(f"Unsupported video codec id: {codec_id:#x}")
                return

            while self._running:
                header = _recv_exact(self._sock, PACKET_HEADER_SIZE)
                if header[0] & 0x80:
                    # Session packet: carries the video size
                    width, height = struct.unpack(">II", header[4:12])
                    self._update_size(width, height)
                    continue

                size = struct.unpack(">I", header[8:12])[0]
                payload = _recv_exact(self._sock, size)
                self._feed(payload)
        except (ConnectionError, OSError):
            pass
        finally:
            self._running = False

    def _feed(self, payload: bytes) -> None:
        width, height = self.size
        if not width or not height:
            return

        decoder = self._decoder
        if (
            decoder is None
            or not decoder.alive()
            or (decoder.width, decoder.height) != (width, height)
        ):
            if decoder:
                decoder.close()
            decoder = self._decoder = _FfmpegDecoder(width, height)
            if self._restarted:
                print("Restarting ffmpeg decoder for video stream")
            self._restarted = True
        decoder.feed(payload)

    def close(self) -> None:
        self._running = False
        try:
            self._sock.close()
        except OSError:
            pass
        if self._decoder:
            self._decoder.close()


class ScrcpyController(TemplateDetector):
    """Controls an Android device over the scrcpy control protocol.

    Screenshots come from the live H.264 video socket (falling back to
    `adb screencap`); taps, swipes, pinch-zooms and keys are injected through
    the control socket.
    """

    def __init__(
        self,
        device_id: str | None = None,
        verbose: bool = False,
        port: int | None = None,
        scid: int | None = None,
    ):
        super().__init__()
        self.device_id = device_id
        self.verbose = verbose
        self.port = port or config.SCRCPY_PORT
        self.scid = scid if scid is not None else config.SCRCPY_SCID
        self.socket_name = f"scrcpy_{self.scid:08x}"

        self.w = 0
        self.h = 0

        self._lock = threading.Lock()
        self._size_lock = threading.Lock()
        self._video_sock: socket.socket | None = None
        self._control_sock: socket.socket | None = None
        self._listener: socket.socket | None = None
        self._server_proc: subprocess.Popen[bytes] | None = None
        self._video: _VideoStream | None = None

        if not self.device_id:
            self.device_id = select_device()
        if not self.device_id:
            raise RuntimeError("No ADB device available")

        try:
            self._push_server()
            self._bind_listener()
            self._setup_reverse()
            self._start_server()
            self._accept_sockets()
            if self._video_sock is None:
                raise RuntimeError("Video socket not connected")
            self._video = _VideoStream(self._video_sock, on_size=self._on_video_size)
            self._video.start()
            self._wait_for_size()
        except Exception:
            self.close()
            raise

    # ------------------------------------------------------------------ setup

    def _run_adb(self, args: list[str], check: bool = True):
        cmd = ["adb"]
        if self.device_id:
            cmd += ["-s", self.device_id]
        cmd += args
        return subprocess.run(
            cmd, capture_output=True, check=check, timeout=config.ADB_TIMEOUT
        )

    def _push_server(self) -> None:
        self._run_adb(
            ["push", config.SCRCPY_SERVER_JAR, config.SCRCPY_DEVICE_SERVER_PATH]
        )

    def _bind_listener(self) -> None:
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            listener.bind(("127.0.0.1", self.port))
        except OSError as e:
            listener.close()
            raise RuntimeError(f"Could not bind 127.0.0.1:{self.port}: {e}") from e
        listener.listen(8)
        listener.settimeout(30)
        self._listener = listener

    def _setup_reverse(self) -> None:
        self._run_adb(
            [
                "reverse",
                f"localabstract:{self.socket_name}",
                f"tcp:{self.port}",
            ]
        )

    def _start_server(self) -> None:
        device_id = self.device_id
        if device_id is None:
            raise RuntimeError("No ADB device")
        shell_cmd = (
            f"CLASSPATH={config.SCRCPY_DEVICE_SERVER_PATH} app_process / "
            f"com.genymobile.scrcpy.Server {config.SCRCPY_SERVER_VERSION} "
            f"scid={self.scid:08x} log_level=info "
            f"video=true audio=false control=true"
        )
        self._server_proc = subprocess.Popen(
            ["adb", "-s", device_id, "shell", shell_cmd],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    def _accept_sockets(self) -> None:
        listener = self._listener
        if listener is None:
            raise RuntimeError("Listener not bound")
        try:
            # Connections arrive in order: video, then control
            self._video_sock, _ = listener.accept()
            self._control_sock, _ = listener.accept()
        except TimeoutError as e:
            raise RuntimeError(
                "Timed out waiting for the scrcpy server to connect"
            ) from e
        finally:
            listener.close()
            self._listener = None
        control = self._control_sock
        if control is not None:
            control.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)

    def _on_video_size(self, width: int, height: int) -> None:
        with self._size_lock:
            self.w, self.h = width, height
        if self.verbose:
            print(f"Video stream size: {width}x{height}")

    def _get_size(self) -> tuple[int, int]:
        """Reads the current screen size (safe across the video thread)."""
        with self._size_lock:
            return self.w, self.h

    def _wm_size(self) -> tuple[int, int]:
        try:
            out = self._run_adb(["shell", "wm", "size"])
            m = re.search(r"(\d+)\s*x\s*(\d+)", out.stdout.decode())
            if m:
                return int(m.group(1)), int(m.group(2))
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError):
            pass
        return 0, 0

    def _wait_for_size(self, timeout: float = 10.0) -> None:
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self._get_size() != (0, 0):
                return
            time.sleep(0.1)
        width, height = self._wm_size()
        if width and height:
            with self._size_lock:
                self.w, self.h = width, height
            return
        print("WARNING: could not determine screen size; touch input disabled")

    def check_connection(self) -> bool:
        """Returns True while the scrcpy video stream and control socket are alive."""
        if self._control_sock is None:
            return False
        return self._video is not None and self._video.is_alive()

    # ---------------------------------------------------------------- messages

    def _send(self, data: bytes) -> bool:
        sock = self._control_sock
        if sock is None:
            return False
        try:
            with self._lock:
                sock.sendall(data)
            return True
        except OSError as e:
            print(f"Failed to send control message: {e}")
            return False

    def touch(
        self,
        action: int,
        pointer_id: int,
        x: int,
        y: int,
        pressure: float = 1.0,
        action_button: int = 0,
        buttons: int = 0,
    ) -> bool:
        """Injects a touch event (reference §5.3). Returns True if sent."""
        w, h = self._get_size()
        if not w or not h:
            print("WARNING: screen size unknown, touch event dropped")
            return False
        msg = struct.pack(
            ">BbqiiHHHII",
            MSG_INJECT_TOUCH_EVENT,
            action,
            pointer_id,
            x,
            y,
            w,
            h,
            _float_to_u16fp(pressure),
            action_button,
            buttons,
        )
        return self._send(msg)

    # ----------------------------------------------------------------- input

    def tap(self, x: int, y: int, offset: int = 0, hold: float = 0.1) -> bool:
        """Performs a human-like tap with random offset.

        `hold` is the delay between DOWN and UP; some games ignore taps that
        end too quickly, so keep it long enough to register.

        Returns True if both touch events were sent.
        """
        tx = x + random.randint(-offset, offset)
        ty = y + random.randint(-offset, offset)
        down_ok = self.touch(ACTION_DOWN, POINTER_ID_GENERIC_FINGER, tx, ty)
        time.sleep(hold)
        up_ok = self.touch(ACTION_UP, POINTER_ID_GENERIC_FINGER, tx, ty)
        return down_ok and up_ok

    def swipe(
        self,
        x1: int,
        y1: int,
        x2: int,
        y2: int,
        steps: int = 20,
        dt: float = 0.01,
    ) -> None:
        """Performs a swipe from (x1, y1) to (x2, y2)."""
        self.touch(ACTION_DOWN, POINTER_ID_GENERIC_FINGER, x1, y1)
        for i in range(1, steps + 1):
            x = x1 + (x2 - x1) * i // steps
            y = y1 + (y2 - y1) * i // steps
            self.touch(ACTION_MOVE, POINTER_ID_GENERIC_FINGER, int(x), int(y))
            time.sleep(dt)
        self.touch(ACTION_UP, POINTER_ID_GENERIC_FINGER, x2, y2)

    def scroll(
        self,
        x: int,
        y: int,
        hscroll: float = 0.0,
        vscroll: float = 0.0,
        buttons: int = 0,
    ) -> None:
        """Injects a scroll event (reference §5.4)."""
        h = max(-32768, min(32767, round(hscroll * 32768)))
        v = max(-32768, min(32767, round(vscroll * 32768)))
        w, hh = self._get_size()
        self._send(
            struct.pack(
                ">BiiiHhhI",
                MSG_INJECT_SCROLL_EVENT,
                x,
                y,
                w,
                hh,
                h,
                v,
                buttons,
            )
        )

    def pinch_zoom(
        self,
        direction: str = "in",
        center: tuple[int, int] | None = None,
        start_dist: int | None = None,
        end_dist: int | None = None,
        steps: int = 25,
        dt: float = 0.01,
    ) -> None:
        """Pinch-zoom gesture (reference §9.3).

        `direction` "in" spreads the fingers apart (zoom in), "out" brings
        them together (zoom out).
        """
        w, h = self._get_size()
        if not w or not h:
            print("WARNING: screen size unknown, pinch zoom dropped")
            return

        cx, cy = center or (w // 2, h // 2)
        if direction == "in":
            start, end = start_dist or 60, end_dist or 320
        else:
            start, end = start_dist or 320, end_dist or 60

        # DOWN both fingers (same loop iteration = "simultaneous")
        self.touch(ACTION_DOWN, POINTER_ID_GENERIC_FINGER, int(cx - start), cy)
        self.touch(ACTION_DOWN, POINTER_ID_VIRTUAL_FINGER, int(cx + start), cy)
        # MOVE both fingers
        for i in range(1, steps + 1):
            dist = start + (end - start) * i / steps
            self.touch(ACTION_MOVE, POINTER_ID_GENERIC_FINGER, int(cx - dist), cy)
            self.touch(ACTION_MOVE, POINTER_ID_VIRTUAL_FINGER, int(cx + dist), cy)
            time.sleep(dt)
        # UP both fingers
        self.touch(ACTION_UP, POINTER_ID_GENERIC_FINGER, int(cx - end), cy)
        self.touch(ACTION_UP, POINTER_ID_VIRTUAL_FINGER, int(cx + end), cy)

    # -------------------------------------------------------------- screenshots

    def take_screenshot(self, local_path=config.SCREENSHOT_NAME) -> bool:
        """Captures a screenshot from the live video stream.

        Falls back to `adb screencap` if no decoded frame is available yet.
        On failure the old screenshot file is removed so detection can never
        act on a stale frame. Returns success.
        """
        frame = self._video.latest_frame if self._video else None
        if frame is not None:
            if cv2.imwrite(local_path, frame):
                return True
            print("Failed to write screenshot frame")
            self._remove_screenshot(local_path)
            return False
        return self._fallback_screencap(local_path)

    def _remove_screenshot(self, local_path) -> None:
        try:
            os.remove(local_path)
        except OSError:
            pass

    def _fallback_screencap(self, local_path) -> bool:
        device_id = self.device_id
        if device_id is None:
            return False
        tmp_path = local_path + ".tmp"
        try:
            cmd = ["adb", "-s", device_id, "exec-out", "screencap", "-p"]
            with open(tmp_path, "wb") as f:
                subprocess.run(cmd, check=True, stdout=f, timeout=config.ADB_TIMEOUT)
            os.replace(tmp_path, local_path)
            return True
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as e:
            print(f"Failed to take screenshot: {e}")
            self._remove_screenshot(tmp_path)
            self._remove_screenshot(local_path)
            return False

    # ------------------------------------------------------------------ teardown

    def close(self) -> None:
        """Stops the video stream, closes sockets and kills the server."""
        if self._video:
            self._video.close()
            self._video = None
        for sock in (self._control_sock, self._video_sock, self._listener):
            if sock is not None:
                try:
                    sock.close()
                except OSError:
                    pass
        self._control_sock = None
        self._video_sock = None
        self._listener = None
        if self._server_proc is not None:
            try:
                self._server_proc.terminate()
            except OSError:
                pass
            self._server_proc = None
        if self.device_id:
            self._run_adb(
                ["reverse", "--remove", f"localabstract:{self.socket_name}"],
                check=False,
            )
