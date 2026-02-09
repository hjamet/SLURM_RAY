"""
Tests for file_sync module — Mirror Mode.
Tests list_local_files() which is the core of the stateless mirror sync.
"""

import os
import shutil
import tempfile
import unittest

from slurmray.file_sync import list_local_files


class TestListLocalFiles(unittest.TestCase):
    """Tests for list_local_files function."""

    def setUp(self):
        """Create a temp project structure."""
        self.project_root = tempfile.mkdtemp()
        self._write("src/pkg/__init__.py", "# init")
        self._write("src/pkg/main.py", "def main(): pass")
        self._write("src/pkg/sub/helper.py", "def help(): pass")
        self._write("config.yaml", "debug: true")

    def tearDown(self):
        shutil.rmtree(self.project_root)

    def _write(self, rel_path, content):
        abs_path = os.path.join(self.project_root, rel_path)
        os.makedirs(os.path.dirname(abs_path), exist_ok=True)
        with open(abs_path, "w") as f:
            f.write(content)

    # --- Directory walking ---

    def test_walks_directory_recursively(self):
        """Passing a directory should find all files recursively."""
        result = list_local_files(self.project_root, ["src"])
        expected = {
            "src/pkg/__init__.py",
            "src/pkg/main.py",
            "src/pkg/sub/helper.py",
        }
        assert result == expected

    def test_walks_multiple_entries(self):
        """Passing dirs + files should combine all results."""
        result = list_local_files(self.project_root, ["src", "config.yaml"])
        assert len(result) == 4
        assert "config.yaml" in result
        assert "src/pkg/main.py" in result

    def test_individual_file(self):
        """Passing individual file paths should work."""
        result = list_local_files(self.project_root, ["src/pkg/main.py"])
        assert result == {"src/pkg/main.py"}

    # --- Skip logic ---

    def test_skips_pycache(self):
        """__pycache__ directories should be excluded."""
        self._write("src/pkg/__pycache__/main.cpython-311.pyc", "bytecode")
        result = list_local_files(self.project_root, ["src"])
        assert not any("__pycache__" in f for f in result)

    def test_skips_nonexistent_entries(self):
        """Non-existent paths should be silently skipped."""
        result = list_local_files(
            self.project_root, ["does_not_exist", "config.yaml"]
        )
        assert result == {"config.yaml"}

    # --- Edge cases ---

    def test_empty_input(self):
        """Empty file list should return empty set."""
        result = list_local_files(self.project_root, [])
        assert result == set()

    def test_deduplication(self):
        """Overlapping entries should not produce duplicates."""
        result = list_local_files(
            self.project_root,
            ["src", "src/pkg/main.py"],  # main.py included twice
        )
        assert len([f for f in result if f == "src/pkg/main.py"]) == 1

    # --- Return type ---

    def test_returns_set_of_strings(self):
        """Return value must be a set of relative path strings."""
        result = list_local_files(self.project_root, ["src"])
        assert isinstance(result, set)
        for item in result:
            assert isinstance(item, str)
            assert not os.path.isabs(item)

    # --- Rename/Delete scenarios ---

    def test_rename_changes_listing(self):
        """After renaming a file, old name is gone, new name appears."""
        before = list_local_files(self.project_root, ["src"])
        assert "src/pkg/main.py" in before

        # Rename
        os.rename(
            os.path.join(self.project_root, "src/pkg/main.py"),
            os.path.join(self.project_root, "src/pkg/core.py"),
        )

        after = list_local_files(self.project_root, ["src"])
        assert "src/pkg/main.py" not in after
        assert "src/pkg/core.py" in after

    def test_delete_removes_from_listing(self):
        """After deleting a file, it is no longer listed."""
        os.remove(os.path.join(self.project_root, "src/pkg/sub/helper.py"))
        result = list_local_files(self.project_root, ["src"])
        assert "src/pkg/sub/helper.py" not in result

    def test_mirror_sync_scenario(self):
        """Full mirror scenario: local_files ∩ remote → orphans detected."""
        # Simulate: local has 4 files
        local = list_local_files(self.project_root, ["src", "config.yaml"])
        assert len(local) == 4

        # Simulate: remote has 5 files (including a stale one)
        remote = local | {"src/pkg/embedding.py"}  # stale ghost

        orphans = remote - local
        assert orphans == {"src/pkg/embedding.py"}


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
