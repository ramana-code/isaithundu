from __future__ import annotations

import threading
import sounddevice as sd
import numpy as np
from audio_loader import AudioData


class AudioPlayer:
    """Sample-clock-driven real-time player for AudioData."""

    def __init__(self) -> None:
        self.audio: AudioData | None = None
        self._stream: sd.OutputStream | None = None
        self._lock = threading.Lock()
        self._start_sample = 0
        self._end_sample = 0
        self._position_sample = 0
        self._playing = False
        self._paused = False
        self._loop = False

    def set_audio(self, audio: AudioData) -> None:
        self.stop()
        with self._lock:
            self.audio = audio
            self._start_sample = 0
            self._end_sample = len(audio.samples)
            self._position_sample = 0
            self._playing = False
            self._paused = False

    def set_loop(self, enabled: bool) -> None:
        with self._lock:
            self._loop = bool(enabled)

    @property
    def loop(self) -> bool:
        with self._lock:
            return self._loop

    @property
    def is_playing(self) -> bool:
        with self._lock:
            return self._playing and not self._paused

    @property
    def is_paused(self) -> bool:
        with self._lock:
            return self._paused

    @property
    def current_time(self) -> float:
        with self._lock:
            audio = self.audio
            position = self._position_sample
        if audio is None or audio.sample_rate <= 0:
            return 0.0
        return position / audio.sample_rate

    def play(self, start_time: float | None = None,
             end_time: float | None = None) -> None:
        with self._lock:
            if self.audio is None:
                raise RuntimeError("No audio has been loaded.")
            if start_time is not None:
                self._start_sample = self._time_to_sample(start_time)
                self._position_sample = self._start_sample
            if end_time is not None:
                self._end_sample = self._time_to_sample(end_time)
            elif start_time is not None:
                self._end_sample = len(self.audio.samples)

            self._start_sample = max(0, min(self._start_sample, len(self.audio.samples)))
            self._end_sample = max(self._start_sample, min(self._end_sample, len(self.audio.samples)))
            if self._position_sample >= self._end_sample:
                self._position_sample = self._start_sample
            self._paused = False
            self._playing = True
            stream = self._stream
            sample_rate = self.audio.sample_rate

        if stream is None:
            self._start_stream(sample_rate)

    def pause(self) -> None:
        with self._lock:
            if self._playing:
                self._paused = True

    def stop(self) -> None:
        with self._lock:
            self._playing = False
            self._paused = False
            self._position_sample = self._start_sample
            stream = self._stream
            self._stream = None
        if stream is not None:
            try:
                stream.stop()
            finally:
                stream.close()

    def close(self) -> None:
        self.stop()

    def _start_stream(self, sample_rate: int) -> None:
        stream = sd.OutputStream(
            samplerate=sample_rate,
            channels=1,
            dtype="float32",
            callback=self._audio_callback,
            finished_callback=self._stream_finished,
        )
        with self._lock:
            if not self._playing:
                stream.close()
                return
            self._stream = stream
        try:
            stream.start()
        except Exception:
            with self._lock:
                if self._stream is stream:
                    self._stream = None
                    self._playing = False
            stream.close()
            raise

    def _audio_callback(self, outdata: np.ndarray, frames: int,
                        time_info, status) -> None:
        outdata.fill(0)
        with self._lock:
            audio = self.audio
            if (audio is None or not self._playing or self._paused or
                    self._position_sample >= self._end_sample):
                return

            samples = audio.samples
            position = self._position_sample
            end = self._end_sample
            loop = self._loop
            remaining = frames
            output_offset = 0

            while remaining > 0:
                available = end - position
                if available <= 0:
                    if loop:
                        position = self._start_sample
                        continue
                    self._playing = False
                    self._position_sample = end
                    break

                count = min(remaining, available)
                outdata[output_offset:output_offset + count, 0] = samples[position:position + count]
                position += count
                output_offset += count
                remaining -= count

                if position >= end:
                    if loop and remaining > 0:
                        position = self._start_sample
                    elif not loop:
                        self._playing = False
                        self._position_sample = end
                        break

            self._position_sample = position

    def _stream_finished(self) -> None:
        with self._lock:
            self._stream = None

    def _time_to_sample(self, time_seconds: float) -> int:
        if self.audio is None:
            return 0
        time_seconds = max(0.0, min(float(time_seconds), self.audio.duration))
        return int(round(time_seconds * self.audio.sample_rate))
