# League Mod Repather

**A standalone tool to automatically fix League of Legends mods after game updates.**

When Riot Games updates League of Legends, old mods often stop working. This tool **automatically updates your mods** to work with the latest game version by "repathing" them.

**In simple terms:** It fixes broken mods so they work again! ✨

---

## 📚 Tutorial - How to Use

### **First Time Setup** (One-time only)

1. **Download** `LeagueModRepather.exe` and run it
2. Click **"📥 Download"** to get hash files
3. Wait for download to complete (about 1 minute)

### **Repathing Your Mod**

#### **Step 1: Select Your Files**

1. **Champions Folder:**
   - Click **"Browse"** next to "Champions folder"
   - Navigate to: `C:\Riot Games\League of Legends\Game\DATA\FINAL\Champions`
   - Click "Select Folder"

2. **Your Mod** (Choose one):
   - **Option A:** Click "Browse" next to ".fantome file" and select your mod
   - **Option B:** Click "Browse" next to "Mod folder" and select your own mod folder (MOSTLY FOR CREATORS OF MODS) dont use if regular user

3. **Custom Prefix** (Optional):
   - Leave blank for automatic (recommended)
   - Or enter your own (e.g., "mymod")

4. Click **"Next"**

#### **Step 2: Wait for Processing**

The tool will automatically:
- 🔍 Detect which champion the mod is for
- 📦 Extract and process files
- 🎨 Convert textures
- ⏱️ Takes 2-5 minutes

Status will show: `✓ Overlay complete`

Click **"Next"**

#### **Step 3: Select Main Skin**

1. Choose from dropdown (usually **Skin0**)
2. Click **"Next"**

#### **Step 4: Automatic Repathing**

The tool will:
- 🔧 Fix files
- 🔄 Repath everything
- 🖼️ Add missing textures
- 📦 Create your new mod

When done, you'll see: `✓ DONE! Created {name}_repathed.fantome`

### **Find Your Repathed Mod**

Your new mod is in: `C:\Users\<YourName>\Documents\FantomeRepathTool\`

Look for: `{original_name}_repathed.fantome`

### **Install & Use**

1. Open your mod manager (Fantome, LCS Manager, etc.)
2. Import the `_repathed.fantome` file
3. Enable it
4. Play! 🎮

---

## ✨ Features

- ✅ Works with `.fantome` files OR extracted mod folders
- ✅ Automatically detects champion
- ✅ Fixes missing textures
- ✅ Custom or random prefixes
- ✅ No installation required - just run the EXE!

---

## ❓ Common Questions

**Q: Do I need Python installed?**  
A: No! Just download and run the EXE.

**Q: My mod still doesn't work!**  
A: Try these:
- Make sure you selected Skin0 (or the correct skin)
- Click "Update" to refresh hash files
- Try repathing again

**Q: Is this safe?**  
A: Yes! It only modifies mod files, never your League installation.

**Q: Where are hash files stored?**  
A: `C:\Users\<YourName>\AppData\Roaming\FrogTools\hashes\`

**Q: Can I delete the work folder?**  
A: Yes! Keep only your `_repathed.fantome` files.

**Q: The tool is stuck on "Converting TEX → DDS"**  
A: This is normal for large mods! Wait 2-5 minutes. ☕

---

## 🙏 Credits

Built upon the excellent work of:

- **[GuiSai (GuiSaiUwU)](https://github.com/GuiSaiUwU)** - Creator of [pyRitoFile](https://github.com/GuiSaiUwU/pyritofile-package)
- **[tarngaina](https://github.com/tarngaina)** - Creator of [LtMAO-hai](https://github.com/tarngaina/LtMAO)
- **CommunityDragon** - Hash tables from [CommunityDragon/Data](https://github.com/CommunityDragon/Data)

Special thanks to the League modding community! 💜

---

**Made with ❤️ for the League modding community**
