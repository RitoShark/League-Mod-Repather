import os
import sys
import tempfile
import zipfile
import shutil
import threading
from pathlib import Path
from typing import Dict
import json
import tkinter as tk
from tkinter import filedialog, messagebox

# Add project root to path for pyRitoFile
# Handle both development and PyInstaller bundled mode
if getattr(sys, 'frozen', False):
	# Running as compiled exe
	PROJECT_ROOT = Path(sys._MEIPASS)
else:
	# Running as script
	PROJECT_ROOT = Path(__file__).parent.parent

if str(PROJECT_ROOT) not in sys.path:
	sys.path.insert(0, str(PROJECT_ROOT))

import pyRitoFile

try:
	import ttkbootstrap as tb
	from ttkbootstrap.dialogs import Messagebox
except Exception:
	tb = None
	Messagebox = None


APP_TITLE = "League Mod Repather"


class WizardApp:
	def __init__(self, root: tk.Tk):
		self.root = root
		self.root.title(APP_TITLE)
		self.root.geometry("900x560")

		# State
		self.champions_dir = tk.StringVar()
		self.fantome_path = tk.StringVar()
		self.detected_wad_name = tk.StringVar()
		self.s2_status_text = tk.StringVar(value="Waiting to start...")
		self.main_bin_choice = tk.StringVar(value="Skin0")
		self.hash_status = tk.StringVar(value="Checking hashes...")

		# internal: store full member path inside .fantome
		self._fantome_member_path = None
		
		# Step completion tracking
		self.step_completed = [False, False, False, False]  # Track if each step is completed

		self.temp_dir = os.path.join(tempfile.gettempdir(), "FrogTools", "fantome_repath")
		os.makedirs(self.temp_dir, exist_ok=True)

		# Steps
		self.steps = []
		self.current_step = 0

		self._build_layout()
		self._build_steps()
		# load persisted config (champions path)
		try:
			cfg = self._load_config()
			if isinstance(cfg, dict) and 'champions_dir' in cfg:
				self.champions_dir.set(cfg.get('champions_dir') or '')
		except Exception:
			pass
		self._show_step(0)

	def _frame(self, *args, **kwargs):
		return (tb.Frame if tb else tk.Frame)(*args, **kwargs)

	def _label(self, *args, **kwargs):
		return (tb.Label if tb else tk.Label)(*args, **kwargs)

	def _entry(self, *args, **kwargs):
		return (tb.Entry if tb else tk.Entry)(*args, **kwargs)

	def _button(self, *args, **kwargs):
		return (tb.Button if tb else tk.Button)(*args, **kwargs)

	def _copy_menu(self, widget):
		menu = tk.Menu(widget, tearoff=0)
		menu.add_command(label="Copy", command=lambda: widget.event_generate('<<Copy>>'))
		menu.add_command(label="Select All", command=lambda: (widget.select_range(0, 'end'), widget.icursor('end')))
		def show_menu(event):
			menu.tk_popup(event.x_root, event.y_root)
		widget.bind('<Button-3>', show_menu)
		return menu

	def _copyable_entry(self, parent, textvariable, width=80):
		e = self._entry(parent, textvariable=textvariable, width=width)
		try:
			e.configure(state='readonly')
		except Exception:
			pass
		self._copy_menu(e)
		return e

	def _build_layout(self):
		self.container = self._frame(self.root)
		self.container.pack(fill=tk.BOTH, expand=True)

		self.nav = self._frame(self.root)
		self.nav.pack(fill=tk.X, side=tk.BOTTOM)

		self.back_btn = self._button(self.nav, text="◀ Back", command=self._on_back)
		self.back_btn.pack(side=tk.LEFT, padx=8, pady=8)

		self.next_btn = self._button(self.nav, text="Next ▶", command=self._on_next)
		self.next_btn.pack(side=tk.RIGHT, padx=8, pady=8)

	def _build_steps(self):
		# Step 1: Hash Management + Pick paths
		s1 = self._frame(self.container)
		self._label(s1, text="Step 1 — Hash Files & Mod Selection").pack(anchor=tk.W, padx=12, pady=(12, 6))
		
		# Hash Management Section
		hash_section = self._frame(s1)
		hash_section.pack(fill=tk.X, padx=12, pady=6)
		self._label(hash_section, text="Hash Files (required for tool to work):", font=('Arial', 10, 'bold')).pack(anchor=tk.W, pady=(0, 4))
		
		# Hash status
		hash_status_frame = self._frame(hash_section)
		hash_status_frame.pack(fill=tk.X, pady=4)
		self._label(hash_status_frame, text="Status:").pack(side=tk.LEFT)
		self._copyable_entry(hash_status_frame, self.hash_status, width=60).pack(side=tk.LEFT, padx=8, fill=tk.X, expand=True)
		
		# Hash buttons
		hash_btn_frame = self._frame(hash_section)
		hash_btn_frame.pack(pady=4)
		self._button(hash_btn_frame, text="📥 Download", command=self._download_hashes, width=15).pack(side=tk.LEFT, padx=4)
		self._button(hash_btn_frame, text="🔄 Update", command=self._update_hashes, width=15).pack(side=tk.LEFT, padx=4)
		self._button(hash_btn_frame, text="📁 Open Folder", command=self._open_hash_folder, width=15).pack(side=tk.LEFT, padx=4)
		
		# Separator
		sep = self._frame(s1, height=2)
		sep.pack(fill=tk.X, padx=12, pady=12)
		
		# Mod Selection Section
		self._label(s1, text="Mod Selection:", font=('Arial', 10, 'bold')).pack(anchor=tk.W, padx=12, pady=(0, 6))

		row1 = self._frame(s1)
		row1.pack(fill=tk.X, padx=12, pady=6)
		self._label(row1, text="Champions folder:").pack(side=tk.LEFT)
		e1 = self._entry(row1, textvariable=self.champions_dir, width=80)
		e1.pack(side=tk.LEFT, padx=8, fill=tk.X, expand=True)
		self._button(row1, text="Browse", command=self._pick_champions_dir).pack(side=tk.LEFT)

		row2 = self._frame(s1)
		row2.pack(fill=tk.X, padx=12, pady=6)
		self._label(row2, text=".fantome file:").pack(side=tk.LEFT)
		e2 = self._entry(row2, textvariable=self.fantome_path, width=80)
		e2.pack(side=tk.LEFT, padx=8, fill=tk.X, expand=True)
		self._button(row2, text="Browse", command=self._pick_fantome).pack(side=tk.LEFT)

		self.steps.append(s1)

		# Step 2: Detection & extraction placeholders
		s2 = self._frame(self.container)
		self._label(s2, text="Step 2 — Detect champion wad and extract").pack(anchor=tk.W, padx=12, pady=(12, 6))
		self._label(s2, text="Detected wad:").pack(anchor=tk.W, padx=12, pady=(0, 4))
		self._copyable_entry(s2, self.detected_wad_name, width=100).pack(fill=tk.X, padx=12, pady=(0, 8))
		self._label(s2, text="Status:").pack(anchor=tk.W, padx=12, pady=(0, 4))
		self.s2_status = self._copyable_entry(s2, self.s2_status_text, width=100)
		self.s2_status.pack(fill=tk.X, padx=12, pady=(0, 8))
		# Open work folder button
		s2_btn_frame = self._frame(s2)
		s2_btn_frame.pack(pady=8)
		self._button(s2_btn_frame, text="📁 Open Work Folder", command=self._open_work_folder, width=20).pack()
		self.steps.append(s2)

		# Step 3: Overlay + BIN selection
		s3 = self._frame(self.container)
		self._label(s3, text="Step 3 — Overlay mod onto fresh and select main BIN").pack(anchor=tk.W, padx=12, pady=(12, 6))
		row3 = self._frame(s3)
		row3.pack(fill=tk.X, padx=12, pady=6)
		self._label(row3, text="Main BIN:").pack(side=tk.LEFT)
		e3 = self._entry(row3, textvariable=self.main_bin_choice, width=20)
		e3.pack(side=tk.LEFT, padx=8)
		# Open work folder button
		s3_btn_frame = self._frame(s3)
		s3_btn_frame.pack(pady=8)
		self._button(s3_btn_frame, text="📁 Open Work Folder", command=self._open_work_folder, width=20).pack()
		self.steps.append(s3)

		# Step 4: Repath & package (with automatic placeholder fixing)
		s4 = self._frame(self.container)
		self._label(s4, text="Step 4 — Repath, Fix Missing Files & Package").pack(anchor=tk.W, padx=12, pady=(12, 6))
		self._label(s4, text="Status:").pack(anchor=tk.W, padx=12, pady=(0, 4))
		self._copyable_entry(s4, self.s2_status_text, width=100).pack(fill=tk.X, padx=12, pady=(0, 8))
		# Buttons for Step 4
		s4_btn_frame = self._frame(s4)
		s4_btn_frame.pack(pady=8)
		self._button(s4_btn_frame, text="📁 Open Work Folder", command=self._open_work_folder, width=20).pack(side=tk.LEFT, padx=4)
		self.retry_btn = self._button(s4_btn_frame, text="🔄 Refresh / Retry", command=self._retry_step4, width=20)
		self.retry_btn.pack(side=tk.LEFT, padx=4)
		self.retry_btn.configure(state=tk.DISABLED)  # Disabled until process completes
		self.steps.append(s4)

	def _show_step(self, idx: int):
		for i, s in enumerate(self.steps):
			if i == idx:
				s.pack(fill=tk.BOTH, expand=True)
			else:
				s.pack_forget()
		self.current_step = idx
		# Check hashes when showing step 1 (first step with hash management)
		if idx == 0:
			self._check_hashes()
		self._update_nav()

	def _update_nav(self):
		self.back_btn.configure(state=tk.NORMAL if self.current_step > 0 else tk.DISABLED)
		
		# Update Next button text and state
		if self.current_step == len(self.steps) - 1:
			self.next_btn.configure(text="Finish")
		else:
			self.next_btn.configure(text="Next ▶")
		
		# Disable Next button if current step is not completed (except for step 0 which validates on click)
		if self.current_step > 0 and not self.step_completed[self.current_step]:
			self.next_btn.configure(state=tk.DISABLED)
		else:
			self.next_btn.configure(state=tk.NORMAL)

	def _on_back(self):
		if self.current_step > 0:
			self._show_step(self.current_step - 1)

	def _on_next(self):
		if self.current_step == 0:
			if not self._validate_inputs():
				return
			# Mark step 0 as completed
			self.step_completed[0] = True
			# start detection/extraction in a background thread
			self._show_step(1)
			t = threading.Thread(target=self._detect_and_extract, daemon=True)
			t.start()
		elif self.current_step == 1:
			# Can't proceed from step 1 if extraction isn't complete
			if not self.step_completed[1]:
				messagebox.showwarning(APP_TITLE, "Please wait for extraction to complete before proceeding.")
				return
			# Mark step 2 as complete (user can now select main BIN)
			self.step_completed[2] = True
			self._show_step(self.current_step + 1)
		elif self.current_step == 2:
			# Step 3 -> Step 4: run repath now using selected main_bin_choice
			self._show_step(3)
			t = threading.Thread(target=self._run_repath_current, daemon=True)
			t.start()
		elif self.current_step < len(self.steps) - 1:
			self._show_step(self.current_step + 1)
		else:
			messagebox.showinfo(APP_TITLE, "All done! You can now close the wizard or re-run the process.")

	def _pick_champions_dir(self):
		path = filedialog.askdirectory(title="Select Champions folder")
		if path:
			self.champions_dir.set(path)
			self._save_config()

	def _pick_fantome(self):
		path = filedialog.askopenfilename(title="Select .fantome file", filetypes=[("Fantome", "*.fantome"), ("Zip", "*.zip"), ("All", "*.*")])
		if path:
			self.fantome_path.set(path)

	def _validate_inputs(self) -> bool:
		champs = self.champions_dir.get().strip()
		fantome = self.fantome_path.get().strip()
		if not champs or not os.path.isdir(champs):
			messagebox.showerror(APP_TITLE, "Please select a valid Champions folder.")
			return False
		# persist on successful validation of champs path
		try:
			self._save_config()
		except Exception:
			pass
		if not fantome or not os.path.isfile(fantome):
			messagebox.showerror(APP_TITLE, "Please select a valid .fantome file.")
			return False
		if not (fantome.lower().endswith(".fantome") or fantome.lower().endswith(".zip")):
			messagebox.showerror(APP_TITLE, "Selected file is not a .fantome/.zip archive.")
			return False
		return True

	# ---------- Step 2: Detection & Extraction ----------
	def _project_root(self) -> Path:
		"""
		Returns the root directory containing pyRitoFile and hashes.
		When running as EXE, this is the temporary extraction folder.
		When running as script, this is the project directory.
		"""
		return PROJECT_ROOT

	def _work_root(self) -> Path:
		"""
		Returns the working directory for extractions and output.
		When running as EXE, use Documents folder.
		When running as script, use project directory.
		"""
		if getattr(sys, 'frozen', False):
			# Running as EXE - use Documents/FantomeRepathTool
			import os
			docs = Path(os.path.expanduser("~")) / "Documents" / "FantomeRepathTool"
			docs.mkdir(parents=True, exist_ok=True)
			return docs
		else:
			# Running as script - use project directory for testing
			root = self._project_root() / "repath tool test"
			root.mkdir(parents=True, exist_ok=True)
			return root

	def _config_path(self) -> Path:
		# persist under %APPDATA%/FrogTools
		base = Path(os.getenv('APPDATA') or Path.home() / 'AppData' / 'Roaming')
		cfg_dir = base / 'FrogTools'
		cfg_dir.mkdir(parents=True, exist_ok=True)
		return cfg_dir / 'fantome_repath_config.json'

	def _load_config(self) -> Dict:
		p = self._config_path()
		if p.exists():
			with open(p, 'r', encoding='utf-8') as f:
				return json.load(f)
		return {}

	def _save_config(self):
		p = self._config_path()
		data = {
			'champions_dir': self.champions_dir.get().strip(),
		}
		try:
			with open(p, 'w', encoding='utf-8') as f:
				json.dump(data, f, indent=2, ensure_ascii=False)
		except Exception:
			pass

	def _set_status(self, text: str):
		try:
			self.s2_status_text.set(text)
		except Exception:
			pass

	def _detect_wad_member_in_fantome(self, fantome_path: Path, champions_dir: Path) -> str:
		"""
		Detect the champion WAD file inside the fantome by matching against Champions folder.
		For multi-WAD fantomes (e.g., kayn.wad.client + common.wad.client + ui.wad.client),
		we identify which WAD corresponds to an actual champion.
		"""
		with zipfile.ZipFile(fantome_path, 'r') as zf:
			names = zf.namelist()
		
		# Language codes to exclude
		language_codes = [
			'.en_us.', '.ja_jp.', '.ko_kr.', '.zh_cn.', '.zh_tw.',
			'.de_de.', '.es_es.', '.es_mx.', '.fr_fr.', '.it_it.',
			'.pl_pl.', '.pt_br.', '.ro_ro.', '.ru_ru.', '.tr_tr.'
		]
		
		# Find all .wad.client files in wad/ folder (case-insensitive)
		# Accepts both "wad/" and "WAD/" and any other casing
		all_wads = []
		for name in names:
			name_parts = name.split('/')
			if len(name_parts) >= 2:
				# Check if first part is "wad" (case-insensitive) and ends with .wad.client
				if name_parts[0].lower() == 'wad' and name.lower().endswith('.wad.client'):
					all_wads.append(name)
		
		# Filter out language-specific WADs
		non_language_wads = []
		for wad in all_wads:
			wad_lower = wad.lower()
			is_language_wad = any(lang_code in wad_lower for lang_code in language_codes)
			if not is_language_wad:
				non_language_wads.append(wad)
		
		# Store all WAD members for later (so we can include non-champion WADs in final fantome)
		self._all_fantome_wads = non_language_wads
		
		# Try to match each WAD against the Champions folder
		matched_wads = []
		debug_info = []
		for wad_member in non_language_wads:
			# Extract just the filename (e.g., "Kayn.wad.client" from "WAD/Kayn.wad.client")
			wad_filename = wad_member.split('/')[-1]
			
			# Check if this WAD exists in the Champions folder (case-insensitive match)
			matching_wad = self._find_fresh_wad(champions_dir, wad_filename)
			# Check if not None (function returns None when not found)
			exists = matching_wad is not None
			debug_info.append(f"{wad_filename}: {'FOUND' if exists else 'NOT FOUND'} (path: {matching_wad if exists else 'N/A'})")
			
			if exists:
				# Found a champion WAD!
				matched_wads.append((wad_member, wad_filename))
		
		# Debug: print what we found
		print(f"[DEBUG] WADs checked: {', '.join(debug_info)}")
		print(f"[DEBUG] Matched WADs: {len(matched_wads)}")
		
		# If we found champion WADs, return the first one
		if matched_wads:
			print(f"[DEBUG] Returning: {matched_wads[0][0]}")
			return matched_wads[0][0]
		
		# If no champion WAD found, return empty (don't use fallback to avoid wrong WAD)
		print(f"[DEBUG] No champion WAD found, returning empty")
		return ''

	def _extract_file_from_fantome(self, fantome_path: Path, member: str, dest_path: Path):
		dest_path.parent.mkdir(parents=True, exist_ok=True)
		with zipfile.ZipFile(fantome_path, 'r') as zf:
			with zf.open(member) as src, open(dest_path, 'wb') as dst:
				shutil.copyfileobj(src, dst, length=1024 * 1024)

	def _find_fresh_wad(self, champions_dir: Path, wad_name: str) -> Path | None:
		"""
		Find the champion WAD file, excluding language-specific WADs.
		Example: sivir.wad.client ✓, sivir.en_us.wad.client ✗
		Returns None if not found.
		"""
		wad_lower = wad_name.lower()
		print(f"[DEBUG _find_fresh_wad] Looking for: {wad_name} (lowercase: {wad_lower})")
		print(f"[DEBUG _find_fresh_wad] Champions dir: {champions_dir}")
		
		# Extract champion name from the wad filename (e.g., "sivir" from "sivir.wad.client")
		# Pattern: championname.wad.client
		if not wad_lower.endswith('.wad.client'):
			# If it doesn't end with .wad.client, just do exact match
			for root, _dirs, files in os.walk(champions_dir):
				for f in files:
					if f.lower() == wad_lower:
						found = Path(root) / f
						print(f"[DEBUG _find_fresh_wad] FOUND (exact): {found}")
						return found
			print(f"[DEBUG _find_fresh_wad] NOT FOUND (exact match)")
			return None
		
		# Get the champion name (everything before .wad.client)
		champ_name = wad_lower.replace('.wad.client', '')
		
		# Look for exact match: championname.wad.client (no language code)
		target_name = f"{champ_name}.wad.client"
		print(f"[DEBUG _find_fresh_wad] Target name: {target_name}")
		
		for root, _dirs, files in os.walk(champions_dir):
			for f in files:
				f_lower = f.lower()
				# Must match exactly: championname.wad.client
				# Reject: championname.en_us.wad.client, championname.ja_jp.wad.client, etc.
				if f_lower == target_name:
					found = Path(root) / f
					print(f"[DEBUG _find_fresh_wad] FOUND: {found}")
					return found
		
		print(f"[DEBUG _find_fresh_wad] NOT FOUND after walking directory")
		return None

	def _try_extract_wad(self, wad_path: Path, out_dir: Path, hashes_dir: Path) -> bool:
		out_dir.mkdir(parents=True, exist_ok=True)
		# Primary: pyRitoFile.wad with local hashes
		try:
			sys.path.insert(0, str(self._project_root()))
			import pyRitoFile
			from pyRitoFile import wad as pywad
			hashtables = self._load_wad_hashtables(hashes_dir)
			# Read wad and extract chunks
			w = pywad.WAD().read(str(wad_path))
			# Un-hash to filenames if tables available
			try:
				w.un_hash(hashtables)
			except Exception:
				pass
			# Stream read chunk data and write files
			from pyRitoFile.stream import BytesStream
			with BytesStream.reader(str(wad_path)) as bs:
				for chunk in w.chunks:
					try:
						chunk.read_data(bs)
						# decide filename
						filename = chunk.hash
						# ensure extension
						if '.' not in filename and chunk.extension:
							filename = f"{filename}.{chunk.extension}"
						dest = out_dir / filename.replace('\\', '/')
						dest.parent.mkdir(parents=True, exist_ok=True)
						if chunk.data is not None:
							with open(dest, 'wb') as f:
								f.write(chunk.data)
						chunk.free_data()
					except Exception:
						# continue on per-chunk errors
						continue
			return True
		except Exception:
			pass

		return False

	def _load_wad_hashtables(self, hashes_dir: Path) -> Dict[str, Dict[str, str]]:
		tables: Dict[str, Dict[str, str]] = {
			'hashes.game.txt': {},
			'hashes.lcu.txt': {},
		}
		try:
			if not hashes_dir or not hashes_dir.exists():
				return tables
			for name in list(tables.keys()):
				file_path = hashes_dir / name
				if not file_path.exists():
					continue
				with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
					for line in f:
						line = line.strip()
						if not line or line.startswith('#'):
							continue
						# expected format: "hex<space>raw"
						# split once at first space
						parts = line.split(' ', 1)
						if len(parts) != 2:
							continue
						hex_key, raw_val = parts[0].strip(), parts[1].strip()
						if hex_key and raw_val:
							tables[name][hex_key] = raw_val
		except Exception:
			pass
		return tables

	def _overlay_copy(self, src_dir: Path, dst_dir: Path) -> tuple[int, int]:
		"""Copy all files from src_dir into dst_dir, overwriting. Returns (copied, skipped)."""
		copied = 0
		skipped = 0
		src = Path(src_dir)
		dst = Path(dst_dir)
		if not src.exists():
			return (0, 0)
		for root, _dirs, files in os.walk(src):
			root_p = Path(root)
			rel = root_p.relative_to(src)
			target_root = dst / rel
			target_root.mkdir(parents=True, exist_ok=True)
			for f in files:
				src_file = root_p / f
				dst_file = target_root / f
				try:
					shutil.copy2(src_file, dst_file)
					copied += 1
				except Exception:
					skipped += 1
		return (copied, skipped)

	# Hash storage (minimal version of LtMAO hash_helper.Storage)
	class _HashStorage:
		hashtables = {}
		
		@staticmethod
		def read_all_hashes(hashes_dir: Path):
			"""Read all hashes from hashes/ directory."""
			_HashStorage = WizardApp._HashStorage
			_HashStorage.hashtables = {}
			bin_files = ['hashes.binentries.txt', 'hashes.binhashes.txt', 'hashes.bintypes.txt', 'hashes.binfields.txt']
			wad_files = ['hashes.game.txt', 'hashes.lcu.txt']
			for fname in bin_files + wad_files:
				_HashStorage.hashtables[fname] = {}
				fpath = hashes_dir / fname
				if not fpath.is_file():
					continue
				sep = 16 if fname in wad_files else 8
				with open(fpath, 'r', encoding='utf-8') as f:
					for line in f:
						if len(line) <= sep:
							continue
						key = line[:sep]
						val = line[sep+1:-1]
						_HashStorage.hashtables[fname][key] = val
		
		@staticmethod
		def free_all_hashes():
			WizardApp._HashStorage.hashtables = {}
	
	class _LocalBum:
		def __init__(self, project_root: Path):
			self._py = pyRitoFile
			self.source_dirs = []
			self.source_files = {}
			self.source_bins = {}
			self.scanned_tree = {}
			self.entry_prefix = {}
			self.entry_name = {}
			self.linked_bins = {}
		
		def unify_path(self, path: str) -> str:
			W = self._py.wad.WADHasher
			p = path.replace('\\','/').lower()
			if W.is_hash(p):
				return p
			basename = p.split('.')[0]
			if W.is_hash(basename):
				return basename
			return W.raw_to_hex(p)
		
		def add_source_dirs(self, dirs: list[str]):
			self.source_dirs += dirs
			for sd in dirs:
				for root, _dirs, files in os.walk(sd):
					for f in files:
						full = str(Path(root)/f)
						rel = Path(os.path.relpath(full, sd)).as_posix()
						u = self.unify_path(rel)
						if u not in self.source_files:
							self.source_files[u] = (full, rel)
							if rel.lower().endswith('.bin'):
								self.source_bins[u] = False
		
		def _is_character_bin(self, path):
			path = path.lower()
			if 'characters/' in path and path.endswith('.bin'):
				chars = path.split('characters/')[1].replace('.bin', '').split('/')
				return chars[0] == chars[1]
			return False
		
		def scan(self):
			"""Exact scan logic from LtMAO-hai/bumpath.py"""
			self.scanned_tree = {}
			self.scanned_tree['All_BINs'] = {}
			self.entry_prefix['All_BINs'] = 'Uneditable'
			self.entry_name['All_BINs'] = 'All_BINs'
			
			def scan_value(value, value_type, entry_hash):
				if value_type == self._py.bin.BINType.STRING:
					value_lower = value.lower()
					if 'assets/' in value_lower or 'data/' in value_lower:
						unify_file = self.unify_path(value)
						if unify_file in self.source_files:
							self.scanned_tree[entry_hash][unify_file] = (True, value)
						else:
							self.scanned_tree[entry_hash][unify_file] = (False, value)
				elif value_type in (self._py.bin.BINType.LIST, self._py.bin.BINType.LIST2):
					for v in value.data:
						scan_value(v, value_type, entry_hash)
				elif value_type in (self._py.bin.BINType.EMBED, self._py.bin.BINType.POINTER):
					if value.data != None:
						for f in value.data:
							scan_field(f, entry_hash)
			
			def scan_field(field, entry_hash):
				if field.type in (self._py.bin.BINType.LIST, self._py.bin.BINType.LIST2):
					for v in field.data:
						scan_value(v, field.value_type, entry_hash)
				elif field.type in (self._py.bin.BINType.EMBED, self._py.bin.BINType.POINTER):
					if field.data != None:
						for f in field.data:
							scan_field(f, entry_hash)
				elif field.type == self._py.bin.BINType.MAP:
					for key, value in field.data.items():
						scan_value(key, field.key_type, entry_hash)
						scan_value(value, field.value_type, entry_hash)
				elif field.type == self._py.bin.BINType.OPTION and field.value_type == self._py.bin.BINType.STRING:
					if field.data != None:
						scan_value(field.data, field.value_type, entry_hash)
				else:
					scan_value(field.data, field.type, entry_hash)
			
			def scan_bin(bin_path, unify_file):
				bin = self._py.bin.BIN().read(bin_path)
				self.linked_bins[unify_file] = []
				for link in bin.links:
					if self._is_character_bin(link):
						continue
					unify_link = self.unify_path(link)
					if unify_link in self.source_files:
						self.scanned_tree['All_BINs'][unify_link] = (True, link)
						scan_bin(self.source_files[unify_link][0], unify_link)
						self.linked_bins[unify_file].append(unify_link)
					else:
						self.scanned_tree['All_BINs'][unify_link] = (False, link)
				for entry in bin.entries:
					entry_hash = entry.hash
					self.scanned_tree[entry_hash] = {}
					self.entry_prefix[entry_hash] = 'bum'
					for field in entry.data:
						scan_field(field, entry_hash)
					if entry_hash not in self.entry_name:
						self.entry_name[entry_hash] = self._py.bin.BINHasher.hex_to_raw(WizardApp._HashStorage.hashtables, entry_hash)
			
			for unify_file in self.source_bins:
				if self.source_bins[unify_file]:
					full, rel = self.source_files[unify_file]
					self.scanned_tree['All_BINs'][unify_file] = (True, rel)
					scan_bin(full, unify_file)
			
			self.scanned_tree = dict(sorted(self.scanned_tree.items(), key=lambda item: self.entry_name[item[0]]))
		
		def _flat_list_linked_bins(self, source_unify_file, linked_bins):
			res = []
			def list_linked_bins(unify_file):
				for linked_unify_file in linked_bins[unify_file]:
					if linked_unify_file not in res and linked_unify_file != source_unify_file:
						res.append(linked_unify_file)
						list_linked_bins(linked_unify_file)
			list_linked_bins(source_unify_file)
			return res
		
		def bum(self, output_dir, ignore_missing=False, combine_linked=False):
			"""Exact bum logic from LtMAO-hai/bumpath.py"""
			def bum_value(value, value_type, entry_hash):
				if value_type == self._py.bin.BINType.STRING:
					value_lower = value.lower()
					if 'assets/' in value_lower or 'data/' in value_lower:
						unify_file = self.unify_path(value_lower)
						if unify_file in self.scanned_tree[entry_hash]:
							existed, path = self.scanned_tree[entry_hash][unify_file]
							if existed:
								# bum_path logic inlined
								if '/' in value:
									first_slash = value.index('/')
									return value[:first_slash] + f'/{self.entry_prefix[entry_hash]}' + value[first_slash:]
								else:
									return f'{self.entry_prefix[entry_hash]}/' + value
				elif value_type in (self._py.bin.BINType.LIST, self._py.bin.BINType.LIST2):
					value.data = [bum_value(v, value_type, entry_hash) for v in value.data]
				elif value_type in (self._py.bin.BINType.EMBED, self._py.bin.BINType.POINTER):
					if value.data != None:
						for f in value.data:
							bum_field(f, entry_hash)
				return value
			
			def bum_field(field, entry_hash):
				if field.type in (self._py.bin.BINType.LIST, self._py.bin.BINType.LIST2):
					field.data = [bum_value(value, field.value_type, entry_hash) for value in field.data]
				elif field.type in (self._py.bin.BINType.EMBED, self._py.bin.BINType.POINTER):
					if field.data != None:
						for f in field.data:
							bum_field(f, entry_hash)
				elif field.type == self._py.bin.BINType.MAP:
					field.data = {
						bum_value(key, field.key_type, entry_hash): bum_value(value, field.value_type, entry_hash)
						for key, value in field.data.items()
					}
				elif field.type == self._py.bin.BINType.OPTION and field.value_type == self._py.bin.BINType.STRING:
					if field.data != None:
						field.data = bum_value(field.data, field.value_type, entry_hash)
				else:
					field.data = bum_value(field.data, field.type, entry_hash)
			
			def bum_bin(bin_path):
				bin = self._py.bin.BIN().read(bin_path)
				for entry in bin.entries:
					entry_hash = entry.hash
					for field in entry.data:
						bum_field(field, entry_hash)
				bin.write(bin_path)
			
			# error checks
			if len(self.scanned_tree) == 0:
				raise Exception('bumpath: Error: No entry scanned, make sure you select at least one source BIN.')
			if not ignore_missing:
				for entry_hash in self.scanned_tree:
					for unify_file in self.scanned_tree[entry_hash]:
						existed, short_file = self.scanned_tree[entry_hash][unify_file]
						if not existed:
							raise Exception(f'bumpath: Error: {entry_hash}/{short_file} is missing/not found in Source Folders.')
			# clean up output
			shutil.rmtree(output_dir, ignore_errors=True)
			# actual bum
			bum_files = {}
			for entry_hash in self.scanned_tree:
				prefix = self.entry_prefix[entry_hash]
				for unify_file in self.scanned_tree[entry_hash]:
					existed, short_file = self.scanned_tree[entry_hash][unify_file]
					# bum outside
					if not short_file.endswith('.bin'):
						# Apply bum_path to non-bins
						if '/' in short_file:
							first_slash = short_file.index('/')
							short_file = short_file[:first_slash] + f'/{prefix}' + short_file[first_slash:]
						else:
							short_file = f'{prefix}/' + short_file
					if not existed:
						continue
					source_file = self.source_files[unify_file][0]
					output_file = os.path.join(output_dir, short_file.lower())
					if len(os.path.basename(output_file)) > 255:
						extension = os.path.splitext(short_file)[1]
						basename = self._py.wad.WADHasher.raw_to_hex(short_file)
						if extension != '':
							basename += extension
						output_file = os.path.join(output_dir, basename)
					# copy
					os.makedirs(os.path.dirname(output_file), exist_ok=True)
					shutil.copy(source_file, output_file)
					# bum inside bins
					if output_file.endswith('.bin'):
						bum_bin(output_file)
					bum_files[unify_file] = output_file
					print(f'bumpath: Finish: Bum {output_file}')
			# combine bin
			if combine_linked:
				for unify_file in self.source_bins:
					if self.source_bins[unify_file]:
						source_bin = self._py.bin.BIN().read(bum_files[unify_file])
						linked_unify_files = self._flat_list_linked_bins(unify_file, self.linked_bins)
						new_links = []
						for link in source_bin.links:
							if not self.unify_path(link) in linked_unify_files:
								new_links.append(link)
						source_bin.links = new_links
						for linked_unify_file in linked_unify_files:
							bum_file = bum_files[linked_unify_file]
							source_bin.entries += self._py.bin.BIN().read(bum_file).entries
							os.remove(bum_file)
						source_bin.write(bum_files[unify_file])
						print(f'bumpath: Finish: Combine all linked BINs to {bum_files[unify_file]}.')
			# remove empty dirs
			for root, dirs, files in os.walk(output_dir, topdown=False):
				if len(os.listdir(root)) == 0:
					os.rmdir(root)
			print(f'bumpath: Finish: Bum {output_dir}.')

	def _repath_fresh(self, fresh_unpack: Path) -> bool:
		# Load hashes before starting (from AppData, not bundled)
		hashes_dir = self._hash_dir()
		self._set_status("Loading hash tables...")
		WizardApp._HashStorage.read_all_hashes(hashes_dir)
		
		# Local repath engine
		bum = self._LocalBum(self._project_root())
		bum.add_source_dirs([str(fresh_unpack)])
		# Determine champion and desired skin index
		champ = getattr(self, '_champion', '').lower()
		desired_raw = (self.main_bin_choice.get() or '').strip()
		desired = desired_raw.lower()
		if not champ:
			self._set_status("Champion not detected from wad; cannot repath.")
			WizardApp._HashStorage.free_all_hashes()
			return False
		if not desired:
			self._set_status("Please enter a main BIN name (e.g., Skin0) before repath.")
			WizardApp._HashStorage.free_all_hashes()
			return False
		# Extract index from desired (e.g., 'skin5' -> 5), treat 'base' as 0
		import re
		if desired == 'base':
			skin_idx = '0'
		else:
			m = re.search(r"(skin)?\s*(\d+)", desired)
			skin_idx = m.group(2) if m else None
		# Search only within data/characters/<champ>/skins/**
		base_dir = fresh_unpack / 'data' / 'characters' / champ / 'skins'
		if not base_dir.exists():
			self._set_status(f"Skins folder not found: {base_dir}")
			WizardApp._HashStorage.free_all_hashes()
			return False
		selected_unify = None
		available = []
		skin_folder = None
		for root, _dirs, files in os.walk(base_dir):
			for f in files:
				if not f.lower().endswith('.bin'):
					continue
				p = Path(root) / f
				rel = Path(os.path.relpath(p, fresh_unpack)).as_posix()
				available.append(rel)
				if skin_idx is not None and skin_folder is None and f"/skins/skin{skin_idx}/" in rel.lower():
					skin_folder = Path(root)
				expected = f"{champ}_skins_skin{skin_idx}.bin" if skin_idx is not None else None
				if expected and f.lower() == expected:
					selected_unify = bum.unify_path(rel)
					break
				if selected_unify is None and desired in rel.lower():
					selected_unify = bum.unify_path(rel)
					break
			if selected_unify:
				break
		if not selected_unify and skin_folder is None and skin_idx is not None:
			cand = base_dir / f"skin{skin_idx}"
			if cand.exists():
				skin_folder = cand
		if not selected_unify and skin_folder is None:
			preview = ', '.join(available[:8]) + (', ...' if len(available) > 8 else '')
			self._set_status(f"Main BIN not found for '{desired_raw}'. Found examples: {preview}")
			WizardApp._HashStorage.free_all_hashes()
			return False
		# If exact unify not present, include all bins within skin_folder
		selected_unifys = []
		if selected_unify in bum.source_bins:
			selected_unifys = [selected_unify]
		else:
			if skin_folder is not None:
				for f in os.listdir(skin_folder):
					if f.lower().endswith('.bin'):
						rel = Path(os.path.relpath(skin_folder / f, fresh_unpack)).as_posix()
						selected_unifys.append(bum.unify_path(rel))
			if not selected_unifys and selected_unify:
				selected_unifys = [selected_unify]
		if not selected_unifys:
			self._set_status("Could not resolve selected BIN(s) to source set.")
			WizardApp._HashStorage.free_all_hashes()
			return False
		for u in selected_unifys:
			bum.source_bins[u] = True
			if u not in bum.source_files:
				cand = fresh_unpack / Path(u)
				if cand.exists():
					bum.source_files[u] = (str(cand), u)
		# Repair, scan, and bum
		fixed = 0
		for u in selected_unifys:
			try:
				bin_path = bum.source_files.get(u, (None, None))[0]
				if not bin_path:
					cand = fresh_unpack / Path(u)
					bin_path = str(cand) if cand.exists() else None
				if bin_path and str(bin_path).lower().endswith('.bin'):
					self._set_status(f"Repairing BIN before repath: {os.path.basename(bin_path)}")
					self._repair_bin_file(Path(bin_path))
					fixed += 1
			except Exception:
				pass
		self._set_status(f"Repaired {fixed} BIN(s); scanning for repath (champ={champ})...")
		bum.scan()
		# Use champion name in the repathed folder name
		output_dir = self._work_root() / f'repathed_{champ}'
		# Store the repathed folder path for later use
		self._repathed_dir = output_dir
		self._set_status("Repathing (ignore missing, combine linked)...")
		try:
			bum.bum(str(output_dir), ignore_missing=True, combine_linked=True)
			self._set_status(f"Repath done: {output_dir}")
			WizardApp._HashStorage.free_all_hashes()
			return True
		except Exception as e:
			self._set_status(f"Repath failed: {e}")
			WizardApp._HashStorage.free_all_hashes()
			return False

	def _package_repathed(self) -> bool:
		try:
			work_root = self._work_root()
			repathed_dir = work_root / 'repathed_test'
			if not repathed_dir.exists():
				self._set_status("No repathed output to package.")
				return False
			fantome = Path(self.fantome_path.get().strip())
			member = getattr(self, '_fantome_member_path', None)
			if not member:
				self._set_status("Original wad member path unknown; cannot build new fantome.")
				return False
			wad_name = Path(member).name
			# pack repathed_dir -> new wad
			new_wad_path = work_root / f"{wad_name}"
			self._set_status("Packing WAD from repathed_test...")
			self._pack_wad(repathed_dir, new_wad_path)
			# build new fantome with same structure, replacing member
			new_fantome = fantome.with_name(f"{fantome.stem}_repathed{fantome.suffix}")
			self._set_status(f"Creating new fantome: {new_fantome.name}")
			import zipfile as _zip
			with _zip.ZipFile(fantome, 'r') as zin, _zip.ZipFile(new_fantome, 'w', compression=_zip.ZIP_DEFLATED) as zout:
				for item in zin.infolist():
					data = zin.read(item.filename)
					if item.filename.replace('\\', '/') == member.replace('\\', '/'):
						# replace with new wad
						with open(new_wad_path, 'rb') as f:
							data = f.read()
						zout.writestr(item.filename, data)
					else:
						zout.writestr(item, data)
			self._set_status(f"New fantome written: {new_fantome}")
			
			# Clean up temporary folders (keep repathed_test for user inspection and missing files check)
			self._set_status("Cleaning up temporary files...")
			try:
				if (work_root / 'mod_extract').exists():
					shutil.rmtree(work_root / 'mod_extract', ignore_errors=True)
				if (work_root / 'fresh_extract').exists():
					shutil.rmtree(work_root / 'fresh_extract', ignore_errors=True)
				# DON'T delete repathed_test - user may want to check missing files
				# if (work_root / 'repathed_test').exists():
				#     shutil.rmtree(work_root / 'repathed_test', ignore_errors=True)
				if new_wad_path.exists():
					os.remove(new_wad_path)
				self._set_status(f"Done! Output: {new_fantome}. Click 'Check Missing Files' to verify.")
			except Exception as cleanup_err:
				self._set_status(f"Cleanup warning: {cleanup_err} | Output: {new_fantome}")
			
			# Mark step 3 as complete and automatically check for missing files
			self.step_completed[3] = True
			self.root.after(0, self._update_nav)
			
			# Automatically check for missing textures and move to step 5
			self.root.after(100, lambda: threading.Thread(target=self._auto_check_and_fix_missing, daemon=True).start())
			
			return True
		except Exception as e:
			self._set_status(f"Package failed: {e}")
			return False

	def _safe_cleanup_work_folder(self, work_root: Path):
		"""Safely clean up specific leftover files/folders from previous runs"""
		try:
			# Only remove specific known folders/files to avoid nuking everything
			safe_to_remove = [
				'mod_extract',
				'fresh_extract'
			]
			
			for item_name in safe_to_remove:
				item_path = work_root / item_name
				if item_path.exists() and item_path.is_dir():
					shutil.rmtree(item_path, ignore_errors=True)
			
			# Remove any repathed_* folders (champion-named folders)
			if work_root.exists():
				for item in work_root.iterdir():
					if item.is_dir() and item.name.startswith('repathed_'):
						try:
							shutil.rmtree(item, ignore_errors=True)
						except Exception:
							pass
			
			# Remove missing files reports from previous runs
			missing_txt = work_root / 'missing_files.txt'
			if missing_txt.exists():
				try:
					missing_txt.unlink()
				except Exception:
					pass
			
			missing_json = work_root / 'missing_files_report.json'
			if missing_json.exists():
				try:
					missing_json.unlink()
				except Exception:
					pass
			
			# Remove any loose .wad.client files in the root (from previous runs)
			if work_root.exists():
				for item in work_root.iterdir():
					if item.is_file():
						# Check for .wad.client or .wad.clien files
						name_lower = item.name.lower()
						if name_lower.endswith('.wad.client') or name_lower.endswith('.wad.clien'):
							try:
								item.unlink()
							except Exception:
								pass
		except Exception:
			pass  # Ignore cleanup errors, continue anyway
	
	def _detect_and_extract(self):
		try:
			champs_dir = Path(self.champions_dir.get().strip())
			fantome = Path(self.fantome_path.get().strip())
			work_root = self._work_root()
			
			# Safe cleanup of previous run leftovers
			self._set_status("Cleaning up previous run files...")
			self._safe_cleanup_work_folder(work_root)
			
			mod_dir = work_root / 'mod_extract'
			fresh_dir = work_root / 'fresh_extract'
			mod_dir.mkdir(parents=True, exist_ok=True)
			fresh_dir.mkdir(parents=True, exist_ok=True)

			self._set_status("Detecting champion .wad.client inside .fantome...")
			member = self._detect_wad_member_in_fantome(fantome, champs_dir)
			if not member:
				self.detected_wad_name.set("No champion wad found in .fantome")
				self._set_status("Aborted: .fantome does not contain a champion wad client.")
				return
			self._fantome_member_path = member
			wad_name = Path(member).name
			# store champion from wad basename (e.g., Sivir.wad.client -> sivir)
			self._champion = wad_name.split('.')[0].lower()
			self.detected_wad_name.set(f"Detected: {wad_name}")

			# extract mod wad file (using exact member path)
			self._set_status("Extracting mod .wad.client from .fantome...")
			mod_wad_path = mod_dir / wad_name
			self._extract_file_from_fantome(fantome, member, mod_wad_path)

			# find fresh wad in champions, with '.clien' → '.client' fallback
			self._set_status("Locating fresh .wad.client in Champions folder...")
			fresh_wad_file = self._find_fresh_wad(champs_dir, wad_name)
			if not fresh_wad_file.exists() and wad_name.lower().endswith('.wad.clien'):
				fixed = wad_name + 't'
				fresh_wad_file = self._find_fresh_wad(champs_dir, fixed)
				if fresh_wad_file.exists():
					wad_name = fixed
			if not fresh_wad_file.exists():
				self._set_status(f"Aborted: could not find {wad_name} under Champions folder.")
				return
			# copy fresh wad to work dir for transparency
			fresh_wad_copy = fresh_dir / wad_name
			shutil.copy2(fresh_wad_file, fresh_wad_copy)

			# attempt extraction using available tools
			# Use AppData hash directory, not bundled
			hashes_dir = self._hash_dir()

			self._set_status("Unpacking mod .wad.client (best-effort)...")
			mod_unpack = mod_dir / 'unpacked'
			ok_mod = self._try_extract_wad(mod_wad_path, mod_unpack, hashes_dir)

			self._set_status("Unpacking fresh .wad.client (best-effort)...")
			fresh_unpack = fresh_dir / 'unpacked'
			ok_fresh = self._try_extract_wad(fresh_wad_copy, fresh_unpack, hashes_dir)

			# After fresh extract, run TEX→DDS conversion using LtMAO.Ritoddstex if available
			try:
				self._set_status("Converting TEX → DDS in fresh_extract...")
				self._convert_all_tex_to_dds(fresh_unpack)
			except Exception as e:
				self._set_status(f"TEX→DDS conversion skipped: {e}")

			# Overlay: copy mod extracted content over fresh extracted content (overwrite)
			self._set_status("Overlaying mod over fresh (overwrite)...")
			copied, skipped = self._overlay_copy(mod_unpack, fresh_unpack)
			self._set_status(f"Overlay complete: copied {copied}, skipped {skipped}. Proceed to Step 3 to choose main BIN and Next to repath.")

			# Mark step 1 as complete and enable Next button
			self.step_completed[1] = True
			self.root.after(0, self._update_nav)

			# Do not repath here; wait for user to proceed to Step 3/4

			if ok_mod and ok_fresh:
				pass
			else:
				missing = []
				if not ok_mod:
					missing.append('mod')
				if not ok_fresh:
					missing.append('fresh')
				self._set_status(f"Finished with issues ({', '.join(missing)}). Files are ready for inspection. Proceed to Step 3 when ready.")
		except Exception as e:
			self._set_status(f"Error: {e}")

	def _tex2dds(self, tex_path: Path, dds_path: Path) -> None:
		# Minimal port of LtMAO.Ritoddstex.tex2dds using pyRitoFile
		sys.path.insert(0, str(self._project_root()))
		import pyRitoFile
		tex = pyRitoFile.tex.TEX().read(str(tex_path))
		dds_header = {
			'dwSize': 124,
			'dwFlags': 0x00001007,
			'dwHeight': tex.height,
			'dwWidth': tex.width,
			'dwPitchOrLinearSize': 0,
			'dwDepth': 0,
			'dwMipMapCount': 0,
			'dwReserved1': [0]*11,
			'ddspf': {
				'dwSize': 32,
				'dwFlags': 0,
				'dwFourCC': 0,
				'dwRGBBitCount': 0,
				'dwRBitMask': 0,
				'dwGBitMask': 0,
				'dwBBitMask': 0,
				'dwABitMask': 0,
			},
			'dwCaps': 0x00001000,
			'dwCaps2': 0,
			'dwCaps3': 0,
			'dwCaps4': 0,
			'dwReserved2': 0,
		}
		pf = dds_header['ddspf']
		if tex.format == pyRitoFile.tex.TEXFormat.DXT1:
			pf['dwFourCC'] = int('DXT1'.encode('ascii')[::-1].hex(), 16)
			pf['dwFlags'] = 0x00000004
		elif tex.format == pyRitoFile.tex.TEXFormat.DXT5:
			pf['dwFourCC'] = int('DXT5'.encode('ascii')[::-1].hex(), 16)
			pf['dwFlags'] = 0x00000004
		elif tex.format == pyRitoFile.tex.TEXFormat.BGRA8:
			pf['dwFlags'] = 0x00000041
			pf['dwRGBBitCount'] = 32
			pf['dwBBitMask'] = 0x000000ff
			pf['dwGBitMask'] = 0x0000ff00
			pf['dwRBitMask'] = 0x00ff0000
			pf['dwABitMask'] = 0xff000000
		else:
			raise RuntimeError(f'Unsupported TEX format: {tex.format}')
		if tex.mipmaps:
			dds_header['dwFlags'] |= 0x00020000
			dds_header['dwCaps'] |= 0x00400008
			dds_header['dwMipMapCount'] = len(tex.data)
		with pyRitoFile.stream.BytesStream.writer(str(dds_path)) as bs:
			bs.write_u32(0x20534444)
			bs.write_u32(
				dds_header['dwSize'], dds_header['dwFlags'], dds_header['dwHeight'], dds_header['dwWidth'],
				dds_header['dwPitchOrLinearSize'], dds_header['dwDepth'], dds_header['dwMipMapCount'],
				*dds_header['dwReserved1'],
				pf['dwSize'], pf['dwFlags'], pf['dwFourCC'], pf['dwRGBBitCount'], pf['dwRBitMask'], pf['dwGBitMask'], pf['dwBBitMask'], pf['dwABitMask'],
				dds_header['dwCaps'], dds_header['dwCaps2'], dds_header['dwCaps3'], dds_header['dwCaps4'], dds_header['dwReserved2']
			)
			if tex.mipmaps:
				for block_data in reversed(tex.data):
					bs.write(block_data)
			else:
				bs.write(tex.data[0])

	# ---------- TEX → DDS conversion ----------
	def _convert_all_tex_to_dds(self, root_dir: Path) -> None:
		root = Path(root_dir)
		if not root.exists():
			return
		converted = 0
		failed = 0
		for dirpath, _dirnames, filenames in os.walk(root):
			for name in filenames:
				if not name.lower().endswith('.tex'):
					continue
				tex_path = Path(dirpath) / name
				dds_path = tex_path.with_suffix('.dds')
				try:
					self._tex2dds(tex_path, dds_path)
					converted += 1
				except Exception:
					failed += 1
		self._set_status(f"TEX→DDS: converted {converted}, failed {failed}")


	def _run_repath_current(self):
		try:
			work_root = self._work_root()
			fresh_unpack = work_root / 'fresh_extract' / 'unpacked'
			if not fresh_unpack.exists():
				self._set_status("Nothing to repath. Please run extraction first.")
				return
			self._set_status("Repathing merged content...")
			repath_ok = self._repath_fresh(fresh_unpack)
			if repath_ok:
				self._set_status("Repath complete. Cleaning up temporary files...")
				# Clean up temporary extraction folders
				try:
					if (work_root / 'mod_extract').exists():
						shutil.rmtree(work_root / 'mod_extract', ignore_errors=True)
					if (work_root / 'fresh_extract').exists():
						shutil.rmtree(work_root / 'fresh_extract', ignore_errors=True)
				except Exception:
					pass
				
				# Mark step 3 as complete
				self.step_completed[3] = True
				self.root.after(0, self._update_nav)
				
				# Automatically check for missing textures and move to step 5
				self._set_status("Repath complete! Checking for missing files...")
				self.root.after(100, lambda: threading.Thread(target=self._auto_check_and_fix_missing, daemon=True).start())
			else:
				self._set_status("Repath step failed or skipped.")
		except Exception as e:
			self._set_status(f"Error: {e}")

	def _repair_bin_file(self, bin_path: Path):
		# Inline minimal FrogFixes: StaticMaterial and HealthBar fixes
		# Load BIN hash tables from AppData
		hashes_dir = self._hash_dir()
		WizardApp._HashStorage.read_all_hashes(hashes_dir)
		
		BIN = pyRitoFile.bin.BIN
		BINField = pyRitoFile.bin.BINField
		BINType = pyRitoFile.bin.BINType
		
		# Create bin_hashes dict: raw_name -> hex_hash (like CACHED_BIN_HASHES)
		# The hashtables are hex -> raw, so we need to invert them
		# Also store with capitalized first letter (CommunityDragon hashes are lowercase)
		H = {}
		for fname in ['hashes.binentries.txt', 'hashes.binhashes.txt', 'hashes.bintypes.txt', 'hashes.binfields.txt']:
			if fname in WizardApp._HashStorage.hashtables:
				for hex_hash, raw_name in WizardApp._HashStorage.hashtables[fname].items():
					H[raw_name] = hex_hash
					# Also add capitalized version for compatibility
					if raw_name and raw_name[0].islower():
						H[raw_name[0].upper() + raw_name[1:]] = hex_hash
		b = BIN().read(str(bin_path))
		# StaticMaterial fixes
		for entry in b.entries:
			if entry.type == H['StaticMaterialDef']:
				for field in entry.data:
					if field.hash == H['SamplerValues'] and isinstance(field.data, list):
						for sampler_def in field.data or []:
							if not hasattr(sampler_def, 'data') or sampler_def.data is None:
								continue
							sampler_name_entries = []
							texture_name_entries = []
							texture_path_entries = []
							for sampler_value in sampler_def.data:
								if sampler_value.hash == H['SamplerName']:
									sampler_name_entries.append(sampler_value)
								elif sampler_value.hash == H['TextureName']:
									texture_name_entries.append(sampler_value)
								elif sampler_value.hash == H['TexturePath']:
									texture_path_entries.append(sampler_value)
							# SamplerName -> TextureName
							for sampler_value in sampler_name_entries:
								sampler_value.hash = H['TextureName']
							# TextureName -> TexturePath if no TexturePath yet and looks like a path
							if texture_name_entries and not texture_path_entries:
								for tn in texture_name_entries:
									if isinstance(tn.data, str):
										data_str = tn.data.lower()
										if any(ext in data_str for ext in ['.dds', '.tga', '.png', 'assets/', 'characters/']):
											tn.hash = H['TexturePath']
		# HealthBar fixes
		HEALTHBAR_NUMBER = 12
		for entry in b.entries:
			if entry.type == H['SkinCharacterDataProperties']:
				has_hb = False
				for s_prop in entry.data:
					if getattr(s_prop, 'hash_type', None) == H['CharacterHealthBarDataRecord']:
						has_hb = True
						has_unit = False
						for inside in s_prop.data or []:
							if inside.hash == H['UnitHealthBarStyle']:
								has_unit = True
								if inside.data != HEALTHBAR_NUMBER:
									inside.data = HEALTHBAR_NUMBER
						if not has_unit:
							new_field = BINField()
							new_field.hash = H['UnitHealthBarStyle']
							new_field.type = BINType.U8
							new_field.data = HEALTHBAR_NUMBER
							s_prop.data.append(new_field)
				if not has_hb:
					uh = BINField()
					uh.hash = H['UnitHealthBarStyle']
					uh.type = BINType.U8
					uh.data = HEALTHBAR_NUMBER
					hb = BINField()
					hb.hash = H['HealthBarData']
					hb.type = BINType.Embed
					hb.hash_type = H['CharacterHealthBarDataRecord']
					hb.data = [uh]
					entry.data.append(hb)
		# write back
		b.write(str(bin_path))
		WizardApp._HashStorage.free_all_hashes()

	def _pack_wad(self, raw_dir: Path, wad_file: Path) -> None:
		# Local pack using pyRitoFile.wad (mirrors LtMAO.wad_tool.pack)
		sys.path.insert(0, str(self._project_root()))
		import pyRitoFile
		raw_dir = Path(raw_dir)
		wad_file = Path(wad_file)
		chunk_datas = []
		chunk_hashes = []
		for root, dirs, files in os.walk(raw_dir):
			for file in files:
				if file == 'hashed_files.json':
					continue
				fpath = str(Path(root) / file)
				chunk_datas.append(fpath)
				basename = Path(file).name
				relative_path = Path(fpath).relative_to(raw_dir).as_posix()
				# if basename looks hashed and located at root, keep as hash
				name_wo_ext = basename.split('.')[0]
				if pyRitoFile.wad.WADHasher.is_hash(name_wo_ext) and relative_path == basename:
					chunk_hashes.append(name_wo_ext)
				else:
					chunk_hashes.append(relative_path)
		wad = pyRitoFile.wad.WAD()
		wad.chunks = [pyRitoFile.wad.WADChunk.default() for _ in range(len(chunk_hashes))]
		wad.write(str(wad_file))
		with pyRitoFile.stream.BytesStream.updater(str(wad_file)) as bs:
			for idx, chunk in enumerate(wad.chunks):
				with open(chunk_datas[idx], 'rb') as f:
					data = f.read()
				chunk.write_data(bs, idx, chunk_hashes[idx], data, previous_chunks=wad.chunks[:idx])
				chunk.free_data()

	# ─────────────────────────────────────────────────────────────────────────────
	# Hash Management
	# ─────────────────────────────────────────────────────────────────────────────
	def _hash_dir(self) -> Path:
		"""Returns the directory where hashes are stored (AppData/FrogTools/hashes)"""
		base = Path(os.getenv('APPDATA') or Path.home() / 'AppData' / 'Roaming')
		hash_dir = base / 'FrogTools' / 'hashes'
		hash_dir.mkdir(parents=True, exist_ok=True)
		return hash_dir
	
	def _check_hashes(self):
		"""Check if all required hash files exist"""
		required = [
			'hashes.binentries.txt',
			'hashes.binfields.txt',
			'hashes.binhashes.txt',
			'hashes.bintypes.txt',
			'hashes.game.txt',
			'hashes.lcu.txt'
		]
		hash_dir = self._hash_dir()
		missing = [f for f in required if not (hash_dir / f).exists()]
		if missing:
			self.hash_status.set(f"Missing {len(missing)} hash file(s). Click Download Hashes.")
		else:
			self.hash_status.set(f"✓ All hash files present ({hash_dir})")
	
	def _download_hashes(self):
		"""Download all hash files from CommunityDragon"""
		def download_thread():
			try:
				import requests
				self.hash_status.set("Downloading hash files from CommunityDragon...")
				
				hash_urls = {
					'hashes.binentries.txt': 'https://raw.githubusercontent.com/CommunityDragon/Data/master/hashes/lol/hashes.binentries.txt',
					'hashes.binfields.txt': 'https://raw.githubusercontent.com/CommunityDragon/Data/master/hashes/lol/hashes.binfields.txt',
					'hashes.binhashes.txt': 'https://raw.githubusercontent.com/CommunityDragon/Data/master/hashes/lol/hashes.binhashes.txt',
					'hashes.bintypes.txt': 'https://raw.githubusercontent.com/CommunityDragon/Data/master/hashes/lol/hashes.bintypes.txt',
					'hashes.lcu.txt': 'https://raw.githubusercontent.com/CommunityDragon/Data/master/hashes/lol/hashes.lcu.txt',
				}
				
				hash_dir = self._hash_dir()
				downloaded = 0
				
				# Download simple files
				for filename, url in hash_urls.items():
					self.hash_status.set(f"Downloading {filename}...")
					response = requests.get(url, timeout=30)
					response.raise_for_status()
					with open(hash_dir / filename, 'wb') as f:
						f.write(response.content)
					downloaded += 1
				
				# Download hashes.game.txt (split into .0 and .1)
				self.hash_status.set("Downloading hashes.game.txt (part 1/2)...")
				part0_url = 'https://raw.githubusercontent.com/CommunityDragon/Data/master/hashes/lol/hashes.game.txt.0'
				part0 = requests.get(part0_url, timeout=30)
				part0.raise_for_status()
				
				self.hash_status.set("Downloading hashes.game.txt (part 2/2)...")
				part1_url = 'https://raw.githubusercontent.com/CommunityDragon/Data/master/hashes/lol/hashes.game.txt.1'
				part1 = requests.get(part1_url, timeout=30)
				part1.raise_for_status()
				
				# Combine and save
				with open(hash_dir / 'hashes.game.txt', 'wb') as f:
					f.write(part0.content)
					f.write(part1.content)
				downloaded += 1
				
				self.hash_status.set(f"✓ Successfully downloaded {downloaded} hash files!")
			except requests.RequestException as e:
				self.hash_status.set(f"❌ Download failed: {e}")
			except Exception as e:
				self.hash_status.set(f"❌ Error: {e}")
		
		threading.Thread(target=download_thread, daemon=True).start()
	
	def _update_hashes(self):
		"""Update existing hash files (same as download)"""
		self._download_hashes()
	
	def _open_hash_folder(self):
		"""Open the hash folder in Windows Explorer"""
		import subprocess
		hash_dir = self._hash_dir()
		try:
			subprocess.Popen(['explorer', str(hash_dir)])
		except Exception as e:
			messagebox.showerror(APP_TITLE, f"Could not open folder: {e}")
	
	def _open_work_folder(self):
		"""Open the work folder (where files are being processed) in Windows Explorer"""
		import subprocess
		work_dir = self._work_root()
		try:
			subprocess.Popen(['explorer', str(work_dir)])
		except Exception as e:
			messagebox.showerror(APP_TITLE, f"Could not open folder: {e}")
	
	def _check_missing_files(self):
		"""Check for missing files in the repathed folder (pyntex check)"""
		def check_thread():
			try:
				# Use the stored repathed directory path
				repathed_dir = getattr(self, '_repathed_dir', None)
				if not repathed_dir or not repathed_dir.exists():
					messagebox.showwarning(APP_TITLE, "No repathed folder found. Please run repath first.")
					return
				
				self._set_status("Checking for missing files in repathed folder...")
				
				# Run pyntex check
				result = self._pyntex_check_dir(repathed_dir)
				
				# Create report
				total_mentioned = sum(len(entry.get('mentioned_files', [])) for bin_results in result.values() if isinstance(bin_results, list) for entry in bin_results)
				total_missing = sum(len(entry.get('missing_files', [])) for bin_results in result.values() if isinstance(bin_results, list) for entry in bin_results)
				junk_files = result.get('junk_files', [])
				
				# Save detailed JSON report
				json_file = self._work_root() / 'missing_files_report.json'
				with open(json_file, 'w', encoding='utf-8') as f:
					json.dump(result, f, indent=4, ensure_ascii=False)
				
				# Show summary
				msg = f"Missing Files Check Complete!\n\n"
				msg += f"Total files mentioned in BINs: {total_mentioned}\n"
				msg += f"Missing files: {total_missing}\n"
				msg += f"Junk files (not referenced): {len(junk_files)}\n\n"
				msg += f"Detailed report saved to:\n{json_file}"
				
				self._set_status(f"Check complete: {total_missing} missing, {len(junk_files)} junk files. See report.")
				messagebox.showinfo("Missing Files Report", msg)
				
			except Exception as e:
				self._set_status(f"Check failed: {e}")
				messagebox.showerror(APP_TITLE, f"Error checking missing files: {e}")
		
		threading.Thread(target=check_thread, daemon=True).start()
	
	def _pyntex_check_dir(self, path: Path):
		"""Inline pyntex logic to check directory for missing files"""
		res = {}
		# list all files
		full_files = []
		for root, dirs, files in os.walk(path):
			for file in files:
				full_files.append(str(Path(root) / file).lower())
		full_files.sort()
		
		existing_files = {
			str(Path(file_path).relative_to(path)).replace('\\', '/'): True 
			for file_path in full_files
		}
		short_files = list(existing_files.keys())
		
		# Load hashes
		hashes_dir = self._hash_dir()
		WizardApp._HashStorage.read_all_hashes(hashes_dir)
		
		# Parse BIN files
		for full_file_index, full_file in enumerate(full_files):
			if full_file.endswith('.bin'):
				try:
					bin_obj = pyRitoFile.bin.BIN().read(full_file)
					bin_obj.un_hash(WizardApp._HashStorage.hashtables)
					result = self._pyntex_parse_bin(bin_obj, existing_files=existing_files)
					if len(result) > 0:
						res[short_files[full_file_index]] = result
					existing_files[short_files[full_file_index]] = False
				except Exception:
					pass
		
		WizardApp._HashStorage.free_all_hashes()
		
		if 'hashed_files.json' in existing_files:
			existing_files['hashed_files.json'] = False
		res['junk_files'] = [file for file in existing_files if existing_files[file]]
		
		return res
	
	def _pyntex_parse_bin(self, bin_obj, *, existing_files={}):
		"""Parse BIN entries to find mentioned and missing files"""
		def parse_entry(entry):
			mentioned_files = []
			missing_files = []
			
			def parse_value(value, value_type):
				if value_type == pyRitoFile.bin.BINType.STRING:
					value = str(value).lower()
					if 'assets/' in value or 'data/' in value:
						if value not in mentioned_files:
							mentioned_files.append(value)
				elif value_type in (pyRitoFile.bin.BINType.LIST, pyRitoFile.bin.BINType.LIST2):
					for v in value.data if hasattr(value, 'data') else []:
						parse_value(v, value_type)
				elif value_type in (pyRitoFile.bin.BINType.EMBED, pyRitoFile.bin.BINType.POINTER):
					if hasattr(value, 'data') and value.data is not None:
						for f in value.data:
							parse_field(f)
			
			def parse_field(field):
				if field.type in (pyRitoFile.bin.BINType.LIST, pyRitoFile.bin.BINType.LIST2):
					for v in field.data if hasattr(field, 'data') else []:
						parse_value(v, field.value_type)
				elif field.type in (pyRitoFile.bin.BINType.EMBED, pyRitoFile.bin.BINType.POINTER):
					if hasattr(field, 'data') and field.data is not None:
						for f in field.data:
							parse_field(f)
				elif field.type == pyRitoFile.bin.BINType.MAP:
					for key, value in (field.data.items() if hasattr(field, 'data') else []):
						parse_value(key, field.key_type)
						parse_value(value, field.value_type)
				elif field.type == pyRitoFile.bin.BINType.OPTION and field.value_type == pyRitoFile.bin.BINType.STRING:
					if hasattr(field, 'data') and field.data is not None:
						parse_value(field.data, field.value_type)
				else:
					parse_value(field.data, field.type)
			
			for field in entry.data:
				parse_field(field)
			
			if len(existing_files) > 0:
				for file in mentioned_files:
					path_unified = self._pyntex_unify_path(file)
					found = False
					for existing_file in existing_files:
						if path_unified == self._pyntex_unify_path(existing_file):
							existing_files[existing_file] = False
							found = True
							# Handle 2x_ and 4x_ DDS variants
							if file.endswith('.dds'):
								splits = file.split('/')
								dds2x = '/'.join(splits[:-1] + ['2x_' + splits[-1]])
								dds4x = '/'.join(splits[:-1] + ['4x_' + splits[-1]])
								if dds2x in existing_files:
									existing_files[dds2x] = False
								if dds4x in existing_files:
									existing_files[dds4x] = False
							break
					if not found:
						missing_files.append(file)
			
			dic = {}
			dic['hash'] = entry.hash
			dic['type'] = entry.type
			dic['mentioned_files'] = mentioned_files
			if len(missing_files) > 0:
				dic['missing_files'] = missing_files
			return dic
		
		results = []
		for entry in bin_obj.entries:
			dic = parse_entry(entry)
			if len(dic['mentioned_files']) > 0:
				results.append(dic)
		return results
	
	def _pyntex_unify_path(self, path: str):
		"""Unify path for comparison (handle hashed paths)"""
		# if the path is straight up hex
		if pyRitoFile.wad.WADHasher.is_hash(path):
			return path
		# if the path is hashed file 
		basename = path.split('.')[0]
		if pyRitoFile.wad.WADHasher.is_hash(basename):
			return basename
		# if the path is pure raw
		return pyRitoFile.wad.WADHasher.raw_to_hex(path)
	
	def _retry_step4(self):
		"""Restart the entire process - reset to step 0"""
		# Reset ALL step completions including step 0
		self.step_completed[0] = False
		self.step_completed[1] = False
		self.step_completed[2] = False
		self.step_completed[3] = False
		
		# Clear main BIN choice
		self.main_bin_choice.set("")
		
		# Reset status
		self.detected_wad_name.set("")
		self.s2_status_text.set("Ready to start...")
		
		# Clear any stored champion name
		if hasattr(self, '_champion'):
			delattr(self, '_champion')
		if hasattr(self, '_repathed_dir'):
			delattr(self, '_repathed_dir')
		if hasattr(self, '_fantome_member_path'):
			delattr(self, '_fantome_member_path')
		
		# Go back to step 0 (file selection)
		self._show_step(0)
		self._update_nav()
	
	def _auto_check_and_fix_missing(self):
		"""Automatically check for missing files, create placeholders, and package final fantome"""
		try:
			# Use the stored repathed directory path
			repathed_dir = getattr(self, '_repathed_dir', None)
			if not repathed_dir or not repathed_dir.exists():
				self._set_status("Error: repathed folder not found")
				return
			
			self._set_status("Checking for missing texture files...")
			
			# Run pyntex check
			result = self._pyntex_check_dir(repathed_dir)
			
			# Collect all missing files (only .dds and .tex)
			missing_textures = []
			for bin_results in result.values():
				if isinstance(bin_results, list):
					for entry in bin_results:
						for missing_file in entry.get('missing_files', []):
							# Only process .dds and .tex files
							if missing_file.lower().endswith(('.dds', '.tex')):
								if missing_file not in missing_textures:
									missing_textures.append(missing_file)
			
			# Save detailed report
			json_file = self._work_root() / 'missing_files_report.json'
			with open(json_file, 'w', encoding='utf-8') as f:
				json.dump(result, f, indent=4, ensure_ascii=False)
			
			# Create placeholders for missing textures
			if len(missing_textures) > 0:
				self._set_status(f"Found {len(missing_textures)} missing textures. Creating placeholders...")
				self._create_placeholder_textures(repathed_dir, missing_textures)
				self._set_status(f"Created {len(missing_textures)} placeholder textures.")
			else:
				self._set_status("✓ No missing texture files found!")
			
			# Automatically package final fantome
			self._set_status("Packaging final .fantome with all fixes...")
			self._create_final_fantome(repathed_dir, len(missing_textures))
			
		except Exception as e:
			self._set_status(f"Error: {e}")
	
	def _create_placeholder_textures(self, repathed_dir: Path, missing_files: list):
		"""Create placeholder invis.dds/invis.tex for missing texture files"""
		# Get bundled placeholder files
		if getattr(sys, 'frozen', False):
			# Running as EXE - placeholders are in _MEIPASS
			placeholder_dir = Path(sys._MEIPASS)
		else:
			# Running as script - placeholders are in project root
			placeholder_dir = self._project_root().parent / "League Mod Repather"
		
		invis_dds = placeholder_dir / 'invis.dds'
		invis_tex = placeholder_dir / 'invis.tex'
		
		if not invis_dds.exists() or not invis_tex.exists():
			self._set_status("Warning: Placeholder files not found. Skipping placeholder creation.")
			return
		
		created_count = 0
		for missing_file in missing_files:
			# Remove "assets/bum/" prefix if present
			clean_path = missing_file
			if clean_path.startswith('assets/bum/'):
				clean_path = clean_path[len('assets/bum/'):]
			elif clean_path.startswith('bum/'):
				clean_path = clean_path[len('bum/'):]
			
			target_file = repathed_dir / clean_path
			target_file.parent.mkdir(parents=True, exist_ok=True)
			
			try:
				if missing_file.lower().endswith('.dds'):
					shutil.copy2(invis_dds, target_file)
					created_count += 1
				elif missing_file.lower().endswith('.tex'):
					shutil.copy2(invis_tex, target_file)
					created_count += 1
			except Exception:
				pass
		
		self._set_status(f"Created {created_count} placeholder texture files.")
	
	def _create_final_fantome(self, repathed_dir: Path, missing_count: int):
		"""Create the final fantome with all fixes applied"""
		try:
			work_root = self._work_root()
			
			# Get fantome info
			fantome = Path(self.fantome_path.get().strip())
			member = getattr(self, '_fantome_member_path', None)
			if not member:
				self._set_status("Error: Original wad member path unknown")
				return
			
			wad_name = Path(member).name
			
			# Pack repathed_dir -> new wad
			final_wad_path = work_root / f"final_{wad_name}"
			self._set_status("Packing WAD from repathed folder...")
			self._pack_wad(repathed_dir, final_wad_path)
			
			# Build final fantome
			final_fantome = fantome.with_name(f"{fantome.stem}_repathed{fantome.suffix}")
			self._set_status(f"Creating final fantome: {final_fantome.name}")
			
			import zipfile as _zip
			with _zip.ZipFile(fantome, 'r') as zin, _zip.ZipFile(final_fantome, 'w', compression=_zip.ZIP_DEFLATED) as zout:
				for item in zin.infolist():
					data = zin.read(item.filename)
					# Case-insensitive comparison for WAD paths
					item_path_normalized = item.filename.replace('\\', '/').lower()
					member_path_normalized = member.replace('\\', '/').lower()
					if item_path_normalized == member_path_normalized:
						# replace with final wad
						with open(final_wad_path, 'rb') as f:
							data = f.read()
						zout.writestr(item.filename, data)
					else:
						zout.writestr(item, data)
			
			# Cleanup final wad
			if final_wad_path.exists():
				os.remove(final_wad_path)
			
			# Mark step 3 as complete
			self.step_completed[3] = True
			self.root.after(0, self._update_nav)
			
			# Enable retry button now that process is complete
			self.root.after(0, lambda: self.retry_btn.configure(state=tk.NORMAL))
			
			# Final status
			if missing_count > 0:
				self._set_status(f"✓ DONE! Created {final_fantome.name} with {missing_count} placeholder textures.")
			else:
				self._set_status(f"✓ DONE! Created {final_fantome.name} - no missing textures found.")
			
		except Exception as e:
			self._set_status(f"Error during packaging: {e}")
			# Enable retry button even on error so user can retry
			self.root.after(0, lambda: self.retry_btn.configure(state=tk.NORMAL))


def main():
	if tb:
		app = tb.Window(themename="darkly")
	else:
		app = tk.Tk()
	
	# Set window icon
	try:
		if getattr(sys, 'frozen', False):
			# Running as EXE - icon is in _MEIPASS
			icon_path = Path(sys._MEIPASS) / 'Untitled.ico'
		else:
			# Running as script - icon is in project root
			icon_path = Path(__file__).parent / 'Untitled.ico'
		
		if icon_path.exists():
			app.iconbitmap(str(icon_path))
	except Exception:
		pass  # Ignore if icon can't be set
	
	WizardApp(app)
	app.mainloop()


if __name__ == "__main__":
	main()


