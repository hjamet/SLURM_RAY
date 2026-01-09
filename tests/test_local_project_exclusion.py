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
    def run(self, cancel_old_jobs: bool = True): pass
    def cancel(self, job_id: str): pass

class TestLocalProjectExclusion(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.launcher = MagicMock()
        self.launcher.project_path = self.test_dir
        self.launcher.pwd_path = self.test_dir
        self.launcher.logger = MagicMock()
        self.launcher.project_name = "test_project"
        self.launcher.files = []
        self.launcher.force_reinstall_venv = False
        
        self.backend = ConcreteBackend(self.launcher)

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    @patch('subprocess.run')
    @patch('slurmray.backend.base.ClusterBackend._is_package_local', return_value=False)
    @patch('slurmray.backend.base.ClusterBackend._get_editable_packages', return_value=set())
    def test_exclude_project_from_pyproject_toml(self, mock_editable, mock_local, mock_run):
        # 1. Create pyproject.toml
        pyproject_content = """
[project]
name = "pathfinder-rag"
version = "0.1.0"
dependencies = ["requests"]
"""
        with open(os.path.join(self.test_dir, "pyproject.toml"), "w") as f:
            f.write(pyproject_content)

        # 2. Mock uv pip list to return the project as if it was installed (e.g. editable)
        # Note: Usually local projects show up as 'pathfinder-rag @ file:///...' locally, 
        # but uv pip list --format=freeze often outputs just names or pathfinder-rag==0.1.0 
        # if it's installed in a way that uv freeze captures.
        # But if it's editable, it might be pathfinder-rag @ file://...
        # The user says: "Le serveur distant tente alors de l'installer depuis PyPI, ce qui échoue car le package n'y existe pas."
        # This implies it appears as `pathfinder-rag==0.1.0` or similar in requirements.txt.
        
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = "requests==2.31.0\npathfinder-rag==0.1.0\n"
        
        # Mock dill version
        with patch('dill.__version__', '0.3.7'):
            self.backend._generate_requirements(force_regenerate=True)
            
        req_file = os.path.join(self.test_dir, "requirements.txt")
        self.assertTrue(os.path.exists(req_file))
        
        with open(req_file, 'r') as f:
            content = f.read()
            
        print(f"Generated requirements:\n{content}")

        # 3. Assert pathfinder-rag IS in there currently (FAILING TEST scenario)
        # Wait, I want to confirm it fails first.
        # If I want to verify the fix, I'll assert it is NOT in there.
        # But for now, let's just inspect.
        
        self.assertNotIn("pathfinder-rag", content, "Project name from pyproject.toml should be excluded")
        self.assertIn("requests", content)

    @patch('subprocess.run')
    @patch('slurmray.backend.base.ClusterBackend._is_package_local', return_value=False)
    @patch('slurmray.backend.base.ClusterBackend._get_editable_packages', return_value=set())
    def test_exclude_project_from_setup_cfg(self, mock_editable, mock_local, mock_run):
        # Extension: Check setup.cfg too
        setup_cfg_content = """
[metadata]
name = pathfinder-cfg
version = 0.1.0
"""
        with open(os.path.join(self.test_dir, "setup.cfg"), "w") as f:
            f.write(setup_cfg_content)

        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = "requests==2.31.0\npathfinder-cfg==0.1.0\n"
        
        with patch('dill.__version__', '0.3.7'):
            self.backend._generate_requirements(force_regenerate=True)
            
        req_file = os.path.join(self.test_dir, "requirements.txt")
        with open(req_file, 'r') as f:
            content = f.read()
        
        self.assertNotIn("pathfinder-cfg", content, "Project name from setup.cfg should be excluded")

if __name__ == '__main__':
    unittest.main()
