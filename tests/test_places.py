import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from core.places import (
    Place,
    folder_contents_summary,
    gvfs_share_name,
    has_subfolders,
    is_hidden,
    is_network_file_system,
    is_system_mount,
    list_photos,
    list_subfolders,
    network_share_name,
    parse_gtk_bookmarks,
    photos_in_folders,
)


class BookmarkTests(unittest.TestCase):
    def test_reads_local_folders_with_names(self) -> None:
        text = (
            "file:///home/matt/Documents Documents\n"
            "file:///mnt/synology_photos/Office%20PC%20-%20My%20Pictures Office PC - My Pictures\n"
            "\n"
            "file:///mnt/synology/Photos\n"
        )

        self.assertEqual(
            parse_gtk_bookmarks(text),
            [
                Place("Documents", Path("/home/matt/Documents")),
                Place("Office PC - My Pictures", Path("/mnt/synology_photos/Office PC - My Pictures")),
                # No name given: the folder's own name.
                Place("Photos", Path("/mnt/synology/Photos")),
            ],
        )

    def test_skips_bookmarks_that_need_a_connection(self) -> None:
        text = "smb://nas.local/photo Photo share\nsftp://server/home Server\n"

        self.assertEqual(parse_gtk_bookmarks(text), [])


class NetworkNameTests(unittest.TestCase):
    def test_windows_style_share(self) -> None:
        self.assertEqual(
            network_share_name("//iramnas.synology.me/photo", Path("/mnt/synology_photos")),
            "photo on iramnas.synology.me",
        )

    def test_mac_share_leaves_out_the_user_name(self) -> None:
        self.assertEqual(
            network_share_name("//matt@nas.local/photo", Path("/Volumes/photo")),
            "photo on nas.local",
        )
        self.assertEqual(
            network_share_name("//WORKGROUP;matt@nas.local/photo", Path("/Volumes/photo")),
            "photo on nas.local",
        )

    def test_nfs_share(self) -> None:
        self.assertEqual(
            network_share_name("nas.local:/volume1/photo", Path("/mnt/photo")),
            "photo on nas.local",
        )

    def test_unknown_device_uses_the_folder_name(self) -> None:
        self.assertEqual(network_share_name("sshfs#me@host:", Path("/mnt/remote")), "remote")

    def test_gvfs_share(self) -> None:
        self.assertEqual(
            gvfs_share_name("smb-share:server=nas.local,share=photo"), "photo on nas.local"
        )
        self.assertEqual(gvfs_share_name("sftp:host=server.lan"), "server.lan")

    def test_network_file_systems(self) -> None:
        self.assertTrue(is_network_file_system("cifs"))
        self.assertTrue(is_network_file_system("nfs4"))
        self.assertFalse(is_network_file_system("ext4"))


class SystemMountTests(unittest.TestCase):
    def test_system_mounts_are_left_out(self) -> None:
        self.assertTrue(is_system_mount("/snap/core/123", "squashfs"))
        self.assertTrue(is_system_mount("/boot/efi", "vfat"))
        self.assertTrue(is_system_mount("/run/user/1000", "tmpfs"))
        # macOS system volumes.
        self.assertTrue(is_system_mount("/System/Volumes/Data", "apfs"))
        self.assertTrue(is_system_mount("/System/Volumes/Preboot", "apfs"))

    def test_drives_are_kept(self) -> None:
        self.assertFalse(is_system_mount("/", "ext4"))
        self.assertFalse(is_system_mount("/media/matt/Data", "ext4"))
        self.assertFalse(is_system_mount("/mnt/backup", "ntfs"))
        self.assertFalse(is_system_mount("/Volumes/Photos SSD", "exfat"))


class FakeEntry:
    """Stands in for os.DirEntry, with chosen Windows attributes or Mac flags."""

    def __init__(self, name: str, *, attributes: int = 0, flags: int = 0) -> None:
        self.name = name
        self._stat = SimpleNamespace(st_file_attributes=attributes, st_flags=flags)

    def stat(self, follow_symlinks: bool = True):
        return self._stat


class HiddenTests(unittest.TestCase):
    def test_dot_names_are_hidden_everywhere(self) -> None:
        for platform in ("linux", "win32", "darwin"):
            self.assertTrue(is_hidden(FakeEntry(".cache"), platform))

    def test_windows_hidden_attribute(self) -> None:
        self.assertTrue(is_hidden(FakeEntry("AppData", attributes=0x2), "win32"))
        self.assertTrue(is_hidden(FakeEntry("desktop.ini", attributes=0x2 | 0x4), "win32"))
        self.assertFalse(is_hidden(FakeEntry("Pictures", attributes=0x10), "win32"))
        # "System" alone (a folder with a custom icon) shows, as in File Explorer.
        self.assertFalse(is_hidden(FakeEntry("2026", attributes=0x10 | 0x4), "win32"))

    def test_mac_hidden_flag(self) -> None:
        self.assertTrue(is_hidden(FakeEntry("Library", flags=0x8000), "darwin"))
        self.assertFalse(is_hidden(FakeEntry("Pictures"), "darwin"))

    def test_linux_only_hides_dot_names(self) -> None:
        self.assertFalse(is_hidden(FakeEntry("AppData", attributes=0x2), "linux"))


class FolderListingTests(unittest.TestCase):
    def setUp(self) -> None:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        self.root = Path(temp_dir.name)
        for name in ("b.JPG", "a.jpg", "raw.CR3", "notes.txt", ".hidden.jpg"):
            (self.root / name).write_bytes(b"")
        for name in ("Zoo", "apples", ".cache"):
            (self.root / name).mkdir()
        # A folder whose name looks like a photo is still a folder.
        (self.root / "folder.jpg").mkdir()

    def test_lists_only_photos_sorted_by_name(self) -> None:
        self.assertEqual(
            [path.name for path in list_photos(self.root)],
            ["a.jpg", "b.JPG", "raw.CR3"],
        )

    def test_lists_visible_subfolders_sorted_by_name(self) -> None:
        self.assertEqual(
            [path.name for path in list_subfolders(self.root)],
            ["apples", "folder.jpg", "Zoo"],
        )

    def test_has_subfolders(self) -> None:
        self.assertTrue(has_subfolders(self.root))
        # Only photos inside, or only a hidden folder: no subfolders.
        self.assertFalse(has_subfolders(self.root / "apples"))
        (self.root / "apples" / "photo.jpg").write_bytes(b"")
        (self.root / "apples" / ".thumbs").mkdir()
        self.assertFalse(has_subfolders(self.root / "apples"))
        self.assertFalse(has_subfolders(self.root / "gone"))

    def test_missing_folder_lists_nothing(self) -> None:
        missing = self.root / "gone"
        self.assertEqual(list_photos(missing), [])
        self.assertEqual(list_subfolders(missing), [])



class FolderPhotosTests(unittest.TestCase):
    """The photos added for folders chosen in the picker."""

    def setUp(self) -> None:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        self.root = Path(temp_dir.name)
        # trip/{b.jpg, A.cr3, notes.txt}, trip/day 1/c.jpg,
        # trip/day 1/morning/d.dng, trip/.hidden/e.jpg, trip/Day 2/f.jpg
        self.trip = self.root / "trip"
        for folder in ("day 1/morning", ".hidden", "Day 2"):
            (self.trip / folder).mkdir(parents=True)
        for name in ("b.jpg", "A.cr3", "notes.txt", "day 1/c.jpg", "day 1/morning/d.dng", ".hidden/e.jpg", "Day 2/f.jpg"):
            (self.trip / name).write_bytes(b"")

    def test_only_the_folders_own_photos_without_subfolders(self) -> None:
        self.assertEqual(
            photos_in_folders([self.trip], recursive=False),
            [self.trip / "A.cr3", self.trip / "b.jpg"],
        )

    def test_every_photo_inside_with_subfolders(self) -> None:
        # Each folder before its subfolders, siblings by name ignoring case;
        # hidden folders left out.
        self.assertEqual(
            photos_in_folders([self.trip], recursive=True),
            [
                self.trip / "A.cr3",
                self.trip / "b.jpg",
                self.trip / "day 1" / "c.jpg",
                self.trip / "day 1" / "morning" / "d.dng",
                self.trip / "Day 2" / "f.jpg",
            ],
        )

    def test_a_photo_found_twice_is_listed_once(self) -> None:
        photos = photos_in_folders([self.trip / "day 1", self.trip], recursive=True)

        self.assertEqual(len(photos), len(set(photos)))
        self.assertEqual(photos[:2], [self.trip / "day 1" / "c.jpg", self.trip / "day 1" / "morning" / "d.dng"])

    def test_stops_when_cancelled(self) -> None:
        self.assertEqual(photos_in_folders([self.trip], recursive=True, cancelled=lambda: True), [])

    @unittest.skipIf(sys.platform == "win32", "symlinks need extra rights on Windows")
    def test_a_link_to_a_parent_folder_is_not_followed(self) -> None:
        (self.trip / "day 1" / "loop").symlink_to(self.trip, target_is_directory=True)

        photos = photos_in_folders([self.trip], recursive=True)

        self.assertEqual(len(photos), 5)

    def test_folder_contents_summary_counts_photos_and_folders(self) -> None:
        # Hidden folder and the text file don't count.
        self.assertEqual(folder_contents_summary(self.trip), (2, 2))
        self.assertEqual(folder_contents_summary(self.trip / "day 1" / "morning"), (1, 0))
        self.assertEqual(folder_contents_summary(self.root / "missing"), (0, 0))


if __name__ == "__main__":
    unittest.main()
