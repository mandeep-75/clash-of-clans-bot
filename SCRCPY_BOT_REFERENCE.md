# scrcpy Control Protocol — Bot Reference

Full guide for controlling an Android device from a bot over scrcpy's control
socket. Covers tapping, swiping, multi-touch/pinch-zoom, keys, text, scroll,
clipboard, display, panels, UHID and more.

Source: this scrcpy checkout (`app/src/control_msg.c`, `app/src/control_msg.h`,
`app/src/android/input.h`, `app/src/android/keycodes.h`, and the server in
`server/src/main/java/com/genymobile/scrcpy/control/`).

---

## 1. Architecture in one picture

```
Your bot  --TCP-->  adb reverse tunnel  --localabstract socket-->  scrcpy server on device
   |                        ^                                            |
   | writes serialized      |                                            +-- injects input into Android
   | control messages       |                                            +-- replies (clipboard, acks)
   +----------------------------------------------------<---------------+
```

- The device-side server (`scrcpy-server.jar`) is the input injector.
- Your bot is the **controller client**: it opens the control socket and sends
  byte-serialized messages.
- The control socket is full-duplex: client→device = commands, device→client =
  clipboard/ack/UHID-output messages.

---

## 2. Setting up the tunnel

### 2.1 Install the server jar (once per device)

```bash
adb push scrcpy-server.jar /data/local/tmp/
```

### 2.2 Start a headless server for the bot

Use a dedicated `--socket-name` so it never collides with a normal scrcpy GUI.

```bash
adb reverse localabstract:scrcpyBOT tcp:27183
adb shell CLASSPATH=/data/local/tmp/scrcpy-server.jar app_process / \
  com.genymobile.scrcpy.Server 3.1 \
  --scid=00000001 --socket-name=scrcpyBOT \
  --control=true --video=false --audio=false --log_level=info
```

### 2.3 The bot connects

```bash
# bot side: listen on 127.0.0.1:27183, accept ONE connection (the control socket)
```

> If `--video=true --audio=true` too, connections arrive in order
> **video → audio → control** — accept that many times and keep the last socket
> (video socket = real-time frames, see §10 for screenshots).

### 2.4 Alternative: reuse a running scrcpy

A normal `scrcpy` window already holds its own control socket — the bot cannot
share it. Always run your own server session with its own socket name.

---

## 3. Wire format conventions

- **Big-endian** for every multi-byte integer.
- Byte 0 of every client→device message = **type** (1 byte, 0–22).
- Strings: see `u32len-str` and `u8len-str` below.
- Fixed-point:
  - pressure: float [0,1] → **u16** `round(f * 65536)` (clamp 65535).
    `1.0` → `0xffff`.
  - scroll: float [-1,1] → **i16** `round(f * 32768)` (clamp ±32767).

### String encodings
| Name | Encoding |
|------|----------|
| `u32len-str` | 4-byte big-endian length + raw UTF-8 (no NUL) |
| `u8len-str`  | 1-byte length + raw UTF-8 (no NUL) |

### Position (`write_position`)
For touch/scroll: 4B `x` (i32), 4B `y` (i32), 2B screen `width` (u16),
2B screen `height` (u16). Positions are in **device pixels**.

---

## 4. Message type IDs (client → device)

| ID | Name | Size (bytes) | Page |
|----|------|--------------|------|
| 0  | `INJECT_KEYCODE` | 14 | §5.1 |
| 1  | `INJECT_TEXT` | 5 + text | §5.2 |
| 2  | `INJECT_TOUCH_EVENT` | 32 | §5.3 |
| 3  | `INJECT_SCROLL_EVENT` | 21 | §5.4 |
| 4  | `BACK_OR_SCREEN_ON` | 2 | §5.5 |
| 5  | `EXPAND_NOTIFICATION_PANEL` | 1 | §5.6 |
| 6  | `EXPAND_SETTINGS_PANEL` | 1 | §5.6 |
| 7  | `COLLAPSE_PANELS` | 1 | §5.6 |
| 8  | `GET_CLIPBOARD` | 2 | §5.7 |
| 9  | `SET_CLIPBOARD` | 14 + text | §5.8 |
| 10 | `SET_DISPLAY_POWER` | 2 | §5.9 |
| 11 | `ROTATE_DEVICE` | 1 | §5.6 |
| 12 | `UHID_CREATE` | 7 + name + desc | §5.10 |
| 13 | `UHID_INPUT` | 5 + data | §5.10 |
| 14 | `UHID_DESTROY` | 3 | §5.10 |
| 15 | `OPEN_HARD_KEYBOARD_SETTINGS` | 1 | §5.6 |
| 16 | `START_APP` | 2 + name | §5.11 |
| 17 | `RESET_VIDEO` | 1 | §5.6 |
| 18 | `CAMERA_SET_TORCH` | 2 | §5.12 |
| 19 | `CAMERA_ZOOM_IN` | 1 | §5.12 |
| 20 | `CAMERA_ZOOM_OUT` | 1 | §5.12 |
| 21 | `RESIZE_DISPLAY` | 5 | §5.13 |
| 22 | `SCAN_FILE` | 5 + path | §5.14 |

Max message size = 256 KB. Touch/key/scroll events may be dropped by the client
when the buffer is full; UHID create/destroy are never dropped.

---

## 5. Message formats

### 5.1 `INJECT_KEYCODE` (type 0) — 14 bytes
```
byte 0: type = 0
byte 1: action   (keyevent action, see §7.1)
bytes 2-5: keycode  (u32, see §7.3)
bytes 6-9: repeat   (u32, usually 0)
bytes 10-13: metastate (u32 bitmask, see §7.2)
```

### 5.2 `INJECT_TEXT` (type 1) — 5 + N bytes
```
byte 0: type = 1
bytes 1-4: length N (u32)
bytes 5..5+N-1: UTF-8 text (max 300 bytes)
```
The server converts each char into key events (handles accents/UTF-8).

### 5.3 `INJECT_TOUCH_EVENT` (type 2) — 32 bytes
```
byte 0: type = 2
byte 1: action   (motionevent action, see §7.4)
bytes 2-9: pointer_id (i64)
bytes 10-13: x (i32)
bytes 14-17: y (i32)
bytes 18-19: screen width (u16)
bytes 20-21: screen height (u16)
bytes 22-23: pressure (u16 fixed-point, 1.0 → 0xffff)
bytes 24-27: action_button (u32 button mask, see §7.5)
bytes 28-31: buttons (u32 button mask)
```

Pointer IDs:
| Value | Meaning |
|-------|---------|
| `-1` (mouse) | real mouse pointer |
| `-2` (generic finger) | normal finger |
| `-3` (virtual finger) | pinch-to-zoom companion finger |
| any other | extra finger (use `-4`, `-5`, ...) |

Multi-touch: send DOWN for each pointer id before MOVE(s), then UP for each.
The server merges all pointer ids into one Android `MotionEvent`.

### 5.4 `INJECT_SCROLL_EVENT` (type 3) — 21 bytes
```
byte 0: type = 3
bytes 1-4: x (i32)
bytes 5-8: y (i32)
bytes 9-10: screen width (u16)
bytes 11-12: screen height (u16)
bytes 13-14: hscroll (i16 fixed-point, ±1.0)
bytes 15-16: vscroll (i16 fixed-point, ±1.0)
bytes 17-20: buttons (u32)
```
Server divides by 16 then normalizes: only values in [-16,16] are meaningful.

### 5.5 `BACK_OR_SCREEN_ON` (type 4) — 2 bytes
```
byte 0: type = 4
byte 1: action (keyevent action)
```
If the screen is on → injects BACK. If off → turns the screen on (action DOWN).

### 5.6 Payload-less messages — 1 byte
```
byte 0: type = 5 (expand notification), 6 (settings), 7 (collapse),
        11 (rotate device), 15 (open hard keyboard settings), 17 (reset video)
```

### 5.7 `GET_CLIPBOARD` (type 8) — 2 bytes
```
byte 0: type = 8
byte 1: copy_key (0 none, 1 copy, 2 cut)
```
Device replies with `CLIPBOARD` (see §8) if autosync is off.

### 5.8 `SET_CLIPBOARD` (type 9) — 14 + N bytes
```
byte 0: type = 9
bytes 1-8: sequence (u64; 0 = don't ack)
byte 9: paste flag (0/1)
bytes 10-13: length N (u32)
bytes 14..14+N-1: UTF-8 text (max 256 KB - 14)
```
With a non-zero `sequence`, device replies `ACK_CLIPBOARD` (see §8).

### 5.9 `SET_DISPLAY_POWER` (type 10) — 2 bytes
```
byte 0: type = 10
byte 1: on (0/1)
```

### 5.10 UHID (HID passthrough) — types 12/13/14
```
UHID_CREATE (12):
  byte 0: type = 12
  bytes 1-2: id (u16)
  bytes 3-4: vendor_id (u16)
  bytes 5-6: product_id (u16)
  byte 7: name length L (u8, ≤127)
  bytes 8..: name (L bytes)
  next 2 bytes: report_desc_size (u16)
  then: report descriptor bytes

UHID_INPUT (13):
  byte 0: type = 13
  bytes 1-2: id (u16)
  bytes 3-4: size (u16)
  bytes 5..: raw HID report bytes

UHID_DESTROY (14):
  byte 0: type = 14
  bytes 1-2: id (u16)
```
Creates a virtual keyboard/mouse/controller device on Android. The device can
reply with `UHID_OUTPUT` (see §8).

### 5.11 `START_APP` (type 16) — 2 + N bytes
```
byte 0: type = 16
byte 1: name length N (u8, ≤255)
bytes 2..: app name (package or component)
```

### 5.12 Camera — types 18/19/20
```
CAMERA_SET_TORCH (18): byte 0 = 18, byte 1 = on (0/1)
CAMERA_ZOOM_IN   (19): byte 0 = 19
CAMERA_ZOOM_OUT  (20): byte 0 = 20
```

### 5.13 `RESIZE_DISPLAY` (type 21) — 5 bytes
```
byte 0: type = 21
bytes 1-2: width (u16)
bytes 3-4: height (u16)
```

### 5.14 `SCAN_FILE` (type 22) — 5 + N bytes
```
byte 0: type = 22
bytes 1-4: length N (u32, ≤256)
bytes 5..: UTF-8 path to rescan (e.g. after pushing a file)
```

---

## 6. Positions & screen size

- Send the **current video size** in every positional message. If the device
  resolution differs, the server maps coordinates and may ignore the event
  (a `VERBOSE` log says `Ignore positional event`).
- Get the size from the first video frame metadata or via
  `adb shell wm size` (e.g. `1080x2400`).

---

## 7. Android constants

### 7.1 Key event actions
| Value | Name |
|-------|------|
| 0 | DOWN |
| 1 | UP |
| 2 | MULTIPLE |

### 7.2 Meta states (bitmask)
| Value | Meaning |
|-------|---------|
| 0x01 | SHIFT |
| 0x02 | ALT |
| 0x04 | SYM |
| 0x08 | FUNCTION |
| 0x1000 | CTRL |
| 0x10000 | META |
| 0x100000 | CAPS LOCK |

### 7.3 Common keycodes (full list in `app/src/android/keycodes.h`)
| Code | Key | Code | Key |
|------|-----|------|-----|
| 3 | HOME | 61 | TAB |
| 4 | BACK | 62 | SPACE |
| 19/20/21/22 | DPAD up/down/left/right | 66 | ENTER |
| 24/25 | VOLUME up/down | 67 | DEL (backspace) |
| 26 | POWER | 82 | MENU |
| 29–54 | A–Z | 84 | SEARCH |
| 7–16 | 0–9 | 85 | MEDIA_PLAY_PAUSE |
| 57/58 | ALT left/right | 86 | MEDIA_STOP |
| 59/60 | SHIFT left/right | 87/88 | MEDIA next/previous |
| 113/114 | CTRL left/right | 111 | ESCAPE |
| 168/169 | ZOOM in/out | 122/123 | MOVE home/end |
| 187 | APP_SWITCH | 277/278/279 | CUT/COPY/PASTE |

### 7.4 Motion event actions
| Value | Name | Use |
|-------|------|-----|
| 0 | DOWN | first finger touches |
| 1 | UP | last finger lifts |
| 2 | MOVE | drag/pinch |
| 3 | CANCEL | abort gesture |
| 5 | POINTER_DOWN | extra finger goes down |
| 6 | POINTER_UP | extra finger goes up |
| 7 | HOVER_MOVE | mouse move without button |
| 8 | SCROLL | wheel scroll |

For multi-touch, scrcpy also accepts the base DOWN/UP/MOVE actions and the
server resolves the pointer index for you.

### 7.5 Button masks (for touch/scroll `buttons` / `action_button`)
| Value | Button |
|-------|--------|
| 0x01 | PRIMARY (left) |
| 0x02 | SECONDARY (right) |
| 0x04 | TERTIARY (middle) |
| 0x08 | BACK |
| 0x10 | FORWARD |
| 0x20 | STYLUS primary |
| 0x40 | STYLUS secondary |

---

## 8. Device → client messages

Read on the same socket. First byte = type:

| ID | Name | Format |
|----|------|--------|
| 0 | CLIPBOARD | byte `0`, u32 length, UTF-8 text |
| 1 | ACK_CLIPBOARD | byte `1`, u64 sequence |
| 2 | UHID_OUTPUT | byte `2`, u16 id, u16 size, raw bytes |

---

## 9. Recipes (Python)

### 9.1 Minimal client

```python
import socket, struct, time

class ScrcpyControl:
    def __init__(self, host="127.0.0.1", port=27183, w=1080, h=2400):
        self.w, self.h = w, h
        srv = socket.socket()
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind((host, port)); srv.listen(1)
        self.sock, _ = srv.accept()   # control socket

    # generic senders
    def _send(self, data: bytes):
        self.sock.sendall(data)

    def touch(self, action, pid, x, y, pressure=1.0, action_button=0, buttons=0):
        p = min(65535, int(pressure * 65536))
        self._send(struct.pack(">BbqiiHHI I",
            2, action, pid, x, y, self.w, self.h, p, action_button, buttons))

    def scroll(self, x, y, hscroll=0.0, vscroll=0.0, buttons=0):
        h = max(-32768, min(32767, int(hscroll * 32768)))
        v = max(-32768, min(32767, int(vscroll * 32768)))
        self._send(struct.pack(">BiiiHhh I",
            3, x, y, self.w, self.h, h, v, buttons))

    def key(self, keycode, action=0, repeat=0, metastate=0):
        self._send(struct.pack(">BBIII", 0, action, keycode, repeat, metastate))

    def text(self, s: str):
        raw = s.encode("utf-8")[:300]
        self._send(struct.pack(">BI", 1, len(raw)) + raw)

    def back(self, action=0):
        self._send(struct.pack(">BB", 4, action))

    def set_clipboard(self, text, paste=False, sequence=1):
        raw = text.encode("utf-8")[:262130]   # 256KB - 14
        self._send(struct.pack(">BQB I", 9, sequence, int(paste), len(raw)) + raw)

    def get_clipboard(self):
        self._send(struct.pack(">BB", 8, 1))  # copy key = COPY
        # then read reply: 1B type + 4B len + text

    def read_device_msg(self):
        t = self.sock.recv(1)
        if not t: return None
        if t == b"\x00":                      # clipboard
            n = struct.unpack(">I", self._recv_exact(4))[0]
            return ("clipboard", self._recv_exact(n).decode("utf-8"))
        if t == b"\x01":                      # ack
            return ("ack", struct.unpack(">Q", self._recv_exact(8))[0])
        if t == b"\x02":                      # uhid output
            iid, n = struct.unpack(">HH", self._recv_exact(4))
            return ("uhid_output", iid, self._recv_exact(n))
        raise ValueError(f"unknown device msg type {t[0]}")

    def _recv_exact(self, n):
        buf = b""
        while len(buf) < n:
            chunk = self.sock.recv(n - len(buf))
            if not chunk: raise ConnectionError("control socket closed")
            buf += chunk
        return buf
```

### 9.2 Tap, long-press, swipe

```python
def tap(c, x, y, duration=0.05):
    c.touch(0, -2, x, y)          # DOWN
    time.sleep(duration)
    c.touch(1, -2, x, y)          # UP

def long_press(c, x, y, seconds=0.8):
    c.touch(0, -2, x, y)
    time.sleep(seconds)
    c.touch(1, -2, x, y)

def swipe(c, x1, y1, x2, y2, steps=20, dt=0.01):
    c.touch(0, -2, x1, y1)                       # DOWN
    for i in range(1, steps + 1):
        x = x1 + (x2 - x1) * i / steps
        y = y1 + (y2 - y1) * i / steps
        c.touch(2, -2, int(x), int(y))           # MOVE
        time.sleep(dt)
    c.touch(1, -2, x2, y2)                       # UP
```

### 9.3 Pinch zoom (two fingers at the same time)

```python
def pinch(c, cx, cy, start_dist, end_dist, steps=30, dt=0.01):
    # DOWN both fingers (same loop iteration = "simultaneous")
    c.touch(0, -2, cx - start_dist, cy)
    c.touch(0, -3, cx + start_dist, cy)
    # MOVE both, spreading apart = zoom IN, closing = zoom OUT
    for i in range(1, steps + 1):
        d = start_dist + (end_dist - start_dist) * i / steps
        c.touch(2, -2, int(cx - d), cy)
        c.touch(2, -3, int(cx + d), cy)
        time.sleep(dt)
    # UP both
    c.touch(1, -2, int(cx - end_dist), cy)
    c.touch(1, -3, int(cx + end_dist), cy)

# zoom in: pinch(c, W//2, H//2, 50, 300)
# zoom out: pinch(c, W//2, H//2, 300, 50)
```

For rotate/tilt (Ctrl+Shift style):
- vertical tilt: finger 1 at `(x, y)`, finger 2 at `(x, H - y)`
- horizontal tilt: finger 1 at `(x, y)`, finger 2 at `(W - x, y)`
- rotate/pinch: finger 2 mirrored through center: `(W - x, H - y)`

### 9.4 Keys

```python
c.key(4, 0); time.sleep(0.05); c.key(4, 1)     # BACK
c.key(3, 0); time.sleep(0.05); c.key(3, 1)     # HOME
c.key(187, 0); c.key(187, 1)                   # app switch
c.key(26, 0); c.key(26, 1)                     # power
c.key(24, 0); c.key(24, 1)                     # volume up
# typed text
c.text("hello bot")
# Ctrl+C (copy) via keycode + metastate
c.key(29, 0, 0, 0x1000); c.key(31, 0, 0, 0x1000)   # CTRL down, C down
c.key(31, 1, 0, 0x1000); c.key(29, 1, 0, 0x1000)   # C up, CTRL up
```

### 9.5 Panels / rotate / misc

```python
c._send(bytes([5]))    # expand notifications
c._send(bytes([6]))    # expand quick settings
c._send(bytes([7]))    # collapse panels
c._send(bytes([11]))   # rotate device
c._send(bytes([15]))   # open keyboard settings
c._send(bytes([17]))   # reset video stream
```

### 9.6 Screenshots

See §10 for the full details. Quick copy of the two options:

```python
# Option A — one-off shot, no scrcpy server needed
import subprocess
subprocess.run("adb exec-out screencap -p > screen.png", shell=True)

# Option B — real-time frames from the video socket (needs --video=true)
video_sock, control_sock = accept_video_then_control()   # see §10.2
for frame in video_frames(video_sock):                    # raw H.264 NALs
    save_or_decode(frame)                                 # → PNG/JPEG/MP4
```

---

## 10. Screenshots from the bot

scrcpy's video stream is a continuous screenshot feed. Two ways to grab frames:

### 10.1 Option A — one-off `screencap` (simplest)

No scrcpy server involved; works anywhere adb works:

```bash
adb exec-out screencap -p > screen.png
adb exec-out screencap -p > screen.jpg   # if device/Android supports jpeg
```

~300–500 ms per shot. Good for occasional "verify state" snapshots.

### 10.2 Option B — real-time frames from the video stream

**Setup** — run the server with video enabled:

```bash
adb shell CLASSPATH=/data/local/tmp/scrcpy-server.jar app_process / \
  com.genymobile.scrcpy.Server 3.1 \
  --scid=00000001 --socket-name=scrcpyBOT \
  --control=true --video=true --audio=false --log_level=info
```

Accept **two** connections — first is **video**, second is **control**.

**Stream format** (`app/src/demuxer.c`):

```
bytes 0-3:  codec id (u32 BE) — "h264" = 0x68323634 (default)

then repeating frames, each prefixed by a 12-byte header:

  byte 0 MSB (0x80) = 1  →  SESSION packet:
     bytes 4-7:   width (u32)
     bytes 8-11:  height (u32)
     (no payload follows)

  byte 0 MSB = 0         →  MEDIA packet:
     bytes 0-7:   PTS + flags (u64)
                  bit 0x80 = config packet (SPS/PPS)
                  bit 0x40 = key frame
     bytes 8-11:  packet size (u32)
     then <size> bytes of raw H.264 (one frame / NAL sequence)
```

**Python:**

```python
import socket, struct, subprocess

def recv_exact(sock, n):
    buf = b""
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise ConnectionError("video socket closed")
        buf += chunk
    return buf

def accept_video_then_control(port=27183):
    srv = socket.socket()
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", port)); srv.listen(2)
    video, _ = srv.accept()      # 1st connection = video
    control, _ = srv.accept()    # 2nd connection = control
    return video, control

def video_frames(video):
    codec_id = struct.unpack(">I", recv_exact(video, 4))[0]  # 0x68323634 = h264
    w = h = 0
    while True:
        hdr = recv_exact(video, 12)
        if hdr[0] & 0x80:                       # session packet → size info
            w, h = struct.unpack(">II", hdr[4:12])
            continue
        n = struct.unpack(">I", hdr[8:12])[0]
        yield (hdr, recv_exact(video, n))       # header + raw H.264 frame
```

**Save a PNG** by piping frames into ffmpeg:

```python
ff = subprocess.Popen(
    ["ffmpeg", "-f", "h264", "-i", "pipe:0",
     "-frames:v", "1", "-y", "screen.png"],
    stdin=subprocess.PIPE)
for hdr, frame in video_frames(video):
    if not (hdr[0] & 0x80):                     # skip config packets
        ff.stdin.write(frame)
        if hdr[6] & 0x40:                       # key frame → first decodable frame
            ff.stdin.close(); break
```

For ongoing monitoring, keep the loop running and decode every frame with
OpenCV (`cv2.VideoCapture` on the pipe) or feed ffmpeg to record an MP4.

---

## 11. Gotchas

- **Multi-touch needs distinct pointer ids** — reuse the same id for one finger
  across DOWN/MOVE/UP, never share it between fingers.
- Send the **correct screen size** in positional messages or the server drops
  the event.
- **Don't mix mouse pointer `-1` with HOVER/buttons tricks** unless you want
  mouse semantics; use fingers for touchscreen apps.
- The GUI scrcpy holds its own control socket — the bot needs its own
  `--socket-name` server session.
- Message buffer is 256 KB; if full, touch/scroll/key/text messages are
  *dropped* (never UHID create/destroy). Pace heavy input bursts.
- All integers are big-endian — a wrong endianness silently breaks everything.
- `SCAN_FILE` exists to rescan media after `adb push` of a new file
  (`/sdcard/...`) so apps pick it up.
