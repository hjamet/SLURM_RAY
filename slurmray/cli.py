import os
import time
import subprocess
import signal
import sys
import webbrowser
import argparse
import threading
import json
from abc import ABC, abstractmethod
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.prompt import Prompt, Confirm
from rich.live import Live
from rich.layout import Layout
from dotenv import load_dotenv
import paramiko
from getpass import getpass
import inquirer

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
    QUEUE_FILE = "/tmp/slurmray_desi.queue"
    
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
    
    def _read_queue(self):
        """Read queue file from remote server (read-only, no lock needed)"""
        try:
            stdout, stderr, exit_status = self.run_command(
                f"test -f {self.QUEUE_FILE} && cat {self.QUEUE_FILE} || echo '[]'"
            )
            if exit_status != 0:
                return []
            import json
            queue_data = json.loads(stdout.strip() or "[]")
            return queue_data if isinstance(queue_data, list) else []
        except (json.JSONDecodeError, ValueError, Exception):
            return []
    
    def _write_queue(self, queue_data):
        """Write queue file to remote server with lock management"""
        import json
        import tempfile
        import base64
        
        # Create temporary file with queue data
        queue_json = json.dumps(queue_data, indent=2)
        queue_b64 = base64.b64encode(queue_json.encode('utf-8')).decode('utf-8')
        
        # Write using Python on remote with lock
        python_script = f"""
import json
import fcntl
import base64
import sys

QUEUE_FILE = "{self.QUEUE_FILE}"
queue_b64 = "{queue_b64}"

max_retries = 10
retry_delay = 0.1
success = False

for attempt in range(max_retries):
    try:
        queue_fd = open(QUEUE_FILE, 'w')
        try:
            fcntl.lockf(queue_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            queue_json = base64.b64decode(queue_b64).decode('utf-8')
            queue_data = json.loads(queue_json)
            json.dump(queue_data, queue_fd, indent=2)
            queue_fd.flush()
            import os
            os.fsync(queue_fd.fileno())
            fcntl.lockf(queue_fd, fcntl.LOCK_UN)
            queue_fd.close()
            success = True
            break
        except IOError:
            queue_fd.close()
            if attempt < max_retries - 1:
                import time
                time.sleep(retry_delay)
                continue
    except IOError:
        if attempt < max_retries - 1:
            import time
            time.sleep(retry_delay)
            continue

sys.exit(0 if success else 1)
"""
        # Write script to temp file and execute
        stdout, stderr, exit_status = self.run_command(
            f"python3 -c {repr(python_script)}"
        )
        return exit_status == 0
    
    def _clean_dead_processes_from_queue(self):
        """Remove entries for processes that no longer exist"""
        queue = self._read_queue()
        if not queue:
            return
        
        cleaned_queue = []
        pids_to_check = [entry.get("pid") for entry in queue if entry.get("pid")]
        
        if not pids_to_check:
            return
        
        # Check all PIDs at once
        pids_str = " ".join(pids_to_check)
        stdout, stderr, exit_status = self.run_command(
            f"for pid in {pids_str}; do ps -p $pid >/dev/null 2>&1 && echo $pid; done"
        )
        alive_pids = set(stdout.strip().split())
        
        # Keep only entries with alive processes
        cleaned_queue = [entry for entry in queue if entry.get("pid") in alive_pids]
        
        # If queue changed, write it back
        if len(cleaned_queue) != len(queue):
            self._write_queue(cleaned_queue)
    
    def _get_function_name_from_project(self, project_dir):
        """Try to read function name from func_name.txt in project directory"""
        try:
            # Try direct path first
            func_name_path = f"{project_dir}/func_name.txt"
            stdout, stderr, exit_status = self.run_command(
                f"test -f {func_name_path} && cat {func_name_path} || echo ''"
            )
            func_name = stdout.strip()
            if func_name:
                return func_name
            
            # If not found, try to find func_name.txt in parent directories (up to 2 levels)
            # Sometimes the process might be running from a subdirectory
            for parent_level in [1, 2]:
                parent_dir = "/".join(project_dir.split("/")[:-parent_level]) if parent_level > 0 else project_dir
                if not parent_dir or parent_dir == "/":
                    break
                func_name_path = f"{parent_dir}/func_name.txt"
                stdout, stderr, exit_status = self.run_command(
                    f"test -f {func_name_path} && cat {func_name_path} || echo ''"
                )
                func_name = stdout.strip()
                if func_name:
                    return func_name
            
            return None
        except Exception:
            return None
    
    def _get_project_dir_from_pid(self, pid):
        """Try to get project directory from process working directory"""
        try:
            # Try multiple methods to get working directory
            # Method 1: readlink /proc/{pid}/cwd (Linux)
            stdout, stderr, exit_status = self.run_command(
                f"readlink /proc/{pid}/cwd 2>/dev/null || echo ''"
            )
            cwd = stdout.strip()
            
            # Method 2: pwdx (if available)
            if not cwd:
                stdout, stderr, exit_status = self.run_command(
                    f"pwdx {pid} 2>/dev/null | awk '{{print $2}}' || echo ''"
                )
                cwd = stdout.strip()
            
            # Method 3: ps -o cwd
            if not cwd:
                stdout, stderr, exit_status = self.run_command(
                    f"ps -p {pid} -o cwd --no-headers 2>/dev/null || echo ''"
                )
                cwd = stdout.strip()
            
            if cwd and "slurmray-server" in cwd:
                # Extract project directory (should be in /home/{user}/slurmray-server/{project_name})
                return cwd
            return None
        except Exception:
            return None
    
    def get_jobs(self):
        """Retrieve jobs from Desi using queue file"""
        try:
            self._connect()
            jobs = []
            
            # Clean dead processes from queue first
            self._clean_dead_processes_from_queue()
            
            # Read queue file
            queue = self._read_queue()
            if not queue:
                return []
            
            # Separate running and waiting jobs, sort waiting by timestamp
            running_jobs = []
            waiting_jobs = []
            
            for entry in queue:
                pid = entry.get("pid")
                if not pid:
                    continue
                
                # Verify process exists
                stdout, stderr, exit_status = self.run_command(
                    f"ps -p {pid} >/dev/null 2>&1 && echo 'alive' || echo 'dead'"
                )
                if "dead" in stdout.strip():
                    # Process is dead, skip (will be cleaned next time)
                    continue
                
                # Get elapsed time from ps (more accurate than calculating from timestamp)
                stdout_etime, stderr_etime, exit_status_etime = self.run_command(
                    f"ps -p {pid} -o etime --no-headers 2>/dev/null || echo 'N/A'"
                )
                elapsed_time = stdout_etime.strip() or "N/A"
                
                # Extract job information
                func_name = entry.get("func_name")
                user = entry.get("user", "unknown")
                status = entry.get("status", "unknown")
                
                # If func_name is missing or "Unknown function", try to read it from project_dir
                if not func_name or func_name == "Unknown function":
                    project_dir = entry.get("project_dir")
                    if project_dir:
                        func_name = self._get_function_name_from_project(project_dir)
                    if not func_name or func_name == "Unknown function":
                        # Fail-fast: if we can't get the function name, it's an error
                        console.print(f"[yellow]Warning: Job {pid} has no function name in queue and func_name.txt not found[/yellow]")
                        func_name = "ERROR: func_name missing"
                
                job = {
                    "id": f"desi-{pid}",
                    "name": func_name,
                    "user": user,
                    "state": "RUNNING" if status == "running" else "WAITING",
                    "time": elapsed_time,
                    "nodes": "1",
                    "nodelist": "localhost",
                    "pid": pid,
                    "timestamp": entry.get("timestamp", 0),
                    "queue_position": None
                }
                
                if status == "running":
                    running_jobs.append(job)
                elif status == "waiting":
                    waiting_jobs.append(job)
            
            # Sort waiting jobs by timestamp (oldest first)
            waiting_jobs.sort(key=lambda x: x.get("timestamp", 0))
            
            # Calculate queue positions for waiting jobs
            for idx, job in enumerate(waiting_jobs):
                job["queue_position"] = idx + 1
            
            # Combine: running jobs first, then waiting jobs
            jobs = running_jobs + waiting_jobs
            
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
        table.add_column("User", style="blue", no_wrap=True)
        table.add_column("State", style="green")
        table.add_column("Queue", style="yellow", justify="center")
        table.add_column("Time", style="yellow")
        table.add_column("PID", style="blue", no_wrap=True)

        for job in jobs:
            # Format state display
            state_display = job["state"]
            if job["state"] == "WAITING":
                queue_pos = job.get("queue_position")
                if queue_pos:
                    state_display = f"WAITING (#{queue_pos})"
            
            # Format queue column
            queue_display = "-"
            if job["state"] == "WAITING":
                queue_pos = job.get("queue_position")
                if queue_pos:
                    queue_display = f"#{queue_pos}"
            elif job["state"] == "RUNNING":
                queue_display = "RUNNING"
            
            table.add_row(
                job["id"],
                job.get("name", "N/A"),
                job.get("user", "N/A"),
                state_display,
                queue_display,
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
    
    # Main interactive loop with auto-refresh
    refresh_interval = 10  # seconds
    jobs_data = {"jobs": [], "last_refresh": 0}
    should_exit = threading.Event()
    user_wants_menu = threading.Event()
    
    def auto_refresh_worker():
        """Background thread to auto-refresh jobs every refresh_interval seconds"""
        while not should_exit.is_set():
            time.sleep(refresh_interval)
            if not should_exit.is_set():
                jobs_data["jobs"] = manager.get_jobs()
                jobs_data["last_refresh"] = time.time()
    
    # Start auto-refresh thread
    refresh_thread = threading.Thread(target=auto_refresh_worker, daemon=True)
    refresh_thread.start()
    
    # Initial load
    jobs_data["jobs"] = manager.get_jobs()
    jobs_data["last_refresh"] = time.time()
    
    def render_display():
        """Render the current display"""
        jobs = jobs_data["jobs"]
        last_refresh_time = time.strftime('%H:%M:%S', time.localtime(jobs_data["last_refresh"]))
        
        # Create layout
        layout = Layout()
        layout.split_column(
            Layout(name="header", size=3),
            Layout(name="table"),
            Layout(name="footer", size=4)
        )
        
        layout["header"].update(Panel(f"[bold blue]SlurmRay Manager - {cluster_name}[/bold blue]", style="bold"))
        layout["table"].update(display_jobs_table(jobs, cluster_type))
        
        footer_text = f"[yellow]Auto-refreshing every {refresh_interval}s... Last refresh: {last_refresh_time}[/yellow]\n"
        footer_text += "[dim]Press Enter to open menu (↑↓ to navigate, ←→ to select)[/dim]"
        layout["footer"].update(Panel(footer_text))
        
        return layout
    
    # Main loop: alternate between Live display and menu
    while not should_exit.is_set():
        try:
            # Phase 1: Live auto-updating display
            with Live(render_display(), refresh_per_second=2, screen=True) as live:
                import sys
                import select
                import tty
                import termios
                
                # Set terminal to cbreak mode (less disruptive than raw mode)
                old_settings = termios.tcgetattr(sys.stdin)
                try:
                    tty.setcbreak(sys.stdin.fileno())
                except Exception:
                    # If terminal manipulation fails, use simple mode
                    pass
                
                try:
                    while not should_exit.is_set():
                        # Update display with latest data (reads from jobs_data which is updated by thread)
                        live.update(render_display())
                        
                        # Check if user pressed Enter (non-blocking)
                        try:
                            if select.select([sys.stdin], [], [], 0.1)[0]:
                                char = sys.stdin.read(1)
                                if char == '\n' or char == '\r':
                                    # Exit Live to show menu
                                    break
                                elif char == '\x03':  # Ctrl+C
                                    should_exit.set()
                                    break
                        except (OSError, ValueError):
                            # Terminal might not support select, fall back to simple wait
                            time.sleep(0.5)
                            continue
                        
                        # Small sleep to avoid busy waiting
                        time.sleep(0.1)
                finally:
                    # Restore terminal settings
                    try:
                        termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_settings)
                    except Exception:
                        pass
            
            if should_exit.is_set():
                break
            
            # Phase 2: Show menu with inquirer (outside Live context)
            # Refresh jobs before showing menu
            jobs_data["jobs"] = manager.get_jobs()
            jobs_data["last_refresh"] = time.time()
            
            console.clear()
            console.rule(f"[bold blue]SlurmRay Manager - {cluster_name}[/bold blue]")
            
            # Use latest jobs data
            jobs = jobs_data["jobs"]
            console.print(display_jobs_table(jobs, cluster_type))
            
            last_refresh_time = time.strftime('%H:%M:%S', time.localtime(jobs_data["last_refresh"]))
            console.print(f"\n[yellow]Auto-refreshing every {refresh_interval}s... Last refresh: {last_refresh_time}[/yellow]")
            console.print("[dim]Navigation: Use arrow keys (↑↓) to navigate, Enter to select[/dim]")
            
            # Show menu with inquirer for arrow key navigation
            questions = [
                inquirer.List(
                    'action',
                    message="Select an option",
                    choices=[
                        ('Refresh Now', 'refresh'),
                        ('Cancel Job', 'cancel'),
                        ('Open Dashboard', 'dashboard'),
                        ('Quit', 'quit')
                    ],
                    default='refresh'
                )
            ]
            
            answers = inquirer.prompt(questions)
            if not answers:
                # User cancelled (Ctrl+C)
                break
            
            user_input = answers['action']
            
            # Handle user input
            if user_input == 'quit':
                should_exit.set()
                console.print("Bye!")
                break
            elif user_input == 'refresh':
                jobs_data["jobs"] = manager.get_jobs()
                jobs_data["last_refresh"] = time.time()
                # Return to Live display (continue loop)
                continue
            elif user_input == 'cancel':
                # Refresh jobs before showing cancel menu
                jobs_data["jobs"] = manager.get_jobs()
                jobs_data["last_refresh"] = time.time()
                jobs = jobs_data["jobs"]
                if jobs:
                    job_choices = [f"{job['id']} - {job.get('name', 'N/A')}" for job in jobs]
                    cancel_questions = [
                        inquirer.List(
                            'job_id',
                            message="Select job to cancel",
                            choices=job_choices
                        )
                    ]
                    cancel_answers = inquirer.prompt(cancel_questions)
                    if cancel_answers:
                        selected_job = cancel_answers['job_id']
                        job_id = selected_job.split(' - ')[0]
                        if Confirm.ask(f"Are you sure you want to cancel job {job_id}?"):
                            manager.cancel_job(job_id)
                            console.print("[green]Job cancelled. Refreshing...[/green]")
                            time.sleep(1.5)
                            jobs_data["jobs"] = manager.get_jobs()
                            jobs_data["last_refresh"] = time.time()
                else:
                    console.print("[yellow]No jobs to cancel[/yellow]")
                    time.sleep(1)
                # Return to Live display (continue loop)
                continue
            elif user_input == 'dashboard':
                # Refresh jobs before showing dashboard menu
                jobs_data["jobs"] = manager.get_jobs()
                jobs_data["last_refresh"] = time.time()
                jobs = jobs_data["jobs"]
                if jobs:
                    job_choices = [f"{job['id']} - {job.get('name', 'N/A')}" for job in jobs]
                    dashboard_questions = [
                        inquirer.List(
                            'job_id',
                            message="Select job to connect to",
                            choices=job_choices
                        )
                    ]
                    dashboard_answers = inquirer.prompt(dashboard_questions)
                    if dashboard_answers:
                        selected_job = dashboard_answers['job_id']
                        job_id = selected_job.split(' - ')[0]
                        manager.open_dashboard(job_id)
                        # Refresh after tunnel close
                        jobs_data["jobs"] = manager.get_jobs()
                        jobs_data["last_refresh"] = time.time()
                else:
                    console.print("[yellow]No jobs available[/yellow]")
                    time.sleep(1)
                # Return to Live display (continue loop)
                continue
                    
        except (KeyboardInterrupt, EOFError):
            should_exit.set()
            console.print("\nBye!")
            break
        except Exception as e:
            # Fallback if terminal manipulation fails
            console.print(f"[yellow]Warning: Auto-refresh unavailable ({e}). Using simple mode...[/yellow]")
            should_exit.set()
            # Simple fallback without auto-refresh
            while True:
                console.clear()
                console.rule(f"[bold blue]SlurmRay Manager - {cluster_name}[/bold blue]")
                jobs = manager.get_jobs()
                console.print(display_jobs_table(jobs, cluster_type))
                
                questions = [
                    inquirer.List(
                        'action',
                        message="Select an option",
                        choices=[
                            ('Refresh', 'refresh'),
                            ('Cancel Job', 'cancel'),
                            ('Open Dashboard', 'dashboard'),
                            ('Quit', 'quit')
                        ],
                        default='refresh'
                    )
                ]
                
                answers = inquirer.prompt(questions)
                if not answers or answers['action'] == 'quit':
                    break
                elif answers['action'] == 'refresh':
                    continue
                elif answers['action'] == 'cancel':
                    jobs = manager.get_jobs()
                    if jobs:
                        job_choices = [f"{job['id']} - {job.get('name', 'N/A')}" for job in jobs]
                        cancel_questions = [
                            inquirer.List(
                                'job_id',
                                message="Select job to cancel",
                                choices=job_choices
                            )
                        ]
                        cancel_answers = inquirer.prompt(cancel_questions)
                        if cancel_answers:
                            selected_job = cancel_answers['job_id']
                            job_id = selected_job.split(' - ')[0]
                            if Confirm.ask(f"Are you sure you want to cancel job {job_id}?"):
                                manager.cancel_job(job_id)
                                time.sleep(1.5)
                elif answers['action'] == 'dashboard':
                    jobs = manager.get_jobs()
                    if jobs:
                        job_choices = [f"{job['id']} - {job.get('name', 'N/A')}" for job in jobs]
                        dashboard_questions = [
                            inquirer.List(
                                'job_id',
                                message="Select job to connect to",
                                choices=job_choices
                            )
                        ]
                        dashboard_answers = inquirer.prompt(dashboard_questions)
                        if dashboard_answers:
                            selected_job = dashboard_answers['job_id']
                            job_id = selected_job.split(' - ')[0]
                            manager.open_dashboard(job_id)
            break

if __name__ == "__main__":
    main()
