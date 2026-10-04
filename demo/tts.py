"""Render each narration line in narration.json to its own WAV with Kokoro.

Writes out/vo/<id>.wav and out/vo/durations.json ({id: seconds}), which the
recorder reads so each scene lasts at least as long as its line.

    uv run --no-project --python 3.12 --with kokoro-onnx --with soundfile python tts.py
"""

import json
from pathlib import Path

import soundfile as sf
from kokoro_onnx import Kokoro

HERE = Path(__file__).parent
MODEL_DIR = Path.home() / ".cache" / "kokoro"
OUT = HERE / "out" / "vo"


def main() -> None:
    config = json.loads((HERE / "narration.json").read_text())
    kokoro = Kokoro(
        str(MODEL_DIR / "kokoro-v1.0.onnx"), str(MODEL_DIR / "voices-v1.0.bin")
    )
    OUT.mkdir(parents=True, exist_ok=True)
    durations: dict[str, float] = {}
    for line in config["lines"]:
        samples, rate = kokoro.create(
            line["text"],
            voice=config["voice"],
            speed=config.get("speed", 1.0),
            lang="en-us",
        )
        sf.write(OUT / f"{line['id']}.wav", samples, rate)
        durations[line["id"]] = round(len(samples) / rate, 3)
        print(f"{line['id']:>12}  {durations[line['id']]:5.2f}s  {line['text']}")
    (OUT / "durations.json").write_text(json.dumps(durations, indent=2))
    print(f"{'total':>12}  {sum(durations.values()):5.2f}s")


if __name__ == "__main__":
    main()
