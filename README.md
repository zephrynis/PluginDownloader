# Minecraft Plugin Updater

A Dockerized Python script that automatically checks for and downloads updates for Minecraft plugins from GitHub, Modrinth, and Spigot.

## Features
- Supports GitHub, Modrinth, and Spigot (via Spiget).
- Automatically deletes old versions upon update.
- Configurable check interval.
- Maintains state to track installed versions.

## Usage

1.  **Create a data directory:**
    Create a folder on your host machine (e.g., `updater-data`).

2.  **Create configuration:**
    Copy `config.example.yaml` to your data directory, rename it to `config.yaml`, and edit it with your plugins.

    ```yaml
    check_interval: 3600
    plugins:
      - name: "MyPlugin"
        source: "github"
        repo: "user/repo"
    ```

3.  **Run with Docker:**

    ```bash
    docker run -d \
      --name plugin-updater \
      -v /path/to/updater-data:/data \
      minecraft-plugin-updater
    ```

    Plugins will be downloaded to `/path/to/updater-data/plugins`.

## Configuration Options

- **GitHub:**
  - `source`: "github"
  - `repo`: "owner/repository"
  - `asset_regex`: (Optional) Regex to match specific release asset names.

- **Modrinth:**
  - `source`: "modrinth"
  - `id`: Project ID or Slug
  - `loader`: (Optional) e.g., "spigot", "paper"
  - `game_version`: (Optional) e.g., "1.20.1"

- **Spigot:**
  - `source`: "spigot"
  - `id`: Resource ID (found in the URL, e.g., `https://www.spigotmc.org/resources/plugin-name.12345/` -> `12345`)

