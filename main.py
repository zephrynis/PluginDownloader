import os
import time
import json
import yaml
import requests
import re
import logging
import hashlib

# Configuration
CONFIG_FILE = os.getenv("CONFIG_FILE", "/data/config.yaml")
STATE_FILE = os.getenv("STATE_FILE", "/data/state.json")
PLUGINS_DIR = os.getenv("PLUGINS_DIR", "/data/plugins")

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger()

def load_config():
    if not os.path.exists(CONFIG_FILE):
        logger.error(f"Config file not found at {CONFIG_FILE}")
        return None
    with open(CONFIG_FILE, 'r') as f:
        return yaml.safe_load(f)

def load_state():
    if not os.path.exists(STATE_FILE):
        return {}
    with open(STATE_FILE, 'r') as f:
        return json.load(f)

def save_state(state):
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, indent=2)

def download_file(url, dest_path):
    response = requests.get(url, stream=True)
    response.raise_for_status()
    with open(dest_path, 'wb') as f:
        for chunk in response.iter_content(chunk_size=8192):
            f.write(chunk)
    return dest_path

def get_github_latest(repo, asset_regex=None):
    try:
        url = f"https://api.github.com/repos/{repo}/releases/latest"
        resp = requests.get(url)
        resp.raise_for_status()
        data = resp.json()
        
        assets = data.get('assets', [])
        target_asset = None
        
        if not assets:
            return None, None

        if asset_regex:
            pattern = re.compile(asset_regex)
            for asset in assets:
                if pattern.match(asset['name']):
                    target_asset = asset
                    break
        else:
            # Default to first jar if not specified, or just the first asset
            for asset in assets:
                if asset['name'].endswith('.jar'):
                    target_asset = asset
                    break
            if not target_asset:
                target_asset = assets[0]

        if target_asset:
            return target_asset['name'], target_asset['browser_download_url']
    except Exception as e:
        logger.error(f"Error checking GitHub {repo}: {e}")
    return None, None

def get_modrinth_latest(project_id, loader=None, game_version=None):
    try:
        url = f"https://api.modrinth.com/v2/project/{project_id}/version"
        params = {}
        if loader:
            params['loaders'] = f'["{loader}"]'
        if game_version:
            params['game_versions'] = f'["{game_version}"]'
            
        resp = requests.get(url, params=params)
        resp.raise_for_status()
        versions = resp.json()
        
        if not versions:
            return None, None
            
        latest = versions[0]
        files = latest.get('files', [])
        if not files:
            return None, None
            
        primary_file = next((f for f in files if f.get('primary')), files[0])
        
        return primary_file['filename'], primary_file['url']
    except Exception as e:
        logger.error(f"Error checking Modrinth {project_id}: {e}")
    return None, None

def get_spiget_latest(resource_id, plugin_name=None):
    try:
        # Get latest version info
        url = f"https://api.spiget.org/v2/resources/{resource_id}/versions/latest"
        resp = requests.get(url)
        resp.raise_for_status()
        version_data = resp.json()
        
        # Spiget download URL (proxies to SpigotMC)
        # Note: This might not work for external downloads or paid resources
        download_url = f"https://api.spiget.org/v2/resources/{resource_id}/download"
        
        # We need a filename. Spiget doesn't always give it directly in the version endpoint easily
        # without downloading. We'll construct one or try to fetch headers.
        # Let's try a HEAD request to download_url to get filename
        
        head_resp = requests.head(download_url, allow_redirects=True)
        
        base_name = plugin_name if plugin_name else resource_id
        filename = f"{base_name}-{version_data['name']}.jar" # Fallback
        
        if 'content-disposition' in head_resp.headers:
            cd = head_resp.headers['content-disposition']
            # extract filename="name.jar"
            fname = re.findall('filename="(.+)"', cd)
            if fname:
                filename = fname[0]
                
        return filename, download_url
    except Exception as e:
        logger.error(f"Error checking Spiget {resource_id}: {e}")
    return None, None

def process_plugin(plugin, state):
    name = plugin.get('name')
    source = plugin.get('source')
    
    logger.info(f"Checking {name}...")
    
    filename = None
    download_url = None
    
    if source == 'github':
        filename, download_url = get_github_latest(plugin['repo'], plugin.get('asset_regex'))
    elif source == 'modrinth':
        filename, download_url = get_modrinth_latest(plugin['id'], plugin.get('loader'), plugin.get('game_version'))
    elif source == 'spigot':
        filename, download_url = get_spiget_latest(plugin['id'], name)
    
    if not filename or not download_url:
        logger.warning(f"Could not resolve update for {name}")
        return

    # Check against state
    current_state = state.get(name, {})
    last_filename = current_state.get('filename')
    
    # Check if file exists on disk
    if last_filename:
        last_filepath = os.path.join(PLUGINS_DIR, last_filename)
        if os.path.exists(last_filepath) and last_filename == filename:
             # Just a simple filename check. 
             # Ideally we would check hashes, but filenames usually change with version.
             logger.info(f"{name} is up to date.")
             return

    logger.info(f"Update found for {name}: {filename}. Downloading...")
    
    try:
        dest_path = os.path.join(PLUGINS_DIR, filename)
        download_file(download_url, dest_path)
        logger.info(f"Downloaded {filename}")
        
        # Delete old file
        if last_filename and last_filename != filename:
            old_path = os.path.join(PLUGINS_DIR, last_filename)
            if os.path.exists(old_path):
                os.remove(old_path)
                logger.info(f"Deleted old version: {last_filename}")
        
        # Update state
        state[name] = {
            'filename': filename,
            'source': source,
            'updated_at': time.time()
        }
        save_state(state)
        
    except Exception as e:
        logger.error(f"Failed to update {name}: {e}")

def main():
    if not os.path.exists(PLUGINS_DIR):
        os.makedirs(PLUGINS_DIR)
        
    logger.info("Starting Plugin Updater...")
    
    last_config_mtime = 0
    last_check_time = 0
    config = None
    
    while True:
        # Check for config file changes
        try:
            current_mtime = 0
            if os.path.exists(CONFIG_FILE):
                current_mtime = os.path.getmtime(CONFIG_FILE)
            
            if current_mtime != last_config_mtime:
                logger.info("Config file changed or initial load. Reloading...")
                new_config = load_config()
                if new_config:
                    config = new_config
                    last_config_mtime = current_mtime
                    # Force an immediate check on config change
                    last_check_time = 0
                else:
                    logger.warning("Config file found but failed to load or is empty.")
            
        except Exception as e:
            logger.error(f"Error checking config file: {e}")

        if config:
            interval = config.get('check_interval', 3600)
            
            # Check if it's time to run updates
            if time.time() - last_check_time >= interval:
                state = load_state()
                
                for plugin in config.get('plugins', []):
                    try:
                        process_plugin(plugin, state)
                    except Exception as e:
                        logger.error(f"Error processing {plugin.get('name')}: {e}")
                
                last_check_time = time.time()
                logger.info(f"Check complete. Next check in ~{interval} seconds.")
        else:
            if last_config_mtime == 0:
                 logger.warning("Waiting for valid configuration...")

        time.sleep(5)

if __name__ == "__main__":
    main()
