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

if __name__ == '__main__':
    unittest.main()
