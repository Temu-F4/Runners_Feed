import tempfile
import unittest
from pathlib import Path

from run_cleanup import remove_successful_run


class RunCleanupTest(unittest.TestCase):
    def test_removes_only_the_selected_direct_child(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            run_root = Path(temporary_directory) / "run"
            selected = run_root / "selected-job"
            sibling = run_root / "other-job"
            selected.mkdir(parents=True)
            sibling.mkdir()
            (selected / "output.mp4").write_bytes(b"test")
            (sibling / "keep.txt").write_text("keep", encoding="utf-8")

            removed = remove_successful_run(selected, run_root=run_root)

            self.assertTrue(removed)
            self.assertFalse(selected.exists())
            self.assertTrue(sibling.exists())
            self.assertEqual(
                (sibling / "keep.txt").read_text(encoding="utf-8"),
                "keep",
            )

    def test_missing_direct_child_is_a_noop(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            run_root = Path(temporary_directory) / "run"
            run_root.mkdir()

            removed = remove_successful_run(
                run_root / "missing-job",
                run_root=run_root,
            )

            self.assertFalse(removed)

    def test_rejects_run_root_and_nested_directories(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            run_root = Path(temporary_directory) / "run"
            nested = run_root / "job" / "outputs"
            nested.mkdir(parents=True)

            with self.assertRaisesRegex(ValueError, "direct child"):
                remove_successful_run(run_root, run_root=run_root)
            with self.assertRaisesRegex(ValueError, "direct child"):
                remove_successful_run(nested, run_root=run_root)

            self.assertTrue(run_root.exists())
            self.assertTrue(nested.exists())

    def test_rejects_symbolic_links(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            run_root = root / "run"
            outside = root / "outside"
            run_root.mkdir()
            outside.mkdir()
            link = run_root / "linked-job"
            link.symlink_to(outside, target_is_directory=True)

            with self.assertRaisesRegex(ValueError, "symbolic link"):
                remove_successful_run(link, run_root=run_root)

            self.assertTrue(outside.exists())


if __name__ == "__main__":
    unittest.main()
