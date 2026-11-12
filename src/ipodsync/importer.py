"""Upload an audio file TO the iPod: copy into Fxx/ + metadata + add_track.

MP3 and AAC (.m4a) are supported, with the format codes iTunes writes for them.
ALAC (also .m4a) isn't yet: its codes aren't known (FLAC — via ffmpeg to ALAC).

Metadata is read via mutagen (required for this operation).
"""
from __future__ import annotations

import random
import shutil
from datetime import datetime, timezone
from pathlib import Path

from .library import ItlpLibrary, TrackMeta

MAC_EPOCH = 978307200
MP3_EXT_4CC = 1297101600      # 0x4d503320 ('MP3 ')
MP3_AUDIO_FORMAT = 301
M4A_EXT_4CC = 1295270176      # 0x4d344120 ('M4A ')
AAC_AUDIO_FORMAT = 502
NUM_MUSIC_FOLDERS = 50        # F00..F49

# suffix -> (avformat_info.audio_format, location.extension, kind), as iTunes writes them
FORMATS = {
    ".mp3": (MP3_AUDIO_FORMAT, MP3_EXT_4CC, "MPEG audio file"),
    ".m4a": (AAC_AUDIO_FORMAT, M4A_EXT_4CC, "AAC audio file"),
}


class UnsupportedAudio(ValueError):
    """A file `add` can't put on the iPod (yet)."""


def _mac_now() -> int:
    return int(datetime.now(timezone.utc).timestamp()) - MAC_EPOCH


def _pick_target(music_dir: Path, ext: str) -> tuple[str, Path]:
    """Pick an existing Fxx folder and a free name. Returns (location, abs_path)."""
    for _ in range(200):
        fx = f"F{random.randint(0, NUM_MUSIC_FOLDERS - 1):02d}"
        d = Path(music_dir) / fx
        if d.is_dir():
            name = f"idmix{random.randint(100000, 9999999)}{ext}"
            if not (d / name).exists():
                return f"{fx}/{name}", d / name
    raise RuntimeError("could not find a free Fxx folder on the device")


def read_meta(path: Path) -> dict:
    """Extract duration/bitrate/sample rate and tags from an MP3 or AAC .m4a via
    mutagen, plus the format codes to store. Raises UnsupportedAudio for other files."""
    path = Path(path)
    ext = path.suffix.lower()
    if ext not in FORMATS:
        raise UnsupportedAudio(f"{ext or 'this file type'} isn't supported (MP3 and AAC .m4a only)")
    if ext == ".mp3":
        from mutagen.easyid3 import EasyID3
        from mutagen.mp3 import MP3

        audio = MP3(path, ID3=EasyID3)
    else:
        from mutagen.easymp4 import EasyMP4

        audio = EasyMP4(path)
        codec = getattr(audio.info, "codec", "")
        if codec == "alac":
            raise UnsupportedAudio("Apple Lossless (ALAC) isn't supported yet")
        if codec not in ("mp4a", "mp4a.40.2"):     # AAC-LC, what iTunes encodes
            raise UnsupportedAudio(f"the {codec or 'unknown'} codec isn't supported "
                                   "(AAC .m4a only)")
    info = audio.info
    tags = audio.tags or {}           # the same "easy" keys for ID3 and MP4

    def g(k):
        v = tags.get(k)
        return v[0] if v else ""

    tn = g("tracknumber")
    try:
        tn = int(str(tn).split("/")[0]) if tn else 0
    except ValueError:
        tn = 0
    yr = g("date")
    try:
        yr = int(str(yr)[:4]) if yr else 0
    except ValueError:
        yr = 0
    return {
        "title": g("title"), "artist": g("artist"), "album": g("album"),
        "album_artist": g("albumartist"),
        "sort_title": g("titlesort"), "sort_artist": g("artistsort"),
        "sort_album": g("albumsort"), "sort_album_artist": g("albumartistsort"),
        "genre": g("genre"), "track_number": tn, "year": yr,
        "total_time_ms": int(info.length * 1000),
        "bit_rate": int(getattr(info, "bitrate", 0) // 1000),
        "sample_rate": int(getattr(info, "sample_rate", 44100)),
        "ext": ext, "audio_format": FORMATS[ext][0], "extension": FORMATS[ext][1],
        "kind": FORMATS[ext][2],
    }


def copy_audio_to_ipod(ipod, src: str | Path, ext: str = ".mp3") -> tuple[str, Path]:
    """Copy an audio file into Fxx/ on the device. Returns (location, abs_path)."""
    location, abs_path = _pick_target(ipod.music_dir, ext)
    shutil.copy2(Path(src), abs_path)
    return location, abs_path


def add_audio_to_library(itlp_dir: str | Path, location: str, meta_src: str | Path,
                         file_size: int, guid: bytes, *, overrides: dict | None = None,
                         artwork_dir: str | Path | None = None, meta: dict | None = None) -> int:
    """Add an already-copied MP3/AAC file to the .itlp library (itlp_dir) + resign.

    itlp_dir — directory with the .itdb files (a working copy is fine). meta_src —
    the source file to read tags from (unless `meta`, already read, is given). If
    artwork_dir is given (iPod_Control/Artwork on the device) and the file has embedded
    cover art, it is automatically linked to the track (frames appended to .ithmb, mhii
    to ArtworkDB, fields in item). Returns the pid.
    """
    meta = dict(meta) if meta is not None else read_meta(Path(meta_src))
    if overrides:
        meta.update({k: v for k, v in overrides.items() if v is not None})
        for k, v in overrides.items():       # the file's sort tag belongs to the old name
            if v is not None:
                meta.pop(f"sort_{k}", None)
    if not meta.get("title"):
        meta["title"] = Path(meta_src).stem

    tm = TrackMeta(
        location=location, title=meta["title"], artist=meta.get("artist", ""),
        album=meta.get("album", ""), album_artist=meta.get("album_artist", ""),
        sort_title=meta.get("sort_title", ""), sort_artist=meta.get("sort_artist", ""),
        sort_album=meta.get("sort_album", ""), sort_album_artist=meta.get("sort_album_artist", ""),
        genre=meta.get("genre", ""),
        total_time_ms=meta["total_time_ms"], track_number=meta.get("track_number", 0),
        year=meta.get("year", 0), bit_rate=meta.get("bit_rate", 0),
        sample_rate=meta.get("sample_rate", 44100), audio_format=meta["audio_format"],
        file_size=file_size, extension=meta["extension"], kind=meta["kind"],
    )
    lib = ItlpLibrary(itlp_dir)
    try:
        pid = lib.add_track(tm, date=_mac_now())
        if artwork_dir is not None:
            attach_cover_for_track(lib, pid, meta_src, artwork_dir)
        lib.resign(guid)
    finally:
        lib.close()
    return pid


def attach_cover_for_track(lib: ItlpLibrary, pid: int, audio_src: str | Path,
                           artwork_dir: str | Path) -> int | None:
    """Extract the embedded cover art from audio_src and link it to track pid.

    Appends thumbnails to .ithmb + an mhii to ArtworkDB (incrementally) and
    sets item.artwork_status/artwork_cache_id in lib. Returns image_id
    (for item.artwork_cache_id) or None if there's no cover / it's already linked.
    """
    from .artwork_writer import U64, attach_cover, extract_embedded_cover

    cover = extract_embedded_cover(audio_src)
    if not cover:
        return None
    image_id = attach_cover(artwork_dir, pid % U64, cover)
    if image_id is not None:
        lib.set_track_artwork(pid, image_id)
        # album cover art (the "Albums" view/lists) — points to this track, like iTunes
        album_pid = lib.album_pid_of(pid)
        if album_pid:
            lib.set_album_artwork(album_pid, pid)
    return image_id
