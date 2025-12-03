"""
Script utilitaire pour configurer le fichier .env avec les identifiants Desi.
Ce script crée ou met à jour le fichier .env avec les variables nécessaires.
"""
import os

def setup_desi_env():
    """Configure le fichier .env avec les identifiants Desi"""
    env_file = ".env"
    
    # Identifiants Desi
    desi_username = "henri"
    desi_password = "9wE1Ry^6JUK*1zxX5Aa3"
    
    # Lire le .env existant s'il existe
    env_vars = {}
    if os.path.exists(env_file):
        print(f"📖 Reading existing {env_file}...")
        with open(env_file, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    env_vars[key.strip()] = value.strip()
    
    # Mettre à jour avec les identifiants Desi
    env_vars['DESI_USERNAME'] = desi_username
    env_vars['DESI_PASSWORD'] = desi_password
    
    # Écrire le .env
    print(f"✍️  Writing {env_file}...")
    with open(env_file, 'w') as f:
        f.write("# Desi credentials\n")
        f.write(f"DESI_USERNAME={desi_username}\n")
        f.write(f"DESI_PASSWORD={desi_password}\n")
        f.write("\n")
        
        # Écrire les autres variables si elles existent
        other_vars = {k: v for k, v in env_vars.items() 
                     if k not in ['DESI_USERNAME', 'DESI_PASSWORD']}
        if other_vars:
            f.write("# Other environment variables\n")
            for key, value in other_vars.items():
                f.write(f"{key}={value}\n")
    
    print(f"✅ {env_file} configured successfully!")
    print(f"   DESI_USERNAME={desi_username}")
    print(f"   DESI_PASSWORD={'*' * len(desi_password)}")
    print(f"\n⚠️  Note: {env_file} is in .gitignore and won't be committed to git.")


if __name__ == "__main__":
    setup_desi_env()

