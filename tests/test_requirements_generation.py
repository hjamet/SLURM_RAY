import unittest
import os
import sys
from unittest.mock import MagicMock, patch
import importlib.metadata

# Ensure project root is in path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from slurmray.backend.base import ClusterBackend

# Concrete implementation for testing
class ConcreteBackend(ClusterBackend):
    def run(self, cancel_old_jobs: bool = True): pass
    def cancel(self, job_id: str): pass


class TestRequirementsGeneration(unittest.TestCase):
    def setUp(self):
        self.site_packages = "/usr/lib/python3.10/site-packages"
        self.patcher_site = patch('site.getsitepackages', return_value=[self.site_packages])
        self.mock_site = self.patcher_site.start()
        
    def tearDown(self):
        self.patcher_site.stop()

    @patch('importlib.metadata.distribution')
    def test_is_package_local_editable_metadata_in_site_packages(self, mock_distribution):
        """
        Verify that a package is detected as local even if its metadata is in site-packages,
        provided that it has source files outside site-packages.
        (Simulates editable install behavior)
        """
        dist = MagicMock()
        mock_distribution.return_value = dist
        
        # Mock direct_url.json missing to force file fallback
        dist.locate_file.side_effect = lambda x: f"{self.site_packages}/my_pkg-0.1.0.dist-info/{x}" if ".dist-info" in str(x) or x == "direct_url.json" or x == "METADATA" else f"/home/user/project/{x}"
        
        with patch('os.path.exists', side_effect=lambda x: False if "direct_url.json" in str(x) else True):
             # files list contains METADATA first (in site-packages) and then source code (locally)
            dist.files = ["METADATA", "__init__.py"]
            
            # Use the static method directly
            is_local = ClusterBackend._is_package_local("my-pkg")
            
            self.assertTrue(is_local, "Should be True because __init__.py is outside site-packages")

    @patch('importlib.metadata.distribution')
    def test_is_package_local_standard_pypi(self, mock_distribution):
        """
        Verify that a standard PyPI package (everything in site-packages) is NOT detected as local.
        """
        dist = MagicMock()
        mock_distribution.return_value = dist
        
        dist.locate_file.side_effect = lambda x: f"{self.site_packages}/requests/{x}"

        with patch('os.path.exists', side_effect=lambda x: False):
            dist.files = ["__init__.py", "utils.py"]
            
            is_local = ClusterBackend._is_package_local("requests")
            
            self.assertFalse(is_local, "Should be False because all files are in site-packages")

    @patch('subprocess.run')
    @patch('importlib.metadata.distribution')
    def test_trail_rag_editable_detection_empty_files(self, mock_distribution, mock_subprocess):
        """
        Reproduce 'trail-rag' failure:
        - importlib.metadata.files() is None or empty (common in some editable installs or when RECORD is missing).
        - is_package_local returns False (current bug).
        - BUT 'pip list -e' detection works.
        """
        # Mock distribution finding the package but having NO files
        dist = MagicMock()
        mock_distribution.return_value = dist
        dist.files = None  # Simulating missing RECORD or empty files
        dist.locate_file.side_effect = Exception("Should not be called if files is None")

        # Verify current static method FAILS in this case
        is_local_static = ClusterBackend._is_package_local("trail-rag")
        
        # This assertions confirms the CURRENT BUG/LIMITATION:
        # We expect it to be False currently because _is_package_local relies on files.
        self.assertFalse(is_local_static, "Static check fails when files is None (Expected failure of component)")

        # Now verify full method (once we fix it) uses pip list -e
        # We need to mock _get_editable_packages logic or subprocess
        
        # Mock subprocess to return trail-rag in pip list -e --format=json
        mock_subprocess.return_value.returncode = 0
        mock_subprocess.return_value.stdout = '[{"name": "trail-rag", "version": "0.1.0", "editable_project_location": "/path/to/trail-rag"}]'
        
        # We need an instance of ClusterBackend to test _generate_requirements behavior (or rather, we test the logic we plan to insert)
        # However, _generate_requirements is complex to test fully (file IO etc).
        # We will assume we will modify _generate_requirements to use _get_editable_packages.
        
        # Let's test _get_editable_packages behavior first to ensure it parses this JSON
        launcher_mock = MagicMock()
        backend = ConcreteBackend(launcher_mock)
        editable_pkgs = backend._get_editable_packages()
        
        self.assertIn("trail-rag", editable_pkgs, "pip list -e should detect trail-rag")

class TestUVRequirements(unittest.TestCase):
    def setUp(self):
        self.launcher = MagicMock()
        self.launcher.project_path = "/tmp/test_slurmray"
        self.launcher.pwd_path = "/tmp/test_slurmray"
        self.launcher.logger = MagicMock()
        self.launcher.project_name = "test_project"
        self.launcher.files = []
        self.launcher.force_reinstall_venv = False
        
        if not os.path.exists(self.launcher.project_path):
            os.makedirs(self.launcher.project_path)
            
        self.backend = ConcreteBackend(self.launcher)

    @patch('subprocess.run')
    @patch('slurmray.backend.base.ClusterBackend._is_package_local', return_value=False)
    @patch('slurmray.backend.base.ClusterBackend._get_editable_packages', return_value=set())
    def test_generate_requirements_uv(self, mock_editable, mock_local, mock_run):
        # Mock uv pip list --format=freeze output
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = "accelerate==0.26.0\ntransformers==4.36.0\ntorch==2.1.0\ndill==0.3.7\n"
        
        # Mock dill version
        with patch('dill.__version__', '0.3.7'):
            self.backend._generate_requirements(force_regenerate=True)
            
        req_file = os.path.join(self.launcher.project_path, "requirements.txt")
        self.assertTrue(os.path.exists(req_file))
        
        with open(req_file, 'r') as f:
            content = f.read()
            
        # Check that versions are stripped
        self.assertIn("accelerate\n", content)
        self.assertIn("transformers\n", content)
        self.assertIn("torch\n", content)
        # dill should be pinned
        self.assertIn("dill==0.3.7\n", content)
        # ray[default] and torch should be added if missing
        self.assertIn("ray[default]\n", content)
        
        # Check that versions are NOT there for standard packages
        self.assertNotIn("accelerate==", content)
        self.assertNotIn("transformers==", content)


if __name__ == '__main__':
    unittest.main()
