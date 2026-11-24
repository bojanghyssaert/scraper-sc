"""
Audioverwerking, formaatconversie (FFmpeg) en metadata-tagging (Mutagen).
"""

import io
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import imageio_ffmpeg
import requests
from mutagen.id3 import APIC, ID3, ID3NoHeaderError, TIT2, TPE1
from mutagen.mp4 import MP4, MP4Cover

from .constants import HEADERS
from .exceptions import SoundCloudError
from .logging_config import logger

# Semaphore voor gelijktijdige FFmpeg-conversies
_ffmpeg_semaphore = threading.Semaphore(2)


def embed_metadata(audio_bytes: bytes, extension: str, info: dict) -> bytes:
    """
    Voegt metadata (titel, artiest en cover-art) toe aan de gedownloade audio-bytes.
    Ondersteunt ID3 tags voor .mp3 en MP4 tags voor .m4a.
    Faalt veilig en geeft bij fouten of niet-ondersteunde formaten de ongewijzigde audio-bytes terug.
    """
    if not audio_bytes:
        return audio_bytes

    ext = ("." + extension.lstrip(".")).lower() if extension else ".mp3"

    # Haal cover art op indien artwork_url aanwezig is
    artwork_data: bytes | None = None
    artwork_url = info.get("artwork_url")
    if artwork_url and isinstance(artwork_url, str) and artwork_url.strip():
        try:
            resp = requests.get(artwork_url.strip(), headers=HEADERS, timeout=4)
            if resp.status_code == 200 and resp.content:
                artwork_data = resp.content
        except Exception:
            # Faal veilig als de cover-afbeelding niet laadt
            artwork_data = None

    title = info.get("title") or ""
    artist = info.get("artist") or ""

    if ext == ".mp3":
        try:
            bio = io.BytesIO(audio_bytes)
            try:
                tags = ID3(bio)
            except ID3NoHeaderError:
                tags = ID3()
            except Exception:
                tags = ID3()

            if title:
                tags.add(TIT2(encoding=3, text=str(title)))
            if artist:
                tags.add(TPE1(encoding=3, text=str(artist)))

            if artwork_data:
                mime = "image/png" if artwork_data.startswith(b"\x89PNG") else "image/jpeg"
                tags.add(
                    APIC(
                        encoding=3,
                        mime=mime,
                        type=3,  # Cover (front)
                        desc="Cover",
                        data=artwork_data,
                    )
                )

            tags.save(bio)
            return bio.getvalue()
        except Exception:
            # Faal veilig als metadata-tagging mislukt
            return audio_bytes

    elif ext in (".m4a", ".mp4"):
        try:
            bio = io.BytesIO(audio_bytes)
            audio = MP4(fileobj=bio)
            if audio.tags is None:
                audio.add_tags()

            if title:
                audio["\xa9nam"] = [str(title)]
            if artist:
                audio["\xa9ART"] = [str(artist)]

            if artwork_data:
                img_format = (
                    MP4Cover.FORMAT_PNG
                    if artwork_data.startswith(b"\x89PNG")
                    else MP4Cover.FORMAT_JPEG
                )
                audio["covr"] = [MP4Cover(artwork_data, imageformat=img_format)]

            audio.save(bio)
            return bio.getvalue()
        except Exception:
            # Faal veilig als metadata-tagging mislukt
            return audio_bytes

    return audio_bytes


def normalize_audio(
    audio_bytes: bytes,
    extension: str,
    target_extension: str | None = None,
) -> bytes:
    """
    Normaliseert het volume van audio-bytes via FFmpeg met het EBU R128 loudnorm-filter
    (-af loudnorm=I=-14:TP=-1.5:LRA=11).

    Behoudt voor .mp3 een hoge bitrate (-acodec libmp3lame -b:a 256k) en laat lossless
    bestanden (.wav, .flac) hun eigen codec/extensie behouden.
    Wanneer een track van .m4a naar .mp3 moet worden geconverteerd en genormaliseerd,
    gebeurt dit in één enkele FFmpeg-stap om dubbel hercoderen te voorkomen.

    Args:
        audio_bytes: Ruwe binaire inhoud van het audiobestand.
        extension: Extensie van het invoerbestand (bijv. '.mp3', '.m4a', '.wav', '.flac').
        target_extension: Optionele doel-extensie (bijv. '.mp3' bij conversie vanuit '.m4a').

    Returns:
        Binaire inhoud van het genormaliseerde audiobestand.

    Raises:
        SoundCloudError: Als FFmpeg ontbreekt of het normalisatieproces faalt.
    """
    if not audio_bytes:
        raise SoundCloudError("Geen audiogegevens ontvangen voor volume-normalisatie.")

    try:
        ffmpeg_exe = shutil.which("ffmpeg") or imageio_ffmpeg.get_ffmpeg_exe()
    except Exception as exc:
        logger.error(f"Fout bij bepalen van FFmpeg-pad: {exc}", exc_info=True)
        raise SoundCloudError(f"FFmpeg is niet beschikbaar op het systeem: {exc}") from exc

    if not ffmpeg_exe:
        logger.error("FFmpeg executable niet gevonden via PATH of imageio_ffmpeg.")
        raise SoundCloudError("FFmpeg executable niet gevonden op het systeem.")

    in_ext = ("." + extension.lstrip(".")).lower() if extension else ".mp3"
    if target_extension:
        out_ext = ("." + target_extension.lstrip(".")).lower()
    elif in_ext in (".m4a", ".mp4", ".aac"):
        out_ext = ".mp3"
    else:
        out_ext = in_ext

    with _ffmpeg_semaphore:
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                input_file = Path(tmpdir) / f"input{in_ext}"
                output_file = Path(tmpdir) / f"output{out_ext}"

                input_file.write_bytes(audio_bytes)

                cmd = [
                    str(ffmpeg_exe),
                    "-y",
                    "-i",
                    str(input_file),
                    "-vn",
                    "-af",
                    "loudnorm=I=-14:TP=-1.5:LRA=11",
                ]

                if out_ext == ".mp3":
                    cmd.extend(["-acodec", "libmp3lame", "-b:a", "256k"])
                elif out_ext == ".flac":
                    cmd.extend(["-acodec", "flac"])
                elif out_ext == ".wav":
                    cmd.extend(["-acodec", "pcm_s16le"])
                elif out_ext in (".aiff", ".aif"):
                    cmd.extend(["-acodec", "pcm_s16be"])

                cmd.append(str(output_file))

                subprocess.run(cmd, check=True, capture_output=True, shell=False, timeout=120)

                if not output_file.exists():
                    raise SoundCloudError(f"FFmpeg heeft geen output{out_ext} bestand gegenereerd.")

                return output_file.read_bytes()
        except subprocess.TimeoutExpired as exc:
            logger.error("FFmpeg-normalisatie is verlopen na 120 seconden.", exc_info=True)
            raise SoundCloudError("Volume-normalisatie via FFmpeg is verlopen na 120 seconden.") from exc
        except subprocess.CalledProcessError as exc:
            err_msg = exc.stderr.decode("utf-8", errors="replace") if exc.stderr else str(exc)
            logger.error(f"FFmpeg-normalisatiefout (exit code {exc.returncode}): {err_msg}", exc_info=True)
            safe_err = re.sub(r"[a-zA-Z]:\\[^\s'\"]+", "[bestand]", err_msg)
            raise SoundCloudError(f"Fout tijdens volume-normalisatie: {safe_err}") from exc
        except SoundCloudError:
            raise
        except Exception as exc:
            logger.error(f"Onverwachte fout tijdens volume-normalisatie: {exc}", exc_info=True)
            raise SoundCloudError("Onverwachte fout tijdens volume-normalisatie.") from exc


def convert_m4a_to_mp3(m4a_bytes: bytes, normalize: bool = False) -> bytes:
    """
    Converteert M4A/AAC audio-bytes naar een standaard MP3-bestand (256 kbps) via FFmpeg.
    Schrijft de input tijdelijk weg in een TemporaryDirectory om fragmented MP4/HLS-headers
    foutloos te ontleden en ruimt alle tijdelijke bestanden na afloop direct automatisch op.
    Indien normalize=True wordt het volume tevens genormaliseerd in één enkele FFmpeg-stap.

    Args:
        m4a_bytes: Ruwe binaire inhoud van het M4A/AAC audiobestand.
        normalize: Indien True, pas tevens EBU R128 volume-normalisatie toe.

    Returns:
        Binaire inhoud van het geconverteerde MP3-bestand.

    Raises:
        SoundCloudError: Als FFmpeg ontbreekt of de audioconversie faalt (wordt gelogd naar error.log).
    """
    if normalize:
        fn_norm = getattr(sys.modules[__name__], "normalize_audio", normalize_audio)
        return fn_norm(m4a_bytes, extension=".m4a", target_extension=".mp3")

    if not m4a_bytes:
        raise SoundCloudError("Geen audiogegevens ontvangen voor M4A-naar-MP3 conversie.")

    try:
        ffmpeg_exe = shutil.which("ffmpeg") or imageio_ffmpeg.get_ffmpeg_exe()
    except Exception as exc:
        logger.error(f"Fout bij bepalen van FFmpeg-pad: {exc}", exc_info=True)
        raise SoundCloudError(f"FFmpeg is niet beschikbaar op het systeem: {exc}") from exc

    if not ffmpeg_exe:
        logger.error("FFmpeg executable niet gevonden via PATH of imageio_ffmpeg.")
        raise SoundCloudError("FFmpeg executable niet gevonden op het systeem.")

    with _ffmpeg_semaphore:
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                input_file = Path(tmpdir) / "input.m4a"
                output_file = Path(tmpdir) / "output.mp3"

                input_file.write_bytes(m4a_bytes)

                cmd = [
                    str(ffmpeg_exe),
                    "-y",
                    "-i",
                    str(input_file),
                    "-vn",
                    "-acodec",
                    "libmp3lame",
                    "-b:a",
                    "256k",
                    str(output_file),
                ]

                subprocess.run(cmd, check=True, capture_output=True, shell=False, timeout=120)

                if not output_file.exists():
                    raise SoundCloudError("FFmpeg heeft geen output.mp3 bestand gegenereerd.")

                return output_file.read_bytes()
        except subprocess.TimeoutExpired as exc:
            logger.error("FFmpeg-conversie is verlopen na 120 seconden.", exc_info=True)
            raise SoundCloudError("Audioconversie via FFmpeg is verlopen na 120 seconden.") from exc
        except subprocess.CalledProcessError as exc:
            err_msg = exc.stderr.decode("utf-8", errors="replace") if exc.stderr else str(exc)
            logger.error(f"FFmpeg-conversiefout (exit code {exc.returncode}): {err_msg}", exc_info=True)
            safe_err = re.sub(r"[a-zA-Z]:\\[^\s'\"]+", "[bestand]", err_msg)
            raise SoundCloudError(f"Fout tijdens audioconversie naar MP3: {safe_err}") from exc
        except SoundCloudError:
            raise
        except Exception as exc:
            logger.error(f"Onverwachte fout tijdens audioconversie naar MP3: {exc}", exc_info=True)
            raise SoundCloudError("Onverwachte fout tijdens audioconversie naar MP3.") from exc
