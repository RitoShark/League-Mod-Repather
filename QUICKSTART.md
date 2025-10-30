# Quick Start Guide

## 🚀 Running the Tool (Python)

```bash
python fantome_repath_gui.py
```

## 🔨 Building the EXE

```bash
build.bat
```

The EXE will be created in `dist\LeagueModRepather.exe`

## 📦 First Time Setup

1. Install Python 3.8+
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## 🎮 Using the Tool

### Step 1: Hash Files
- Click **"Download"** to get hash files from CommunityDragon
- This only needs to be done once
- Click **"Open Folder"** to see where hashes are stored
- Click **"Update"** to refresh hash files when League updates

### Step 2: Select Files
- **Champions Folder**: Browse to your League installation
  - Example: `C:\Riot Games\League of Legends\Game\DATA\FINAL\Champions`
- **Fantome File**: Select your `.fantome` mod file

### Step 3: Detect & Extract
- Click **"Next"** - the tool will:
  - Detect which champion WAD is in your mod
  - Extract the mod's WAD
  - Extract the fresh WAD from your League folder
  - Convert all `.tex` files to `.dds`

### Step 4: Select Main BIN
- Enter the skin name (e.g., `Skin0`, `Skin5`, `base`)
- The tool will:
  - Overlay your mod files onto the fresh files
  - Find and repair the main BIN
  - Apply FrogFixes (StaticMaterial & HealthBar)

### Step 5: Repath & Package
- Click **"Next"** - the tool will:
  - Repath all files with the "bum/" prefix
  - Pack everything into a new WAD
  - Create a new `.fantome` with `_repathed` suffix
  - Clean up temporary files

## 📁 Output Location

Your repathed mod will be saved next to the original fantome:
- Original: `my_mod.fantome`
- Repathed: `my_mod_repathed.fantome`

Temporary files are stored in:
- **EXE**: `C:\Users\<YourName>\Documents\FantomeRepathTool\`
- **Python**: `<project>\repath tool test\`

## ❓ Troubleshooting

**"Missing hash files"**
- Click "Download" in Step 1

**"Champion not detected"**
- Make sure your `.fantome` has a valid `wad/` folder inside

**"Main BIN not found"**
- Check the available skins listed in the error
- Try `Skin0` (base skin) or `base`

**"Repath failed"**
- Check that hash files are downloaded
- Make sure the Champions folder path is correct

## 🔧 Development

To modify the tool:
1. Edit `fantome_repath_gui.py`
2. Test with: `python fantome_repath_gui.py`
3. Build with: `build.bat`

## 📝 Notes

- Hash files are ~220MB total (downloaded once, stored locally)
- Each repath takes 1-5 minutes depending on mod size
- Temporary files are automatically cleaned up
- The tool does NOT modify your original files

