"""
Make assets/app_icon.ico from assets/app_icon_128.png.

Windows wants a multi-size .ico: the exe's icon, the Start menu and desktop
shortcuts, and the installer itself use it, picking the size that fits
(16, 32, 48, 256). Run once after the PNG changes and commit the .ico:

    python packaging/make_windows_icon.py

The 256 px image is scaled up from the 128 px PNG, so it is a little soft;
a 256 px source would look sharper there.
"""

from pathlib import Path

from PIL import Image

ICON_SIZES = [(16, 16), (32, 32), (48, 48), (256, 256)]


def main() -> None:
    assets = Path(__file__).resolve().parent.parent / "assets"
    source = Image.open(assets / "app_icon_128.png").convert("RGBA")
    # Pillow drops any size larger than the image it saves, so the 256 px
    # frame comes from an upscaled copy. The smaller frames are given
    # ready-made from the original, resampled once rather than twice.
    largest = source.resize(ICON_SIZES[-1], Image.LANCZOS)
    smaller = [source.resize(size, Image.LANCZOS) for size in ICON_SIZES[:-1]]
    largest.save(assets / "app_icon.ico", format="ICO", sizes=ICON_SIZES, append_images=smaller)
    print(f"Wrote {assets / 'app_icon.ico'} with sizes {ICON_SIZES}")


if __name__ == "__main__":
    main()
