"""
Bring the settings over from the app's old name, once.

Why this file exists:
    The app was called "Photo GPS Editor" until 1.9.0 and is now FotoFixer.
    Qt keeps settings under the app's name (Linux: ~/.config/<name>/,
    Windows: the registry under HKCU\\Software\\<name>, macOS: a plist), so
    after the rename the backups option, the Esri key, the last folder, and
    the map size would seem lost. On the first start under the new name they
    are copied from the old place; the old ones are left as they were.
"""

from __future__ import annotations

from PySide6.QtCore import QSettings

OLD_NAME = "Photo GPS Editor"
# Set once the copy has been made (or found nothing), so it never runs again.
COPIED_KEY = "settingsCopiedFromPhotoGpsEditor"


def copy_settings_from_old_name(new: QSettings, old: QSettings | None = None) -> int:
    """
    Copy every setting from the old name's settings into new, unless new
    already has settings of its own. Returns how many were copied.
    """
    if new.value(COPIED_KEY, False, type=bool) or new.allKeys():
        return 0
    old = old if old is not None else QSettings(OLD_NAME, OLD_NAME)
    keys = old.allKeys()
    for key in keys:
        new.setValue(key, old.value(key))
    new.setValue(COPIED_KEY, True)
    new.sync()
    return len(keys)
