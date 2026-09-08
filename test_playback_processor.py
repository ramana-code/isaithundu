from pathlib import Path

import soundfile as sf

from audio_loader import AudioLoader
from playback_processor import (
    PlaybackProcessor,
    PlaybackTransform,
)


INPUT = Path("mohananga.mp3")
OUTPUT = Path("mohananga_shifted.wav")


def main() -> None:
    audio = AudioLoader().load(INPUT)

    processor = PlaybackProcessor()

    transform = PlaybackTransform(
        pitch_semitones=-2,
        pitch_cents=20,
        speed=0.8,
    )

    processed = processor.process(
        samples=audio.samples,
        sample_rate=audio.sample_rate,
        transform=transform,
    )

    sf.write(
        OUTPUT,
        processed,
        audio.sample_rate,
        subtype="FLOAT",
    )

    print(f"Input : {INPUT}")
    print(f"Output: {OUTPUT}")
    print(f"Input samples : {len(audio.samples):,}")
    print(f"Output samples: {len(processed):,}")
    print(
        f"Input duration : "
        f"{len(audio.samples) / audio.sample_rate:.3f} s"
    )
    print(
        f"Output duration: "
        f"{len(processed) / audio.sample_rate:.3f} s"
    )


if __name__ == "__main__":
    main()
