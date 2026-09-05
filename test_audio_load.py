from pathlib import Path

from metadata import MetadataParser
from audio_loader import AudioLoader


def main():
    # YAML metadata file
    yaml_path = Path("mohananga.yaml")

    # 1. Create the metadata parser
    parser = MetadataParser()

    # 2. Load the YAML metadata
    metadata = parser.load(yaml_path)

    # 3. Get the audio filename from the metadata
    #    and resolve it relative to the YAML file.
    audio_path = yaml_path.parent / metadata.audio_filename

    print(f"Metadata file : {yaml_path}")
    print(f"Audio file    : {audio_path}")

    # 4. Load/decode the audio
    loader = AudioLoader()
    audio = loader.load(audio_path)

    # 5. Display information about the loaded audio
    print()
    print("Audio loaded successfully")
    print("-------------------------")
    print(f"Source        : {audio.source_path}")
    print(f"Sample rate   : {audio.sample_rate} Hz")
    print(f"Samples       : {len(audio.samples)}")
    print(f"Duration      : {audio.duration:.3f} seconds")
    print(f"Data type     : {audio.samples.dtype}")
    print("Channels      : mono")


if __name__ == "__main__":
    main()