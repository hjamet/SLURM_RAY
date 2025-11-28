import os
import time
import subprocess
import signal
import sys
import webbrowser
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

class SlurmManager:
    def __init__(self):
        self.username = os.getenv("CURNAGL_USERNAME") or os.environ.get("USER")
        self.password = os.getenv("CURNAGL_PASSWORD")
        self.ssh_host = "curnagl.dcsr.unil.ch"
        self.active_tunnel = None
        self.ssh_client = None
    
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

    def open_dashboard(self, job_id):
        """Open Ray dashboard for a job"""
        # 1. Find the head node
        head_node = self.get_head_node(job_id)
        if not head_node:
            console.print(f"[red]Could not determine head node for job {job_id}. Is it running?[/red]")
            return

        console.print(f"[blue]Head node identified: {head_node}[/blue]")
        
        # 2. Ask for password if needed
        if not self.password:
            self.password = getpass("Enter cluster password: ")

        # 3. Setup Tunnel
        try:
            console.print("[yellow]Setting up SSH tunnel... (Press Ctrl+C to stop)[/yellow]")
            # Use local_port=0 to let OS pick a free port, remote_port=8265 for standard Ray Dashboard
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
                
                # Open browser
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

def display_jobs_table(jobs):
    table = Table(title=f"SLURM Jobs ({len(jobs)})")
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
    return table

def main():
    manager = SlurmManager()
    
    while True:
        try:
            console.clear()
            console.rule("[bold blue]SLURM Ray Manager[/bold blue]")
            
            jobs = manager.get_jobs()
            console.print(display_jobs_table(jobs))
            
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
