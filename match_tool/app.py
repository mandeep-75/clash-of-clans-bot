import json
import os
import posixpath
import subprocess
import time
import uuid

import cv2
import numpy as np
from flask import Flask, Response, jsonify, request, send_file, send_from_directory

app = Flask(
    __name__,
    static_folder="static",
    static_url_path="/static",
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SCREENSHOT_DIR = os.path.join(BASE_DIR, "screenshots")
CROP_DIR = os.path.join(BASE_DIR, "crops")
EDITED_DIR = os.path.join(BASE_DIR, "edited")
TEMPLATES_DIR = os.path.abspath(os.path.join(BASE_DIR, "..", "templates"))
os.makedirs(SCREENSHOT_DIR, exist_ok=True)
os.makedirs(CROP_DIR, exist_ok=True)
os.makedirs(EDITED_DIR, exist_ok=True)

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


def _safe_rel(rel: str | None) -> str | None:
    """Resolves a templates-relative path, refusing to escape TEMPLATES_DIR.

    Symlinks are resolved with ``realpath`` so a link pointing outside the
    templates dir cannot smuggle reads either.
    """
    if not rel:
        return None
    normalized = rel.replace("\\", "/").lstrip("/")
    base = os.path.realpath(TEMPLATES_DIR)
    target = os.path.realpath(os.path.join(TEMPLATES_DIR, normalized))
    if not (target == base or target.startswith(base + os.sep)):
        return None
    return normalized


def _template_tree(base: str, rel: str) -> list[dict]:
    """Recursively lists the templates directory as a tree of dirs/files."""
    nodes: list[dict] = []
    for entry in sorted(os.scandir(base), key=lambda e: e.name.lower()):
        entry_rel = posixpath.join(rel, entry.name) if rel else entry.name
        if entry.is_dir():
            nodes.append(
                {
                    "name": entry.name,
                    "rel": entry_rel,
                    "type": "dir",
                    "children": _template_tree(entry.path, entry_rel),
                }
            )
        elif entry.is_file() and entry.name.lower().endswith(
            (".png", ".jpg", ".jpeg", ".webp")
        ):
            nodes.append({"name": entry.name, "rel": entry_rel, "type": "file"})
    return nodes


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
    return send_file(DEFAULT_IMAGE, mimetype="image/png")


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
    try:
        threshold = float(data.get("threshold", 0.8))
    except (TypeError, ValueError):
        return jsonify({"error": "Invalid threshold"}), 400

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
    """Matches multiple template folders (templates style) against the image.

    Body JSON: {"folders": [str, ...], "threshold": float}
    """
    data = request.get_json(silent=True) or {}
    folders = data.get("folders") or []
    try:
        threshold = float(data.get("threshold", 0.8))
    except (TypeError, ValueError):
        return jsonify({"error": "Invalid threshold"}), 400

    full = cv2.imread(DEFAULT_IMAGE)
    if full is None:
        return jsonify({"error": "No image loaded"}), 400

    results: dict[str, list[dict]] = {}
    for folder in folders:
        rel = _safe_rel(str(folder))
        if rel is None:
            return jsonify({"error": f"Invalid folder: {folder}"}), 400
        folder_path = os.path.join(TEMPLATES_DIR, rel)
        if not os.path.isdir(folder_path):
            return jsonify({"error": f"Folder not found: {folder}"}), 404
        folder_matches: list[dict] = []
        for fname in sorted(os.listdir(folder_path)):
            fpath = os.path.join(folder_path, fname)
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


def _crop_region(
    full: np.ndarray, crop: dict[str, int]
) -> tuple[np.ndarray, dict[str, int]] | None:
    """Clamps a crop to the image and returns (tile, clipped-crop), or None."""
    fh, fw = full.shape[:2]
    try:
        cx, cy = int(crop["x"]), int(crop["y"])
        cw, ch = int(crop["w"]), int(crop["h"])
    except (TypeError, KeyError, ValueError):
        return None
    x1 = max(0, min(cx, fw - 1))
    y1 = max(0, min(cy, fh - 1))
    x2 = max(x1 + 1, min(cx + cw, fw))
    y2 = max(y1 + 1, min(cy + ch, fh))
    tile = full[y1:y2, x1:x2].copy()
    if tile.size == 0:
        return None
    meta = {"x": x1, "y": y1, "w": x2 - x1, "h": y2 - y1}
    return tile, meta


@app.route("/api/save_crop", methods=["POST"])
def api_save_crop():
    """Saves the crop region as a unique PNG plus its match results.

    Body JSON: {"crop": {"x","y","w","h"}, "threshold": float}
    Returns metadata including the matches found at save time.
    """
    data = request.get_json(silent=True) or {}
    try:
        threshold = float(data.get("threshold", 0.8))
    except (TypeError, ValueError):
        return jsonify({"error": "Invalid threshold"}), 400

    full = cv2.imread(DEFAULT_IMAGE)
    if full is None:
        return jsonify({"error": "No image loaded"}), 400

    clipped = _crop_region(full, data.get("crop") or {})
    if clipped is None:
        return jsonify({"error": "Invalid crop region"}), 400
    tile, meta = clipped

    crop_id = time.strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:6]
    png_name = crop_id + ".png"
    json_name = crop_id + ".json"
    if not cv2.imwrite(os.path.join(CROP_DIR, png_name), tile):
        return jsonify({"error": "Failed to write crop image"}), 500

    matches = find_matches(full, tile, threshold)
    record = {
        "crop": meta,
        "full": {"x": 0, "y": 0, "w": int(full.shape[1]), "h": int(full.shape[0])},
        "threshold": threshold,
        "matches": matches,
    }
    with open(os.path.join(CROP_DIR, json_name), "w", encoding="utf-8") as f:
        json.dump(record, f)

    return jsonify(
        {
            "id": crop_id,
            "url": f"/api/crops/{crop_id}",
            "matches": len(matches),
            "threshold": threshold,
        }
    )


@app.route("/api/crops")
def api_crops():
    """Lists saved crops, newest first."""
    items: list[dict] = []
    for fname in os.listdir(CROP_DIR):
        if not fname.endswith(".png"):
            continue
        crop_id = fname[:-4]
        items.append(
            {
                "id": crop_id,
                "url": f"/api/crops/{crop_id}",
                "time": os.path.getmtime(os.path.join(CROP_DIR, fname)),
            }
        )
    items.sort(key=lambda c: c["time"], reverse=True)
    return jsonify({"crops": items})


@app.route("/api/clear_crops", methods=["POST"])
def api_clear_crops():
    """Deletes all saved crop images and their match records."""
    removed = {"png": 0, "json": 0}
    for fname in os.listdir(CROP_DIR):
        path = os.path.join(CROP_DIR, fname)
        if fname.endswith(".png"):
            os.remove(path)
            removed["png"] += 1
        elif fname.endswith(".json"):
            os.remove(path)
            removed["json"] += 1
    return jsonify({"ok": True, "removed": removed})


@app.route("/api/crops/<crop_id>")
def api_crop_image(crop_id: str):
    """Serves a saved crop image by its id."""
    if "/" in crop_id or ".." in crop_id:
        return jsonify({"error": "Invalid id"}), 400
    return send_from_directory(CROP_DIR, crop_id + ".png")


@app.route("/api/crop_matches/<crop_id>")
def api_crop_matches(crop_id: str):
    """Returns the stored crop region and matches for a saved crop."""
    if "/" in crop_id or ".." in crop_id:
        return jsonify({"error": "Invalid id"}), 400
    json_name = crop_id + ".json"
    json_path = os.path.join(CROP_DIR, json_name)
    if not os.path.exists(json_path):
        return jsonify({"error": "Crop not found"}), 404
    with open(json_path, encoding="utf-8") as f:
        return jsonify(json.load(f))


@app.route("/api/template_tree")
def api_template_tree():
    """Returns the templates folder tree for the template manager."""
    if not os.path.isdir(TEMPLATES_DIR):
        return jsonify({"root": TEMPLATES_DIR, "tree": []})
    return jsonify({"root": TEMPLATES_DIR, "tree": _template_tree(TEMPLATES_DIR, "")})


@app.route("/api/template_new_folder", methods=["POST"])
def api_template_new_folder():
    """Creates a new template folder (optionally nested, e.g. "troops/archer").

    Body JSON: {"folder": "templates-relative path to create"}
    """
    rel = _safe_rel((request.get_json(silent=True) or {}).get("folder"))
    if rel is None:
        return jsonify({"error": "Invalid folder name"}), 400
    path = os.path.join(TEMPLATES_DIR, rel)
    if os.path.exists(path):
        return jsonify({"error": "Folder already exists"}), 400
    try:
        os.makedirs(path)
    except OSError as e:
        return jsonify({"error": f"Failed to create folder: {e}"}), 500
    return jsonify({"created": rel})


@app.route("/api/template_image")
def api_template_image():
    """Serves a template image by its templates-relative path."""
    safe = _safe_rel(request.args.get("rel"))
    if safe is None:
        return jsonify({"error": "Invalid path"}), 400
    return send_from_directory(TEMPLATES_DIR, safe)


@app.route("/api/template_upload", methods=["POST"])
def api_template_upload():
    """Uploads images into a template folder (drag & drop).

    Body: multipart with `folder` (templates-relative) and multiple `files`.
    Only image files are accepted and existing names are never overwritten.
    """
    folder = _safe_rel(request.form.get("folder"))
    if folder is None:
        return jsonify({"error": "Invalid folder"}), 400
    folder_path = os.path.join(TEMPLATES_DIR, folder)
    if not os.path.isdir(folder_path):
        return jsonify({"error": "Folder not found"}), 404

    saved: list[dict] = []
    for f in request.files.getlist("files"):
        if not f or not f.filename:
            continue
        name = os.path.basename(f.filename)
        if not name.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
            return jsonify({"error": f"Unsupported file type: {name}"}), 400
        dest = os.path.join(folder_path, name)
        if os.path.exists(dest):
            return jsonify({"error": f"File already exists: {name}"}), 400
        f.save(dest)
        if image_dims(dest) is None:
            os.remove(dest)
            return jsonify({"error": f"Not a valid image: {name}"}), 400
        saved.append({"name": name, "rel": posixpath.join(folder, name)})

    if not saved:
        return jsonify({"error": "No files uploaded"}), 400
    return jsonify({"saved": saved, "count": len(saved)})


@app.route("/api/template_delete", methods=["POST"])
def api_template_delete():
    """Deletes a template image by its templates-relative path."""
    rel = _safe_rel((request.get_json(silent=True) or {}).get("rel"))
    if rel is None:
        return jsonify({"error": "Invalid path"}), 400
    path = os.path.join(TEMPLATES_DIR, rel)
    if not os.path.isfile(path):
        return jsonify({"error": "Not found"}), 404
    os.remove(path)
    return jsonify({"ok": True})


@app.route("/api/template_save_crop", methods=["POST"])
def api_template_save_crop():
    """Saves the current crop as a template image into a template folder.

    Body JSON: {"crop": {"x","y","w","h"}, "folder": "templates-relative"}
    """
    data = request.get_json(silent=True) or {}
    folder = _safe_rel(data.get("folder"))
    if folder is None:
        return jsonify({"error": "Invalid folder"}), 400
    folder_path = os.path.join(TEMPLATES_DIR, folder)
    if not os.path.isdir(folder_path):
        return jsonify({"error": "Folder not found"}), 404

    full = cv2.imread(DEFAULT_IMAGE)
    if full is None:
        return jsonify({"error": "No image loaded"}), 400

    clipped = _crop_region(full, data.get("crop") or {})
    if clipped is None:
        return jsonify({"error": "Invalid crop region"}), 400
    tile, meta = clipped

    name = time.strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:6] + ".png"
    if not cv2.imwrite(os.path.join(folder_path, name), tile):
        return jsonify({"error": "Failed to write template image"}), 500

    return jsonify({"name": name, "rel": posixpath.join(folder, name), "crop": meta})


@app.route("/api/template_add_crop", methods=["POST"])
def api_template_add_crop():
    """Copies a saved crop into a template folder (drag & drop a saved crop).

    Body JSON: {"crop_id": str, "folder": "templates-relative"}
    """
    data = request.get_json(silent=True) or {}
    crop_id = data.get("crop_id") or ""
    folder = _safe_rel(data.get("folder"))
    if folder is None:
        return jsonify({"error": "Invalid folder"}), 400
    if "/" in crop_id or ".." in crop_id or not crop_id:
        return jsonify({"error": "Invalid crop id"}), 400
    if not os.path.isdir(os.path.join(TEMPLATES_DIR, folder)):
        return jsonify({"error": "Folder not found"}), 404

    src = os.path.join(CROP_DIR, crop_id + ".png")
    if not os.path.isfile(src):
        return jsonify({"error": "Saved crop not found"}), 404

    name = crop_id + ".png"
    if not cv2.imwrite(os.path.join(TEMPLATES_DIR, folder, name), cv2.imread(src)):
        return jsonify({"error": "Failed to write template image"}), 500

    return jsonify({"name": name, "rel": posixpath.join(folder, name)})


@app.route("/api/crop_image")
def api_crop_region():
    """Returns the crop region of the current full image as a PNG.

    Query: x, y, w, h (full-image pixel space). Used to load a Match-tab
    crop into the image editor.
    """
    try:
        crop = {
            "x": int(request.args.get("x", 0)),
            "y": int(request.args.get("y", 0)),
            "w": int(request.args.get("w", 0)),
            "h": int(request.args.get("h", 0)),
        }
    except ValueError:
        return jsonify({"error": "Invalid crop"}), 400

    if crop["w"] < 2 or crop["h"] < 2:
        return jsonify({"error": "Crop too small"}), 400

    full = cv2.imread(DEFAULT_IMAGE)
    if full is None:
        return jsonify({"error": "No image loaded"}), 400

    clipped = _crop_region(full, crop)
    if clipped is None:
        return jsonify({"error": "Invalid crop region"}), 400

    retval, buf = cv2.imencode(".png", clipped[0])
    if not retval:
        return jsonify({"error": "Failed to encode crop"}), 500
    return Response(buf.tobytes(), mimetype="image/png")


@app.route("/api/edited")
def api_edited():
    """Lists stored edited images, newest first."""
    items: list[dict] = []
    for fname in os.listdir(EDITED_DIR):
        if not fname.endswith(".png"):
            continue
        edit_id = fname[:-4]
        items.append(
            {
                "id": edit_id,
                "url": f"/api/edited_image/{edit_id}",
                "time": os.path.getmtime(os.path.join(EDITED_DIR, fname)),
            }
        )
    items.sort(key=lambda c: c["time"], reverse=True)
    return jsonify({"edited": items})


@app.route("/api/edited_image/<edit_id>")
def api_edited_image(edit_id: str):
    """Serves a stored edited image by id."""
    if "/" in edit_id or ".." in edit_id:
        return jsonify({"error": "Invalid id"}), 400
    return send_from_directory(EDITED_DIR, edit_id + ".png")


@app.route("/api/edited/save", methods=["POST"])
def api_edited_save():
    """Stores an edited image uploaded from the editor.

    Body: multipart with a single `file`.
    """
    f = request.files.get("file")
    if f is None or f.filename == "":
        return jsonify({"error": "No file uploaded"}), 400
    edit_id = time.strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:6]
    f.save(os.path.join(EDITED_DIR, edit_id + ".png"))
    if image_dims(os.path.join(EDITED_DIR, edit_id + ".png")) is None:
        os.remove(os.path.join(EDITED_DIR, edit_id + ".png"))
        return jsonify({"error": "Uploaded file is not a valid image"}), 400
    return jsonify({"id": edit_id, "url": f"/api/edited_image/{edit_id}"})


@app.route("/api/edited/delete", methods=["POST"])
def api_edited_delete():
    """Deletes an edited image by id."""
    data = request.get_json(silent=True) or {}
    edit_id = data.get("edit_id") or ""
    if "/" in edit_id or ".." in edit_id or not edit_id:
        return jsonify({"error": "Invalid id"}), 400
    path = os.path.join(EDITED_DIR, edit_id + ".png")
    if not os.path.isfile(path):
        return jsonify({"error": "Not found"}), 404
    os.remove(path)
    return jsonify({"ok": True})


@app.route("/api/edited/clear", methods=["POST"])
def api_edited_clear():
    """Deletes all stored edited images."""
    removed = 0
    for fname in os.listdir(EDITED_DIR):
        if fname.endswith(".png"):
            os.remove(os.path.join(EDITED_DIR, fname))
            removed += 1
    return jsonify({"ok": True, "removed": removed})


@app.route("/api/template_add_edited", methods=["POST"])
def api_template_add_edited():
    """Copies a stored edited image into a template folder.

    Body JSON: {"edited_id": str, "folder": "templates-relative"}
    """
    data = request.get_json(silent=True) or {}
    edit_id = data.get("edited_id") or ""
    folder = _safe_rel(data.get("folder"))
    if folder is None:
        return jsonify({"error": "Invalid folder"}), 400
    if "/" in edit_id or ".." in edit_id or not edit_id:
        return jsonify({"error": "Invalid edited id"}), 400
    if not os.path.isdir(os.path.join(TEMPLATES_DIR, folder)):
        return jsonify({"error": "Folder not found"}), 404

    src = os.path.join(EDITED_DIR, edit_id + ".png")
    if not os.path.isfile(src):
        return jsonify({"error": "Edited image not found"}), 404

    name = edit_id + ".png"
    if not cv2.imwrite(os.path.join(TEMPLATES_DIR, folder, name), cv2.imread(src)):
        return jsonify({"error": "Failed to write template image"}), 500

    return jsonify({"name": name, "rel": posixpath.join(folder, name)})


def find_matches_alpha(
    full: np.ndarray,
    tpl_bgra: np.ndarray,
    threshold: float,
) -> list[dict]:
    """Finds template matches where only opaque pixels of the template count.

    Uses per-channel zero-mean normalized cross-correlation computed with
    convolutions, so transparent areas of the edited template are ignored
    instead of being composited over a color.
    """
    fh, fw = full.shape[:2]
    th, tw = tpl_bgra.shape[:2]
    if fh < th or fw < tw:
        return []

    mask = (tpl_bgra[:, :, 3] > 0).astype(np.float32)
    msum = float(mask.sum())
    if msum < 1:
        return []

    t = tpl_bgra[:, :, :3].astype(np.float32)
    f = full.astype(np.float32)

    mt_r = mask * t[:, :, 0]
    mt_g = mask * t[:, :, 1]
    mt_b = mask * t[:, :, 2]

    s2 = float((mt_r + mt_g + mt_b).sum())
    t2 = float(
        (mask * (t[:, :, 0] * t[:, :, 0])).sum()
        + (mask * (t[:, :, 1] * t[:, :, 1])).sum()
        + (mask * (t[:, :, 2] * t[:, :, 2])).sum()
    )

    def filt(src: np.ndarray, kern: np.ndarray) -> np.ndarray:
        return cv2.filter2D(
            src,
            cv2.CV_32F,
            kern,
            anchor=(0, 0),
            borderType=cv2.BORDER_CONSTANT,
        )

    s1 = filt(f[:, :, 2], mt_b) + filt(f[:, :, 1], mt_g) + filt(f[:, :, 0], mt_r)
    s3 = filt(f[:, :, 2], mask) + filt(f[:, :, 1], mask) + filt(f[:, :, 0], mask)
    f2 = (
        filt(f[:, :, 2] * f[:, :, 2], mask)
        + filt(f[:, :, 1] * f[:, :, 1], mask)
        + filt(f[:, :, 0] * f[:, :, 0], mask)
    )

    num = s1 - (s2 * s3) / msum
    var_t = t2 - s2 * s2 / msum
    var_f = f2 - s3 * s3 / msum
    denom = np.sqrt(np.maximum(var_t, 0) * np.maximum(var_f, 0))
    score = np.divide(num, denom, out=np.zeros_like(num), where=denom > 1e-6)

    kernel = np.ones((3, 3), np.uint8)
    dilated = cv2.dilate(score, kernel)
    peaks = np.argwhere((score == dilated) & (score >= threshold) & (score > 0))

    matches: list[dict] = []
    for py, px in peaks:
        matches.append(
            {
                "x": int(px),
                "y": int(py),
                "w": int(tw),
                "h": int(th),
                "score": round(float(score[py, px]), 4),
                "center_x": int(px + tw // 2),
                "center_y": int(py + th // 2),
            }
        )
    matches.sort(key=lambda m: m["score"], reverse=True)
    return matches


@app.route("/api/match_edited", methods=["POST"])
def api_match_edited():
    """Template-matches an uploaded edited image against the current screenshot.

    Body: multipart with `file` (PNG, may be transparent) and `threshold`.
    Transparent pixels of the edited image are ignored during matching.
    Returns all match locations found in the full screenshot.
    """
    f = request.files.get("file")
    if f is None or f.filename == "":
        return jsonify({"error": "No file uploaded"}), 400
    try:
        threshold = float(request.form.get("threshold", 0.8))
    except ValueError:
        return jsonify({"error": "Invalid threshold"}), 400

    buf = np.frombuffer(f.read(), np.uint8)
    tpl = cv2.imdecode(buf, cv2.IMREAD_UNCHANGED)
    if tpl is None:
        return jsonify({"error": "Uploaded file is not a valid image"}), 400

    full = cv2.imread(DEFAULT_IMAGE)
    if full is None:
        return jsonify({"error": "No screenshot loaded"}), 400

    if tpl.ndim == 2:
        tpl = cv2.cvtColor(tpl, cv2.COLOR_GRAY2BGRA)
    matches = find_matches_alpha(full, tpl, threshold)
    return jsonify(
        {
            "matches": matches,
            "count": len(matches),
            "template": {
                "w": int(tpl.shape[1]),
                "h": int(tpl.shape[0]),
            },
        }
    )


def main() -> None:
    """Runs the match tool web server on http://127.0.0.1:<port>."""
    import sys

    port = 8081
    if len(sys.argv) > 1:
        try:
            port = int(sys.argv[1])
        except ValueError:
            print(f"Invalid port: {sys.argv[1]}")
            return
    app.run(host="127.0.0.1", port=port, debug=False)


if __name__ == "__main__":
    main()
