"""
Unit tests for file hash synchronization logic.

Tests the core hash computation, comparison, and incremental upload detection
without requiring SSH/network access.
"""

import os
import sys
import json
import time
import tempfile
import shutil
from pathlib import Path

# Add parent directory to path to import slurmray
sys.path.insert(0, str(Path(__file__).parent.parent))

from slurmray.file_sync import FileHashManager, LocalFileSyncManager


class TestFileHashManager:
    """Tests for FileHashManager hash computation."""

    def setup_method(self):
        """Create a temp project directory with files."""
        self.tmpdir = tempfile.mkdtemp()
        self.project_root = self.tmpdir

        # Create a nested package structure: src/mypkg/sub/
        os.makedirs(os.path.join(self.project_root, "src", "mypkg", "sub"))
        self._write("src/mypkg/__init__.py", "# init")
        self._write("src/mypkg/core.py", "def core(): pass")
        self._write("src/mypkg/sub/__init__.py", "# sub init")
        self._write("src/mypkg/sub/utils.py", "def util(): pass")
        # A non-.py file
        self._write("src/mypkg/config.yaml", "key: value")
        # A top-level file
        self._write("requirements.txt", "numpy==1.0")

        self.hash_manager = FileHashManager(self.project_root)

    def teardown_method(self):
        shutil.rmtree(self.tmpdir)

    def _write(self, rel_path, content):
        abs_path = os.path.join(self.project_root, rel_path)
        os.makedirs(os.path.dirname(abs_path), exist_ok=True)
        with open(abs_path, "w") as f:
            f.write(content)

    def _read(self, rel_path):
        with open(os.path.join(self.project_root, rel_path)) as f:
            return f.read()

    def test_compute_hashes_walks_recursively(self):
        """compute_hashes(['src']) should find ALL files under src/, not just .py."""
        hashes = self.hash_manager.compute_hashes(["src"])

        expected_files = {
            "src/mypkg/__init__.py",
            "src/mypkg/core.py",
            "src/mypkg/sub/__init__.py",
            "src/mypkg/sub/utils.py",
            "src/mypkg/config.yaml",
        }
        assert set(hashes.keys()) == expected_files, (
            f"Expected files: {expected_files}, got: {set(hashes.keys())}"
        )

    def test_compute_hashes_skips_pycache(self):
        """__pycache__ directories should be excluded."""
        os.makedirs(os.path.join(self.project_root, "src", "mypkg", "__pycache__"))
        self._write("src/mypkg/__pycache__/core.cpython-311.pyc", "bytecode")

        hashes = self.hash_manager.compute_hashes(["src"])
        for key in hashes:
            assert "__pycache__" not in key, f"Unexpected pycache file: {key}"

    def test_compute_hashes_individual_files(self):
        """compute_hashes with individual file paths."""
        hashes = self.hash_manager.compute_hashes(
            ["src/mypkg/core.py", "requirements.txt"]
        )
        assert set(hashes.keys()) == {"src/mypkg/core.py", "requirements.txt"}

    def test_hash_changes_on_modification(self):
        """Hash should differ after file content changes."""
        hashes_before = self.hash_manager.compute_hashes(["src/mypkg/core.py"])
        hash_before = hashes_before["src/mypkg/core.py"]["hash"]

        # Modify file
        self._write("src/mypkg/core.py", "def core_v2(): pass  # modified")

        hashes_after = self.hash_manager.compute_hashes(["src/mypkg/core.py"])
        hash_after = hashes_after["src/mypkg/core.py"]["hash"]

        assert hash_before != hash_after, "Hash should change when file is modified"

    def test_hash_stable_without_modification(self):
        """Hash should be identical for unmodified files."""
        h1 = self.hash_manager.compute_hashes(["src/mypkg/core.py"])
        h2 = self.hash_manager.compute_hashes(["src/mypkg/core.py"])
        assert h1["src/mypkg/core.py"]["hash"] == h2["src/mypkg/core.py"]["hash"]


class TestLocalFileSyncManager:
    """Tests for incremental upload detection logic."""

    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        self.project_root = self.tmpdir

        os.makedirs(os.path.join(self.project_root, "src", "pkg", "sub"))
        self._write("src/pkg/__init__.py", "# init")
        self._write("src/pkg/main.py", "def main(): pass")
        self._write("src/pkg/sub/helper.py", "def help(): pass")
        self._write("config.yaml", "debug: true")

        self.hash_manager = FileHashManager(self.project_root)
        self.sync_manager = LocalFileSyncManager(
            self.project_root, self.hash_manager
        )

    def teardown_method(self):
        shutil.rmtree(self.tmpdir)

    def _write(self, rel_path, content):
        abs_path = os.path.join(self.project_root, rel_path)
        os.makedirs(os.path.dirname(abs_path), exist_ok=True)
        with open(abs_path, "w") as f:
            f.write(content)

    def test_first_sync_uploads_everything(self):
        """With empty remote_hashes, all files should be flagged for upload."""
        files_to_upload, files_to_delete, total = self.sync_manager.get_files_to_upload(
            ["src", "config.yaml"], remote_hashes={}
        )
        # src/ has 3 .py files + config.yaml at root = 4 files total
        assert total == 4, f"Expected 4 tracked files, got {total}"
        assert len(files_to_upload) == 4, (
            f"Expected 4 files to upload, got {len(files_to_upload)}"
        )
        assert len(files_to_delete) == 0

    def test_no_upload_when_hashes_match(self):
        """After simulating a full sync, no files should need upload."""
        # First pass: compute "remote" hashes (simulating first dispatch)
        local_hashes = self.hash_manager.compute_hashes(["src", "config.yaml"])
        remote_hashes = dict(local_hashes)  # Deep-ish copy of current state

        # Second pass: compare against remote
        files_to_upload, files_to_delete, total = self.sync_manager.get_files_to_upload(
            ["src", "config.yaml"], remote_hashes=remote_hashes
        )
        assert len(files_to_upload) == 0, (
            f"Expected 0 files, got {files_to_upload}"
        )
        assert len(files_to_delete) == 0
        assert total == 4

    def test_detects_modified_file(self):
        """Modified file should be detected via hash comparison."""
        # Simulate first dispatch
        local_hashes = self.hash_manager.compute_hashes(["src", "config.yaml"])
        remote_hashes = dict(local_hashes)

        # Modify a file
        self._write("src/pkg/main.py", "def main_v2(): pass  # updated!")

        # Second dispatch
        files_to_upload, files_to_delete, total = self.sync_manager.get_files_to_upload(
            ["src", "config.yaml"], remote_hashes=remote_hashes
        )
        assert "src/pkg/main.py" in files_to_upload, (
            f"Modified file not detected! Got: {files_to_upload}"
        )
        assert len(files_to_upload) == 1
        assert len(files_to_delete) == 0

    def test_detects_new_file(self):
        """Newly added file should be detected as 'new'."""
        local_hashes = self.hash_manager.compute_hashes(["src", "config.yaml"])
        remote_hashes = dict(local_hashes)

        # Add a new file
        self._write("src/pkg/sub/new_module.py", "def new(): pass")

        files_to_upload, files_to_delete, total = self.sync_manager.get_files_to_upload(
            ["src", "config.yaml"], remote_hashes=remote_hashes
        )
        assert "src/pkg/sub/new_module.py" in files_to_upload
        assert len(files_to_delete) == 0
        assert total == 5  # 4 original + 1 new

    def test_detects_deeply_nested_modification(self):
        """Modification deep in directory tree should be detected."""
        local_hashes = self.hash_manager.compute_hashes(["src"])
        remote_hashes = dict(local_hashes)

        # Modify deep file
        self._write("src/pkg/sub/helper.py", "def help_v2(): return 42")

        files_to_upload, files_to_delete, total = self.sync_manager.get_files_to_upload(
            ["src"], remote_hashes=remote_hashes
        )
        assert "src/pkg/sub/helper.py" in files_to_upload
        assert len(files_to_upload) == 1
        assert len(files_to_delete) == 0

    def test_returns_correct_tuple_format(self):
        """get_files_to_upload should return (list, list, int) tuple."""
        result = self.sync_manager.get_files_to_upload(["src"], remote_hashes={})
        assert isinstance(result, tuple), f"Expected tuple, got {type(result)}"
        assert len(result) == 3
        assert isinstance(result[0], list)  # files_to_upload
        assert isinstance(result[1], list)  # files_to_delete
        assert isinstance(result[2], int)   # total

    def test_update_remote_hashes_records_uploaded(self):
        """update_remote_hashes should record hashes for uploaded files."""
        remote_hashes = {}
        uploaded = ["src/pkg/main.py", "config.yaml"]

        self.sync_manager.update_remote_hashes(uploaded, remote_hashes)

        assert "src/pkg/main.py" in remote_hashes
        assert "config.yaml" in remote_hashes
        assert "hash" in remote_hashes["src/pkg/main.py"]

    def test_full_round_trip_sync_cycle(self):
        """Simulate complete sync → modify → sync cycle."""
        local_files = ["src", "config.yaml"]

        # --- Dispatch 1: fresh sync ---
        files_to_upload_1, files_to_delete_1, total_1 = self.sync_manager.get_files_to_upload(
            local_files, remote_hashes={}
        )
        assert len(files_to_upload_1) == 4  # All new
        assert len(files_to_delete_1) == 0
        assert total_1 == 4

        # Simulate successful upload → update remote hashes
        remote_hashes = {}
        self.sync_manager.update_remote_hashes(files_to_upload_1, remote_hashes)
        assert len(remote_hashes) == 4

        # --- Dispatch 2: nothing changed ---
        files_to_upload_2, files_to_delete_2, total_2 = self.sync_manager.get_files_to_upload(
            local_files, remote_hashes=remote_hashes
        )
        assert len(files_to_upload_2) == 0
        assert len(files_to_delete_2) == 0
        assert total_2 == 4

        # --- Modify a file ---
        self._write("src/pkg/main.py", "def main_v3(): return 'SYNC OK'")

        # --- Dispatch 3: detect modification ---
        files_to_upload_3, files_to_delete_3, total_3 = self.sync_manager.get_files_to_upload(
            local_files, remote_hashes=remote_hashes
        )
        assert files_to_upload_3 == ["src/pkg/main.py"], (
            f"Expected only main.py, got {files_to_upload_3}"
        )
        assert len(files_to_delete_3) == 0
        assert total_3 == 4

        # Simulate upload → update
        self.sync_manager.update_remote_hashes(files_to_upload_3, remote_hashes)

        # --- Dispatch 4: stable again ---
        files_to_upload_4, files_to_delete_4, _ = self.sync_manager.get_files_to_upload(
            local_files, remote_hashes=remote_hashes
        )
        assert len(files_to_upload_4) == 0
        assert len(files_to_delete_4) == 0

    def test_detects_renamed_file(self):
        """Renamed file should appear in files_to_delete (old) and files_to_upload (new)."""
        local_files = ["src", "config.yaml"]

        # Simulate first sync
        local_hashes = self.hash_manager.compute_hashes(local_files)
        remote_hashes = dict(local_hashes)

        # Rename: src/pkg/main.py -> src/pkg/core_main.py
        os.remove(os.path.join(self.project_root, "src/pkg/main.py"))
        self._write("src/pkg/core_main.py", "def main(): pass")

        files_to_upload, files_to_delete, total = self.sync_manager.get_files_to_upload(
            local_files, remote_hashes=remote_hashes
        )
        assert "src/pkg/main.py" in files_to_delete, (
            f"Old filename should be in files_to_delete! Got: {files_to_delete}"
        )
        assert "src/pkg/core_main.py" in files_to_upload, (
            f"New filename should be in files_to_upload! Got: {files_to_upload}"
        )

    def test_detects_deleted_file(self):
        """Deleted file should appear in files_to_delete."""
        local_files = ["src", "config.yaml"]

        # Simulate first sync
        local_hashes = self.hash_manager.compute_hashes(local_files)
        remote_hashes = dict(local_hashes)

        # Delete a file locally
        os.remove(os.path.join(self.project_root, "src/pkg/sub/helper.py"))

        files_to_upload, files_to_delete, total = self.sync_manager.get_files_to_upload(
            local_files, remote_hashes=remote_hashes
        )
        assert "src/pkg/sub/helper.py" in files_to_delete, (
            f"Deleted file not detected! Got: {files_to_delete}"
        )
        assert len(files_to_upload) == 0
        assert total == 3  # 4 - 1 deleted

    def test_cleanup_remote_hashes(self):
        """cleanup_remote_hashes should remove deleted entries from cache."""
        remote_hashes = {
            "src/pkg/main.py": {"hash": "abc", "mtime": 1.0, "size": 10},
            "src/pkg/old.py": {"hash": "def", "mtime": 2.0, "size": 20},
            "config.yaml": {"hash": "ghi", "mtime": 3.0, "size": 30},
        }

        self.sync_manager.cleanup_remote_hashes(
            ["src/pkg/old.py"], remote_hashes
        )

        assert "src/pkg/old.py" not in remote_hashes
        assert "src/pkg/main.py" in remote_hashes
        assert "config.yaml" in remote_hashes
        assert len(remote_hashes) == 2

    def test_partial_dependency_graph_does_not_delete_existing_files(self):
        """Files existing locally but outside the dependency graph must NOT be deleted.

        Reproduces the v9.3.0 regression: dill's dependency graph only includes
        a subset of project files (e.g. dense.py), but other files (base.py,
        colbert.py, etc.) exist on disk and on the cluster. They must survive.
        """
        all_files = ["src", "config.yaml"]

        # Simulate first sync with ALL files
        local_hashes = self.hash_manager.compute_hashes(all_files)
        remote_hashes = dict(local_hashes)
        assert len(remote_hashes) == 4  # All 4 files tracked remotely

        # Second sync with a PARTIAL dependency graph (only main.py)
        # This simulates dill only detecting one file as a dependency
        partial_files = ["src/pkg/main.py"]

        files_to_upload, files_to_delete, total = self.sync_manager.get_files_to_upload(
            partial_files, remote_hashes=remote_hashes
        )

        # Files outside the dependency graph but existing on disk must NOT be deleted
        assert len(files_to_delete) == 0, (
            f"Files that exist locally should NOT be deleted! Got: {files_to_delete}"
        )
        assert total == 1  # Only 1 file in the dependency graph

    def test_recovery_after_destructive_sync(self):
        """Files deleted on remote can be recovered by expanding local_files
        to include parent directories of tracked files.

        Simulates the directory expansion fix in _sync_local_files_incremental:
        if remote_hashes tracks pkg/main.py, scanning the parent directory
        discovers ALL sibling files for re-upload.
        """
        all_files = ["src", "config.yaml"]

        # Simulate first sync with ALL files
        local_hashes = self.hash_manager.compute_hashes(all_files)
        remote_hashes = dict(local_hashes)
        assert len(remote_hashes) == 4

        # Simulate v9.3.0 destructive cleanup: remote_hashes cleaned to 1 file
        # (as if cleanup_remote_hashes removed everything except main.py)
        remote_hashes = {
            "src/pkg/main.py": local_hashes["src/pkg/main.py"],
        }

        # With partial local_files (dill graph), only main.py is seen → 0 uploads
        partial_files = ["src/pkg/main.py"]
        up, dl, total = self.sync_manager.get_files_to_upload(
            partial_files, remote_hashes=remote_hashes
        )
        assert len(up) == 0, "Baseline: partial graph sees nothing to upload"

        # With directory expansion (simulates the fix in remote.py):
        # Extract parent dirs from remote_hashes keys and add to local_files
        import os as _os
        synced_dirs = set()
        for rel_path in remote_hashes:
            parent = _os.path.dirname(rel_path)
            while parent:
                synced_dirs.add(parent)
                parent = _os.path.dirname(parent)

        expanded_files = list(partial_files)
        for d in synced_dirs:
            abs_d = _os.path.join(self.project_root, d)
            if d not in expanded_files and _os.path.isdir(abs_d):
                expanded_files.append(d)

        # Now all 3 sibling files are discovered and flagged for upload
        up, dl, total = self.sync_manager.get_files_to_upload(
            expanded_files, remote_hashes=remote_hashes
        )
        assert len(up) >= 2, (
            f"Expanded scope should detect missing files for upload! Got: {up}"
        )
        assert "src/pkg/sub/helper.py" in up, f"Missing sibling file! Got: {up}"
        assert "src/pkg/__init__.py" in up, f"Missing __init__.py! Got: {up}"


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
