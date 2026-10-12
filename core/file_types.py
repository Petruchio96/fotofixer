from pathlib import Path

# Single source of truth for which files the app can open (the Add Photos
# picker lists only these). Only files cameras and phones make: JPEG, RAW,
# and HEIC/HEIF (not formats made by software, such as PNG or TIFF; the
# user's call, 2026-10-12). ExifTool reads and writes GPS and dates in all.
JPEG_EXTENSIONS = {
    ".jpg",
    ".jpeg",
}

# RAW files: Canon (CR2, CR3), Adobe DNG, Nikon (NEF, NRW), Sony (ARW),
# Fujifilm (RAF), Olympus/OM System (ORF), Panasonic (RW2), Pentax (PEF),
# Samsung (SRW). Each holds JPEG previews the thumbnails are made from.
RAW_EXTENSIONS = {
    ".cr2",
    ".cr3",
    ".dng",
    ".nef",
    ".nrw",
    ".arw",
    ".raf",
    ".orf",
    ".rw2",
    ".pef",
    ".srw",
}

# HEIC/HEIF: iPhone photos (.heic) and Canon's HEIF (.hif). Their thumbnails
# are decoded with pillow-heif (see gui/thumbnail_loader.py).
HEIF_EXTENSIONS = {
    ".heic",
    ".heif",
    ".hif",
}

SUPPORTED_EXTENSIONS = JPEG_EXTENSIONS | RAW_EXTENSIONS | HEIF_EXTENSIONS


def is_supported_file(path: Path) -> bool:
    return path.suffix.lower() in SUPPORTED_EXTENSIONS


def is_raw_file(path: Path) -> bool:
    return path.suffix.lower() in RAW_EXTENSIONS


def is_heif_file(path: Path) -> bool:
    return path.suffix.lower() in HEIF_EXTENSIONS


def may_hold_preview(path: Path) -> bool:
    """
    Files whose thumbnail comes from a preview image stored inside them
    (RAW files; some HEIF files, such as Canon's, have a JPEG one too),
    rather than from decoding the photo itself.
    """
    return is_raw_file(path) or is_heif_file(path)
