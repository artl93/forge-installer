#!/bin/sh
# script to install a minecraft server using Forge
# parameters: <forge_version> <target_directory> [mods_and_resource_directory] [saves_directory]

# Function to display usage
show_usage() {
    echo "Usage: $0 <forge_version> <target_directory> [mods_and_resource_directory] [saves_directory]"
    echo ""
    echo "Parameters:"
    echo "  forge_version                 - Version of Forge to install (e.g., 1.20.1-47.4.4)"
    echo "  target_directory             - Directory where the server will be installed"
    echo "  mods_and_resource_directory  - Optional: Source directory containing mods and resourcepacks"
    echo "  saves_directory              - Optional: Source directory containing world saves"
    echo ""
    echo "Examples:"
    echo "  $0 1.20.1-47.4.4 /opt/minecraft-server"
    echo "  $0 1.20.1-47.4.4 /opt/minecraft-server /home/user/modpack"
    echo "  $0 1.20.1-47.4.4 /opt/minecraft-server /home/user/modpack /home/user/worlds"
    exit 1
}

# Check if required parameters are provided
if [ $# -lt 2 ]; then
    echo "Error: Missing required parameters."
    echo ""
    show_usage
fi

# Validate forge version parameter
if [ -z "$1" ]; then
    echo "Error: Forge version cannot be empty."
    show_usage
fi

# Validate target directory parameter
if [ -z "$2" ]; then
    echo "Error: Target directory cannot be empty."
    show_usage
fi


# set the user parameter from the command line to the version of Forge you want to install, like 1.20.1-47.4.4
FORGE_VERSION="$1"
TARGET_DIR="$2"
MODS_RESOURCE_DIR="$3"
SAVES_DIR="$4"

# check if the target directory exists, if not create it
if [ ! -d "$TARGET_DIR" ]; then
  echo "Target directory $TARGET_DIR does not exist. Creating it."
  mkdir -p "$TARGET_DIR"
else
  echo "Target directory $TARGET_DIR already exists."
fi

# Create temp directory for downloads
TEMP_DIR="./temp"
mkdir -p "$TEMP_DIR"

# download the specified version of the file from forge (if not already downloaded)
INSTALLER_JAR="forge-$FORGE_VERSION-installer.jar"
TEMP_INSTALLER_PATH="$TEMP_DIR/$INSTALLER_JAR"

if [ -f "$TEMP_INSTALLER_PATH" ]; then
    echo "Forge installer already exists at $TEMP_INSTALLER_PATH, skipping download"
else
    echo "Downloading Forge installer to $TEMP_INSTALLER_PATH"
    curl -L -o "$TEMP_INSTALLER_PATH" https://maven.minecraftforge.net/net/minecraftforge/forge/$FORGE_VERSION/forge-$FORGE_VERSION-installer.jar
fi

# Change to target directory
pushd "$TARGET_DIR"

# install the server to a directory
java -jar "../$TEMP_INSTALLER_PATH" --installServer

# copy mods and resource packs (if source directory provided)
if [ -n "$MODS_RESOURCE_DIR" ] && [ -d "$MODS_RESOURCE_DIR" ]; then
    echo "Copying mods and resource packs from $MODS_RESOURCE_DIR"
    if [ -d "$MODS_RESOURCE_DIR/mods" ]; then
        cp -r "$MODS_RESOURCE_DIR/mods" .
        echo "Mods copied successfully"
    else
        echo "Warning: mods directory not found in $MODS_RESOURCE_DIR"
    fi
    
    if [ -d "$MODS_RESOURCE_DIR/resourcepacks" ]; then
        cp -r "$MODS_RESOURCE_DIR/resourcepacks" .
        echo "Resource packs copied successfully"
    else
        echo "Warning: resourcepacks directory not found in $MODS_RESOURCE_DIR"
    fi
else
    echo "Skipping mods and resource packs (no source directory provided or directory doesn't exist)"
fi

# copy worlds / saves (if saves directory provided)
if [ -n "$SAVES_DIR" ] && [ -d "$SAVES_DIR" ]; then
    echo "Copying world saves from $SAVES_DIR"
    cp -r "$SAVES_DIR"/* "./world/" 2>/dev/null || mkdir -p "./world" && cp -r "$SAVES_DIR"/* "./world/"
    echo "World saves copied successfully"
elif [ -n "$MODS_RESOURCE_DIR" ] && [ -d "$MODS_RESOURCE_DIR/saves" ]; then
    echo "Copying world saves from $MODS_RESOURCE_DIR/saves"
    cp -r "$MODS_RESOURCE_DIR/saves" .
    echo "World saves copied successfully"
else
    echo "Skipping world saves (no saves directory provided or directory doesn't exist)"
fi

# create eula.txt and agree to the EULA (required for server to start)
echo "eula=true" > "eula.txt"
echo "EULA agreement created"

popd