# League Mod Repather

A standalone tool to repath League of Legends `.fantome` mod files for compatibility with updated game files.

## Features

- ✅ **Automatic Hash Management**: Download/update hash files from CommunityDragon
- ✅ **WAD Extraction**: Extracts both mod and fresh WAD files
- ✅ **TEX→DDS Conversion**: Converts fresh textures for compatibility
- ✅ **BIN Repair**: Applies Fixes (StaticMaterial & HealthBar fixes)
- ✅ **Smart Repathing**: Uses LtMAO-hai bumpath algorithm
- ✅ **Clean Output**: Automatically cleans up temporary files

## Requirements

- Python 3.8+ (for building)
- League of Legends installation

## Usage

### For End Users (EXE)

1. Run `LeagueModRepather.exe`
2. **Step 1**: Download hash files (first time only)
3. Select your League Champions folder
4. Select your `.fantome` mod file
5. Enter the main skin BIN (e.g., "Skin0")
6. Click through the wizard
7. Find your repathed mod in `Documents\FantomeRepathTool\`

### For Developers

**Setup:**
```bash
pip install -r requirements.txt
```

**Run from source:**
```bash
python fantome_repath_gui.py
```

**Build EXE:**
```bash
build.bat
```

## How It Works

1. **Extract**: Unpacks both the mod's WAD and the fresh WAD from your League installation
2. **Convert**: Converts all `.tex` files in the fresh WAD to `.dds`
3. **Overlay**: Overlays the mod files onto the fresh files
4. **Repair**: Applies FrogFixes to the selected main BIN
5. **Repath**: Updates all file paths with the "bum/" prefix
6. **Pack**: Creates a new `.fantome` with `_repathed` suffix

## Output Location

- **Standalone EXE**: `C:\Users\<YourName>\Documents\FantomeRepathTool\`
- **Development**: `<project>\repath tool test\`

## Hash Files

Hash files are downloaded from [CommunityDragon](https://github.com/CommunityDragon/Data) and stored in:
- `C:\Users\<YourName>\AppData\Roaming\FrogTools\hashes\`

You can update them anytime by clicking "Update" in the tool.

## Credits

This tool is built upon the excellent work of:

- **[GuiSai (GuiSaiUwU)](https://github.com/GuiSaiUwU)**: Creator of [pyRitoFile](https://github.com/GuiSaiUwU/pyritofile-package) - Python library for League of Legends file formats (BIN, WAD, SKL, TEX, etc.)
BIN repair logic for StaticMaterial and HealthBar fixes
- **[tarngaina](https://github.com/tarngaina)**: Creator of [LtMAO-hai](https://github.com/tarngaina/LtMAO) - Comprehensive League modding toolpack, from which the bumpath algorithm and various utilities were adapted
- **CommunityDragon**: Hash tables and game data

Special thanks to the League modding community for their continuous contributions and support.

## License

For personal use only.

