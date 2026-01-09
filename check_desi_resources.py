
import paramiko
import os

hostname = "130.223.73.209"
username = "henri"
password = "9wE1Ry^6JUK*1zxX5Aa3"

print(f"Connecting to {username}@{hostname}...")
client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

try:
    client.connect(hostname=hostname, username=username, password=password)
    
    print("\n--- CPU INFO ---")
    stdin, stdout, stderr = client.exec_command("nproc")
    print(f"Logical CPUs: {stdout.read().decode().strip()}")
    
    stdin, stdout, stderr = client.exec_command("lscpu | grep 'Model name'")
    print(f"CPU Model: {stdout.read().decode().strip()}")

    print("\n--- RAM INFO ---")
    stdin, stdout, stderr = client.exec_command("free -h")
    print(stdout.read().decode().strip())

    print("\n--- GPU INFO ---")
    stdin, stdout, stderr = client.exec_command("nvidia-smi --query-gpu=name,memory.total --format=csv")
    print(stdout.read().decode().strip())
    
    print("\n--- GPU STATUS (nvidia-smi) ---")
    stdin, stdout, stderr = client.exec_command("nvidia-smi")
    print(stdout.read().decode().strip())

finally:
    client.close()
