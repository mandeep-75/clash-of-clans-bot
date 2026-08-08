import os
import subprocess

import cv2
import numpy as np
from flask import Flask, Response, jsonify, request, send_from_directory

app = Flask(
    __name__,
    static_folder="static",
    static_url_path="/static",
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SCREENSHOT_DIR = os.path.join(BASE_DIR, "screenshots")
os.makedirs(SCREENSHOT_DIR, exist_ok=True)

DEFAULT_IMAGE = os.path.join(SCREENSHOT_DIR, "live.png")


def find_adb_devices() -> list[str]:
    """Returns a list of connected ADB device ids."""
    try:
        result = subprocess.run(
            ["adb", "devices"], capture_output=True, text=True, check=True
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return []
    devices = []
    for line in result.stdout.strip().split("\n")[1:]:
        if line.strip() and "\tdevice" in line:
            devices.append(line.split("\t")[0].strip())
    return devices


def pull_screenshot(device_id: str | None, dest: str) -> bool:
    """Captures a screenshot from an ADB device into dest."""
    try:
        cmd = ["adb"]
        if device_id:
            cmd += ["-s", device_id]
        cmd += ["exec-out", "screencap", "-p"]
        with open(dest, "wb") as f:
            subprocess.run(cmd, check=True, stdout=f)
        return True
    except subprocess.CalledProcessError:
        return False


def image_dims(path: str) -> tuple[int, int] | None:
    """Returns (width, height) of an image file, or None if invalid."""
    img = cv2.imread(path)
    if img is None:
        return None
    h, w = img.shape[:2]
    return w, h


def find_matches(
    full: np.ndarray,
    template: np.ndarray,
    threshold: float,
) -> list[dict]:
    """Finds all template matches above threshold.

    Uses TM_CCOEFF_NORMED, then local-max+peak extraction so every distinct
    match location is returned (not just a sliding-window smear).
    """
    if full.shape[0] < template.shape[0] or full.shape[1] < template.shape[1]:
        return []

    result = cv2.matchTemplate(full, template, cv2.TM_CCOEFF_NORMED)
    result = np.where(np.isnan(result), 0, result)

    kernel = np.ones((3, 3), np.uint8)
    dilated = cv2.dilate(result, kernel)
    peaks = np.argwhere((result == dilated) & (result >= threshold))

    matches: list[dict] = []
    tw, th = template.shape[1], template.shape[0]
    for py, px in peaks:
        score = float(result[py, px])
        matches.append(
            {
                "x": int(px),
                "y": int(py),
                "w": int(tw),
                "h": int(th),
                "score": round(score, 4),
                "center_x": int(px + tw // 2),
                "center_y": int(py + th // 2),
            }
        )

    matches.sort(key=lambda m: m["score"], reverse=True)
    return matches


@app.route("/")
def index():
    """Serves the tool's frontend."""
    return send_from_directory(os.path.join(BASE_DIR, "templates"), "index.html")


@app.route("/api/devices")
def api_devices():
    return jsonify({"devices": find_adb_devices()})


@app.route("/api/pull_screenshot")
def api_pull_screenshot():
    """Captures a screenshot from the ADB device and loads it as the full image."""
    devices = find_adb_devices()
    if not devices:
        return jsonify({"error": "No ADB devices connected"}), 400
    device_id = request.args.get("device") or devices[0]

    if not pull_screenshot(device_id, DEFAULT_IMAGE):
        return jsonify({"error": f"Failed to screencap on {device_id}"}), 500

    dims = image_dims(DEFAULT_IMAGE)
    if dims is None:
        return jsonify({"error": "Screenshot could not be decoded"}), 500

    return jsonify({"width": dims[0], "height": dims[1]})


@app.route("/api/image")
def api_image():
    """Returns the current full image."""
    if not os.path.exists(DEFAULT_IMAGE):
        return jsonify({"error": "No image loaded yet"}), 404
    return Response(open(DEFAULT_IMAGE, "rb").read(), mimetype="image/png")


@app.route("/api/upload_image", methods=["POST"])
def api_upload_image():
    """Stores an uploaded image as the current full image."""
    f = request.files.get("file")
    if f is None or f.filename == "":
        return jsonify({"error": "No file uploaded"}), 400
    f.save(DEFAULT_IMAGE)
    dims = image_dims(DEFAULT_IMAGE)
    if dims is None:
        return jsonify({"error": "Uploaded file is not a valid image"}), 400
    return jsonify({"width": dims[0], "height": dims[1]})


@app.route("/api/match", methods=["POST"])
def api_match():
    """Finds all locations of the given crop region in the full image.

    Body JSON:
        {"crop": {"x": int, "y": int, "w": int, "h": int}, "threshold": float}
    Crop coordinates are in full-image pixel space.
    """
    data = request.get_json(silent=True) or {}
    crop = data.get("crop") or {}
    threshold = float(data.get("threshold", 0.8))

    try:
        cx, cy = int(crop["x"]), int(crop["y"])
        cw, ch = int(crop["w"]), int(crop["h"])
    except (TypeError, KeyError, ValueError):
        return jsonify({"error": "Invalid crop region"}), 400

    if cw < 2 or ch < 2:
        return jsonify({"matches": []})

    full = cv2.imread(DEFAULT_IMAGE)
    if full is None:
        return jsonify({"error": "No image loaded"}), 400

    fh, fw = full.shape[:2]
    x1 = max(0, min(cx, fw - 1))
    y1 = max(0, min(cy, fh - 1))
    x2 = max(x1 + 1, min(cx + cw, fw))
    y2 = max(y1 + 1, min(cy + ch, fh))

    template = full[y1:y2, x1:x2].copy()
    if template.size == 0:
        return jsonify({"matches": []})

    matches = find_matches(full, template, threshold)
    return jsonify(
        {"matches": matches, "template": {"x": x1, "y": y1, "w": x2 - x1, "h": y2 - y1}}
    )


@app.route("/api/batch_match", methods=["POST"])
def api_batch_match():
    """Matches multiple template folders (ui_main_base style) against the image.

    Body JSON: {"folders": [str, ...], "threshold": float}
    """
    data = request.get_json(silent=True) or {}
    folders = data.get("folders") or []
    threshold = float(data.get("threshold", 0.8))

    full = cv2.imread(DEFAULT_IMAGE)
    if full is None:
        return jsonify({"error": "No image loaded"}), 400

    results: dict[str, list[dict]] = {}
    for folder in folders:
        folder_matches: list[dict] = []
        for fname in sorted(os.listdir(folder)):
            fpath = os.path.join(folder, fname)
            if not os.path.isfile(fpath):
                continue
            tpl = cv2.imread(fpath)
            if tpl is None:
                continue
            for m in find_matches(full, tpl, threshold):
                m["template_file"] = fname
                folder_matches.append(m)
        results[folder] = folder_matches

    return jsonify({"results": results})


def main() -> None:
    """Runs the match tool web server on http://127.0.0.1:<port>."""
    import sys

    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8080
    app.run(host="127.0.0.1", port=port, debug=False)


if __name__ == "__main__":
    main()
