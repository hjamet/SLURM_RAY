import unittest
import os
import sys
import tempfile
import shutil
from unittest.mock import MagicMock, patch

# Ensure project root is in path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from slurmray.backend.base import ClusterBackend


class ConcreteBackend(ClusterBackend):
    """Concrete implementation for testing."""
    def run(self, cancel_old_jobs: bool = True, wait: bool = True): pass
    def cancel(self, job_id: str): pass


class TestWheelPackagesDetection(unittest.TestCase):
    """Tests for _get_local_wheel_packages() reading [tool.hatch.build.targets.wheel]."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.launcher = MagicMock()
        self.launcher.pwd_path = self.test_dir
        self.launcher.project_path = os.path.join(self.test_dir, ".slogs", "test")
        self.launcher.logger = MagicMock()
        os.makedirs(self.launcher.project_path, exist_ok=True)
        self.backend = ConcreteBackend(self.launcher)

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_detect_hatch_wheel_packages(self):
        """Detects packages from [tool.hatch.build.targets.wheel].packages."""
        # Create pyproject.toml with hatch wheel config
        pyproject_content = """\
[project]
name = "my-project"
version = "0.1.0"

[tool.hatch.build.targets.wheel]
packages = ["src/my_package", "vendored_lib"]
"""
        with open(os.path.join(self.test_dir, "pyproject.toml"), "w") as f:
            f.write(pyproject_content)

        # Create the actual directories
        os.makedirs(os.path.join(self.test_dir, "src", "my_package"), exist_ok=True)
        os.makedirs(os.path.join(self.test_dir, "vendored_lib"), exist_ok=True)

        result = self.backend._get_local_wheel_packages()

        self.assertEqual(result, ["src/my_package", "vendored_lib"])

    def test_detect_hatch_wheel_packages_no_section(self):
        """Returns empty list when pyproject.toml has no hatch wheel section."""
        pyproject_content = """\
[project]
name = "my-project"
version = "0.1.0"

[tool.poetry.dependencies]
python = "^3.10"
"""
        with open(os.path.join(self.test_dir, "pyproject.toml"), "w") as f:
            f.write(pyproject_content)

        result = self.backend._get_local_wheel_packages()

        self.assertEqual(result, [])

    def test_detect_hatch_wheel_packages_no_pyproject(self):
        """Returns empty list when no pyproject.toml exists."""
        result = self.backend._get_local_wheel_packages()

        self.assertEqual(result, [])

    def test_detect_hatch_wheel_packages_missing_paths_crashes(self):
        """Crashes when a declared package path does not exist (fail-fast, no fallback)."""
        pyproject_content = """\
[project]
name = "my-project"
version = "0.1.0"

[tool.hatch.build.targets.wheel]
packages = ["src/my_package", "nonexistent_lib"]
"""
        with open(os.path.join(self.test_dir, "pyproject.toml"), "w") as f:
            f.write(pyproject_content)

        # Only create one of the two directories
        os.makedirs(os.path.join(self.test_dir, "src", "my_package"), exist_ok=True)
        # nonexistent_lib is NOT created

        with self.assertRaises(FileNotFoundError) as ctx:
            self.backend._get_local_wheel_packages()

        self.assertIn("nonexistent_lib", str(ctx.exception))

    @patch('subprocess.run')
    @patch('slurmray.backend.base.ClusterBackend._is_package_local', return_value=False)
    @patch('slurmray.backend.base.ClusterBackend._get_editable_packages', return_value=set())
    def test_wheel_packages_excluded_from_requirements(self, mock_editable, mock_local, mock_run):
        """Wheel packages are excluded from generated requirements.txt."""
        # Create pyproject.toml with hatch wheel config
        pyproject_content = """\
[project]
name = "my-project"
version = "0.1.0"

[tool.hatch.build.targets.wheel]
packages = ["src/pathfinder_rag", "ragatouille"]
"""
        # Use project_path for pyproject.toml location (pwd_path)
        with open(os.path.join(self.test_dir, "pyproject.toml"), "w") as f:
            f.write(pyproject_content)

        # Create the wheel package directories
        os.makedirs(os.path.join(self.test_dir, "src", "pathfinder_rag"), exist_ok=True)
        os.makedirs(os.path.join(self.test_dir, "ragatouille"), exist_ok=True)

        # Mock uv pip list --format=freeze
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = (
            "requests==2.31.0\n"
            "pathfinder-rag==0.1.0\n"
            "ragatouille==0.0.8\n"
            "transformers==4.36.0\n"
        )

        # Set strict_versions to False for simpler output
        self.launcher.strict_versions = False

        with patch('dill.__version__', '0.3.7'):
            self.backend._generate_requirements(force_regenerate=True)

        req_file = os.path.join(self.launcher.project_path, "requirements.txt")
        self.assertTrue(os.path.exists(req_file))

        with open(req_file, 'r') as f:
            content = f.read()

        # Wheel packages MUST be excluded
        self.assertNotIn("pathfinder-rag", content,
                         "pathfinder-rag should be excluded (wheel package)")
        self.assertNotIn("ragatouille", content,
                         "ragatouille should be excluded (wheel package)")

        # Regular packages MUST remain
        self.assertIn("requests", content)
        self.assertIn("transformers", content)

    def test_wheel_packages_no_duplicates_in_files(self):
        """Wheel packages are not added to files if already covered by editable detection."""
        pyproject_content = """\
[project]
name = "my-project"
version = "0.1.0"

[tool.hatch.build.targets.wheel]
packages = ["src/pathfinder_rag"]
"""
        with open(os.path.join(self.test_dir, "pyproject.toml"), "w") as f:
            f.write(pyproject_content)

        os.makedirs(os.path.join(self.test_dir, "src", "pathfinder_rag"), exist_ok=True)

        # Simulate that the path is already in files (from editable detection)
        existing_files = ["src/pathfinder_rag"]

        wheel_packages = self.backend._get_local_wheel_packages()

        # Check deduplication logic (same as in RayLauncher.__init__)
        added = []
        for pkg_path in wheel_packages:
            is_covered = any(
                pkg_path == existing or pkg_path.startswith(existing + os.sep)
                for existing in existing_files
            )
            if not is_covered:
                added.append(pkg_path)

        self.assertEqual(added, [], "Should not add src/pathfinder_rag again")


if __name__ == '__main__':
    unittest.main()
