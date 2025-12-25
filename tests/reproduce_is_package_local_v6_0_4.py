import unittest
import os
import sys
from unittest.mock import MagicMock, patch

# Ensure project root is in path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from slurmray.backend.base import ClusterBackend

class TestIsPackageLocalFix(unittest.TestCase):
    def setUp(self):
        self.site_packages = "/home/user/.venv/lib/python3.12/site-packages"
        self.venv_bin = "/home/user/.venv/bin"
        self.patcher_site = patch('site.getsitepackages', return_value=[self.site_packages])
        self.mock_site = self.patcher_site.start()
        
    def tearDown(self):
        self.patcher_site.stop()

    @patch('importlib.metadata.distribution')
    def test_package_with_binary_is_not_local(self, mock_distribution):
        """
        Verify that a package with a binary in .venv/bin is NOT detected as local (fix v6.0.4).
        """
        dist = MagicMock()
        mock_distribution.return_value = dist
        
        # Mock files: metadata in site-packages, binary in venv/bin
        # abs_path should be normalized
        def mock_locate(file_path):
            if ".dist-info" in file_path:
                return f"{self.site_packages}/gdown-4.7.1.dist-info/{file_path}"
            if file_path == "bin/gdown":
                return f"{self.venv_bin}/gdown"
            return f"{self.site_packages}/gdown/{file_path}"

        dist.files = [".dist-info/METADATA", "bin/gdown", "__init__.py"]
        dist.locate_file.side_effect = mock_locate

        # Mock direct_url.json missing
        with patch('os.path.exists', side_effect=lambda x: False):
            is_local = ClusterBackend._is_package_local("gdown")
            
            # WITHOUT FIX: True (because bin/gdown is outside site-packages)
            # WITH FIX: False (because bin/gdown is ignored)
            self.assertFalse(is_local, "gdown should NOT be detected as local despite having a binary in .venv/bin")

    @patch('importlib.metadata.distribution')
    def test_truly_local_package_is_still_local(self, mock_distribution):
        """
        Verify that a truly local package (source in project) is still detected as local.
        """
        dist = MagicMock()
        mock_distribution.return_value = dist
        
        project_dir = os.path.abspath(project_root)
        
        def mock_locate(file_path):
            return f"{project_dir}/my_local_pkg/{file_path}"

        dist.files = ["__init__.py", "core.py"]
        dist.locate_file.side_effect = mock_locate

        with patch('os.path.exists', side_effect=lambda x: False):
            is_local = ClusterBackend._is_package_local("my-local-pkg")
            self.assertTrue(is_local, "Truly local package should still be detected as local")

if __name__ == '__main__':
    unittest.main()
