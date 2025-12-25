
import unittest
from unittest.mock import MagicMock, patch
import sys
import os

# Add project root to path
sys.path.append(os.getcwd())

from slurmray.backend.remote import RemoteMixin
from slurmray.backend.desi import DesiBackend
from slurmray.backend.slurm import SlurmBackend

class MockLauncher:
    def __init__(self):
        self.server_ssh = "mock_host"
        self.server_username = "mock_user"
        self.server_password = "mock_password"
        self.project_name = "mock_project"
        self.project_path = "/tmp/mock_project"
        self.logger = MagicMock()
        self.pwd_path = "/tmp"
        self.local_python_version = "3.12"
        self.cluster = False
        self.server_run = True

class TestSFTPReuse(unittest.TestCase):
    
    @patch('paramiko.SSHClient')
    def test_desi_sftp_reuse(self, mock_ssh_cls):
        launcher = MockLauncher()
        backend = DesiBackend(launcher)
        
        # Mock SSH client
        mock_ssh = mock_ssh_cls.return_value
        mock_sftp = MagicMock()
        mock_ssh.open_sftp.return_value = mock_sftp
        
        # 1. Call get_sftp first time
        sftp1 = backend.get_sftp()
        mock_ssh.open_sftp.assert_called_once()
        self.assertEqual(sftp1, mock_sftp)
        
        # 2. Call get_sftp second time
        sftp2 = backend.get_sftp()
        mock_ssh.open_sftp.assert_called_once() # Should NOT be called again
        self.assertEqual(sftp1, sftp2)
        
        # 3. Simulate connection reset (e.g. listdir raises error)
        mock_sftp.listdir.side_effect = OSError("Socket closed")
        
        # 4. Call get_sftp should reconnect
        sftp3 = backend.get_sftp()
        self.assertEqual(mock_ssh.open_sftp.call_count, 2)
        
    @patch('paramiko.SSHClient')
    def test_slurm_sftp_reuse(self, mock_ssh_cls):
        launcher = MockLauncher()
        # Slurm backend setup
        backend = SlurmBackend(launcher)
        
        mock_ssh = mock_ssh_cls.return_value
        mock_sftp = MagicMock()
        mock_ssh.open_sftp.return_value = mock_sftp
        
        # Inject mock ssh client into backend (simulate _launch_server)
        backend.ssh_client = mock_ssh
        
        # 1. Call get_sftp
        sftp1 = backend.get_sftp()
        mock_ssh.open_sftp.assert_called_once()
        
        # 2. Call get_sftp again
        sftp2 = backend.get_sftp()
        mock_ssh.open_sftp.assert_called_once() # Reuse
        
if __name__ == '__main__':
    unittest.main()
