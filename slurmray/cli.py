import os
import time
import subprocess
import signal
import sys
import webbrowser
import argparse
import threading
from abc import ABC, abstractmethod
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.prompt import Prompt, Confirm
from rich.live import Live
from dotenv import load_dotenv
import paramiko
from getpass import getpass

# Try to import RayLauncher components
try:
    from slurmray.utils import SSHTunnel
except ImportError:
    # Fallback if running from root without package installed
    sys.path.append(os.getcwd())
    from slurmray.utils import SSHTunnel

load_dotenv()

console = Console()

class ClusterManager(ABC):
    """Abstract base class for cluster managers"""
    
    def __init__(self, username: str = None, password: str = None, ssh_host: str = None):
        self.username = username
        self.password = password
        self.ssh_host = ssh_host
        self.active_tunnel = None
        self.ssh_client = None
    
    @abstractmethod
    def _connect(self):
        """Connect to the cluster if not already connected"""
        pass
    
    @abstractmethod
    def get_jobs(self):
        """Retrieve jobs from the cluster"""
        pass
    
    @abstractmethod
    def cancel_job(self, job_id):
        """Cancel a job"""
        pass
    
    @abstractmethod
    def get_head_node(self, job_id):
        """Get head node for a job"""
        pass
    
    def open_dashboard(self, job_id):
        """Open Ray dashboard for a job"""
        head_node = self.get_head_node(job_id)
        if not head_node:
            console.print(f"[red]Could not determine head node for job {job_id}. Is it running?[/red]")
            return

        console.print(f"[blue]Head node identified: {head_node}[/blue]")
        
        if not self.password:
            self.password = getpass("Enter cluster password: ")

        try:
            console.print("[yellow]Setting up SSH tunnel... (Press Ctrl+C to stop)[/yellow]")
            self.active_tunnel = SSHTunnel(
                ssh_host=self.ssh_host,
                ssh_username=self.username,
                ssh_password=self.password,
                remote_host=head_node,
                local_port=0, 
                remote_port=8265
            )
            
            with self.active_tunnel:
                url = f"http://localhost:{self.active_tunnel.local_port}"
                console.print(f"[green]Dashboard available at: {url}[/green]")
                
                console.print("Opening browser...")
                try:
                    webbrowser.open(url)
                except Exception as e:
                    console.print(f"[yellow]Could not open browser automatically: {e}[/yellow]")
                
                console.print("Tunnel active. Keeping connection alive...")
                try:
                    while True:
                        time.sleep(1)
                except KeyboardInterrupt:
                    console.print("\n[yellow]Closing tunnel...[/yellow]")
        except Exception as e:
            console.print(f"[red]Failed to establish tunnel: {e}[/red]")

class SlurmManager(ClusterManager):
    def __init__(self, username: str = None, password: str = None, ssh_host: str = None):
        super().__init__(username, password, ssh_host)
        self.username = username or os.getenv("CURNAGL_USERNAME") or os.environ.get("USER")
        self.password = password or os.getenv("CURNAGL_PASSWORD")
        self.ssh_host = ssh_host or "curnagl.dcsr.unil.ch"
    
    def _connect(self):
        """Connect to the cluster if not already connected"""
        if self.ssh_client and self.ssh_client.get_transport() and self.ssh_client.get_transport().is_active():
            return

        if not self.password:
            self.password = getpass("Enter cluster password: ")

        try:
            self.ssh_client = paramiko.SSHClient()
            self.ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            self.ssh_client.connect(
                hostname=self.ssh_host,
                username=self.username,
                password=self.password
            )
        except Exception as e:
            console.print(f"[red]Failed to connect to cluster: {e}[/red]")
            self.ssh_client = None
            raise

    def run_command(self, command):
        """Run a command on the cluster via SSH"""
        self._connect()
        stdin, stdout, stderr = self.ssh_client.exec_command(command)
        return stdout.read().decode("utf-8"), stderr.read().decode("utf-8")

    def get_jobs(self):
        """Retrieve jobs from squeue"""
        try:
            # Run squeue command remotely
            stdout, stderr = self.run_command(f"squeue -u {self.username} -o '%.18i %.9P %.30j %.8u %.8T %.10M %.6D %R' --noheader")
            
            lines = stdout.strip().split("\n")
            jobs = []
            for line in lines:
                if not line.strip():
                    continue
                parts = line.split()
                if len(parts) >= 8:
                    jobs.append({
                        "id": parts[0],
                        "partition": parts[1],
                        "name": parts[2],
                        "user": parts[3],
                        "state": parts[4],
                        "time": parts[5],
                        "nodes": parts[6],
                        "nodelist": parts[7]
                    })
            return jobs
        except Exception as e:
            console.print(f"[red]Error retrieving jobs: {e}[/red]")
            return []

    def cancel_job(self, job_id):
        """Cancel a SLURM job"""
        try:
            stdout, stderr = self.run_command(f"scancel {job_id}")
            if stderr:
                console.print(f"[red]Failed to cancel job {job_id}: {stderr}[/red]")
            else:
                console.print(f"[green]Job {job_id} cancelled successfully.[/green]")
        except Exception as e:
            console.print(f"[red]Error cancelling job: {e}[/red]")

    def get_head_node(self, job_id):
        """Get head node for a job"""
        try:
            # Get job info remotely
            stdout, stderr = self.run_command(f"scontrol show job {job_id}")
            output = stdout
            
            # Simple parsing for NodeList
            import re
            match = re.search(r"NodeList=([^\s]+)", output)
            if match:
                nodelist = match.group(1)
                # Convert nodelist to hostname
                stdout, stderr = self.run_command(f"scontrol show hostnames {nodelist}")
                hosts = stdout.strip().split("\n")
                if hosts:
                    return hosts[0]
            return None
        except Exception:
            return None


class DesiManager(ClusterManager):
    """Manager for Desi server (ISIPOL09) using Smart Lock"""
    
    LOCK_FILE = "/tmp/slurmray_desi.lock"
    
    def __init__(self, username: str = None, password: str = None, ssh_host: str = None):
        super().__init__(username, password, ssh_host)
        self.username = username or os.getenv("DESI_USERNAME") or os.environ.get("USER")
        self.password = password or os.getenv("DESI_PASSWORD")
        self.ssh_host = ssh_host or "130.223.73.209"
        self.base_dir = f"/home/{self.username}/slurmray-server"
    
    def _connect(self):
        """Connect to the Desi server if not already connected"""
        if self.ssh_client and self.ssh_client.get_transport() and self.ssh_client.get_transport().is_active():
            return

        if not self.password:
            self.password = getpass("Enter Desi server password: ")

        try:
            self.ssh_client = paramiko.SSHClient()
            self.ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            self.ssh_client.connect(
                hostname=self.ssh_host,
                username=self.username,
                password=self.password
            )
        except Exception as e:
            console.print(f"[red]Failed to connect to Desi server: {e}[/red]")
            self.ssh_client = None
            raise
    
    def run_command(self, command):
        """Run a command on the Desi server via SSH"""
        self._connect()
        stdin, stdout, stderr = self.ssh_client.exec_command(command)
        exit_status = stdout.channel.recv_exit_status()
        return stdout.read().decode("utf-8"), stderr.read().decode("utf-8"), exit_status
    
    def get_jobs(self):
        """Retrieve jobs from Desi using Smart Lock and process detection"""
        try:
            self._connect()
            jobs = []
            seen_pids = set()
            
            # Check for running Python processes related to slurmray
            stdout, stderr, exit_status = self.run_command(
                f"ps aux | grep -E '(desi_wrapper|spython\.py)' | grep -v grep || echo ''"
            )
            if stdout.strip():
                for line in stdout.strip().split('\n'):
                    if not line.strip():
                        continue
                    parts = line.split()
                    if len(parts) >= 11:
                        pid = parts[1]
                        if pid in seen_pids:
                            continue
                        seen_pids.add(pid)
                        
                        # Try to get elapsed time
                        stdout_etime, stderr_etime, exit_status_etime = self.run_command(
                            f"ps -p {pid} -o etime --no-headers 2>/dev/null || echo 'N/A'"
                        )
                        elapsed_time = stdout_etime.strip() or "N/A"
                        
                        # Determine job name
                        cmd_line = " ".join(parts[10:]) if len(parts) > 10 else "slurmray"
                        if "desi_wrapper" in cmd_line:
                            job_name = "desi_wrapper.py"
                        elif "spython" in cmd_line:
                            job_name = "spython.py"
                        else:
                            job_name = "slurmray"
                        
                        jobs.append({
                            "id": f"desi-{pid}",
                            "name": job_name,
                            "state": "RUNNING",
                            "time": elapsed_time,
                            "nodes": "1",
                            "nodelist": "localhost",
                            "pid": pid
                        })
            
            # Also check if lock file exists and try to find process holding it
            # This helps detect jobs even if ps doesn't show them clearly
            stdout, stderr, exit_status = self.run_command(f"test -f {self.LOCK_FILE} && echo 'exists' || echo 'not_exists'")
            if "exists" in stdout.strip():
                # Try to find process using the lock file (multiple methods for compatibility)
                # Method 1: lsof (if available)
                stdout, stderr, exit_status = self.run_command(
                    f"lsof {self.LOCK_FILE} 2>/dev/null | tail -n +2 | awk '{{print $2}}' | head -1"
                )
                pid_from_lsof = stdout.strip()
                
                # Method 2: fuser (if available)
                if not pid_from_lsof:
                    stdout, stderr, exit_status = self.run_command(
                        f"fuser {self.LOCK_FILE} 2>/dev/null | awk '{{print $1}}' | head -1"
                    )
                    pid_from_lsof = stdout.strip()
                
                if pid_from_lsof and pid_from_lsof not in seen_pids:
                    # Verify the process is still running and related to slurmray
                    stdout, stderr, exit_status = self.run_command(
                        f"ps -p {pid_from_lsof} -o cmd --no-headers 2>/dev/null || echo ''"
                    )
                    if stdout.strip() and ("desi_wrapper" in stdout or "spython" in stdout or "slurmray" in stdout):
                        seen_pids.add(pid_from_lsof)
                        stdout_etime, stderr_etime, exit_status_etime = self.run_command(
                            f"ps -p {pid_from_lsof} -o etime --no-headers 2>/dev/null || echo 'N/A'"
                        )
                        elapsed_time = stdout_etime.strip() or "N/A"
                        
                        jobs.append({
                            "id": f"desi-{pid_from_lsof}",
                            "name": "desi_wrapper.py",
                            "state": "RUNNING",
                            "time": elapsed_time,
                            "nodes": "1",
                            "nodelist": "localhost",
                            "pid": pid_from_lsof
                        })
            
            return jobs
        except Exception as e:
            console.print(f"[red]Error retrieving jobs: {e}[/red]")
            return []
    
    def cancel_job(self, job_id):
        """Cancel a Desi job by killing the process"""
        try:
            # Extract PID from job_id (format: desi-<pid>)
            if job_id.startswith("desi-"):
                pid = job_id.split("-", 1)[1]
            else:
                pid = job_id
            
            # Kill the process
            stdout, stderr, exit_status = self.run_command(f"kill -TERM {pid} 2>&1")
            if exit_status == 0:
                console.print(f"[green]Job {job_id} (PID {pid}) cancelled successfully.[/green]")
                # Wait a bit and force kill if still running
                time.sleep(2)
                stdout, stderr, exit_status = self.run_command(f"kill -9 {pid} 2>&1")
            else:
                console.print(f"[red]Failed to cancel job {job_id}: {stderr or 'Process not found'}[/red]")
        except Exception as e:
            console.print(f"[red]Error cancelling job: {e}[/red]")
    
    def get_head_node(self, job_id):
        """Get head node for a Desi job (always localhost)"""
        # For Desi, the head node is always localhost since it's a single machine
        return "127.0.0.1"

def display_jobs_table(jobs, cluster_type="slurm"):
    """Display jobs in a table, adapting to cluster type"""
    if cluster_type == "slurm":
        table = Table(title=f"Slurm Jobs ({len(jobs)})")
        table.add_column("ID", style="cyan", no_wrap=True)
        table.add_column("Name", style="magenta")
        table.add_column("State", style="green")
        table.add_column("Time", style="yellow")
        table.add_column("Nodes", justify="right")
        table.add_column("NodeList", style="blue")

        for i, job in enumerate(jobs):
            # Add position in queue for pending jobs
            state_display = job["state"]
            if job["state"] == "PENDING":
                state_display += f" (#{i+1})"
                
            table.add_row(
                job["id"],
                job["name"],
                state_display,
                job["time"],
                job["nodes"],
                job["nodelist"]
            )
    else:  # desi
        table = Table(title=f"Desi Jobs ({len(jobs)})")
        table.add_column("ID", style="cyan", no_wrap=True)
        table.add_column("Name", style="magenta")
        table.add_column("State", style="green")
        table.add_column("Time", style="yellow")
        table.add_column("PID", style="blue", no_wrap=True)

        for job in jobs:
            table.add_row(
                job["id"],
                job.get("name", "N/A"),
                job["state"],
                job.get("time", "N/A"),
                job.get("pid", "N/A")
            )
    return table

def main():
    parser = argparse.ArgumentParser(
        description="SlurmRay CLI - Interactive job manager for Slurm clusters and Desi server",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  slurmray              # Show help
  slurmray curnagl      # Connect to Curnagl (Slurm cluster)
  slurmray desi         # Connect to Desi server (ISIPOL09)
        """
    )
    parser.add_argument(
        "cluster",
        nargs="?",
        choices=["curnagl", "desi"],
        help="Cluster to connect to (curnagl for Slurm, desi for Desi server)"
    )
    parser.add_argument(
        "--username",
        help="Username for SSH connection (overrides environment variables)"
    )
    parser.add_argument(
        "--password",
        help="Password for SSH connection (overrides environment variables, not recommended)"
    )
    parser.add_argument(
        "--host",
        help="SSH hostname (overrides default: curnagl.dcsr.unil.ch for Curnagl, 130.223.73.209 for Desi)"
    )
    
    args = parser.parse_args()
    
    # If no cluster specified, show help
    if not args.cluster:
        parser.print_help()
        return
    
    # Create appropriate manager
    if args.cluster == "curnagl":
        manager = SlurmManager(
            username=args.username,
            password=args.password,
            ssh_host=args.host
        )
        cluster_name = "Curnagl (Slurm)"
        cluster_type = "slurm"
    elif args.cluster == "desi":
        manager = DesiManager(
            username=args.username,
            password=args.password,
            ssh_host=args.host
        )
        cluster_name = "Desi (ISIPOL09)"
        cluster_type = "desi"
    else:
        console.print("[red]Invalid cluster specified[/red]")
        return
    
    # Main interactive loop
    while True:
        try:
            console.clear()
            console.rule(f"[bold blue]SlurmRay Manager - {cluster_name}[/bold blue]")
            
            jobs = manager.get_jobs()
            console.print(display_jobs_table(jobs, cluster_type))
            
            console.print("\n[bold]Options:[/bold]")
            console.print("[r] Refresh")
            console.print("[c] Cancel Job")
            console.print("[d] Open Dashboard")
            console.print("[q] Quit")
            
            choice = Prompt.ask("\nSelect an option", choices=["r", "c", "d", "q"], default="r")
            
            if choice == "q":
                console.print("Bye!")
                break
            elif choice == "r":
                continue
            elif choice == "c":
                job_id = Prompt.ask("Enter Job ID to cancel")
                if Confirm.ask(f"Are you sure you want to cancel job {job_id}?"):
                    manager.cancel_job(job_id)
                    time.sleep(1.5) # Let user see result
            elif choice == "d":
                job_id = Prompt.ask("Enter Job ID to connect to")
                manager.open_dashboard(job_id)
                # Return to loop after tunnel close
        except (KeyboardInterrupt, EOFError):
            console.print("\nBye!")
            break

if __name__ == "__main__":
    main()
