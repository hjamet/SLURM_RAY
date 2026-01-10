
import os
import time
import shutil
import logging
from datetime import datetime

# Configuration
BASE_DIR = "/home/henri/slurmray-server"
LOG_FILE = "/home/henri/cluster_management/cleanup_projects.log"
DEFAULT_RETENTION_DAYS = 7  # Fallback if metadata is missing (optional, safe to verify first)

# Setup logging
logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

def cleanup_projects():
    logging.info("Starting project cleanup...")
    
    if not os.path.exists(BASE_DIR):
        logging.warning(f"Base directory {BASE_DIR} does not exist.")
        return

    now = time.time()
    deleted_count = 0
    
    # Iterate over all project directories
    for project_name in os.listdir(BASE_DIR):
        if project_name.startswith('.'):
            continue
            
        project_path = os.path.join(BASE_DIR, project_name)
        if not os.path.isdir(project_path):
            continue

        # Look for retention metadata
        timestamp_file = os.path.join(project_path, ".retention_timestamp")
        days_file = os.path.join(project_path, ".retention_days")
        
        try:
            if os.path.exists(timestamp_file) and os.path.exists(days_file):
                with open(timestamp_file, 'r') as f:
                    creation_time = int(f.read().strip())
                with open(days_file, 'r') as f:
                    retention_days = int(f.read().strip())
                
                # Check expiration
                expiration_time = creation_time + (retention_days * 86400)
                
                if now > expiration_time:
                    age_days = (now - creation_time) / 86400
                    logging.info(f"Deleting expired project '{project_name}' (Age: {age_days:.1f} days, Limit: {retention_days} days)")
                    try:
                        shutil.rmtree(project_path)
                        deleted_count += 1
                        logging.info(f"✅ Successfully deleted {project_path}")
                    except Exception as e:
                        logging.error(f"❌ Failed to delete {project_path}: {e}")
                else:
                    # Project is still valid
                    # logging.debug(f"Project '{project_name}' is valid. Expires in {(expiration_time - now)/86400:.1f} days.")
                    pass
            else:
                # No metadata found - skip or warn?
                # For safety, we skip. We only delete what we explicitly know is expired.
                # logging.warning(f"Skipping '{project_name}': Missing retention metadata.")
                pass
                
        except Exception as e:
            logging.error(f"Error processing {project_name}: {e}")

    logging.info(f"Cleanup finished. Deleted {deleted_count} projects.")

if __name__ == "__main__":
    cleanup_projects()
