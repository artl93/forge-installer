# Minecraft Forge Server Installer

A shell script to automatically install and configure a Minecraft server using Forge with optional mod packs and world saves.

## Features

- 🚀 **Automated Forge Installation**: Downloads and installs any specified Forge version
- 📦 **Mod Pack Support**: Automatically copies mods and resource packs from a source directory
- 🌍 **World Save Management**: Copies world saves to the server
- ⚡ **Efficient Downloads**: Caches downloaded installers to avoid re-downloading
- 📋 **EULA Agreement**: Automatically agrees to Minecraft EULA
- 🛡️ **Error Handling**: Comprehensive parameter validation and error checking
- 👤 **Ownership Management**: Optional file ownership changes for server deployment

## Prerequisites

- Java 8 or higher installed
- `curl` command available
- Shell environment (bash/zsh/sh)
- Internet connection for downloading Forge installer

## Usage

```bash
./install-forge.sh <forge_version> <target_directory> [mods_and_resource_directory] [saves_directory] [owner_account]
```

### Parameters

| Parameter | Required | Description |
|-----------|----------|-------------|
| `forge_version` | ✅ | Version of Forge to install (e.g., `1.20.1-47.4.4`) |
| `target_directory` | ✅ | Directory where the server will be installed |
| `mods_and_resource_directory` | ❌ | Source directory containing `mods/` and `resourcepacks/` folders |
| `saves_directory` | ❌ | Source directory containing world saves |
| `owner_account` | ❌ | User account to set as owner of server files (requires sudo) |

### Examples

#### Basic server installation:
```bash
./install-forge.sh 1.20.1-47.4.4 /opt/minecraft-server
```

#### With mod pack:
```bash
./install-forge.sh 1.20.1-47.4.4 /opt/minecraft-server /home/user/modpack
```

#### With mod pack and custom world saves:
```bash
./install-forge.sh 1.20.1-47.4.4 /opt/minecraft-server /home/user/modpack /home/user/worlds
```

#### With ownership change to minecraft user:
```bash
./install-forge.sh 1.20.1-47.4.4 /opt/minecraft-server /home/user/modpack /home/user/worlds minecraft
```

## Directory Structure

### Expected Source Structure
If using the optional `mods_and_resource_directory`, it should be organized as:
```
mods_and_resource_directory/
├── mods/
│   ├── mod1.jar
│   ├── mod2.jar
│   └── ...
├── resourcepacks/
│   ├── pack1.zip
│   ├── pack2.zip
│   └── ...
└── saves/ (optional, used if no separate saves_directory provided)
    ├── world1/
    ├── world2/
    └── ...
```

### Generated Server Structure
After running the script, your target directory will contain:
```
target_directory/
├── forge-<version>.jar (main server jar)
├── eula.txt (automatically agreed)
├── libraries/ (Forge dependencies)
├── mods/ (copied from source)
├── resourcepacks/ (copied from source)
└── world/ (world saves)
```

### Cache Directory Structure
The script also creates a cache directory in the location where you run the script:
```
./temp/
└── forge-<version>-installer.jar (cached installers)
```

## How It Works

1. **Validation**: Checks all required parameters and validates input
2. **Directory Setup**: Creates target directory if it doesn't exist
3. **Download Management**: 
   - Creates a `temp/` directory in the current working directory for caching installers
   - Downloads Forge installer only if not already cached
   - Reuses cached installers for faster subsequent runs
4. **Server Installation**: Runs the Forge installer to set up the server
5. **Content Copying**: 
   - Copies mods and resource packs if source directory provided
   - Copies world saves from either dedicated saves directory or from mod pack directory
6. **EULA Agreement**: Creates `eula.txt` with agreement to Minecraft EULA
7. **Ownership Management**: Optionally changes file ownership to specified user account
8. **Cleanup**: Returns to original directory

## Caching

The script creates a `temp/` directory in the current working directory (where you run the script) to cache downloaded Forge installers. This means:

- ✅ Faster subsequent installations of the same Forge version
- ✅ Reduced bandwidth usage
- ✅ Offline capability for previously downloaded versions
- ℹ️ Cache is shared across all server installations from the same location
- ℹ️ Manual cleanup required if you want to free up space

To clear the cache:
```bash
rm -rf temp/
```

## Error Handling

The script includes comprehensive error handling for:

- Missing required parameters
- Empty or invalid parameters
- Missing source directories
- Failed downloads
- Missing subdirectories (with warnings)

## Starting Your Server

After installation, navigate to your target directory and start the server:

```bash
cd /path/to/your/server
java -Xmx4G -Xms2G -jar forge-<version>.jar nogui
```

Adjust memory allocation (`-Xmx4G -Xms2G`) based on your server's requirements and available RAM.

## Troubleshooting

### Common Issues

**"Permission denied" error:**
```bash
chmod +x install-forge.sh
```

**Java not found:**
- Ensure Java 8+ is installed and in your PATH
- On macOS: `brew install openjdk`
- On Ubuntu/Debian: `sudo apt install openjdk-17-jdk`

**Download fails:**
- Check internet connection
- Verify the Forge version exists at [Minecraft Forge Downloads](https://files.minecraftforge.net/)

**Server won't start:**
- Check Java version compatibility with Minecraft version
- Ensure sufficient RAM allocation
- Review server logs for specific errors

## Contributing

Feel free to submit issues and enhancement requests!

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

**Note**: This script automatically agrees to the [Minecraft EULA](https://aka.ms/MinecraftEULA) by creating `eula.txt` with `eula=true`. Make sure you agree with the EULA terms before using this script.
