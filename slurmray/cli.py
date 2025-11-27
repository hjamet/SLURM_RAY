import os
import time
import subprocess
import signal
import sys
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
    from slurmray.RayLauncher import SSHTunnel
except ImportError:
    # Fallback if running from root without package installed
    sys.path.append(os.getcwd())
    from slurmray.RayLauncher import SSHTunnel

load_dotenv()

console = Console()

class SlurmManager:
    def __init__(self):
        self.username = os.getenv("CURNAGL_USERNAME") or os.environ.get("USER")
        self.password = os.getenv("CURNAGL_PASSWORD")
        self.ssh_host = "curnagl.dcsr.unil.ch"
        self.active_tunnel = None

    def get_jobs(self):
        """Retrieve jobs from squeue"""
        try:
            # Run squeue command
            result = subprocess.run(
                ["squeue", "-u", self.username, "-o", "%.18i %.9P %.30j %.8u %.8T %.10M %.6D %R"],
                capture_output=True,
                text=True
            )
            
            if result.returncode != 0:
                return []

            lines = result.stdout.strip().split("\n")
            if len(lines) < 2:
                return []

            jobs = []
            for line in lines[1:]:
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
        except FileNotFoundError:
            # Mock data for local testing if squeue not found
            return []
        except Exception as e:
            console.print(f"[red]Error retrieving jobs: {e}[/red]")
            return []

    def cancel_job(self, job_id):
        """Cancel a SLURM job"""
        try:
            subprocess.run(["scancel", job_id], check=True)
            console.print(f"[green]Job {job_id} cancelled successfully.[/green]")
        except subprocess.CalledProcessError:
            console.print(f"[red]Failed to cancel job {job_id}.[/red]")
        except FileNotFoundError:
            console.print("[red]scancel command not found.[/red]")

    def get_head_node(self, job_id):
        """Get head node for a job"""
        try:
            # Get job info
            result = subprocess.run(
                ["scontrol", "show", "job", job_id],
                capture_output=True,
                text=True
            )
            output = result.stdout
            
            # Simple parsing for NodeList (simplified version of RayLauncher logic)
            import re
            match = re.search(r"NodeList=([^\s]+)", output)
            if match:
                nodelist = match.group(1)
                # Convert nodelist to hostname (simplified, assuming first node is head)
                # Need scontrol show hostnames for robust parsing
                res_host = subprocess.run(
                    ["scontrol", "show", "hostnames", nodelist],
                    capture_output=True,
                    text=True
                )
                hosts = res_host.stdout.strip().split("\n")
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
            self.active_tunnel = SSHTunnel(
                ssh_host=self.ssh_host,
                ssh_username=self.username,
                ssh_password=self.password,
                remote_host=head_node,
                local_port=8888,
                remote_port=8888
            )
            
            with self.active_tunnel:
                console.print("[green]Dashboard available at: http://localhost:8888[/green]")
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

