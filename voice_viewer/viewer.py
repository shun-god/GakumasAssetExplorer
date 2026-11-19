"""Serve the local voice library in a browser."""

import csv
import sys
import wave
import webbrowser
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from flask import Flask, abort, jsonify, request, send_file
from werkzeug.serving import make_server


VIEWER_DIR = Path(__file__).resolve().parent
REPO_ROOT = VIEWER_DIR.parent


@dataclass(frozen=True)
class Clip:
    wav: Path
    text: str
    status: str
    duration: float | None


def wav_duration(path: Path) -> float | None:
    try:
        with wave.open(str(path), "rb") as source:
            return source.getnframes() / source.getframerate()
    except (OSError, EOFError, wave.Error):
        return None


def read_clips(folder: Path) -> tuple[list[Clip], int]:
    clips = []
    errors = 0
    for caption_file in sorted(folder.rglob("captions.csv")):
        archive_clips = []
        try:
            with caption_file.open(encoding="utf-8-sig", newline="") as stream:
                rows = csv.DictReader(stream)
                if not {"filename", "text"}.issubset(rows.fieldnames or ()):
                    raise ValueError("Missing filename or text column")
                for row in rows:
                    name = row["filename"]
                    if (
                        not name
                        or Path(name).name != name
                        or not name.lower().endswith(".wav")
                    ):
                        continue
                    wav = caption_file.with_name(name)
                    archive_clips.append(
                        Clip(wav, row["text"] or "", row.get("caption_status") or "", wav_duration(wav))
                    )
        except (OSError, UnicodeError, csv.Error, ValueError):
            errors += 1
            continue
        clips.extend(archive_clips)
    return clips, errors


def create_app(initial_folder: Path) -> Flask:
    app = Flask(__name__)
    app.config["TRUSTED_HOSTS"] = ["127.0.0.1", "localhost"]
    libraries: dict[str, list[Clip]] = {}

    @app.get("/")
    def index():
        return send_file(VIEWER_DIR / "index.html")

    @app.get("/api/settings")
    def settings():
        return jsonify(folder=str(initial_folder))

    @app.post("/api/library")
    def library():
        body = request.get_json(silent=True)
        if not isinstance(body, dict) or not isinstance(body.get("folder"), str):
            abort(400)
        raw_path = body["folder"].strip().strip('"')
        if not raw_path:
            return jsonify(error="音声フォルダのパスを入力してください。"), 400
        try:
            folder = (REPO_ROOT / raw_path).resolve()
            if not folder.is_dir():
                return jsonify(error="指定したフォルダが見つかりません。"), 404
            clips, errors = read_clips(folder)
        except (OSError, ValueError):
            return jsonify(error="指定したフォルダを読み込めませんでした。"), 400
        if not clips:
            return jsonify(error="読み込める captions.csv がありません。"), 404

        key = uuid4().hex
        payload = {
            "folder": str(folder),
            "errors": errors,
            "clips": [
                {
                    "url": f"/audio/{key}/{index}",
                    "filename": clip.wav.name,
                    "archive": clip.wav.parent.relative_to(folder).as_posix(),
                    "text": clip.text,
                    "status": clip.status,
                    "duration": clip.duration,
                }
                for index, clip in enumerate(clips)
            ],
        }
        libraries[key] = clips
        return jsonify(payload)

    @app.get("/audio/<key>/<int:index>")
    def audio(key: str, index: int):
        clips = libraries.get(key)
        if clips is None or index >= len(clips):
            abort(404)
        path = clips[index].wav
        if not path.is_file():
            abort(404)
        return send_file(path, mimetype="audio/wav", conditional=True)

    return app


def main() -> None:
    folder = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else REPO_ROOT / "shro_voices"
    with make_server("127.0.0.1", 0, create_app(folder), threaded=True) as server:
        url = f"http://127.0.0.1:{server.server_port}/"
        print(f"Voice viewer: {url}", flush=True)
        webbrowser.open(url)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
