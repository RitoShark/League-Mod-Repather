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
import random
import string
import re
import webbrowser

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
		self.custom_prefix = tk.StringVar()  # Custom prefix for repathing
		self.no_skin_lite_enabled = tk.BooleanVar(value=False)  # No Skin Lite checkbox
		self.merge_linked_bins_enabled = tk.BooleanVar(value=True)  # Merge Linked BINs checkbox (enabled by default)
		self.bulk_fantome_paths = []  # List of fantome paths for bulk processing

		# internal: store full member path inside .fantome
		self._fantome_member_path = None
		# internal: store HUD folder path from mod before repathing
		self._mod_hud_folder = None
		# internal: bulk processing state
		self._bulk_current_index = 0
		self._bulk_total_count = 0
		self._current_fantome_index = 0  # Current fantome being processed in bulk mode
		
		# Step completion tracking (5 steps now: 0, 1, 2, 3, 4)
		self.step_completed = [False, False, False, False, False]  # Track if each step is completed

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
	
	def _generate_random_prefix(self):
		"""Generate a random prefix by picking one cool word from League hashes."""
		# Curated list of cool words from hashes.binhashes.txt
		cool_words = [
			'fire', 'ice', 'storm', 'shadow', 'light', 'dark', 'void', 'star',
			'moon', 'blood', 'steel', 'frost', 'flame', 'thunder', 'wind', 'dragon',
			'blade', 'spirit', 'chaos', 'magic', 'crystal', 'poison', 'mystic',
			'cosmic', 'royal', 'wild', 'rage', 'fury', 'power', 'death'
		]
		
		# Pick one random word
		return random.choice(cool_words)
	
	def _show_no_skin_lite_info(self):
		"""Show information about No Skin Lite feature"""
		info_text = (
			"No Skin Lite Feature\n\n"
			"When enabled, this will:\n"
			"• Take your selected Base/Skin0\n"
			"• Copy it to all other skin slots (1-99)\n"
			"• Make every skin look like the base skin\n\n"
			"Example: If you select Skin0/Base, all skins (Skin1-Skin99) will become Skin0.\n\n"
			"⚠️ IMPORTANT: ONLY works with Base/Skin0 selection, NOT Skin1+.\n"
			"This prevents skin hacking by ensuring only base skin is copied.\n\n"
			"This is useful for:\n"
			"• Creating 'no skin' mods where everything uses base skin\n"
			"• Simplifying skin selection in-game\n"
			"• Ensuring all skins show the base appearance"
		)
		messagebox.showinfo("No Skin Lite Info", info_text)
	
	def _show_merge_linked_bins_info(self):
		"""Show information about Merge Linked BINs feature"""
		info_text = (
			"Merge Linked BINs Feature\n\n"
			"When enabled, this will:\n"
			"• Extract linked BIN paths from fresh (unmodified) game files\n"
			"• Add those linked BIN paths to your mod's BIN file\n"
			"• The repather will automatically combine all linked BINs\n\n"
			"🔧 This can potentially repair broken skins that cause crashes!\n\n"
			"Common issues this fixes:\n"
			"• Game crashes when using certain abilities (e.g., Yone E)\n"
			"• Missing entries in linked BINs that cause errors\n"
			"• Outdated mods that are missing newer linked BIN entries\n\n"
			"How it works:\n"
			"• Fresh game files contain updated linked BIN paths\n"
			"• These paths are added to your mod BIN's links list\n"
			"• The repather combines all linked BINs automatically\n"
			"• Missing entries from newer game versions are included\n\n"
			"💡 Recommended: Keep this enabled unless you have a specific reason to disable it."
		)
		messagebox.showinfo("Merge Linked BINs Info", info_text)

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
		self._label(row2, text="Your mod:").pack(side=tk.LEFT)
		self.mod_folder_path = tk.StringVar()
		e2 = self._entry(row2, textvariable=self.fantome_path, width=80)
		e2.pack(side=tk.LEFT, padx=8, fill=tk.X, expand=True)
		self._button(row2, text="Browse", command=self._pick_mod).pack(side=tk.LEFT)
		
		# Hint label
		mod_hint = self._label(s1, text="💡 Select .fantome file(s) or a mod folder - You can select multiple .fantome files for bulk processing", 
		                       font=('Arial', 8), foreground='gray')
		mod_hint.pack(anchor=tk.W, padx=12, pady=(0, 6))

		# Prefix Input Section
		row3 = self._frame(s1)
		row3.pack(fill=tk.X, padx=12, pady=6)
		self._label(row3, text="Custom Prefix:").pack(side=tk.LEFT)
		e3 = self._entry(row3, textvariable=self.custom_prefix, width=80)
		e3.pack(side=tk.LEFT, padx=8, fill=tk.X, expand=True)
		
		# Hint label below prefix input
		prefix_hint = self._label(s1, text="💡 Leave empty for random prefix (e.g., 'shadow', 'dragon', 'void'). Enter custom prefix (e.g., 'mymod', 'custom') for consistent naming.", 
		                          font=('Arial', 8), foreground='gray')
		prefix_hint.pack(anchor=tk.W, padx=12, pady=(0, 6))

		# No Skin Lite checkbox with info icon
		row4 = self._frame(s1)
		row4.pack(fill=tk.X, padx=12, pady=6)
		
		if tb:
			no_skin_checkbox = tb.Checkbutton(row4, text="No Skin Lite", variable=self.no_skin_lite_enabled)
		else:
			no_skin_checkbox = tk.Checkbutton(row4, text="No Skin Lite", variable=self.no_skin_lite_enabled)
		no_skin_checkbox.pack(side=tk.LEFT)
		
		# Info button with tooltip
		info_btn = self._button(row4, text="ℹ️", width=3, command=self._show_no_skin_lite_info)
		info_btn.pack(side=tk.LEFT, padx=4)
		
		# Hint label for No Skin Lite
		no_skin_hint = self._label(s1, text="💡 Copies Base/Skin0 to all other skin slots (1-99) - ONLY works with Base/Skin0 to prevent skin hacking", 
		                            font=('Arial', 8), foreground='gray')
		no_skin_hint.pack(anchor=tk.W, padx=12, pady=(0, 6))
		
		# Merge Linked BINs checkbox with info icon
		row5 = self._frame(s1)
		row5.pack(fill=tk.X, padx=12, pady=6)
		
		if tb:
			merge_linked_checkbox = tb.Checkbutton(row5, text="Merge Linked BINs", variable=self.merge_linked_bins_enabled)
		else:
			merge_linked_checkbox = tk.Checkbutton(row5, text="Merge Linked BINs", variable=self.merge_linked_bins_enabled)
		merge_linked_checkbox.pack(side=tk.LEFT)
		
		# Info button with tooltip
		merge_linked_info_btn = self._button(row5, text="ℹ️", width=3, command=self._show_merge_linked_bins_info)
		merge_linked_info_btn.pack(side=tk.LEFT, padx=4)
		
		# Hint label for Merge Linked BINs
		merge_linked_hint = self._label(s1, text="💡 Adds linked BIN paths from fresh game files to mod BIN - can repair broken skins that cause crashes (e.g., Yone E)", 
		                                 font=('Arial', 8), foreground='gray')
		merge_linked_hint.pack(anchor=tk.W, padx=12, pady=(0, 6))

		self.steps.append(s1)

		# Step 2: Quick Extract (automatic - populates BIN dropdown)
		s2 = self._frame(self.container)
		self._label(s2, text="Step 2 — Quick Extract (Detecting available BINs)").pack(anchor=tk.W, padx=12, pady=(12, 6))
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

		# Step 3: Select Main BIN (user must choose before full extraction)
		s3 = self._frame(self.container)
		self._label(s3, text="Step 3 — Select Main BIN").pack(anchor=tk.W, padx=12, pady=(12, 6))
		self._label(s3, text="Detected wad:").pack(anchor=tk.W, padx=12, pady=(0, 4))
		self._copyable_entry(s3, self.detected_wad_name, width=100).pack(fill=tk.X, padx=12, pady=(0, 8))
		
		# BIN selection
		bin_row = self._frame(s3)
		bin_row.pack(fill=tk.X, padx=12, pady=6)
		self._label(bin_row, text="Main BIN:").pack(side=tk.LEFT)
		
		# Use Combobox for BIN selection (dropdown + manual entry)
		if tb:
			self.bin_combo = tb.Combobox(bin_row, textvariable=self.main_bin_choice, width=30)
		else:
			# Fallback for vanilla tkinter
			from tkinter import ttk
			self.bin_combo = ttk.Combobox(bin_row, textvariable=self.main_bin_choice, width=30)
		self.bin_combo.pack(side=tk.LEFT, padx=8)
		
		# Hint label
		bin_hint = self._label(s3, text="💡 Select from dropdown or type manually (e.g., Skin0, Skin5, Base). This will be used to extract and merge linked BINs.", 
		                       font=('Arial', 8), foreground='gray')
		bin_hint.pack(anchor=tk.W, padx=12, pady=(0, 6))
		
		# Paid skin warning and link
		paid_skin_frame = self._frame(s3)
		paid_skin_frame.pack(fill=tk.X, padx=12, pady=(0, 6))
		paid_skin_warning = self._label(paid_skin_frame, 
		                                text="⚠️ IMPORTANT: If you're using a paid skin, you need to select the correct Skin ID. ", 
		                                font=('Arial', 9), foreground='orange')
		paid_skin_warning.pack(anchor=tk.W)
		
		# Link to skin explorer
		link_frame = self._frame(s3)
		link_frame.pack(fill=tk.X, padx=12, pady=(0, 6))
		link_label = self._label(link_frame, text="🔗 Find your skin ID here: ", font=('Arial', 9))
		link_label.pack(side=tk.LEFT)
		
		def open_skin_explorer():
			webbrowser.open("https://sirdexal.pages.dev/skin-explorer")
		
		link_button = self._button(link_frame, text="Skin Explorer", command=open_skin_explorer, width=15)
		link_button.pack(side=tk.LEFT, padx=(0, 8))
		
		# Example image
		try:
			# Handle both development and PyInstaller bundled mode
			if getattr(sys, 'frozen', False):
				# Running as compiled exe - image is in _MEIPASS or same directory as exe
				example_img_path = Path(sys.executable).parent / 'example.png'
				if not example_img_path.exists():
					example_img_path = Path(sys._MEIPASS) / 'example.png'
			else:
				# Running as script - image is in project root
				example_img_path = Path(__file__).parent / 'example.png'
			
			if example_img_path.exists():
				try:
					from PIL import Image, ImageTk
					img = Image.open(example_img_path)
					# Resize image to fit (max width 600px, maintain aspect ratio)
					max_width = 600
					if img.width > max_width:
						ratio = max_width / img.width
						new_height = int(img.height * ratio)
						img = img.resize((max_width, new_height), Image.Resampling.LANCZOS)
					
					photo = ImageTk.PhotoImage(img)
					img_label = tk.Label(s3, image=photo)
					img_label.image = photo  # Keep a reference
					img_label.pack(padx=12, pady=(0, 6))
				except ImportError:
					# PIL not available, try tkinter's built-in PhotoImage
					try:
						photo = tk.PhotoImage(file=str(example_img_path))
						img_label = tk.Label(s3, image=photo)
						img_label.image = photo  # Keep a reference
						img_label.pack(padx=12, pady=(0, 6))
					except Exception:
						pass
		except Exception as e:
			# If image loading fails, just skip it
			print(f"[DEBUG] Could not load example image: {e}")
		
		# Open work folder button
		s3_btn_frame = self._frame(s3)
		s3_btn_frame.pack(pady=8)
		self._button(s3_btn_frame, text="📁 Open Work Folder", command=self._open_work_folder, width=20).pack()
		self.steps.append(s3)

		# Step 4: Full extraction with selected BIN (extracts linked BINs for the selected BIN)
		s4 = self._frame(self.container)
		self._label(s4, text="Step 4 — Full Extraction with Linked BINs").pack(anchor=tk.W, padx=12, pady=(12, 6))
		self._label(s4, text="Status:").pack(anchor=tk.W, padx=12, pady=(0, 4))
		self.s4_status = self._copyable_entry(s4, self.s2_status_text, width=100)
		self.s4_status.pack(fill=tk.X, padx=12, pady=(0, 8))
		# Open work folder button
		s4_btn_frame = self._frame(s4)
		s4_btn_frame.pack(pady=8)
		self._button(s4_btn_frame, text="📁 Open Work Folder", command=self._open_work_folder, width=20).pack()
		self.steps.append(s4)

		# Step 5: Repath & package (with automatic placeholder fixing)
		s5 = self._frame(self.container)
		self._label(s5, text="Step 5 — Repath, Fix Missing Files & Package").pack(anchor=tk.W, padx=12, pady=(12, 6))
		self._label(s5, text="Status:").pack(anchor=tk.W, padx=12, pady=(0, 4))
		self._copyable_entry(s5, self.s2_status_text, width=100).pack(fill=tk.X, padx=12, pady=(0, 8))
		# Buttons for Step 5
		s5_btn_frame = self._frame(s5)
		s5_btn_frame.pack(pady=8)
		self._button(s5_btn_frame, text="📁 Open Work Folder", command=self._open_work_folder, width=20).pack(side=tk.LEFT, padx=4)
		self.retry_btn = self._button(s5_btn_frame, text="🔄 Refresh / Retry", command=self._retry_step4, width=20)
		self.retry_btn.pack(side=tk.LEFT, padx=4)
		self.retry_btn.configure(state=tk.DISABLED)  # Disabled until process completes
		self.steps.append(s5)

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
		
		# Disable Next button if current step is not completed
		# Exception: step 0 (validates on click) and step 2 (BIN selection - validates on click)
		if self.current_step > 0 and self.current_step != 2 and not self.step_completed[self.current_step]:
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
			# Check if bulk processing (multiple fantome files)
			if self.bulk_fantome_paths and len(self.bulk_fantome_paths) > 1:
				# Bulk processing mode - automatically use Skin0 and process all files
				self.main_bin_choice.set("Skin0")  # Auto-set to Skin0 for bulk processing
				self._show_step(1)
				t = threading.Thread(target=self._process_bulk_fantomes, daemon=True)
				t.start()
			else:
				# Single file mode - do quick extraction to populate BIN dropdown
				self._show_step(1)
				t = threading.Thread(target=self._quick_extract_for_bin_selection, daemon=True)
				t.start()
		elif self.current_step == 1:
			# Can't proceed from step 1 if quick extraction isn't complete
			if not self.step_completed[1]:
				messagebox.showwarning(APP_TITLE, "Please wait for quick extraction to complete before proceeding.")
				return
			# Step 1 -> Step 2: Show BIN selection
			self._show_step(2)
		elif self.current_step == 2:
			# Step 2: Validate BIN selection before proceeding
			if not self.main_bin_choice.get().strip():
				messagebox.showwarning(APP_TITLE, "Please select a main BIN before proceeding.")
				return
			# Step 2 -> Step 3: Proceed to full extraction with selected BIN
			self._show_step(3)
			t = threading.Thread(target=self._detect_and_extract_with_bin, daemon=True)
			t.start()
		elif self.current_step == 3:
			# Can't proceed from step 3 if full extraction isn't complete
			if not self.step_completed[3]:
				messagebox.showwarning(APP_TITLE, "Please wait for full extraction to complete before proceeding.")
				return
			# Step 3 -> Step 4: run repath now using selected main_bin_choice
			self._show_step(4)
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

	def _pick_mod(self):
		"""Unified file picker that handles both .fantome files and folders"""
		# Create custom dialog
		dialog = tk.Toplevel(self.root)
		dialog.title(APP_TITLE)
		dialog.geometry("400x180")
		dialog.resizable(False, False)
		dialog.transient(self.root)
		dialog.grab_set()
		
		# Center the dialog
		dialog.update_idletasks()
		x = (dialog.winfo_screenwidth() // 2) - (400 // 2)
		y = (dialog.winfo_screenheight() // 2) - (180 // 2)
		dialog.geometry(f"400x180+{x}+{y}")
		
		result = {'choice': None}
		
		# Message
		msg = tk.Label(dialog, text="Select mod type:", font=("Segoe UI", 12, "bold"))
		msg.pack(pady=(30, 20))
		
		# Button frame
		btn_frame = tk.Frame(dialog)
		btn_frame.pack(pady=10)
		
		def choose_fantome():
			result['choice'] = 'fantome'
			dialog.destroy()
		
		def choose_folder():
			result['choice'] = 'folder'
			dialog.destroy()
		
		# Buttons
		fantome_btn = tk.Button(btn_frame, text=".fantome File", command=choose_fantome, 
								width=15, height=2, font=("Segoe UI", 10))
		fantome_btn.pack(side=tk.LEFT, padx=10)
		
		folder_btn = tk.Button(btn_frame, text="Mod Folder", command=choose_folder,
							   width=15, height=2, font=("Segoe UI", 10))
		folder_btn.pack(side=tk.LEFT, padx=10)
		
		dialog.wait_window()
		
		if result['choice'] == 'fantome':
			# Pick .fantome file(s) - allow multiple selection
			paths = filedialog.askopenfilenames(
				title="Select .fantome file(s) - You can select multiple files",
				filetypes=[("Fantome", "*.fantome"), ("Zip", "*.zip"), ("All", "*.*")]
			)
			if paths:
				self.bulk_fantome_paths = list(paths)
				if len(paths) == 1:
					self.fantome_path.set(paths[0])
					self.mod_folder_path.set("")
				else:
					# Show "X files selected" in the entry field
					self.fantome_path.set(f"{len(paths)} files selected: {', '.join([Path(p).name for p in paths[:3]])}{'...' if len(paths) > 3 else ''}")
					self.mod_folder_path.set("")
		elif result['choice'] == 'folder':
			# Pick folder
			path = filedialog.askdirectory(title="Select mod folder")
			if path:
				self.fantome_path.set(path)
				self.mod_folder_path.set(path)

	def _validate_inputs(self) -> bool:
		champs = self.champions_dir.get().strip()
		fantome = self.fantome_path.get().strip()
		mod_folder = self.mod_folder_path.get().strip()
		
		if not champs or not os.path.isdir(champs):
			messagebox.showerror(APP_TITLE, "Please select a valid Champions folder.")
			return False
		# persist on successful validation of champs path
		try:
			self._save_config()
		except Exception:
			pass
		
		# Check if we have bulk fantome paths (multiple files selected)
		if self.bulk_fantome_paths:
			# Validate all bulk paths
			for path in self.bulk_fantome_paths:
				if not os.path.isfile(path):
					messagebox.showerror(APP_TITLE, f"Invalid file: {path}")
					return False
				if not (path.lower().endswith(".fantome") or path.lower().endswith(".zip")):
					messagebox.showerror(APP_TITLE, f"File must be a .fantome or .zip archive: {Path(path).name}")
					return False
			return True
		
		# Check if either fantome OR mod folder is provided (not both, unless they're the same path for folder mode)
		if fantome and mod_folder and fantome != mod_folder:
			messagebox.showerror(APP_TITLE, "Please select EITHER a .fantome file OR a mod folder, not both.")
			return False
		
		if fantome and os.path.isfile(fantome):
			# Validate fantome file
			if not (fantome.lower().endswith(".fantome") or fantome.lower().endswith(".zip")):
				messagebox.showerror(APP_TITLE, "File must be a .fantome or .zip archive.")
				return False
		elif mod_folder or (fantome and os.path.isdir(fantome)):
			# Validate mod folder
			if not os.path.isdir(mod_folder):
				messagebox.showerror(APP_TITLE, "Please select a valid mod folder.")
				return False
			# Champion name will be auto-detected from folder structure
		else:
			# Neither provided
			messagebox.showerror(APP_TITLE, "Please select either a .fantome file or a mod folder.")
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
	
	def _is_valid_binary_bin(self, bin_path: Path) -> bool:
		"""
		Check if a file is a valid binary BIN file (PROP or PTCH signature).
		Returns False for text-based BIN files (like #PROP_text format).
		"""
		try:
			with open(bin_path, 'rb') as f:
				signature = f.read(4).decode('utf-8', errors='ignore')
				return signature in ('PROP', 'PTCH')
		except Exception:
			return False

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
		for wad_member in non_language_wads:
			# Extract just the filename (e.g., "Kayn.wad.client" from "WAD/Kayn.wad.client")
			wad_filename = wad_member.split('/')[-1]
			
			# Check if this WAD exists in the Champions folder (case-insensitive match)
			matching_wad = self._find_fresh_wad(champions_dir, wad_filename)
			# Check if not None (function returns None when not found)
			exists = matching_wad is not None
			
			if exists:
				# Found a champion WAD!
				matched_wads.append((wad_member, wad_filename))
		
		# If we found champion WADs, return the first one
		if matched_wads:
			return matched_wads[0][0]
		
		# If no champion WAD found, return empty (don't use fallback to avoid wrong WAD)
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
		# Primary: pyRitoFile.wad with local hashes (mirrors LtMAO wad_tool.unpack)
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
			
			hashed_files = {}  # Track files that had to be hashed due to path length
			
			# Create directories first (like LtMAO does)
			from pyRitoFile.stream import BytesStream
			with BytesStream.reader(str(wad_path)) as bs:
				for chunk in w.chunks:
					file_path = str(out_dir / chunk.hash.replace('\\', '/'))
					dir_path = os.path.dirname(file_path)
					try:
						os.makedirs(dir_path, exist_ok=True)
					except Exception:
						pass  # Continue anyway, file creation will handle it
			
			# Actual extract
			with BytesStream.reader(str(wad_path)) as bs:
				for chunk in w.chunks:
					try:
						chunk.read_data(bs)
						
						# Output file path of this chunk
						file_path = str(out_dir / chunk.hash.replace('\\', '/'))
						
						# Add extension to hashed file if known
						if pyRitoFile.wad.WADHasher.is_hash(chunk.hash) and chunk.extension:
							ext = f'.{chunk.extension}'
							if not file_path.endswith(ext):
								file_path += ext
						
						# Check if file should be hashed (like LtMAO)
						should_be_hashed = False
						# Hash file with long basename (>255 chars Windows limit)
						if len(os.path.basename(file_path)) > 255:
							should_be_hashed = True
						# Hash file if same name as directory
						if os.path.exists(file_path) and os.path.isdir(file_path):
							should_be_hashed = True
						
						if should_be_hashed:
							basename = pyRitoFile.wad.WADHasher.raw_to_hex(chunk.hash)
							if chunk.extension:
								basename += f'.{chunk.extension}'
							hashed_file = str(out_dir / basename)
							hashed_files[basename] = chunk.hash
							file_path = hashed_file
						
						# Write out chunk data to file
						try:
							os.makedirs(os.path.dirname(file_path), exist_ok=True)
							if chunk.data is not None:
								with open(file_path, 'wb') as f:
									f.write(chunk.data)
						except (FileNotFoundError, OSError) as e:
							# Handle path length issues - try fallback with hashed name
							if len(file_path) > 200:  # Windows path limit safety
								basename = pyRitoFile.wad.WADHasher.raw_to_hex(chunk.hash)
								if chunk.extension:
									basename += f'.{chunk.extension}'
								short_file_path = str(out_dir / basename)
								hashed_files[basename] = chunk.hash
								try:
									os.makedirs(os.path.dirname(short_file_path), exist_ok=True)
									if chunk.data is not None:
										with open(short_file_path, 'wb') as f:
											f.write(chunk.data)
								except Exception:
									continue  # Skip this file if we can't write it
							else:
								continue  # Skip on other errors
						
						chunk.free_data()
					except Exception:
						# continue on per-chunk errors
						continue
			
			# Remove empty dirs (like LtMAO does)
			for root, dirs, files in os.walk(out_dir, topdown=False):
				if len(os.listdir(root)) == 0:
					try:
						os.rmdir(root)
					except Exception:
						pass
			
			# Write hashed_files.json to track mappings (like LtMAO does)
			if len(hashed_files) > 0:
				hashed_files_json = out_dir / 'hashed_files.json'
				with open(hashed_files_json, 'w', encoding='utf-8') as f:
					json.dump(hashed_files, f, indent=4, ensure_ascii=False)
			
			return True
		except Exception as e:
			print(f"[DEBUG] WAD extraction error: {e}")
			import traceback
			traceback.print_exc()
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

	def _extract_hashes_from_folder(self, folder: Path, hashes_dir: Path):
		"""Extract hashes from BIN files in the mod folder and update user's hash files"""
		try:
			# Prepare hash tables
			wad_hash = pyRitoFile.wad.WADHasher.raw_to_hex
			start_game_path = ['assets/', 'clientstates/', 'data/', 'levels/', 'maps/', 'uiautoatlas/', 'ux/']
			
			hashtables = {
				'hashes.binentries.txt': {},
				'hashes.binhashes.txt': {},
				'hashes.game.txt': {}
			}
			
			def extract_file_value(value, value_type):
				if value_type == pyRitoFile.bin.BINType.STRING:
					value_str = str(value).lower()
					if any(value_str.startswith(prefix) for prefix in start_game_path):
						hash_key = wad_hash(value_str)
						hashtables['hashes.game.txt'][hash_key] = value_str
						# Also add 2x_ and 4x_ variants for DDS files
						if value_str.endswith('.dds'):
							parts = value_str.split('/')
							basename = parts[-1]
							dirname = '/'.join(parts[:-1])
							value2x = f'{dirname}/2x_{basename}'
							value4x = f'{dirname}/4x_{basename}'
							hashtables['hashes.game.txt'][wad_hash(value2x)] = value2x
							hashtables['hashes.game.txt'][wad_hash(value4x)] = value4x
				elif value_type in (pyRitoFile.bin.BINType.LIST, pyRitoFile.bin.BINType.LIST2):
					if hasattr(value, 'data'):
						for v in value.data:
							extract_file_value(v, value_type)
				elif value_type in (pyRitoFile.bin.BINType.EMBED, pyRitoFile.bin.BINType.POINTER):
					if hasattr(value, 'data') and value.data is not None:
						for f in value.data:
							extract_file_field(f)
			
			def extract_file_field(field):
				if field.type in (pyRitoFile.bin.BINType.LIST, pyRitoFile.bin.BINType.LIST2):
					for v in field.data:
						extract_file_value(v, field.value_type)
				elif field.type in (pyRitoFile.bin.BINType.EMBED, pyRitoFile.bin.BINType.POINTER):
					if field.data is not None:
						for f in field.data:
							extract_file_field(f)
				elif field.type == pyRitoFile.bin.BINType.MAP:
					for key, value in field.data.items():
						extract_file_value(key, field.key_type)
						extract_file_value(value, field.value_type)
				elif field.type == pyRitoFile.bin.BINType.OPTION and field.value_type == pyRitoFile.bin.BINType.STRING:
					if field.data is not None:
						extract_file_value(field.data, field.value_type)
				else:
					extract_file_value(field.data, field.type)
			
			# Scan all BIN files in the folder
			bin_count = 0
			for root, _dirs, files in os.walk(folder):
				for file in files:
					if file.lower().endswith('.bin'):
						bin_path = Path(root) / file
						try:
							# Check if file is a valid binary BIN file
							if not self._is_valid_binary_bin(bin_path):
								continue
							
							bin_obj = pyRitoFile.bin.BIN().read(str(bin_path))
							# Extract file references from BIN
							for entry in bin_obj.entries:
								for field in entry.data:
									extract_file_field(field)
							# Extract from links
							for link in bin_obj.links:
								extract_file_value(link, pyRitoFile.bin.BINType.STRING)
							bin_count += 1
						except Exception:
							pass  # Skip problematic BINs
			
			# Update user's hash files
			if bin_count > 0:
				for filename, new_hashes in hashtables.items():
					if len(new_hashes) == 0:
						continue
					
					hash_file = hashes_dir / filename
					existing_hashes = {}
					
					# Read existing hashes
					if hash_file.exists():
						try:
							with open(hash_file, 'r', encoding='utf-8') as f:
								sep = 16 if filename in ['hashes.game.txt', 'hashes.lcu.txt'] else 8
								for line in f:
									if len(line) > sep:
										key = line[:sep]
										val = line[sep+1:-1]
										existing_hashes[key] = val
						except Exception:
							pass
					
					# Merge new hashes
					existing_hashes.update(new_hashes)
					
					# Write back sorted
					try:
						with open(hash_file, 'w', encoding='utf-8') as f:
							for key, value in sorted(existing_hashes.items(), key=lambda item: item[1]):
								f.write(f'{key} {value}\n')
					except Exception:
						pass
				
				self._set_status(f"✓ Extracted hashes from {bin_count} BIN files")
			else:
				self._set_status("No BIN files found for hash extraction")
		
		except Exception as e:
			print(f"[DEBUG] Hash extraction error: {e}")
			raise
	
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
	
	def _copy_vo_files_original(self, src_dir: Path, dst_dir: Path) -> int:
		"""Copy VO files from src_dir to dst_dir with original paths (no prefix, no hashing)."""
		vo_count = 0
		src = Path(src_dir)
		dst = Path(dst_dir)
		if not src.exists():
			return 0
		for root, _dirs, files in os.walk(src):
			root_p = Path(root)
			rel = root_p.relative_to(src).as_posix()
			rel_lower = rel.lower()
			# Only process VO directory
			if 'assets/sounds/wwise2016/vo/' not in rel_lower:
				continue
			for f in files:
				# Copy all VO-related files (.bnk, .wem, .wpk, and any other files in VO directory)
				# Common VO file extensions
				if not f.lower().endswith(('.bnk', '.wem', '.wpk', '.bnk.client', '.wem.client')):
					# Skip non-VO files (but be permissive - copy most files in VO directory)
					continue
				src_file = root_p / f
				# Keep original path structure
				dst_file = dst / rel / f
				try:
					dst_file.parent.mkdir(parents=True, exist_ok=True)
					shutil.copy2(src_file, dst_file)
					vo_count += 1
				except Exception as e:
					print(f"[DEBUG] Failed to copy VO file {src_file}: {e}")
		return vo_count
	
	def _store_mod_hud_folder(self, mod_unpack: Path, champion: str) -> None:
		"""Store the HUD folder from mod before repathing so we can restore it later with prefix."""
		champ = champion.lower() if champion else ''
		if not champ:
			return
		
		# Look for HUD folder in mod: assets/characters/{champion}/hud
		hud_path = mod_unpack / 'assets' / 'characters' / champ / 'hud'
		
		if hud_path.exists() and hud_path.is_dir():
			self._mod_hud_folder = hud_path
			print(f"[DEBUG] Stored mod HUD folder: {hud_path}")
		else:
			# Try alternative paths (case-insensitive search)
			assets_chars = mod_unpack / 'assets' / 'characters'
			if assets_chars.exists():
				for char_dir in assets_chars.iterdir():
					if char_dir.is_dir() and char_dir.name.lower() == champ:
						alt_hud = char_dir / 'hud'
						if alt_hud.exists() and alt_hud.is_dir():
							self._mod_hud_folder = alt_hud
							print(f"[DEBUG] Stored mod HUD folder (alt path): {alt_hud}")
							break
	
	def _fix_hud_paths_in_bin(self, bin_path: Path) -> tuple[bool, int]:
		"""
		Fix HUD texture paths in BIN file: change .dds to .tex if found.
		Returns (modified, count_of_changes).
		"""
		if not bin_path or not bin_path.exists():
			return (False, 0)
		
		changes_count = 0
		modified = False
		
		try:
			# Check if file is a valid binary BIN file
			if not self._is_valid_binary_bin(bin_path):
				print(f"[DEBUG] Skipping text-based BIN file: {bin_path}")
				return (False, 0)
			
			import pyRitoFile
			bin_obj = pyRitoFile.bin.BIN().read(str(bin_path))
			print(f"[DEBUG] Reading BIN file: {bin_path}")
			print(f"[DEBUG] BIN has {len(bin_obj.entries)} entries")
			
			def fix_value(value, value_type, path_context=""):
				nonlocal changes_count, modified
				if value_type == pyRitoFile.bin.BINType.STRING:
					if isinstance(value, str):
						value_lower = value.lower()
						# Look for HUD-related paths with .dds
						if 'hud' in value_lower and '.dds' in value_lower:
							# Check if it's a HUD-related texture (iconCircle, iconSquare, etc.)
							if any(keyword in value_lower for keyword in ['icon', 'circle', 'square', 'hud']):
								# Replace .dds with .tex (case-insensitive)
								original = value
								# Replace .dds with .tex (preserve case)
								if '.DDS' in value:
									value = value.replace('.DDS', '.TEX')
								else:
									value = value.replace('.dds', '.tex')
								if value != original:
									changes_count += 1
									modified = True
									print(f"[DEBUG] Fixed HUD path in BIN ({path_context}): {original} -> {value}")
								return value
				elif value_type in (pyRitoFile.bin.BINType.LIST, pyRitoFile.bin.BINType.LIST2):
					if hasattr(value, 'data'):
						value.data = [fix_value(v, value_type, path_context) for v in value.data]
				elif value_type in (pyRitoFile.bin.BINType.EMBED, pyRitoFile.bin.BINType.POINTER):
					if hasattr(value, 'data') and value.data is not None:
						for f in value.data:
							fix_field(f, path_context)
				return value
			
			def fix_field(field, path_context=""):
				nonlocal changes_count, modified
				field_hash = getattr(field, 'hash', 'unknown')
				current_context = f"field:{field_hash}"
				
				if field.type in (pyRitoFile.bin.BINType.LIST, pyRitoFile.bin.BINType.LIST2):
					if hasattr(field, 'data'):
						field.data = [fix_value(v, field.value_type, current_context) for v in field.data]
				elif field.type in (pyRitoFile.bin.BINType.EMBED, pyRitoFile.bin.BINType.POINTER):
					if hasattr(field, 'data') and field.data is not None:
						for f in field.data:
							fix_field(f, current_context)
				elif field.type == pyRitoFile.bin.BINType.MAP:
					if hasattr(field, 'data'):
						new_map = {}
						for key, value in field.data.items():
							new_key = fix_value(key, field.key_type, current_context)
							new_value = fix_value(value, field.value_type, current_context)
							new_map[new_key] = new_value
						field.data = new_map
				elif field.type == pyRitoFile.bin.BINType.OPTION:
					if field.value_type == pyRitoFile.bin.BINType.STRING:
						if hasattr(field, 'data') and field.data is not None:
							new_value = fix_value(field.data, field.value_type, current_context)
							if new_value != field.data:
								field.data = new_value
				else:
					# For basic types including STRING, directly modify field.data
					if hasattr(field, 'data'):
						new_value = fix_value(field.data, field.type, current_context)
						if new_value != field.data:
							field.data = new_value
			
			# Fix all entries
			for entry_idx, entry in enumerate(bin_obj.entries):
				entry_hash = getattr(entry, 'hash', 'unknown')
				print(f"[DEBUG] Processing entry {entry_idx}: hash={entry_hash}")
				for field in entry.data:
					fix_field(field, f"entry:{entry_hash}")
			
			# Write back if modified
			if modified:
				print(f"[DEBUG] Writing modified BIN file back to: {bin_path}")
				bin_obj.write(str(bin_path))
				print(f"[DEBUG] Updated BIN file with {changes_count} HUD path changes")
			else:
				print(f"[DEBUG] No HUD .dds paths found to fix in BIN file")
			
		except Exception as e:
			print(f"[DEBUG] Error fixing HUD paths in BIN: {e}")
			import traceback
			traceback.print_exc()
		
		return (modified, changes_count)
	
	def _copy_hud_files_with_prefix(self, hud_source: Path, dst_dir: Path, prefix: str, champion: str, bin_path: Path = None) -> tuple[int, int]:
		"""
		Copy ONLY the icons2d folder from HUD to repathed output WITHOUT prefix (like VO files).
		Other HUD files are already copied by bum.bum() with prefix.
		Returns (copied_count, converted_count)
		"""
		if not hud_source or not hud_source.exists():
			return (0, 0)
		
		champ = champion.lower() if champion else ''
		if not champ:
			return (0, 0)
		
		# Only copy icons2d folder - destination WITHOUT prefix: assets/characters/{champion}/hud/icons2d
		icons2d_source = hud_source / 'icons2d'
		if not icons2d_source.exists() or not icons2d_source.is_dir():
			return (0, 0)
		
		dst_hud_no_prefix = dst_dir / 'assets' / 'characters' / champ / 'hud'
		dst_icons2d = dst_hud_no_prefix / 'icons2d'
		
		copied = 0
		converted = 0
		
		# Copy only files in icons2d folder (and subfolders)
		for root, _dirs, files in os.walk(icons2d_source):
			root_p = Path(root)
			rel = root_p.relative_to(icons2d_source)
			target_dir = dst_icons2d / rel
			target_dir.mkdir(parents=True, exist_ok=True)
			
			for f in files:
				src_file = root_p / f
				name_lower = f.lower()
				
				if name_lower.endswith('.dds'):
					dst_dds = target_dir / f
					dst_tex = target_dir / f"{src_file.stem}.tex"
					
					try:
						# Copy DDS first
						shutil.copy2(src_file, dst_dds)
						copied += 1
						
						# Always convert DDS to TEX (BIN should reference .tex now)
						if not dst_tex.exists():
							try:
								self._dds2tex(dst_dds, dst_tex)
								converted += 1
								print(f"[DEBUG] Converted icons2d DDS→TEX: {src_file} -> {dst_tex}")
							except Exception as e:
								print(f"[DEBUG] Failed to convert icons2d DDS→TEX {src_file}: {e}")
					except Exception as e:
						print(f"[DEBUG] Failed to copy icons2d file {src_file}: {e}")
				
				elif name_lower.endswith('.tex'):
					dst_tex = target_dir / f
					
					try:
						# Copy TEX file (no conversion needed)
						shutil.copy2(src_file, dst_tex)
						copied += 1
						print(f"[DEBUG] Copied icons2d TEX: {src_file} -> {dst_tex}")
					except Exception as e:
						print(f"[DEBUG] Failed to copy icons2d file {src_file}: {e}")
				
				else:
					# Other files: just copy
					dst_file = target_dir / f
					try:
						shutil.copy2(src_file, dst_file)
						copied += 1
						print(f"[DEBUG] Copied icons2d file: {src_file} -> {dst_file}")
					except Exception as e:
						print(f"[DEBUG] Failed to copy icons2d file {src_file}: {e}")
		
		return (copied, converted)
	
	def _convert_hud_dds_to_tex(self, base_dir: Path, champion: str, main_bin_path: Path = None) -> int:
		"""
		Convert HUD DDS files to TEX in the base_dir BEFORE repathing.
		Reads iconCircle and iconSquare paths from the main BIN file to know which files to convert.
		This handles already-repathed paths (e.g., ASSETS/sungyone/Characters/Yone/HUD/Yone_Circle_0.tex).
		Returns count of converted files.
		"""
		converted_count = 0
		champ = champion.lower() if champion else ''
		
		if not champ:
			return 0
		
		# Load hashes to find iconCircle and iconSquare fields
		hashes_dir = self._hash_dir()
		WizardApp._HashStorage.read_all_hashes(hashes_dir)
		
		# Create hash lookup
		H = {}
		for fname in ['hashes.binfields.txt', 'hashes.bintypes.txt']:
			if fname in WizardApp._HashStorage.hashtables:
				for hex_hash, raw_name in WizardApp._HashStorage.hashtables[fname].items():
					H[raw_name] = hex_hash
					if raw_name and raw_name[0].islower():
						H[raw_name[0].upper() + raw_name[1:]] = hex_hash
		
		# Find the main BIN file (user selected)
		bin_file = None
		if main_bin_path and main_bin_path.exists():
			bin_file = main_bin_path
		else:
			# Fallback: find BIN based on selected_bin choice
			selected_bin = self.main_bin_choice.get().strip() if hasattr(self, 'main_bin_choice') else None
			if selected_bin:
				characters_dir = base_dir / 'data' / 'characters'
				if characters_dir.exists():
					champ_dir = characters_dir / champ
					if champ_dir.exists():
						skins_dir = champ_dir / 'skins'
						if skins_dir.exists():
							# Parse selected BIN (e.g., "Skin0", "Skin5", "Base")
							selected_lower = selected_bin.lower().strip()
							skin_idx = None
							if selected_lower == 'base':
								skin_idx = 0
							else:
								m = re.search(r"(skin)?\s*(\d+)", selected_lower)
								if m:
									skin_idx = int(m.group(2))
							
							if skin_idx is not None:
								bin_file = skins_dir / f'skin{skin_idx}.bin'
								if not bin_file.exists():
									bin_file = None
		
		# Collect HUD texture paths from the main BIN file (iconCircle, iconSquare, etc.)
		hud_tex_paths = set()
		
		if bin_file and bin_file.exists():
			try:
				# Check if file is a valid binary BIN file
				if not self._is_valid_binary_bin(bin_file):
					print(f"[DEBUG] Skipping text-based BIN file: {bin_file}")
					return hud_tex_paths
				
				import pyRitoFile
				BIN = pyRitoFile.bin.BIN
				bin_obj = BIN().read(str(bin_file))
				print(f"[DEBUG] Reading main BIN for HUD paths: {bin_file}")
				
				# Find SkinCharacterDataProperties entry
				scdp_hash = H.get('SkinCharacterDataProperties')
				icon_circle_hash = H.get('iconCircle')
				icon_square_hash = H.get('iconSquare')
				icon_avatar_hash = H.get('iconAvatar')
				
				# Debug: Check if hashes were found
				if not scdp_hash:
					print(f"[DEBUG] WARNING: SkinCharacterDataProperties hash not found in hash tables")
				if not icon_circle_hash:
					print(f"[DEBUG] WARNING: iconCircle hash not found in hash tables")
				if not icon_square_hash:
					print(f"[DEBUG] WARNING: iconSquare hash not found in hash tables")
				if not icon_avatar_hash:
					print(f"[DEBUG] WARNING: iconAvatar hash not found in hash tables")
				
				if scdp_hash and (icon_circle_hash or icon_square_hash or icon_avatar_hash):
					found_scdp = False
					for entry in bin_obj.entries:
						if entry.type == scdp_hash:
							found_scdp = True
							print(f"[DEBUG] Found SkinCharacterDataProperties entry, checking {len(entry.data)} fields")
							# Look for iconCircle, iconSquare, and iconAvatar fields
							for field in entry.data:
								# Check if this is iconCircle, iconSquare, or iconAvatar
								is_icon_circle = icon_circle_hash and field.hash == icon_circle_hash
								is_icon_square = icon_square_hash and field.hash == icon_square_hash
								is_icon_avatar = icon_avatar_hash and field.hash == icon_avatar_hash
								
								if is_icon_circle or is_icon_square or is_icon_avatar:
									if is_icon_circle:
										field_name = "iconCircle"
									elif is_icon_square:
										field_name = "iconSquare"
									else:
										field_name = "iconAvatar"
									print(f"[DEBUG] Found {field_name} field: type={field.type}, value_type={getattr(field, 'value_type', None)}, data={field.data}")
									
									# Handle OPTION[string] type
									if field.type == pyRitoFile.bin.BINType.OPTION:
										if hasattr(field, 'value_type') and field.value_type == pyRitoFile.bin.BINType.STRING:
											if field.data is not None and isinstance(field.data, str):
												# Path might already be repathed (e.g., ASSETS/sungyone/Characters/Yone/HUD/Yone_Circle_0.tex)
												tex_path_str = field.data
												if 'hud' in tex_path_str.lower() and ('.tex' in tex_path_str.lower() or '.dds' in tex_path_str.lower()):
													hud_tex_paths.add(tex_path_str)
													print(f"[DEBUG] Found HUD texture path in main BIN ({field_name}): {tex_path_str}")
												else:
													print(f"[DEBUG] {field_name} path found but doesn't look like HUD texture: {tex_path_str}")
											else:
												print(f"[DEBUG] {field_name} field data is None or not a string: {field.data}")
										else:
											print(f"[DEBUG] {field_name} is OPTION but value_type is not STRING: {getattr(field, 'value_type', None)}")
									else:
										# Try direct string access (in case it's not OPTION)
										if hasattr(field, 'data') and field.data is not None:
											if isinstance(field.data, str):
												tex_path_str = field.data
												if 'hud' in tex_path_str.lower() and ('.tex' in tex_path_str.lower() or '.dds' in tex_path_str.lower()):
													hud_tex_paths.add(tex_path_str)
													print(f"[DEBUG] Found HUD texture path in main BIN ({field_name}, non-OPTION): {tex_path_str}")
							break
					
					if not found_scdp:
						print(f"[DEBUG] WARNING: SkinCharacterDataProperties entry not found in BIN")
				else:
					print(f"[DEBUG] WARNING: Missing required hashes - scdp_hash={scdp_hash}, icon_circle_hash={icon_circle_hash}, icon_square_hash={icon_square_hash}")
			except Exception as e:
				print(f"[DEBUG] Error reading main BIN {bin_file} for HUD paths: {e}")
				import traceback
				traceback.print_exc()
		else:
			if not bin_file:
				print(f"[DEBUG] WARNING: Main BIN file not found (bin_file is None)")
			else:
				print(f"[DEBUG] WARNING: Main BIN file does not exist: {bin_file}")
		
		# If no paths found in BIN, fall back to converting all DDS files in HUD folders
		if not hud_tex_paths:
			print(f"[DEBUG] No HUD texture paths found in BINs, falling back to converting all DDS files in HUD folders")
			# Search for HUD folders in both data and assets
			hud_search_paths = [
				base_dir / 'data' / 'characters' / champ / 'hud',
				base_dir / 'assets' / 'characters' / champ / 'hud',
			]
			
			# Also search in all character subfolders
			if characters_dir.exists():
				for char_folder in characters_dir.iterdir():
					if char_folder.is_dir():
						hud_search_paths.append(char_folder / 'hud')
			
			characters_dir_assets = base_dir / 'assets' / 'characters'
			if characters_dir_assets.exists():
				for char_folder in characters_dir_assets.iterdir():
					if char_folder.is_dir():
						hud_search_paths.append(char_folder / 'hud')
			
			# Find and convert all DDS files in HUD folders
			for hud_dir in hud_search_paths:
				if not hud_dir.exists():
					continue
				
				for root, _dirs, files in os.walk(hud_dir):
					for f in files:
						if not f.lower().endswith('.dds'):
							continue
						
						dds_path = Path(root) / f
						tex_path = dds_path.with_suffix('.tex')
						
						try:
							if tex_path.exists():
								tex_path.unlink()
							self._dds2tex(dds_path, tex_path)
							converted_count += 1
							print(f"[DEBUG] Converted HUD DDS→TEX (before repath): {dds_path} -> {tex_path}")
						except Exception as e:
							print(f"[DEBUG] Failed to convert HUD DDS→TEX {dds_path}: {e}")
							continue
		else:
			# Convert specific files referenced in BIN
			print(f"[DEBUG] Processing {len(hud_tex_paths)} HUD texture paths from BIN")
			for tex_path_str in hud_tex_paths:
				try:
					# Normalize path (handle already-repathed paths)
					# Path might be: ASSETS/sungyone/Characters/Yone/HUD/Yone_Circle_0.tex
					# Or: ASSETS/Characters/Yone/HUD/Yone_Circle_0.tex
					path_normalized = tex_path_str.replace('\\', '/')
					print(f"[DEBUG] Processing HUD path: {path_normalized}")
					
					# Extract the relative path after ASSETS/ or DATA/
					# Handle already-repathed: ASSETS/sungyone/Characters/... -> Characters/...
					# Handle normal: ASSETS/Characters/... -> Characters/...
					path_lower = path_normalized.lower()
					if 'assets' in path_lower:
						parts = path_normalized.split('/')
						assets_idx = None
						for i, part in enumerate(parts):
							if part.lower() == 'assets':
								assets_idx = i
								break
						
						if assets_idx is not None and assets_idx + 1 < len(parts):
							# Check if next part is a prefix (not a standard folder like Characters, levels, etc.)
							next_part = parts[assets_idx + 1].lower()
							standard_folders = ['characters', 'levels', 'maps', 'data', 'sounds', 'uiautoatlas', 'ux']
							
							if next_part not in standard_folders:
								# Already repathed - skip the prefix part
								relative_path = '/'.join(parts[assets_idx + 2:])
								prefix = parts[assets_idx + 1]
								print(f"[DEBUG] Detected repathed path with prefix '{prefix}', relative_path: {relative_path}")
							else:
								# Normal path
								relative_path = '/'.join(parts[assets_idx + 1:])
								prefix = None
								print(f"[DEBUG] Normal path (no prefix), relative_path: {relative_path}")
							
							# Try to find the file in base_dir
							# The file structure is: base_dir/assets/[prefix]/characters/champ/hud/filename
							# Build candidate paths with proper case handling
							candidate_paths = []
							
							# First, try with the exact path structure from BIN (with prefix if present)
							if prefix:
								# Try: base_dir/assets/prefix/Characters/Yone/HUD/Yone_Circle_0.dds
								candidate_paths.append(base_dir / 'assets' / prefix / relative_path)
								candidate_paths.append(base_dir / 'ASSETS' / prefix / relative_path)
								# Try lowercase version: base_dir/assets/prefix/characters/yone/hud/Yone_Circle_0.dds
								relative_lower = relative_path.lower()
								candidate_paths.append(base_dir / 'assets' / prefix / relative_lower)
								candidate_paths.append(base_dir / 'ASSETS' / prefix / relative_lower)
							else:
								# No prefix, try normal paths
								candidate_paths.append(base_dir / 'assets' / relative_path)
								candidate_paths.append(base_dir / 'ASSETS' / relative_path)
								relative_lower = relative_path.lower()
								candidate_paths.append(base_dir / 'assets' / relative_lower)
								candidate_paths.append(base_dir / 'ASSETS' / relative_lower)
							
							# Also try without the prefix in the path (in case files are stored without prefix)
							relative_no_prefix = '/'.join(parts[assets_idx + 1:]) if prefix else relative_path
							candidate_paths.append(base_dir / 'assets' / relative_no_prefix)
							candidate_paths.append(base_dir / 'ASSETS' / relative_no_prefix)
							relative_no_prefix_lower = relative_no_prefix.lower()
							candidate_paths.append(base_dir / 'assets' / relative_no_prefix_lower)
							candidate_paths.append(base_dir / 'ASSETS' / relative_no_prefix_lower)
							
							print(f"[DEBUG] Trying {len(candidate_paths)} candidate paths:")
							for cp in candidate_paths:
								print(f"[DEBUG]   - {cp} (exists: {cp.exists()})")
							
							# Find the actual file (might be .tex or .dds)
							found_file = None
							for candidate in candidate_paths:
								# Try .tex first (if BIN already references .tex)
								if candidate.exists():
									found_file = candidate
									print(f"[DEBUG] Found file (as .tex): {found_file}")
									break
								# Try .dds (need to convert)
								dds_candidate = candidate.with_suffix('.dds')
								if dds_candidate.exists():
									found_file = dds_candidate
									print(f"[DEBUG] Found file (as .dds): {found_file}")
									break
								# Try with lowercase filename
								candidate_lower = candidate.parent / candidate.name.lower()
								if candidate_lower.exists():
									found_file = candidate_lower
									print(f"[DEBUG] Found file (as .tex, lowercase filename): {found_file}")
									break
								dds_candidate_lower = candidate_lower.with_suffix('.dds')
								if dds_candidate_lower.exists():
									found_file = dds_candidate_lower
									print(f"[DEBUG] Found file (as .dds, lowercase filename): {found_file}")
									break
							
							if not found_file:
								print(f"[DEBUG] WARNING: Could not find file for path: {path_normalized}")
								print(f"[DEBUG] Base directory: {base_dir}")
								print(f"[DEBUG] Base directory exists: {base_dir.exists()}")
								# Try to find any file with the same name in the HUD folder
								filename = Path(relative_path).name
								print(f"[DEBUG] Searching for filename: {filename}")
								
								# Try multiple HUD folder locations
								hud_folders_to_try = [
									base_dir / 'assets' / 'characters' / champ / 'hud',
									base_dir / 'ASSETS' / 'characters' / champ / 'hud',
									base_dir / 'assets' / 'Characters' / champ.capitalize() / 'HUD',
								]
								if prefix:
									hud_folders_to_try.extend([
										base_dir / 'assets' / prefix / 'characters' / champ / 'hud',
										base_dir / 'ASSETS' / prefix / 'characters' / champ / 'hud',
										base_dir / 'assets' / prefix / 'Characters' / champ.capitalize() / 'HUD',
									])
								
								for hud_folder in hud_folders_to_try:
									if hud_folder.exists():
										print(f"[DEBUG] Searching in HUD folder: {hud_folder}")
										for f in hud_folder.rglob(filename):
											print(f"[DEBUG] Found potential match in HUD folder: {f}")
											found_file = f
											break
										if found_file:
											break
										# Also try case-insensitive search
										for f in hud_folder.rglob('*'):
											if f.name.lower() == filename.lower():
												print(f"[DEBUG] Found case-insensitive match in HUD folder: {f}")
												found_file = f
												break
										if found_file:
											break
							
							if found_file and found_file.suffix.lower() == '.dds':
								# Convert DDS to TEX
								tex_output = found_file.with_suffix('.tex')
								try:
									if tex_output.exists():
										tex_output.unlink()
									self._dds2tex(found_file, tex_output)
									converted_count += 1
									print(f"[DEBUG] Converted HUD DDS→TEX (from BIN path): {found_file} -> {tex_output}")
								except Exception as e:
									print(f"[DEBUG] Failed to convert HUD DDS→TEX {found_file}: {e}")
									import traceback
									traceback.print_exc()
							elif found_file and found_file.suffix.lower() == '.tex':
								print(f"[DEBUG] HUD texture already exists as TEX: {found_file}")
					# Also handle DATA/ paths
					elif '/data/' in path_normalized.lower() or 'data' in path_lower:
						parts = path_normalized.split('/')
						data_idx = None
						for i, part in enumerate(parts):
							if part.lower() == 'data':
								data_idx = i
								break
						
						if data_idx is not None and data_idx + 1 < len(parts):
							next_part = parts[data_idx + 1].lower()
							standard_folders = ['characters', 'levels', 'maps']
							
							if next_part not in standard_folders:
								relative_path = '/'.join(parts[data_idx + 2:])
							else:
								relative_path = '/'.join(parts[data_idx + 1:])
							
							candidate_paths = [
								base_dir / 'data' / relative_path,
								base_dir / 'DATA' / relative_path,
							]
							
							if next_part not in standard_folders:
								prefix = parts[data_idx + 1]
								candidate_paths.extend([
									base_dir / 'data' / prefix / relative_path,
									base_dir / 'DATA' / prefix / relative_path,
								])
							
							found_file = None
							for candidate in candidate_paths:
								if candidate.exists():
									found_file = candidate
									break
								dds_candidate = candidate.with_suffix('.dds')
								if dds_candidate.exists():
									found_file = dds_candidate
									break
							
							if found_file and found_file.suffix.lower() == '.dds':
								tex_output = found_file.with_suffix('.tex')
								try:
									if tex_output.exists():
										tex_output.unlink()
									self._dds2tex(found_file, tex_output)
									converted_count += 1
									print(f"[DEBUG] Converted HUD DDS→TEX (from BIN path): {found_file} -> {tex_output}")
								except Exception as e:
									print(f"[DEBUG] Failed to convert HUD DDS→TEX {found_file}: {e}")
									import traceback
									traceback.print_exc()
							elif found_file and found_file.suffix.lower() == '.tex':
								print(f"[DEBUG] HUD texture already exists as TEX: {found_file}")
					else:
						print(f"[DEBUG] Path does not contain 'assets' or 'data', skipping: {path_normalized}")
				except Exception as e:
					print(f"[DEBUG] Exception processing HUD path {tex_path_str}: {e}")
					import traceback
					traceback.print_exc()
					continue
		
		WizardApp._HashStorage.free_all_hashes()
		return converted_count

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
		def __init__(self, project_root: Path, custom_prefix: str = 'bum'):
			self._py = pyRitoFile
			self.custom_prefix = custom_prefix  # Store custom prefix
			self.source_dirs = []
			self.source_files = {}
			self.source_bins = {}
			self.scanned_tree = {}
			self.entry_prefix = {}
			self.entry_name = {}
			self.linked_bins = {}
		
		def _is_valid_binary_bin(self, bin_path: Path) -> bool:
			"""
			Check if a file is a valid binary BIN file (PROP or PTCH signature).
			Returns False for text-based BIN files (like #PROP_text format).
			"""
			try:
				with open(bin_path, 'rb') as f:
					signature = f.read(4).decode('utf-8', errors='ignore')
					return signature in ('PROP', 'PTCH')
			except Exception:
				return False
		
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
						rel_lower = rel.lower()
						u = self.unify_path(rel)
						if u not in self.source_files:
							# Skip text-based BIN files - they cause errors and can't be processed
							if rel.lower().endswith('.bin'):
								if not self._is_valid_binary_bin(Path(full)):
									print(f"[DEBUG] Skipping text-based BIN file in source: {rel}")
									continue
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
					# Skip VO files - they should not be repathed or included in scan
					if 'assets/sounds/wwise2016/vo/' in value_lower:
						return
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
				# Check if file is a valid binary BIN file
				if not self._is_valid_binary_bin(Path(bin_path)):
					return
				
				bin = self._py.bin.BIN().read(bin_path)
				self.linked_bins[unify_file] = []
				for link in bin.links:
					if self._is_character_bin(link):
						continue
					unify_link = self.unify_path(link)
					if unify_link in self.source_files:
						# Double-check it's a valid binary BIN before processing
						bin_path = Path(self.source_files[unify_link][0])
						if bin_path.exists() and bin_path.suffix.lower() == '.bin':
							if not self._is_valid_binary_bin(bin_path):
								print(f"[DEBUG] Skipping text-based linked BIN: {link}")
								self.scanned_tree['All_BINs'][unify_link] = (False, link)
								continue
						self.scanned_tree['All_BINs'][unify_link] = (True, link)
						scan_bin(self.source_files[unify_link][0], unify_link)
						self.linked_bins[unify_file].append(unify_link)
					else:
						self.scanned_tree['All_BINs'][unify_link] = (False, link)
				for entry in bin.entries:
					entry_hash = entry.hash
					self.scanned_tree[entry_hash] = {}
					self.entry_prefix[entry_hash] = self.custom_prefix
					for field in entry.data:
						scan_field(field, entry_hash)
					if entry_hash not in self.entry_name:
						self.entry_name[entry_hash] = self._py.bin.BINHasher.hex_to_raw(WizardApp._HashStorage.hashtables, entry_hash)
			
			for unify_file in self.source_bins:
				if self.source_bins[unify_file]:
					if unify_file not in self.source_files:
						print(f"[DEBUG] Warning: unify_file not in source_files: {unify_file}, skipping")
						continue
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
						# NEVER repath VO paths (voice-over files)
						if 'assets/sounds/wwise2016/vo/' in value_lower:
							return value
						
						unify_file = self.unify_path(value_lower)
						# Check if file exists in scanned tree
						existed = False
						if entry_hash in self.scanned_tree and unify_file in self.scanned_tree[entry_hash]:
							existed, path = self.scanned_tree[entry_hash][unify_file]
						
						# Repath if file exists OR if we're ignoring missing files (repath missing files too)
						if existed or ignore_missing:
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
				# Check if file is a valid binary BIN file
				if not self._is_valid_binary_bin(Path(bin_path)):
					return
				
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
					if unify_file not in self.source_files:
						print(f"[DEBUG] Warning: unify_file not in source_files: {unify_file}, skipping")
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
					# Removed per-file logging to reduce console spam
			# combine bin
			if combine_linked:
				for unify_file in self.source_bins:
					if self.source_bins[unify_file]:
						bum_file_path = Path(bum_files[unify_file])
						# Check if file is a valid binary BIN file
						if not self._is_valid_binary_bin(bum_file_path):
							continue
						
						source_bin = self._py.bin.BIN().read(bum_files[unify_file])
						linked_unify_files = self._flat_list_linked_bins(unify_file, self.linked_bins)
						new_links = []
						for link in source_bin.links:
							if not self.unify_path(link) in linked_unify_files:
								new_links.append(link)
						source_bin.links = new_links
						
						# Track existing entry hashes to avoid duplicates
						existing_entry_hashes = set()
						for entry in source_bin.entries:
							if hasattr(entry, 'hash'):
								existing_entry_hashes.add(entry.hash)
						
						for linked_unify_file in linked_unify_files:
							if linked_unify_file not in bum_files:
								continue
							bum_file = bum_files[linked_unify_file]
							if not os.path.exists(bum_file):
								continue
							try:
								# Check if file is a valid binary BIN file
								if not self._is_valid_binary_bin(Path(bum_file)):
									continue
								
								linked_bin = self._py.bin.BIN().read(bum_file)
								# Only add entries that don't already exist (by hash)
								new_entries = []
								for entry in linked_bin.entries:
									if hasattr(entry, 'hash') and entry.hash not in existing_entry_hashes:
										new_entries.append(entry)
								source_bin.entries += new_entries
								# Update set of existing hashes for next iteration
								for entry in new_entries:
									if hasattr(entry, 'hash'):
										existing_entry_hashes.add(entry.hash)
								os.remove(bum_file)
							except Exception as e:
								print(f"[DEBUG] Error combining linked BIN {linked_unify_file}: {e}")
								continue
						source_bin.write(bum_files[unify_file])
						print(f'bumpath: Finish: Combine all linked BINs to {bum_files[unify_file]}.')
			# remove empty dirs
			for root, dirs, files in os.walk(output_dir, topdown=False):
				if len(os.listdir(root)) == 0:
					os.rmdir(root)
			print(f'bumpath: Finish: Bum {output_dir}.')

	def _apply_no_skin_lite_to_wad(self, repathed_dir: Path):
		"""
		Apply No Skin Lite: Copy the main skin BIN to all other skin slots (skin0-skin99).
		This runs on the repathed directory after fixing missing textures.
		Based on LtMAO no_skin.mini_no_skin logic.
		Processes all character subfolders (main champion + subfolders like shacoboxes, annietibbers, etc.)
		"""
		import re
		
		# Load hash tables
		hashes_dir = self._hash_dir()
		WizardApp._HashStorage.read_all_hashes(hashes_dir)
		
		# Get champion and main skin selection
		champ = getattr(self, '_champion', '').lower()
		desired_raw = (self.main_bin_choice.get() or '').strip()
		desired = desired_raw.lower()
		
		if not champ or not desired:
			raise Exception("Champion or main skin not selected")
		
		# Extract skin index from desired (e.g., 'skin5' -> 5, 'base' -> 0)
		if desired == 'base':
			skin_idx = 0
		else:
			m = re.search(r"(skin)?\s*(\d+)", desired)
			skin_idx = int(m.group(2)) if m else 0
		
		# No Skin Lite ONLY works with Base/Skin0 (prevents skin hacking with Skin1+)
		if skin_idx != 0:
			raise Exception("No Skin Lite only works with Base/Skin0, not Skin1+ (prevents skin hacking)")
		
		# Get the custom prefix used during repathing
		prefix = getattr(self, '_used_prefix', 'bum')
		
		# Find ALL character subfolders and process each one
		# This includes main champion folder and subfolders like shacoboxes, annietibbers, lantern, etc.
		search_paths = [
			repathed_dir / 'data' / prefix / 'characters',
			repathed_dir / 'assets' / prefix / 'characters',
			repathed_dir / 'data' / 'characters',  # Fallback without prefix
			repathed_dir / 'assets' / 'characters'  # Fallback without prefix
		]
		
		# Collect all character folders that have skins
		character_folders_to_process = []
		
		for base_path in search_paths:
			if not base_path.exists():
				continue
			
			for char_folder in base_path.iterdir():
				if not char_folder.is_dir():
					continue
				
				skins_dir = char_folder / 'skins'
				if not skins_dir.exists():
					continue
				
				# Check if this folder has the main skin BIN (Skin0)
				has_main_skin = False
				for root, _dirs, files in os.walk(skins_dir):
					for f in files:
						if not f.lower().endswith('.bin'):
							continue
						
						p = Path(root) / f
						rel = Path(os.path.relpath(p, repathed_dir)).as_posix()
						
						# Check if this is the main skin BIN (Skin0)
						if f"/skins/skin{skin_idx}/" in rel.lower() or f.lower() == f"skin{skin_idx}.bin":
							character_folders_to_process.append((char_folder, base_path, p))
							has_main_skin = True
							break
					
					if has_main_skin:
						break
		
		if not character_folders_to_process:
			raise Exception(f"Main skin BIN (Skin{skin_idx}) not found in any character folder in repathed directory")
		
		print(f"[DEBUG] No Skin Lite: Found {len(character_folders_to_process)} character folder(s) to process")
		
		# Get hash values for the types we need (only need to do this once)
		bin_hashes = {}
		if 'hashes.bintypes.txt' in WizardApp._HashStorage.hashtables:
			for hex_hash, raw_name in WizardApp._HashStorage.hashtables['hashes.bintypes.txt'].items():
				bin_hashes[raw_name] = hex_hash
		
		scdp_hash = bin_hashes.get('SkinCharacterDataProperties')
		rr_hash = bin_hashes.get('ResourceResolver')
		mrr_field_hash = bin_hashes.get('mResourceResolver')
		
		# Convert field hash from binfields.txt if needed
		if not mrr_field_hash and 'hashes.binfields.txt' in WizardApp._HashStorage.hashtables:
			for hex_hash, raw_name in WizardApp._HashStorage.hashtables['hashes.binfields.txt'].items():
				if raw_name == 'mResourceResolver':
					mrr_field_hash = hex_hash
					break
		
		total_copied_count = 0
		
		# Process each character folder (main champion + subfolders)
		for char_folder, base_path, main_skin_bin in character_folders_to_process:
			char_name = char_folder.name
			print(f"[DEBUG] No Skin Lite: Processing character folder: {char_name}")
			print(f"[DEBUG] No Skin Lite: Using main BIN: {main_skin_bin}")
			
			# First, read the source BIN once to get the original paths
			# Check if file is a valid binary BIN file
			if not self._is_valid_binary_bin(main_skin_bin):
				print(f"[DEBUG] No Skin Lite: Skipping text-based BIN file: {main_skin_bin}")
				return
			
			source_bin = pyRitoFile.bin.BIN().read(str(main_skin_bin))
			
			# Find base_scdp, base_rr, and base_mrr from main skin
			base_scdp = None
			base_rr = None
			base_mrr = None
			
			for entry in source_bin.entries:
				if scdp_hash and entry.type == scdp_hash:
					base_scdp = entry
					for field in entry.data:
						if mrr_field_hash and field.hash == mrr_field_hash:
							base_mrr = field
							break
				elif rr_hash and entry.type == rr_hash:
					base_rr = entry
			
			if not base_scdp:
				print(f"[DEBUG] No Skin Lite: Warning - Could not find SkinCharacterDataProperties in {char_name}, skipping")
				continue
			
			# Get the original SCDP and RR hash values from main skin
			original_scdp_hash = base_scdp.hash
			original_rr_hash = base_rr.hash if base_rr else None
			
			# Unhash to get the raw paths
			base_scdp_path = None
			base_rr_path = None
			
			if 'hashes.binentries.txt' in WizardApp._HashStorage.hashtables:
				base_scdp_path = WizardApp._HashStorage.hashtables['hashes.binentries.txt'].get(original_scdp_hash)
				if original_rr_hash:
					base_rr_path = WizardApp._HashStorage.hashtables['hashes.binentries.txt'].get(original_rr_hash)
			
			# Get the base file path structure
			main_skin_rel = main_skin_bin.relative_to(repathed_dir)
			main_skin_str = str(main_skin_rel).replace('\\', '/')
			
			# Now copy main BIN to all other skin slots (1-99) and edit hash values
			# IMPORTANT: Read the source BIN fresh for each iteration to avoid corruption
			copied_count = 0
			
			for target_skin_idx in range(1, 100):  # Start from 1, skip 0 (base skin)
				# Replace skin index in file path
				target_skin_str = main_skin_str.replace(f'/skin{skin_idx}/', f'/skin{target_skin_idx}/')
				target_skin_str = target_skin_str.replace(f'skin{skin_idx}.bin', f'skin{target_skin_idx}.bin')
				
				target_skin_path = repathed_dir / target_skin_str
				target_skin_path.parent.mkdir(parents=True, exist_ok=True)
				
				try:
					# CRITICAL: Read the source BIN fresh for each iteration
					# Check if file is a valid binary BIN file
					if not self._is_valid_binary_bin(main_skin_bin):
						print(f"[DEBUG] No Skin Lite: Skipping text-based BIN file: {main_skin_bin}")
						continue
					
					target_bin = pyRitoFile.bin.BIN().read(str(main_skin_bin))
					
					# Find the entries in this fresh copy
					target_scdp = None
					target_rr = None
					target_mrr = None
					
					for entry in target_bin.entries:
						if scdp_hash and entry.type == scdp_hash:
							target_scdp = entry
							for field in entry.data:
								if mrr_field_hash and field.hash == mrr_field_hash:
									target_mrr = field
									break
						elif rr_hash and entry.type == rr_hash:
							target_rr = entry
					
					if not target_scdp:
						raise Exception(f"Could not find SkinCharacterDataProperties in BIN for Skin{target_skin_idx}")
					
					# Generate new hash values for target skin
					# Replace character name in path if needed (for subfolders like shacoboxes)
					if base_scdp_path:
						# Replace skin index in the path string (case-insensitive)
						target_scdp_path = base_scdp_path.replace(f'/skin{skin_idx}', f'/skin{target_skin_idx}')
						target_scdp_path = target_scdp_path.replace(f'/Skin{skin_idx}', f'/Skin{target_skin_idx}')
						# Also handle if the path uses lowercase/uppercase variations
						target_scdp_path = target_scdp_path.replace(f'Skin{skin_idx}', f'Skin{target_skin_idx}')
						# Replace character name in path for subfolders (e.g., "Shaco" -> "ShacoBoxes")
						# Check if the current path has the base champion name and replace with actual folder name
						# Match patterns like "Characters/Shaco/" or "characters/shaco/" and replace with folder name
						target_scdp_path = re.sub(
							rf'(?i)(characters?[/\\]){re.escape(champ)}([/\\])',
							rf'\1{char_name}\2',
							target_scdp_path
						)
						# Convert path to hex string hash (entry.hash is stored as hex string)
						target_scdp_hash = pyRitoFile.bin.BINHasher.raw_to_hex(target_scdp_path.lower())
					else:
						# Fallback: construct from character folder name
						target_scdp_path = f"characters/{char_name}/skins/skin{target_skin_idx}"
						target_scdp_hash = pyRitoFile.bin.BINHasher.raw_to_hex(target_scdp_path.lower())
					
					# Same for ResourceResolver - path is like "Characters/Akali/Skins/Skin1/Resources"
					if base_rr_path:
						target_rr_path = base_rr_path.replace(f'/skin{skin_idx}', f'/skin{target_skin_idx}')
						target_rr_path = target_rr_path.replace(f'/Skin{skin_idx}', f'/Skin{target_skin_idx}')
						target_rr_path = target_rr_path.replace(f'Skin{skin_idx}', f'Skin{target_skin_idx}')
						# Replace character name if needed
						target_rr_path = re.sub(
							rf'(?i)(characters?[/\\]){re.escape(champ)}([/\\])',
							rf'\1{char_name}\2',
							target_rr_path
						)
						target_rr_hash = pyRitoFile.bin.BINHasher.raw_to_hex(target_rr_path.lower())
					else:
						target_rr_hash = None
					
					# Update hash values in the fresh BIN copy
					# Entry hashes are hex strings like "e67284f4"
					target_scdp.hash = target_scdp_hash
					if target_rr and target_rr_hash:
						target_rr.hash = target_rr_hash
						# Update mResourceResolver field to link to the new ResourceResolver
						# mResourceResolver field stores LINK type, which is also a hex string
						if target_mrr:
							target_mrr.data = target_rr_hash
					
					# Write the modified BIN to target location
					target_bin.write(str(target_skin_path))
					copied_count += 1
					print(f"[DEBUG] No Skin Lite [{char_name}]: Created Skin{target_skin_idx} at {target_skin_path}")
					
				except Exception as e:
					print(f"[DEBUG] No Skin Lite [{char_name}]: Failed to create Skin{target_skin_idx}: {e}")
					import traceback
					traceback.print_exc()
					continue
			
			total_copied_count += copied_count
			print(f"[DEBUG] No Skin Lite [{char_name}]: Copied Skin{skin_idx} to {copied_count} other slots")
		
		WizardApp._HashStorage.free_all_hashes()
		print(f"[DEBUG] No Skin Lite: Total copied to {total_copied_count} skin slots across {len(character_folders_to_process)} character folder(s)")
		self._set_status(f"No Skin Lite: Copied Skin{skin_idx} to {total_copied_count} slots across {len(character_folders_to_process)} character folder(s)")
	
	def _repath_fresh(self, fresh_unpack: Path) -> bool:
		# Load hashes before starting (from AppData, not bundled)
		hashes_dir = self._hash_dir()
		self._set_status("Loading hash tables...")
		WizardApp._HashStorage.read_all_hashes(hashes_dir)
		
		# Get custom prefix or generate random one
		prefix = self.custom_prefix.get().strip()
		if not prefix:
			prefix = self._generate_random_prefix()
			self._set_status(f"Using randomly generated prefix: {prefix}")
		else:
			self._set_status(f"Using custom prefix: {prefix}")
		
		# Store prefix for later use (e.g., placeholder creation)
		self._used_prefix = prefix
		
		# Local repath engine with custom prefix
		bum = self._LocalBum(self._project_root(), custom_prefix=prefix)
		
		bum.add_source_dirs([str(fresh_unpack)])
		# Determine champion and desired skin index
		champ = getattr(self, '_champion', '').lower()
		desired_raw = (self.main_bin_choice.get() or '').strip()
		desired = desired_raw.lower()
		if not champ:
			error_msg = "Champion not detected from wad; cannot repath."
			self._set_status(error_msg)
			print(f"[DEBUG] _repath_fresh: {error_msg}")
			WizardApp._HashStorage.free_all_hashes()
			return False
		if not desired:
			error_msg = "Please enter a main BIN name (e.g., Skin0) before repath."
			self._set_status(error_msg)
			print(f"[DEBUG] _repath_fresh: {error_msg}")
			WizardApp._HashStorage.free_all_hashes()
			return False
		# Extract index from desired (e.g., 'skin5' -> 5), treat 'base' as 0
		import re
		if desired == 'base':
			skin_idx = '0'
		else:
			m = re.search(r"(skin)?\s*(\d+)", desired)
			skin_idx = m.group(2) if m else None
		# Search within ALL character subfolders for the selected skin
		# e.g., for annie: check annie/skins and annietibbers/skins
		# e.g., for thresh: check thresh/skins and lantern/skins
		characters_dir = fresh_unpack / 'data' / 'characters'
		selected_unifys = []
		available = []
		
		# Find all character subfolders
		if not characters_dir.exists():
			error_msg = f"Characters folder not found: {characters_dir}"
			self._set_status(error_msg)
			print(f"[DEBUG] _repath_fresh: {error_msg}")
			WizardApp._HashStorage.free_all_hashes()
			return False
		
		# Scan ALL character subfolders for the selected skin
		for char_folder in characters_dir.iterdir():
			if not char_folder.is_dir():
				continue
			
			skins_dir = char_folder / 'skins'
			if not skins_dir.exists():
				continue
			
			# Look for BINs matching the selected skin
			for root, _dirs, files in os.walk(skins_dir):
				for f in files:
					if not f.lower().endswith('.bin'):
						continue
					p = Path(root) / f
					rel = Path(os.path.relpath(p, fresh_unpack)).as_posix()
					available.append(rel)
					
					# Check if this BIN matches the selected skin
					# Match by filename or path containing the skin identifier
					if skin_idx is not None:
						# Check if in correct skin folder (e.g., /skins/skin0/)
						if f"/skins/skin{skin_idx}/" in rel.lower():
							selected_unifys.append(bum.unify_path(rel))
						# Check if filename matches (e.g., skin0.bin)
						elif f.lower() == f"skin{skin_idx}.bin":
							selected_unifys.append(bum.unify_path(rel))
						# Check if expected main BIN (e.g., annie_skins_skin0.bin)
						expected = f"{char_folder.name.lower()}_skins_skin{skin_idx}.bin"
						if f.lower() == expected:
							selected_unifys.append(bum.unify_path(rel))
					# Also match by name contains (for manual input)
					if desired in rel.lower() and desired not in ['skin', 'base']:
						selected_unifys.append(bum.unify_path(rel))
		
		if not selected_unifys:
			preview = ', '.join(available[:8]) + (', ...' if len(available) > 8 else '')
			error_msg = f"Main BIN not found for '{desired_raw}'. Found examples: {preview}"
			self._set_status(error_msg)
			print(f"[DEBUG] _repath_fresh: {error_msg}")
			WizardApp._HashStorage.free_all_hashes()
			return False
		
		for u in selected_unifys:
			# Make sure the file exists and is a valid binary BIN before adding
			if u not in bum.source_files:
				cand = fresh_unpack / Path(u)
				if cand.exists():
					# Skip text-based BIN files
					if cand.suffix.lower() == '.bin' and not bum._is_valid_binary_bin(cand):
						print(f"[DEBUG] Skipping text-based BIN in selected_unifys: {u}")
						continue
					bum.source_files[u] = (str(cand), u)
			# Only mark as source bin if it's actually in source_files
			if u in bum.source_files:
				bum.source_bins[u] = True
		# Repair, scan, and bum
		# Only repair BINs from the main champion folder (not subfolders like annietibbers, lantern)
		fixed = 0
		main_champ_path = f"data/characters/{champ}/"
		for u in selected_unifys:
			try:
				bin_path = bum.source_files.get(u, (None, None))[0]
				if not bin_path:
					cand = fresh_unpack / Path(u)
					bin_path = str(cand) if cand.exists() else None
				if bin_path and str(bin_path).lower().endswith('.bin'):
					# Only repair if BIN is in the main champion folder
					bin_path_normalized = str(bin_path).replace('\\', '/')
					if main_champ_path in bin_path_normalized:
						self._set_status(f"Repairing BIN before repath: {os.path.basename(bin_path)}")
						self._repair_bin_file(Path(bin_path), fresh_unpack)
						fixed += 1
					else:
						print(f"[DEBUG] Skipping repair for subfolder BIN: {bin_path}")
			except Exception:
				pass
		self._set_status(f"Repaired {fixed} BIN(s)")
		
		# Fix HUD paths in BIN files BEFORE scanning (change .dds to .tex in BIN paths)
		# This ensures BINs reference .tex files that we'll convert from .dds
		self._set_status("Fixing HUD paths in BIN files (changing .dds to .tex)...")
		bin_fixed_count = 0
		for u in selected_unifys:
			try:
				bin_path = bum.source_files.get(u, (None, None))[0]
				if not bin_path:
					cand = fresh_unpack / Path(u)
					bin_path = str(cand) if cand.exists() else None
				if bin_path and str(bin_path).lower().endswith('.bin'):
					bin_path_normalized = str(bin_path).replace('\\', '/')
					if main_champ_path in bin_path_normalized:
						bin_fixed, changes = self._fix_hud_paths_in_bin(Path(bin_path))
						if bin_fixed:
							bin_fixed_count += changes
							print(f"[DEBUG] Fixed {changes} HUD path(s) in BIN (before repath): {bin_path}")
			except Exception as e:
				print(f"[DEBUG] Error fixing HUD paths in BIN {bin_path}: {e}")
				pass
		
		if bin_fixed_count > 0:
			self._set_status(f"Fixed {bin_fixed_count} HUD path(s) in BIN files")
		
		# HUD DDS→TEX conversion already happened in mod_unpack before overlay
		# No additional conversion needed here - overlay already copied mod's HUD TEX files to fresh_unpack
		
		self._set_status(f"Repaired {fixed} BIN(s); scanning for repath (champ={champ})...")
		try:
			bum.scan()
		except Exception as scan_err:
			self._set_status(f"Scan failed: {scan_err}")
			WizardApp._HashStorage.free_all_hashes()
			import traceback
			traceback.print_exc()
			return False
		
		# Check if scan found any entries
		if len(bum.scanned_tree) == 0:
			error_msg = "No BIN entries found to repath. Check if BIN files are valid binary format."
			self._set_status(error_msg)
			print(f"[DEBUG] _repath_fresh: {error_msg}")
			WizardApp._HashStorage.free_all_hashes()
			return False
		
		# Use champion name in the repathed folder name
		output_dir = self._work_root() / f'repathed_{champ}'
		# Store the repathed folder path for later use
		self._repathed_dir = output_dir
		self._set_status("Repathing (ignore missing, combine linked)...")
		try:
			bum.bum(str(output_dir), ignore_missing=True, combine_linked=True)
			
			# Fix HUD paths in repathed BIN files (change .dds to .tex)
			self._set_status("Fixing HUD paths in repathed BIN files...")
			bin_fixed_count = 0
			if output_dir.exists():
				# Find all BIN files in the repathed output and fix HUD paths
				for bin_file in output_dir.rglob("*.bin"):
					try:
						bin_fixed, changes = self._fix_hud_paths_in_bin(bin_file)
						if bin_fixed:
							bin_fixed_count += changes
							print(f"[DEBUG] Fixed {changes} HUD path(s) in repathed BIN: {bin_file}")
					except Exception as e:
						print(f"[DEBUG] Error fixing repathed BIN {bin_file}: {e}")
			
			if bin_fixed_count > 0:
				self._set_status(f"Fixed {bin_fixed_count} HUD path(s) in repathed BIN files")
			
			# Copy VO files separately with their original paths (no prefix, no hashing)
			self._set_status("Copying VO files with original paths...")
			vo_count = self._copy_vo_files_original(fresh_unpack, output_dir)
			
			# Copy ONLY icons2d folder from HUD (without prefix, like VO files)
			# BUT only if the mod originally had an icons2d folder
			# bum.bum() already copied all other HUD files with prefix from fresh_unpack
			hud_copied = 0
			hud_converted = 0
			if self._mod_hud_folder and self._mod_hud_folder.exists():
				# Check if mod originally had icons2d folder
				mod_icons2d = self._mod_hud_folder / 'icons2d'
				if mod_icons2d.exists() and mod_icons2d.is_dir():
					# Get the icons2d from fresh_unpack (which has mod's files after overlay)
					fresh_hud_folder = fresh_unpack / 'assets' / 'characters' / champ / 'hud'
					if not fresh_hud_folder.exists():
						# Try alternative path
						assets_chars = fresh_unpack / 'assets' / 'characters'
						if assets_chars.exists():
							for char_dir in assets_chars.iterdir():
								if char_dir.is_dir() and char_dir.name.lower() == champ:
									alt_hud = char_dir / 'hud'
									if alt_hud.exists():
										fresh_hud_folder = alt_hud
										break
					
					if fresh_hud_folder.exists():
						self._set_status("Copying icons2d folder (without prefix)...")
						prefix = getattr(self, '_used_prefix', 'bum')
						
						hud_copied, hud_converted = self._copy_hud_files_with_prefix(
							fresh_hud_folder, output_dir, prefix, champ, None
						)
			
			# Status message
			if hud_copied > 0:
				status_msg = f"HUD: {hud_copied} files"
				if hud_converted > 0:
					status_msg += f", {hud_converted} converted"
				if vo_count > 0:
					self._set_status(f"Repath done: {output_dir} ({vo_count} VO files, {status_msg})")
				else:
					self._set_status(f"Repath done: {output_dir} ({status_msg})")
			else:
				if vo_count > 0:
					self._set_status(f"Repath done: {output_dir} ({vo_count} VO files copied)")
				else:
					self._set_status(f"Repath done: {output_dir}")
			
			WizardApp._HashStorage.free_all_hashes()
			return True
		except Exception as e:
			error_msg = f"Repath failed: {e}"
			self._set_status(error_msg)
			print(f"[DEBUG] Exception in _repath_fresh: {e}")
			import traceback
			traceback.print_exc()
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

	def _detect_champion_from_folder(self, mod_folder: Path, champs_dir: Path) -> str:
		"""
		Auto-detect champion name from mod folder structure by looking for data/characters/{champ}/.
		Only considers champions that exist in the Champions folder (ignoring subfolders like annietibbers).
		"""
		try:
			# Look for data/characters/{champ}/ structure
			characters_path = mod_folder / 'data' / 'characters'
			if not characters_path.exists():
				# Try case-insensitive search
				for item in mod_folder.iterdir():
					if item.is_dir() and item.name.lower() == 'data':
						for subitem in item.iterdir():
							if subitem.is_dir() and subitem.name.lower() == 'characters':
								characters_path = subitem
								break
						break
			
			if not characters_path or not characters_path.exists():
				return ""
			
			# Get all champion folders
			champ_folders = [d.name.lower() for d in characters_path.iterdir() if d.is_dir()]
			
			# Filter to only champions that exist in the Champions folder
			# (this excludes subfolders like annietibbers, lantern, etc.)
			valid_champs = []
			for champ_folder in champ_folders:
				wad_name = f"{champ_folder}.wad.client"
				matching_wad = self._find_fresh_wad(champs_dir, wad_name)
				if matching_wad and matching_wad.exists():
					valid_champs.append(champ_folder)
			
			# Return the first valid champion found
			if valid_champs:
				return valid_champs[0]
			
			return ""
		except Exception as e:
			print(f"[DEBUG] Error detecting champion from folder: {e}")
			return ""
	
	def _safe_cleanup_work_folder(self, work_root: Path, cleanup_repathed: bool = False):
		"""Safely clean up specific leftover files/folders from previous runs
		Args:
			work_root: Working directory root
			cleanup_repathed: If True, also delete repathed_* folders (only at start of new operation)
		"""
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
			
			# Only remove repathed_* folders if explicitly requested (at start of new operation)
			# BUT preserve folders with special suffixes (fantome name suffixes added during bulk processing)
			if cleanup_repathed:
				if work_root.exists():
					for item in work_root.iterdir():
						if item.is_dir() and item.name.startswith('repathed_'):
							# Get the suffix after "repathed_"
							folder_suffix = item.name.replace('repathed_', '', 1)
							
							# Preserve folders with special suffixes (fantome names):
							# - Contains dots (from fantome filenames like "MyMod_v1.2")
							# - Ends with underscore + number (like "_1", "_2" from duplicate handling)
							# - Has multiple underscores (suggests fantome name with underscores)
							
							# Delete only simple patterns: repathed_{champion}
							# Champion names are typically single lowercase words or simple patterns
							should_delete = True
							
							# Check for dots (fantome filenames often have dots)
							if '.' in folder_suffix:
								should_delete = False
							# Check if ends with _number pattern (duplicate suffix)
							elif '_' in folder_suffix:
								parts = folder_suffix.split('_')
								if len(parts) > 1 and parts[-1].isdigit():
									# Ends with _number - preserve
									should_delete = False
								elif len(parts) > 2:
									# Multiple underscores suggest fantome name - preserve
									should_delete = False
								# Single underscore might be champion name (like "miss_fortune") or fantome
								# If the part after underscore is not a number and looks like a fantome name, preserve
								elif len(parts) == 2 and not parts[1].isdigit():
									# Could be champion name with underscore or fantome name
									# Check if it looks like a fantome name (has uppercase, numbers, special chars)
									second_part = parts[1]
									if any(c.isupper() for c in second_part) or any(c.isdigit() for c in second_part):
										# Looks like fantome name - preserve
										should_delete = False
							
							if should_delete:
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
	
	def _quick_extract_for_bin_selection(self):
		"""Quick extraction to populate BIN dropdown - only extracts mod to find available BINs"""
		try:
			champs_dir = Path(self.champions_dir.get().strip())
			fantome_path = self.fantome_path.get().strip()
			mod_folder_path = self.mod_folder_path.get().strip()
			work_root = self._work_root()
			
			# Safe cleanup
			self._set_status("Cleaning up previous run files...")
			self._safe_cleanup_work_folder(work_root, cleanup_repathed=True)
			
			mod_dir = work_root / 'mod_extract'
			mod_dir.mkdir(parents=True, exist_ok=True)
			
			hashes_dir = self._hash_dir()
			
			# Determine if using fantome or mod folder
			if mod_folder_path:
				# MOD FOLDER MODE: Copy folder directly
				self._set_status("Using pre-extracted mod folder...")
				mod_folder = Path(mod_folder_path)
				
				# Auto-detect champion name
				champ_name = self._detect_champion_from_folder(mod_folder, champs_dir)
				if not champ_name:
					self._set_status("Aborted: Could not auto-detect champion from mod folder.")
					messagebox.showerror(APP_TITLE, "Could not detect champion from mod folder structure.")
					return
				
				self._champion = champ_name
				self.detected_wad_name.set(f"Auto-detected: {champ_name}")
				
				# Copy mod folder to mod_extract/unpacked
				mod_unpack = mod_dir / 'unpacked'
				shutil.copytree(mod_folder, mod_unpack, dirs_exist_ok=True)
			else:
				# FANTOME MODE: Extract mod WAD
				fantome = Path(fantome_path)
				
				self._set_status("Detecting champion .wad.client inside .fantome...")
				member = self._detect_wad_member_in_fantome(fantome, champs_dir)
				if not member:
					self.detected_wad_name.set("No champion wad found in .fantome")
					self._set_status("Aborted: .fantome does not contain a champion wad client.")
					return
				
				self._fantome_member_path = member
				wad_name = Path(member).name
				self._champion = wad_name.split('.')[0].lower()
				self.detected_wad_name.set(f"Detected: {wad_name}")
				
				# Extract mod wad
				self._set_status("Extracting mod .wad.client from .fantome...")
				mod_wad_path = mod_dir / wad_name
				self._extract_file_from_fantome(fantome, member, mod_wad_path)
				
				# Extract hashes from fantome
				try:
					temp_unpack = mod_dir / 'temp_for_hashes'
					temp_unpack.mkdir(parents=True, exist_ok=True)
					temp_ok = self._try_extract_wad(mod_wad_path, temp_unpack, hashes_dir)
					if temp_ok:
						self._extract_hashes_from_folder(temp_unpack, hashes_dir)
						shutil.rmtree(temp_unpack, ignore_errors=True)
				except Exception:
					pass
				
				# Unpack mod wad
				self._set_status("Unpacking mod .wad.client...")
				mod_unpack = mod_dir / 'unpacked'
				self._try_extract_wad(mod_wad_path, mod_unpack, hashes_dir)
			
			# Populate BIN dropdown
			self._set_status("Populating BIN dropdown...")
			self._populate_bin_dropdown(mod_unpack)
			
			self._set_status("Quick extraction complete. Please select main BIN and proceed.")
			self.step_completed[1] = True
			self.root.after(0, self._update_nav)
			# Show step 2 (BIN selection) - user must select BIN before proceeding
			self.root.after(0, lambda: self._show_step(2))
		
		except Exception as e:
			self._set_status(f"Error: {e}")
			import traceback
			traceback.print_exc()
	
	def _detect_and_extract_with_bin(self):
		"""Full extraction with selected BIN - extracts linked BINs for the selected BIN and merges them"""
		# This is the same as _detect_and_extract but uses the selected BIN to extract linked BINs
		# We'll call the original function but modify it to use selected BIN
		self._detect_and_extract()
	
	def _detect_and_extract(self):
		try:
			champs_dir = Path(self.champions_dir.get().strip())
			fantome_path = self.fantome_path.get().strip()
			mod_folder_path = self.mod_folder_path.get().strip()
			work_root = self._work_root()
			
			# Safe cleanup of previous run leftovers (including repathed folders at start of new operation)
			self._set_status("Cleaning up previous run files...")
			self._safe_cleanup_work_folder(work_root, cleanup_repathed=True)
			
			mod_dir = work_root / 'mod_extract'
			fresh_dir = work_root / 'fresh_extract'
			mod_dir.mkdir(parents=True, exist_ok=True)
			fresh_dir.mkdir(parents=True, exist_ok=True)
			
			# Use AppData hash directory
			hashes_dir = self._hash_dir()
			
			# Determine if using fantome or mod folder
			if mod_folder_path:
				# MOD FOLDER MODE: Copy folder directly, skip fantome extraction
				self._set_status("Using pre-extracted mod folder...")
				mod_folder = Path(mod_folder_path)
				
				# Auto-detect champion name from folder structure
				self._set_status("Auto-detecting champion from folder structure...")
				champ_name = self._detect_champion_from_folder(mod_folder, champs_dir)
				if not champ_name:
					self._set_status("Aborted: Could not auto-detect champion from mod folder.")
					messagebox.showerror(APP_TITLE, "Could not detect champion from mod folder structure.\nPlease ensure the folder contains data/characters/{champion}/ structure.")
					return
				
				self._champion = champ_name
				wad_name = f"{champ_name}.wad.client"
				self.detected_wad_name.set(f"Auto-detected: {champ_name}")
				
				# Copy mod folder to mod_extract/unpacked
				self._set_status("Copying mod folder to work directory...")
				mod_unpack = mod_dir / 'unpacked'
				shutil.copytree(mod_folder, mod_unpack, dirs_exist_ok=True)
				ok_mod = True  # Mod folder copy succeeded
				
				# Find fresh wad in champions folder
				self._set_status("Locating fresh .wad.client in Champions folder...")
				fresh_wad_file = self._find_fresh_wad(champs_dir, wad_name)
				if not fresh_wad_file or not fresh_wad_file.exists():
					self._set_status(f"Aborted: could not find {wad_name} under Champions folder.")
					return
				
				# Copy fresh wad to work dir
				fresh_wad_copy = fresh_dir / wad_name
				shutil.copy2(fresh_wad_file, fresh_wad_copy)
				
				# Extract fresh wad
				self._set_status("Unpacking fresh .wad.client (best-effort)...")
				fresh_unpack = fresh_dir / 'unpacked'
				ok_fresh = self._try_extract_wad(fresh_wad_copy, fresh_unpack, hashes_dir)
				
				# Extract linked BINs from fresh extracted folder for the selected BIN
				# This reads the fresh BIN to get linked paths and stores them for merging
				try:
					selected_bin = self.main_bin_choice.get().strip()
					if selected_bin:
						self._set_status(f"Reading linked BINs from fresh {selected_bin}...")
						self._extract_linked_bins_for_selected_bin(fresh_wad_copy, fresh_unpack, hashes_dir, champ_name, selected_bin)
					else:
						self._set_status("Warning: No BIN selected, skipping linked BIN extraction")
				except Exception as e:
					self._set_status(f"Warning: Linked BIN extraction skipped: {e}")
					print(f"[DEBUG] Linked BIN extraction error: {e}")
				
			else:
				# FANTOME MODE: Original extraction logic
				fantome = Path(fantome_path)
				
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

				# FIRST: Extract hashes from the fantome before unpacking the wad
				# This improves the quality of wad unpacking by having more hash data available
				try:
					self._set_status("Extracting hashes from fantome files...")
					# First do a quick unpack to get BIN files for hash extraction
					temp_unpack = mod_dir / 'temp_for_hashes'
					temp_unpack.mkdir(parents=True, exist_ok=True)
					temp_ok = self._try_extract_wad(mod_wad_path, temp_unpack, hashes_dir)
					if temp_ok:
						self._extract_hashes_from_folder(temp_unpack, hashes_dir)
						# Clean up temp folder
						shutil.rmtree(temp_unpack, ignore_errors=True)
					else:
						self._set_status("Hash extraction skipped: could not unpack wad for hash extraction")
				except Exception as e:
					self._set_status(f"Hash extraction skipped: {e}")

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

				# NOW unpack with improved hashes
				self._set_status("Unpacking mod .wad.client with extracted hashes...")
				mod_unpack = mod_dir / 'unpacked'
				ok_mod = self._try_extract_wad(mod_wad_path, mod_unpack, hashes_dir)

				self._set_status("Unpacking fresh .wad.client (best-effort)...")
				fresh_unpack = fresh_dir / 'unpacked'
				ok_fresh = self._try_extract_wad(fresh_wad_copy, fresh_unpack, hashes_dir)
				
				# Extract linked BINs from fresh extracted folder for the selected BIN
				# This reads the fresh BIN to get linked paths and stores them for merging
				try:
					selected_bin = self.main_bin_choice.get().strip()
					if selected_bin:
						self._set_status(f"Reading linked BINs from fresh {selected_bin}...")
						self._extract_linked_bins_for_selected_bin(fresh_wad_copy, fresh_unpack, hashes_dir, self._champion, selected_bin)
					else:
						self._set_status("Warning: No BIN selected, skipping linked BIN extraction")
				except Exception as e:
					self._set_status(f"Warning: Linked BIN extraction skipped: {e}")
					print(f"[DEBUG] Linked BIN extraction error: {e}")
			
			# Convert mod HUD DDS files to TEX FIRST (before any other conversions)
			# This ensures mod's HUD files are in the correct format from the start
			champ = getattr(self, '_champion', '').lower()
			if champ:
				try:
					# Find the main BIN path based on selected BIN
					main_bin_path = None
					selected_bin = self.main_bin_choice.get().strip() if hasattr(self, 'main_bin_choice') else None
					if selected_bin:
						skins_dir = mod_unpack / 'data' / 'characters' / champ / 'skins'
						if skins_dir.exists():
							selected_lower = selected_bin.lower().strip()
							skin_idx = None
							if selected_lower == 'base':
								skin_idx = 0
							else:
								m = re.search(r"(skin)?\s*(\d+)", selected_lower)
								if m:
									skin_idx = int(m.group(2))
							
							if skin_idx is not None:
								main_bin_path = skins_dir / f'skin{skin_idx}.bin'
								if not main_bin_path.exists():
									main_bin_path = None
					
					self._set_status("Converting mod HUD DDS files to TEX (before overlay)...")
					hud_converted_count = self._convert_hud_dds_to_tex(mod_unpack, champ, main_bin_path)
					if hud_converted_count > 0:
						self._set_status(f"Converted {hud_converted_count} mod HUD DDS file(s) to TEX")
				except Exception as e:
					self._set_status(f"Warning: Mod HUD DDS→TEX conversion failed: {e}")
					print(f"[DEBUG] Mod HUD DDS→TEX conversion error: {e}")

			# After fresh extract, run TEX→DDS conversion using LtMAO.Ritoddstex if available
			try:
				self._set_status("Converting TEX → DDS in fresh_extract...")
				self._convert_all_tex_to_dds(fresh_unpack)
			except Exception as e:
				self._set_status(f"TEX→DDS conversion skipped: {e}")

			# Hash extraction already done earlier for fantome mode
			# For mod folder mode, extract hashes now since we have the unpacked files
			if mod_folder_path:
				try:
					self._set_status("Extracting hashes from mod files...")
					self._extract_hashes_from_folder(mod_unpack, hashes_dir)
				except Exception as e:
					self._set_status(f"Hash extraction skipped: {e}")

			# Convert DDS↔TEX in mod subfolders BEFORE overlay
			# This ensures mod's edited textures match what BINs reference
			champ = getattr(self, '_champion', '').lower()
			try:
				self._set_status("Converting textures in character subfolders (before overlay)...")
				self._convert_dds_tex_in_subfolders(fresh_unpack, mod_unpack, champ)
			except Exception as e:
				self._set_status(f"Texture conversion skipped: {e}")
				print(f"[DEBUG] Texture conversion error: {e}")
			
			# Store HUD folder from mod before overlay (so we can restore it after repathing)
			try:
				self._set_status("Storing mod HUD folder...")
				self._store_mod_hud_folder(mod_unpack, champ)
			except Exception as e:
				self._set_status(f"HUD folder storage skipped: {e}")
				print(f"[DEBUG] HUD folder storage error: {e}")
			
			# Overlay: copy mod extracted content over fresh extracted content (overwrite)
			self._set_status("Overlaying mod over fresh (overwrite)...")
			copied, skipped = self._overlay_copy(mod_unpack, fresh_unpack)
			
			self._set_status(f"Overlay complete: copied {copied}, skipped {skipped}. Proceed to Step 5 to repath.")

			# Mark step 3 as complete (full extraction with linked BINs) and enable Next button
			self.step_completed[3] = True
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

	def _process_bulk_fantomes(self):
		"""Process multiple fantome files in sequence - fully automatic with Skin0"""
		try:
			total_files = len(self.bulk_fantome_paths)
			successful = 0
			failed = []
			
			# Ensure Skin0 is set for bulk processing (required for No Skin Lite if enabled)
			current_bin = self.main_bin_choice.get().strip()
			if not current_bin or current_bin.lower() in ('skin0', 'base', '0'):
				self.main_bin_choice.set("Skin0")
			
			# Clean up at the start of bulk processing (including old repathed folders)
			work_root = self._work_root()
			self._set_status("Cleaning up previous run files...")
			self._safe_cleanup_work_folder(work_root, cleanup_repathed=True)
			
			# Determine skin choice message
			skin_choice = self.main_bin_choice.get().strip()
			self._set_status(f"🔄 BULK MODE: Starting automatic processing of {total_files} file(s) with {skin_choice}...")
			
			# Automatically mark steps as complete since we're processing everything automatically
			self.step_completed[1] = True
			self.step_completed[2] = True
			
			for idx, fantome_path in enumerate(self.bulk_fantome_paths, 1):
				fantome_name = Path(fantome_path).name
				self._set_status(f"[{idx}/{total_files}] Processing: {fantome_name}...")
				
				try:
					# Temporarily set this fantome as the current one
					original_fantome = self.fantome_path.get()
					original_mod_folder = self.mod_folder_path.get()
					original_member_path = getattr(self, '_fantome_member_path', None)
					original_hud_folder = getattr(self, '_mod_hud_folder', None)
					
					self.fantome_path.set(fantome_path)
					self.mod_folder_path.set("")  # Clear mod folder for fantome mode
					self._fantome_member_path = None  # Reset for this file
					self._mod_hud_folder = None  # Reset for this file
					
					# Step 1: Detect and extract
					champs_dir = Path(self.champions_dir.get().strip())
					# work_root already set above at start of bulk processing
					
					# Clean up intermediate folders for this iteration (don't delete repathed folders - keep them for inspection)
					self._safe_cleanup_work_folder(work_root, cleanup_repathed=False)
					
					mod_dir = work_root / 'mod_extract'
					fresh_dir = work_root / 'fresh_extract'
					mod_dir.mkdir(parents=True, exist_ok=True)
					fresh_dir.mkdir(parents=True, exist_ok=True)
					
					hashes_dir = self._hash_dir()
					fantome = Path(fantome_path)
					
					self._set_status(f"[{idx}/{total_files}] Detecting champion in {fantome_name}...")
					member = self._detect_wad_member_in_fantome(fantome, champs_dir)
					if not member:
						self._set_status(f"[{idx}/{total_files}] ⚠ Skipped {fantome_name}: No champion WAD found")
						failed.append((fantome_name, "No champion WAD found"))
						continue
					
					self._fantome_member_path = member
					wad_name = Path(member).name
					self._champion = wad_name.split('.')[0].lower()
					
					# Extract mod wad
					self._set_status(f"[{idx}/{total_files}] Extracting mod WAD from {fantome_name}...")
					mod_wad_path = mod_dir / wad_name
					self._extract_file_from_fantome(fantome, member, mod_wad_path)
					
					# Extract hashes
					try:
						temp_unpack = mod_dir / 'temp_for_hashes'
						temp_unpack.mkdir(parents=True, exist_ok=True)
						temp_ok = self._try_extract_wad(mod_wad_path, temp_unpack, hashes_dir)
						if temp_ok:
							self._extract_hashes_from_folder(temp_unpack, hashes_dir)
							shutil.rmtree(temp_unpack, ignore_errors=True)
					except Exception:
						pass
					
					# Find fresh wad
					fresh_wad_file = self._find_fresh_wad(champs_dir, wad_name)
					if not fresh_wad_file or not fresh_wad_file.exists():
						self._set_status(f"[{idx}/{total_files}] ⚠ Skipped {fantome_name}: Fresh WAD not found")
						failed.append((fantome_name, "Fresh WAD not found"))
						continue
					
					fresh_wad_copy = fresh_dir / wad_name
					shutil.copy2(fresh_wad_file, fresh_wad_copy)
					
					# Unpack
					self._set_status(f"[{idx}/{total_files}] Unpacking WADs...")
					mod_unpack = mod_dir / 'unpacked'
					ok_mod = self._try_extract_wad(mod_wad_path, mod_unpack, hashes_dir)
					fresh_unpack = fresh_dir / 'unpacked'
					ok_fresh = self._try_extract_wad(fresh_wad_copy, fresh_unpack, hashes_dir)
					
					if not ok_mod or not ok_fresh:
						self._set_status(f"[{idx}/{total_files}] ⚠ Skipped {fantome_name}: Unpacking failed")
						failed.append((fantome_name, "Unpacking failed"))
						continue
					
					# Convert textures
					try:
						self._convert_all_tex_to_dds(fresh_unpack)
					except Exception:
						pass
					
					champ = getattr(self, '_champion', '').lower()
					try:
						self._convert_dds_tex_in_subfolders(fresh_unpack, mod_unpack, champ)
					except Exception:
						pass
					
					# Store HUD folder
					try:
						self._store_mod_hud_folder(mod_unpack, champ)
					except Exception:
						pass
					
					# Overlay
					self._set_status(f"[{idx}/{total_files}] Overlaying mod over fresh...")
					self._overlay_copy(mod_unpack, fresh_unpack)
					
					# Step 2: Repath
					self._set_status(f"[{idx}/{total_files}] Repathing {fantome_name}...")
					repath_ok = self._repath_fresh(fresh_unpack)
					if not repath_ok:
						self._set_status(f"[{idx}/{total_files}] ⚠ Skipped {fantome_name}: Repath failed")
						failed.append((fantome_name, "Repath failed"))
						continue
					
					# Step 3: Find and rename repathed directory to keep it unique
					champ = getattr(self, '_champion', '').lower()
					original_repathed_dir = work_root / f'repathed_{champ}'
					
					if not original_repathed_dir.exists():
						self._set_status(f"[{idx}/{total_files}] ⚠ Skipped {fantome_name}: Repathed directory not found")
						failed.append((fantome_name, "Repathed directory not found"))
						continue
					
					# Rename repathed folder to unique name (include fantome name for easy identification)
					fantome_stem = Path(fantome_path).stem  # Get filename without extension
					unique_repathed_dir = work_root / f'repathed_{fantome_stem}'
					
					# If folder already exists, add index suffix
					counter = 1
					while unique_repathed_dir.exists():
						unique_repathed_dir = work_root / f'repathed_{fantome_stem}_{counter}'
						counter += 1
					
					try:
						original_repathed_dir.rename(unique_repathed_dir)
						self._set_status(f"[{idx}/{total_files}] Renamed repathed folder to: {unique_repathed_dir.name}")
					except Exception as e:
						self._set_status(f"[{idx}/{total_files}] ⚠ Warning: Could not rename repathed folder: {e}")
						unique_repathed_dir = original_repathed_dir  # Use original if rename fails
					
					repathed_dir = unique_repathed_dir
					
					# Store repathed_dir for missing files check
					self._repathed_dir = repathed_dir
					
					# Check for missing files and create placeholders (full check, not just counting)
					self._set_status(f"[{idx}/{total_files}] Checking for missing texture files...")
					missing_count = 0
					try:
						# Run full missing files check and create placeholders
						result = self._pyntex_check_dir(repathed_dir)
						
						# Collect missing textures (excluding HUD folder files)
						missing_textures = []
						missing_hud_count = 0
						for key, bin_results in result.items():
							if key == 'junk_files':
								continue
							if isinstance(bin_results, list):
								for entry in bin_results:
									if isinstance(entry, dict):
										missing_in_entry = entry.get('missing_files', [])
										for missing_file in missing_in_entry:
											if missing_file.lower().endswith(('.dds', '.tex')):
												# Skip HUD folder files - don't create placeholders for them
												if '/hud/' in missing_file.lower() or '\\hud\\' in missing_file.lower():
													missing_hud_count += 1
													continue
												if missing_file not in missing_textures:
													missing_textures.append(missing_file)
						
						missing_count = len(missing_textures)
						
						# Create placeholders for missing textures (excluding HUD files)
						if missing_count > 0:
							if missing_hud_count > 0:
								self._set_status(f"[{idx}/{total_files}] Found {missing_count} missing textures (excluding {missing_hud_count} HUD files). Creating placeholders...")
							else:
								self._set_status(f"[{idx}/{total_files}] Found {missing_count} missing textures. Creating placeholders...")
							self._create_placeholder_textures(repathed_dir, missing_textures)
							if missing_hud_count > 0:
								self._set_status(f"[{idx}/{total_files}] Created {missing_count} placeholder textures (HUD files skipped).")
							else:
								self._set_status(f"[{idx}/{total_files}] Created {missing_count} placeholder textures.")
						else:
							if missing_hud_count > 0:
								self._set_status(f"[{idx}/{total_files}] ✓ No missing texture files found (skipped {missing_hud_count} HUD files)!")
							else:
								self._set_status(f"[{idx}/{total_files}] ✓ No missing texture files found!")
					except Exception as e:
						self._set_status(f"[{idx}/{total_files}] ⚠ Warning: Missing files check failed: {e}")
						import traceback
						traceback.print_exc()
					
					# Apply No Skin Lite if enabled (ONLY works with Skin0/Base to prevent skin hacking)
					if self.no_skin_lite_enabled.get():
						desired_raw = (self.main_bin_choice.get() or '').strip()
						desired = desired_raw.lower()
						if desired in ('base', 'skin0', '0'):
							self._set_status(f"[{idx}/{total_files}] Applying No Skin Lite...")
							try:
								self._apply_no_skin_lite_to_wad(repathed_dir)
								self._set_status(f"[{idx}/{total_files}] No Skin Lite applied successfully!")
							except Exception as e:
								self._set_status(f"[{idx}/{total_files}] ⚠ No Skin Lite failed: {e}")
								import traceback
								traceback.print_exc()
						else:
							self._set_status(f"[{idx}/{total_files}] No Skin Lite skipped (only works with Base/Skin0, not Skin1+ to prevent skin hacking)")
					
					# Create final fantome
					self._set_status(f"[{idx}/{total_files}] Creating final fantome for {fantome_name}...")
					fantome_created = self._create_final_fantome_bulk(repathed_dir, missing_count, fantome)
					
					if fantome_created:
						successful += 1
						final_fantome_name = Path(fantome_path).stem + "_repathed" + Path(fantome_path).suffix
						self._set_status(f"[{idx}/{total_files}] ✓ Completed {fantome_name} → {final_fantome_name}")
					else:
						self._set_status(f"[{idx}/{total_files}] ✗ Failed to create fantome for {fantome_name}")
						failed.append((fantome_name, "Fantome creation failed"))
					
					# Clean up intermediate files for this iteration (keep repathed folder for inspection)
					try:
						if mod_dir.exists():
							shutil.rmtree(mod_dir, ignore_errors=True)
						if fresh_dir.exists():
							shutil.rmtree(fresh_dir, ignore_errors=True)
					except Exception:
						pass
					
				except Exception as e:
					self._set_status(f"[{idx}/{total_files}] ✗ Error processing {fantome_name}: {e}")
					failed.append((fantome_name, str(e)))
					import traceback
					traceback.print_exc()
			
			# Final summary
			if successful == total_files:
				self._set_status(f"✓✓✓ BULK PROCESSING COMPLETE! All {total_files} file(s) processed successfully with Skin0.")
			else:
				summary = f"✓✓✓ BULK PROCESSING COMPLETE: {successful}/{total_files} successful"
				if failed:
					summary += f"\nFailed: {', '.join([f[0] for f in failed])}"
				self._set_status(summary)
			
			# Mark all steps as complete (bulk mode processes everything automatically)
			self.step_completed[1] = True
			self.step_completed[2] = True
			self.step_completed[3] = True
			
			# Auto-advance to final step to show completion
			self.root.after(0, lambda: self._show_step(len(self.steps) - 1))
			self.root.after(0, self._update_nav)
			
		except Exception as e:
			self._set_status(f"Bulk processing error: {e}")
			import traceback
			traceback.print_exc()
	
	def _create_final_fantome_bulk(self, repathed_dir: Path, missing_count: int, fantome_path: Path) -> bool:
		"""Create final fantome for bulk processing (uses provided fantome_path instead of self.fantome_path)
		Returns True if successful, False otherwise"""
		try:
			work_root = self._work_root()
			
			# Determine champion name and wad name
			champ = getattr(self, '_champion', '').lower()
			if not champ:
				self._set_status("Error: Champion name unknown")
				return False
			wad_name = f"{champ}.wad.client"
			
			# Pack repathed_dir -> new wad
			final_wad_path = work_root / f"final_{wad_name}"
			self._set_status(f"Packing WAD from {repathed_dir.name}...")
			self._pack_wad(repathed_dir, final_wad_path)
			
			if not final_wad_path.exists():
				self._set_status("Error: WAD packing failed")
				return False
			
			# FANTOME MODE: Copy original fantome and replace the champion WAD
			member = getattr(self, '_fantome_member_path', None)
			if not member:
				self._set_status("Error: Original WAD member path unknown")
				if final_wad_path.exists():
					os.remove(final_wad_path)
				return False
			
			# Build final fantome
			fantome = Path(fantome_path)
			final_fantome = fantome.with_name(f"{fantome.stem}_repathed{fantome.suffix}")
			
			self._set_status(f"Creating fantome: {final_fantome.name}...")
			import zipfile as _zip
			with _zip.ZipFile(fantome, 'r') as zin, _zip.ZipFile(final_fantome, 'w', compression=_zip.ZIP_DEFLATED) as zout:
				has_info_json = False
				for item in zin.infolist():
					data = zin.read(item.filename)
					item_path_normalized = item.filename.replace('\\', '/').lower()
					member_path_normalized = member.replace('\\', '/').lower()
					
					if item_path_normalized in ['meta/info.json', 'info.json']:
						has_info_json = True
						info_json = self._update_info_json(data.decode('utf-8'))
						zout.writestr(item.filename, info_json)
					elif item_path_normalized == member_path_normalized:
						# Replace with new repathed WAD
						with open(final_wad_path, 'rb') as f:
							data = f.read()
						zout.writestr(item.filename, data)
					else:
						zout.writestr(item, data)
				
				if not has_info_json:
					info_json = self._create_info_json(champ, is_new=False)
					zout.writestr("META/info.json", info_json)
			
			# Cleanup final wad (temporary file)
			if final_wad_path.exists():
				os.remove(final_wad_path)
			
			if final_fantome.exists():
				self._set_status(f"✓ Fantome created: {final_fantome.name}")
				return True
			else:
				self._set_status("Error: Fantome file was not created")
				return False
			
		except Exception as e:
			self._set_status(f"Error creating final fantome: {e}")
			print(f"Error creating final fantome: {e}")
			import traceback
			traceback.print_exc()
			return False
	
	def _check_missing_files_simple(self, repathed_dir: Path) -> int:
		"""Quick check for missing files - returns count"""
		missing_count = 0
		try:
			# Simple check: count placeholder textures
			for root, dirs, files in os.walk(repathed_dir):
				for f in files:
					if f.endswith('_placeholder.dds'):
						missing_count += 1
		except Exception:
			pass
		return missing_count

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
			# Skip HUD folders - they should remain as TEX files
			dirpath_lower = str(dirpath).lower()
			if '/hud/' in dirpath_lower or '\\hud\\' in dirpath_lower:
				continue
			
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
	
	# ---------- DDS → TEX conversion ----------
	def _dds2tex(self, dds_path: Path, tex_path: Path) -> None:
		"""Convert DDS file to TEX format using LtMAO's Ritoddstex logic. If file is actually a TEX file, just rename it."""
		import pyRitoFile
		import math
		import struct
		
		# First, try to read as TEX file (in case it's a misnamed TEX file)
		try:
			tex = pyRitoFile.tex.TEX().read(str(dds_path))
			# If successful, it's actually a TEX file - just copy/rename it
			tex.write(str(tex_path))
			return
		except Exception:
			# Not a TEX file, continue with DDS parsing
			pass
		
		# Read DDS header - matching LtMAO's Ritoddstex.dds2tex implementation
		with pyRitoFile.stream.BytesStream.reader(str(dds_path)) as bs:
			signature, = bs.read_u32()
			if signature != 0x20534444:  # "DDS "
				raise ValueError(f"Invalid DDS file (wrong signature): {dds_path}")
			
			# Read all 31 uints at once (matching LtMAO)
			uints = bs.read_u32(31)
			dds_header = {
				'dwSize': uints[0],
				'dwFlags': uints[1],
				'dwHeight': uints[2],
				'dwWidth': uints[3],
				'dwPitchOrLinearSize': uints[4],
				'dwDepth': uints[5],
				'dwMipMapCount': uints[6],
				'dwReserved1': uints[7:7+11],
				'ddspf': {
					'dwSize': uints[18],
					'dwFlags': uints[19],
					'dwFourCC': uints[20],
					'dwRGBBitCount': uints[21],
					'dwRBitMask': uints[22],
					'dwGBitMask': uints[23],
					'dwBBitMask': uints[24],
					'dwABitMask': uints[25],
				},
				'dwCaps': uints[26],
				'dwCaps2': uints[27],
				'dwCaps3': uints[28],
				'dwCaps4': uints[29],
				'dwReserved2': uints[30],
			}
			dds_pixel_format = dds_header['ddspf']
			
			# Read all remaining data at once
			dds_data = bs.read(-1)
		
		# RGBA conversion handling (matching LtMAO)
		custom_rgba_format = False
		rgba_indices = [-1, -1, -1, -1]
		mask_to_index = {
			0x000000ff: 0,
			0x0000ff00: 1,
			0x00ff0000: 2,
			0xff000000: 3
		}
		
		# Prepare TEX header
		tex = pyRitoFile.tex.TEX()
		tex.width = dds_header['dwWidth']
		tex.height = dds_header['dwHeight']
		
		# Determine TEX format from DDS pixel format
		if dds_pixel_format['dwFourCC'] == int('DXT1'.encode('ascii')[::-1].hex(), 16):
			tex.format = pyRitoFile.tex.TEXFormat.DXT1
		elif dds_pixel_format['dwFourCC'] == int('DXT5'.encode('ascii')[::-1].hex(), 16):
			tex.format = pyRitoFile.tex.TEXFormat.DXT5
		elif (dds_pixel_format['dwFlags'] & 0x00000041) == 0x00000041:
			tex.format = pyRitoFile.tex.TEXFormat.BGRA8
			if dds_pixel_format['dwRGBBitCount'] != 32:
				raise ValueError(f"dwRGBBitCount is expected 32, not {dds_pixel_format['dwRGBBitCount']}")
			if (dds_pixel_format['dwBBitMask'] != 0x000000ff or 
			    dds_pixel_format['dwGBitMask'] != 0x0000ff00 or 
			    dds_pixel_format['dwRBitMask'] != 0x00ff0000 or 
			    dds_pixel_format['dwABitMask'] != 0xff000000):
				custom_rgba_format = True
				rgba_indices[0] = mask_to_index[dds_pixel_format['dwRBitMask']]
				rgba_indices[1] = mask_to_index[dds_pixel_format['dwGBitMask']]
				rgba_indices[2] = mask_to_index[dds_pixel_format['dwBBitMask']]
				rgba_indices[3] = mask_to_index[dds_pixel_format['dwABitMask']]
				for index in rgba_indices:
					if index == -1:
						raise ValueError(f"Bitmask data invalid. Cannot convert to BGRA output format.")
		else:
			raise ValueError(f"Unsupported DDS format: {dds_pixel_format['dwFourCC']}")
		
		# Handle mipmaps
		if dds_header['dwMipMapCount'] > 1:
			expected_mipmap_count = math.floor(math.log2(max(dds_header['dwWidth'], dds_header['dwHeight']))) + 1
			if dds_header['dwMipMapCount'] != expected_mipmap_count:
				raise ValueError(f"Wrong DDS mipmap count: {dds_header['dwMipMapCount']}, expected: {expected_mipmap_count}")
			tex.mipmaps = True
		
		# RGBA conversion if needed
		if custom_rgba_format:
			new_data = b''
			r_index, g_index, b_index, a_index = rgba_indices
			for i in range(0, len(dds_data), 4):
				current_pixel_data = 0
				current_pixel_data |= dds_data[i + b_index] << 0
				current_pixel_data |= dds_data[i + g_index] << 8
				current_pixel_data |= dds_data[i + r_index] << 16
				current_pixel_data |= dds_data[i + a_index] << 24
				new_data += struct.pack('I', current_pixel_data)
			dds_data = new_data
		
		# Prepare TEX data (matching LtMAO's mipmap extraction)
		if tex.mipmaps:
			if tex.format == pyRitoFile.tex.TEXFormat.DXT1:
				block_size = 4
				bytes_per_block = 8
			elif tex.format == pyRitoFile.tex.TEXFormat.DXT5:
				block_size = 4
				bytes_per_block = 16
			else:
				block_size = 1
				bytes_per_block = 4
			
			mipmap_count = dds_header['dwMipMapCount']
			current_offset = 0
			tex.data = []
			for i in range(mipmap_count):
				current_width = max(tex.width >> i, 1)
				current_height = max(tex.height >> i, 1)
				block_width = (current_width + block_size - 1) // block_size
				block_height = (current_height + block_size - 1) // block_size
				current_size = bytes_per_block * block_width * block_height
				data = dds_data[current_offset:current_offset+current_size]
				tex.data.append(data)
				current_offset += current_size
			# Mipmap in DDS file is reversed to TEX file
			tex.data.reverse()
		else:
			tex.data = [dds_data]
		
		# Write TEX file
		tex.write(str(tex_path))
	
	def _convert_dds_tex_in_subfolders(self, fresh_unpack: Path, mod_unpack: Path, main_champion: str) -> None:
		"""
		Convert DDS↔TEX in mod's asset subfolders based on fresh unpack structure.
		1. Scan fresh_unpack/data/characters/ to find subfolders (excluding main champion)
		2. For each subfolder found, check mod_unpack/assets/characters/{subfolder}/
		3. In those mod folders: convert DDS→TEX if DDS exists, or TEX→DDS if no DDS but TEX exists
		"""
		fresh_unpack = Path(fresh_unpack)
		mod_unpack = Path(mod_unpack)
		
		if not fresh_unpack.exists() or not mod_unpack.exists():
			return
		
		converted_dds_to_tex = 0
		converted_tex_to_dds = 0
		failed = 0
		main_champion_lower = main_champion.lower() if main_champion else ""
		
		# Step 1: Find subfolders in fresh_unpack/data/characters/ (excluding main champion)
		fresh_data_chars = fresh_unpack / 'data' / 'characters'
		subfolders = []
		
		print(f"[DEBUG] Checking for subfolders in: {fresh_data_chars}")
		print(f"[DEBUG] Main champion to exclude: {main_champion_lower}")
		
		if fresh_data_chars.exists():
			for char_dir in fresh_data_chars.iterdir():
				if char_dir.is_dir():
					char_name = char_dir.name.lower()
					print(f"[DEBUG] Found character folder: {char_dir.name} (lower: {char_name})")
					# Include all subfolders except the main champion
					if char_name != main_champion_lower:
						subfolders.append(char_dir.name)
						print(f"[DEBUG] Added subfolder: {char_dir.name}")
		
		if not subfolders:
			self._set_status("No character subfolders found in fresh unpack.")
			print(f"[DEBUG] No subfolders found (excluding {main_champion_lower})")
			return
		
		print(f"[DEBUG] Subfolders to process: {subfolders}")
		
		# Step 2: For each subfolder, convert in mod_unpack/assets/characters/{subfolder}/
		for subfolder in subfolders:
			mod_assets_subfolder = mod_unpack / 'assets' / 'characters' / subfolder
			
			print(f"[DEBUG] Checking mod folder: {mod_assets_subfolder}")
			
			if not mod_assets_subfolder.exists():
				print(f"[DEBUG] Mod folder does not exist: {mod_assets_subfolder}")
				continue
			
			print(f"[DEBUG] Processing mod folder: {mod_assets_subfolder}")
			
			# Walk through the subfolder and convert files
			files_found = 0
			for dirpath, _dirnames, filenames in os.walk(mod_assets_subfolder):
				current_path = Path(dirpath)
				
				for name in filenames:
					name_lower = name.lower()
					files_found += 1
					
					if name_lower.endswith('.dds'):
						# Found DDS: convert to TEX
						dds_path = current_path / name
						tex_path = dds_path.with_suffix('.tex')
						
						print(f"[DEBUG] Found DDS: {dds_path}")
						
						# Skip if TEX already exists
						if tex_path.exists():
							print(f"[DEBUG] TEX already exists, skipping: {tex_path}")
							continue
						
						try:
							print(f"[DEBUG] Converting DDS→TEX: {dds_path} -> {tex_path}")
							self._dds2tex(dds_path, tex_path)
							converted_dds_to_tex += 1
							print(f"[DEBUG] Successfully converted DDS→TEX: {dds_path}")
						except Exception as e:
							failed += 1
							print(f"[DEBUG] Failed to convert DDS→TEX {dds_path}: {e}")
							import traceback
							traceback.print_exc()
					
					elif name_lower.endswith('.tex'):
						# Found TEX: check if corresponding DDS exists
						tex_path = current_path / name
						dds_path = tex_path.with_suffix('.dds')
						
						print(f"[DEBUG] Found TEX: {tex_path}")
						
						# Only convert TEX→DDS if no DDS exists
						if not dds_path.exists():
							try:
								print(f"[DEBUG] Converting TEX→DDS: {tex_path} -> {dds_path}")
								self._tex2dds(tex_path, dds_path)
								converted_tex_to_dds += 1
								print(f"[DEBUG] Successfully converted TEX→DDS: {tex_path}")
							except Exception as e:
								failed += 1
								print(f"[DEBUG] Failed to convert TEX→DDS {tex_path}: {e}")
								import traceback
								traceback.print_exc()
			
			print(f"[DEBUG] Total files found in {mod_assets_subfolder}: {files_found}")
		
		if converted_dds_to_tex > 0 or converted_tex_to_dds > 0 or failed > 0:
			status_parts = []
			if converted_dds_to_tex > 0:
				status_parts.append(f"DDS→TEX: {converted_dds_to_tex}")
			if converted_tex_to_dds > 0:
				status_parts.append(f"TEX→DDS: {converted_tex_to_dds}")
			if failed > 0:
				status_parts.append(f"failed: {failed}")
			self._set_status(f"Texture conversion in subfolders: {', '.join(status_parts)}")

	def _populate_bin_dropdown(self, mod_unpack: Path):
		"""Populate the BIN dropdown with available skin BINs from the mod"""
		try:
			champ = getattr(self, '_champion', '').lower()
			print(f"[DEBUG populate_bin_dropdown] Champion: {champ}")
			if not champ:
				print("[DEBUG populate_bin_dropdown] No champion found, returning")
				return
			
			# Look for BIN files in the mod's skins folder
			skins_dir = mod_unpack / 'data' / 'characters' / champ / 'skins'
			print(f"[DEBUG populate_bin_dropdown] Skins dir: {skins_dir}")
			print(f"[DEBUG populate_bin_dropdown] Skins dir exists: {skins_dir.exists()}")
			if not skins_dir.exists():
				print("[DEBUG populate_bin_dropdown] Skins dir doesn't exist, returning")
				return
			
			# Find all skin folders that contain BIN files (anywhere in their tree)
			available_bins = set()
			bin_count = 0
			for root, _dirs, files in os.walk(skins_dir):
				for f in files:
					if f.lower().endswith('.bin'):
						bin_count += 1
						print(f"[DEBUG populate_bin_dropdown] Found BIN: {Path(root) / f}")
						# Extract skin identifier from the BIN filename or path
						# e.g., .../skins/skin0/... -> "Skin0"
						# e.g., .../skins/base/... -> "Base"
						# e.g., .../skins/skin0.bin -> "Skin0" (BIN directly in skins folder)
						rel_path = Path(root).relative_to(skins_dir)
						print(f"[DEBUG populate_bin_dropdown] Relative path: {rel_path}")
						
						if rel_path.parts:
							# BIN is in a subfolder (e.g., skins/skin0/file.bin)
							skin_folder = rel_path.parts[0]
							skin_name = skin_folder.capitalize()
							print(f"[DEBUG populate_bin_dropdown] Adding skin from folder: {skin_name}")
							available_bins.add(skin_name)
						else:
							# BIN is directly in skins folder (e.g., skins/skin0.bin)
							# Extract skin name from filename (remove .bin extension)
							skin_name = f.lower().replace('.bin', '').capitalize()
							print(f"[DEBUG populate_bin_dropdown] Adding skin from filename: {skin_name}")
							available_bins.add(skin_name)
			
			print(f"[DEBUG populate_bin_dropdown] Total BINs found: {bin_count}")
			print(f"[DEBUG populate_bin_dropdown] Available bins: {available_bins}")
			
			# Sort and update dropdown
			if available_bins:
				sorted_bins = sorted(available_bins, key=lambda x: (x.lower() != 'base', x.lower()))
				print(f"[DEBUG populate_bin_dropdown] Sorted bins: {sorted_bins}")
				# Update UI in main thread
				def update_dropdown():
					print(f"[DEBUG populate_bin_dropdown] Updating dropdown with: {sorted_bins}")
					self.bin_combo.configure(values=sorted_bins)
					# Set default to first item if nothing is selected
					if not self.main_bin_choice.get():
						print(f"[DEBUG populate_bin_dropdown] Setting default to: {sorted_bins[0]}")
						self.main_bin_choice.set(sorted_bins[0])
				self.root.after(0, update_dropdown)
			else:
				print("[DEBUG populate_bin_dropdown] No bins found!")
		except Exception as e:
			# Log error for debugging
			print(f"[DEBUG populate_bin_dropdown] ERROR: {e}")
			import traceback
			traceback.print_exc()
			self._set_status(f"Warning: Could not populate BIN dropdown: {e}")

	def _run_repath_current(self):
		try:
			work_root = self._work_root()
			fresh_unpack = work_root / 'fresh_extract' / 'unpacked'
			if not fresh_unpack.exists():
				self._set_status("Nothing to repath. Please run extraction first.")
				return
			
			self._set_status("Repathing merged content...")
			print(f"[DEBUG] Starting repath for: {fresh_unpack}")
			repath_ok = self._repath_fresh(fresh_unpack)
			print(f"[DEBUG] Repath result: {repath_ok}")
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
				# Get the last status message to see what went wrong
				current_status = self.s2_status_text.get()
				if current_status and "failed" not in current_status.lower() and "error" not in current_status.lower():
					self._set_status(f"Repath step failed or skipped. Last status: {current_status}")
				else:
					self._set_status(f"Repath step failed or skipped. {current_status}")
				print(f"[DEBUG] Repath failed. Last status: {current_status}")
		except Exception as e:
			error_msg = f"Error during repath: {e}"
			self._set_status(error_msg)
			print(f"[DEBUG] Exception in _run_repath_current: {e}")
			import traceback
			traceback.print_exc()

	def _extract_linked_bins_for_selected_bin(self, fresh_wad_path: Path, fresh_unpack: Path, hashes_dir: Path, champion: str, selected_bin: str):
		"""
		Find and store linked BIN paths from the fresh extracted BIN (not from WAD).
		The linked BINs should already be in fresh_unpack from the initial extraction.
		This just reads the fresh BIN to get the linked paths and stores them for later merging.
		"""
		try:
			import pyRitoFile
			BIN = pyRitoFile.bin.BIN
			champ = champion.lower() if champion else ''
			
			if not champ or not selected_bin:
				return
			
			# Find the specific BIN file in fresh_unpack matching the selected BIN
			characters_dir = fresh_unpack / 'data' / 'characters'
			if not characters_dir.exists():
				return
			
			# Parse selected BIN (e.g., "Skin0", "Skin5", "Base")
			selected_lower = selected_bin.lower().strip()
			skin_idx = None
			if selected_lower == 'base':
				skin_idx = 0
			else:
				m = re.search(r"(skin)?\s*(\d+)", selected_lower)
				if m:
					skin_idx = int(m.group(2))
			
			# Find the matching BIN file in fresh folder
			target_bin_path = None
			for char_folder in characters_dir.iterdir():
				if not char_folder.is_dir():
					continue
				skins_dir = char_folder / 'skins'
				if skins_dir.exists():
					for bin_file in skins_dir.rglob('*.bin'):
						rel_path = str(bin_file.relative_to(fresh_unpack)).replace('\\', '/')
						# Check if this BIN matches the selected skin
						if skin_idx is not None:
							if f"/skins/skin{skin_idx}/" in rel_path.lower() or bin_file.name.lower() == f"skin{skin_idx}.bin":
								target_bin_path = bin_file
								break
						# Also check by name
						if selected_lower in rel_path.lower():
							target_bin_path = bin_file
							break
					if target_bin_path:
						break
			
			if not target_bin_path or not target_bin_path.exists():
				print(f"[DEBUG] Could not find selected BIN {selected_bin} in fresh folder")
				return
			
			print(f"[DEBUG] Found fresh BIN for linked paths: {target_bin_path}")
			
			# Read the fresh BIN to get its linked BIN paths
			# Check if file is a valid binary BIN file
			if not self._is_valid_binary_bin(target_bin_path):
				print(f"[DEBUG] Skipping text-based BIN file: {target_bin_path}")
				return
			
			target_bin = BIN().read(str(target_bin_path))
			bin_path_rel = str(target_bin_path.relative_to(fresh_unpack)).replace('\\', '/')
			
			# Store fresh BIN paths and their linked BIN paths before overlay
			if not hasattr(self, '_fresh_bin_linked_paths'):
				self._fresh_bin_linked_paths = {}
			
			bin_linked_paths = []
			for link in target_bin.links:
				if link and isinstance(link, str) and link.lower().endswith('.bin'):
					link_normalized = link.replace('\\', '/')
					bin_linked_paths.append(link_normalized)
			
			# Store linked paths for this BIN (relative to fresh_unpack)
			self._fresh_bin_linked_paths[bin_path_rel] = bin_linked_paths
			
			if not bin_linked_paths:
				print(f"[DEBUG] No linked BINs found in fresh BIN {selected_bin}")
				self._set_status(f"No linked BINs found in fresh {selected_bin}")
			else:
				print(f"[DEBUG] Found {len(bin_linked_paths)} linked BIN path(s) in fresh {selected_bin}: {bin_linked_paths}")
				self._set_status(f"Found {len(bin_linked_paths)} linked BIN path(s) for {selected_bin}")
		
		except Exception as e:
			print(f"[DEBUG] Error in _extract_linked_bins_for_selected_bin: {e}")
			import traceback
			traceback.print_exc()
	
	def _extract_linked_bins_from_fresh(self, fresh_wad_path: Path, fresh_unpack: Path, hashes_dir: Path, champion: str):
		"""
		Extract linked BIN files from fresh WAD that are referenced by the main BIN.
		This ensures we have the newer linked BINs available for merging into the mod BIN.
		Also stores the linked BIN paths in a class variable for later use during repair.
		"""
		try:
			import pyRitoFile
			from pyRitoFile import wad as pywad
			from pyRitoFile.stream import BytesStream
			
			BIN = pyRitoFile.bin.BIN
			champ = champion.lower() if champion else ''
			
			if not champ:
				return
			
			# Find the main BIN file in fresh_unpack (e.g., Skin0.bin)
			# We'll check all character subfolders
			characters_dir = fresh_unpack / 'data' / 'characters'
			if not characters_dir.exists():
				return
			
			# Find all BIN files in character folders
			main_bin_candidates = []
			for char_folder in characters_dir.iterdir():
				if not char_folder.is_dir():
					continue
				skins_dir = char_folder / 'skins'
				if skins_dir.exists():
					for bin_file in skins_dir.rglob('*.bin'):
						main_bin_candidates.append(bin_file)
			
			if not main_bin_candidates:
				print(f"[DEBUG] No BIN files found in fresh_unpack to extract linked BINs from")
				return
			
			# Store fresh BIN paths and their linked BIN paths before overlay
			# This allows us to access them even after mod BINs overwrite fresh BINs
			if not hasattr(self, '_fresh_bin_linked_paths'):
				self._fresh_bin_linked_paths = {}
			
			# Read the WAD to get access to chunks
			hashtables = self._load_wad_hashtables(hashes_dir)
			w = pywad.WAD().read(str(fresh_wad_path))
			try:
				w.un_hash(hashtables)
			except Exception:
				pass
			
			# Collect all linked BIN paths from all main BINs
			linked_bin_paths = set()
			for main_bin_path in main_bin_candidates:
				try:
					# Check if file is a valid binary BIN file
					if not self._is_valid_binary_bin(main_bin_path):
						continue
					
					main_bin = BIN().read(str(main_bin_path))
					# Store the linked paths for this BIN (relative to fresh_unpack)
					main_bin_rel = str(main_bin_path.relative_to(fresh_unpack)).replace('\\', '/')
					bin_linked_paths = []
					for link in main_bin.links:
						if link and isinstance(link, str) and link.lower().endswith('.bin'):
							link_normalized = link.replace('\\', '/')
							linked_bin_paths.add(link_normalized)
							bin_linked_paths.append(link_normalized)
					# Store linked paths for this BIN
					self._fresh_bin_linked_paths[main_bin_rel] = bin_linked_paths
				except Exception as e:
					print(f"[DEBUG] Error reading main BIN {main_bin_path}: {e}")
					continue
			
			if not linked_bin_paths:
				print(f"[DEBUG] No linked BINs found in fresh BINs")
				return
			
			print(f"[DEBUG] Found {len(linked_bin_paths)} linked BIN path(s) to extract")
			
			# Extract each linked BIN from the WAD
			extracted_count = 0
			with BytesStream.reader(str(fresh_wad_path)) as bs:
				for chunk in w.chunks:
					try:
						chunk.read_data(bs)
						
						# Get the file path for this chunk
						chunk_path = chunk.hash.replace('\\', '/')
						
						# Add extension if known
						if pyRitoFile.wad.WADHasher.is_hash(chunk.hash) and chunk.extension:
							ext = f'.{chunk.extension}'
							if not chunk_path.endswith(ext):
								chunk_path += ext
						
						# Check if this chunk matches any linked BIN path
						chunk_path_lower = chunk_path.lower()
						should_extract = False
						target_path = None
						matched_linked_path = None
						
						for linked_path in linked_bin_paths:
							linked_path_lower = linked_path.lower()
							# Check if chunk path matches linked path (exact or by filename)
							if (chunk_path_lower == linked_path_lower or 
								chunk_path_lower.endswith(linked_path_lower) or
								Path(chunk_path).name.lower() == Path(linked_path).name.lower()):
								should_extract = True
								target_path = fresh_unpack / linked_path
								matched_linked_path = linked_path
								break
						
						if should_extract and chunk.data is not None:
							# Extract this linked BIN file
							target_path.parent.mkdir(parents=True, exist_ok=True)
							
							# Check if file already exists (might have been extracted already)
							if not target_path.exists():
								try:
									with open(target_path, 'wb') as f:
										f.write(chunk.data)
									extracted_count += 1
									print(f"[DEBUG] Extracted linked BIN: {matched_linked_path}")
								except Exception as e:
									print(f"[DEBUG] Error extracting linked BIN {matched_linked_path}: {e}")
						
						chunk.free_data()
					except Exception as e:
						print(f"[DEBUG] Error processing chunk for linked BIN extraction: {e}")
						continue
			
			if extracted_count > 0:
				print(f"[DEBUG] Extracted {extracted_count} linked BIN file(s) from fresh WAD")
			else:
				print(f"[DEBUG] Linked BINs may already be extracted or not found in WAD")
		
		except Exception as e:
			print(f"[DEBUG] Error in _extract_linked_bins_from_fresh: {e}")
			import traceback
			traceback.print_exc()
	
	def _repair_bin_file(self, bin_path: Path, fresh_unpack: Path = None):
		# Inline minimal FrogFixes: StaticMaterial and HealthBar fixes
		# Also merges linked BIN entries from fresh folder (newer versions)
		print(f"[DEBUG] Repair: Starting repair for BIN: {bin_path}")
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
		
		# Check if file is a valid binary BIN file
		if not self._is_valid_binary_bin(bin_path):
			print(f"[DEBUG] Skipping text-based BIN file: {bin_path}")
			return
		
		b = BIN().read(str(bin_path))
		
		# Add linked BIN paths from fresh folder to mod BIN's links list
		# The repather will automatically combine them - we just need to add the paths
		# Only do this if the toggle is enabled
		if self.merge_linked_bins_enabled.get() and fresh_unpack and fresh_unpack.exists():
			try:
				# Extract champion name and skin number from the mod BIN
				champion_name = None
				skin_number = 0  # Default to skin0
				
				# Find SkinCharacterDataProperties entry in mod BIN
				scdp_hash = H.get('SkinCharacterDataProperties')
				if scdp_hash:
					for entry in b.entries:
						if entry.type == scdp_hash:
							# Look for championSkinName field
							champion_skin_name_hash = H.get('championSkinName')
							if champion_skin_name_hash:
								for field in entry.data:
									if field.hash == champion_skin_name_hash and hasattr(field, 'data') and isinstance(field.data, str):
										champion_skin_name = field.data
										print(f"[DEBUG] Repair: Found championSkinName: {champion_skin_name}")
										
										# Extract champion name and skin number
										# Format: "YoneSkin55" -> champion="Yone", skin=55
										# Format: "Yone" -> champion="Yone", skin=0
										# Format: "BaseYorick" -> champion="Yorick", skin=0 (strip "Base" prefix)
										if 'Skin' in champion_skin_name:
											# Has skin number (e.g., "YoneSkin55")
											parts = champion_skin_name.split('Skin')
											if len(parts) == 2:
												champion_name = parts[0]
												# Strip "Base" prefix if present (e.g., "BaseYone" -> "Yone")
												if champion_name.startswith('Base') and len(champion_name) > 4:
													champion_name = champion_name[4:]
												try:
													skin_number = int(parts[1])
												except ValueError:
													skin_number = 0
										else:
											# Just champion name (e.g., "Yone" or "BaseYorick") -> skin0
											champion_name = champion_skin_name
											# Strip "Base" prefix if present (e.g., "BaseYorick" -> "Yorick")
											if champion_name.startswith('Base') and len(champion_name) > 4:
												champion_name = champion_name[4:]
											skin_number = 0
										break
							break
				
				# If we couldn't find championSkinName, try to extract from path
				if not champion_name:
					bin_path_str = str(bin_path).replace('\\', '/')
					try:
						path_parts = bin_path_str.lower().split('/')
						if 'characters' in path_parts:
							char_idx = path_parts.index('characters')
							if char_idx + 1 < len(path_parts):
								champion_name = path_parts[char_idx + 1]
					except Exception:
						pass
				
				if not champion_name:
					print(f"[DEBUG] Repair: Could not determine champion name, skipping linked BIN merge")
					return
				
				print(f"[DEBUG] Repair: Using champion={champion_name}, skin={skin_number}")
				
				# Use the stored fresh BIN linked paths (captured BEFORE overlay)
				# The key is the relative path from fresh_unpack, e.g., "data/characters/yorick/skins/skin0.bin"
				bin_path_rel = str(bin_path.relative_to(fresh_unpack)).replace('\\', '/')
				
				# Also try alternative paths in case of case differences
				bin_path_rel_lower = bin_path_rel.lower()
				
				fresh_linked_paths = []
				if hasattr(self, '_fresh_bin_linked_paths') and self._fresh_bin_linked_paths:
					# Try exact match first
					if bin_path_rel in self._fresh_bin_linked_paths:
						fresh_linked_paths = self._fresh_bin_linked_paths[bin_path_rel]
						print(f"[DEBUG] Repair: Found stored linked paths for: {bin_path_rel}")
					else:
						# Try case-insensitive match
						for stored_key, stored_paths in self._fresh_bin_linked_paths.items():
							if stored_key.lower() == bin_path_rel_lower:
								fresh_linked_paths = stored_paths
								print(f"[DEBUG] Repair: Found stored linked paths (case-insensitive) for: {stored_key}")
								break
					
					# If still not found, try constructing the expected key
					if not fresh_linked_paths:
						expected_key = f"data/characters/{champion_name.lower()}/skins/skin{skin_number}.bin"
						if expected_key in self._fresh_bin_linked_paths:
							fresh_linked_paths = self._fresh_bin_linked_paths[expected_key]
							print(f"[DEBUG] Repair: Found stored linked paths using constructed key: {expected_key}")
						else:
							# Try case-insensitive match on constructed key
							expected_key_lower = expected_key.lower()
							for stored_key, stored_paths in self._fresh_bin_linked_paths.items():
								if stored_key.lower() == expected_key_lower:
									fresh_linked_paths = stored_paths
									print(f"[DEBUG] Repair: Found stored linked paths (case-insensitive, constructed key) for: {stored_key}")
									break
				
				if not fresh_linked_paths:
					print(f"[DEBUG] Repair: No stored linked paths found for {bin_path_rel}, trying to read from file (may be mod BIN after overlay)")
					# Fallback: try to read from file (but this will be the mod BIN after overlay)
					fresh_skin_bin_path = fresh_unpack / 'data' / 'characters' / champion_name.lower() / 'skins' / f'skin{skin_number}.bin'
					if fresh_skin_bin_path.exists():
						# Check if file is a valid binary BIN file
						if self._is_valid_binary_bin(fresh_skin_bin_path):
							fresh_bin = BIN().read(str(fresh_skin_bin_path))
							for link in fresh_bin.links:
								if link and isinstance(link, str) and link.lower().endswith('.bin'):
									link_normalized = link.replace('\\', '/')
									fresh_linked_paths.append(link_normalized)
							print(f"[DEBUG] Repair: Read {len(fresh_linked_paths)} linked paths from file (may be mod BIN)")
					else:
						print(f"[DEBUG] Repair: Fresh BIN file not found: {fresh_skin_bin_path}, skipping linked BIN merge")
						return
				
				print(f"[DEBUG] Repair: Found {len(fresh_linked_paths)} linked BIN path(s) in fresh BIN")
				print(f"[DEBUG] Repair: Mod BIN currently has {len(b.links)} linked BIN path(s)")
				
				if fresh_linked_paths:
					links_added = 0
					links_skipped_base = 0
					links_already_present = 0
					
					for link_path in fresh_linked_paths:
						# Filter out champion base BIN
						champion_base_pattern = f"DATA/Characters/{champion_name}/{champion_name}.bin"
						if link_path.replace('\\', '/').lower() == champion_base_pattern.lower():
							links_skipped_base += 1
							print(f"[DEBUG] Repair: Skipping champion base BIN: {link_path}")
							continue
						
						# Add the linked path to the mod BIN's links list if not already present
						if link_path not in b.links:
							b.links.append(link_path)
							links_added += 1
							print(f"[DEBUG] Repair: Added linked BIN path to links: {link_path}")
						else:
							links_already_present += 1
							print(f"[DEBUG] Repair: Linked BIN path already present in mod BIN: {link_path}")
					
					print(f"[DEBUG] Repair: Summary - Added: {links_added}, Already present: {links_already_present}, Skipped (base): {links_skipped_base}")
					if links_added > 0:
						print(f"[DEBUG] Repair: Added {links_added} linked BIN path(s) from fresh skin{skin_number}.bin - repather will combine them automatically")
					else:
						print(f"[DEBUG] Repair: No new linked BIN paths added (all were already present or filtered)")
				else:
					print(f"[DEBUG] Repair: No linked BIN paths found in fresh skin{skin_number}.bin")
			
			except Exception as e:
				print(f"[DEBUG] Error adding linked BIN paths: {e}")
				import traceback
				traceback.print_exc()
		
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
				relative_path = Path(fpath).relative_to(raw_dir).as_posix()
				chunk_datas.append(fpath)
				basename = Path(file).name
				name_wo_ext = basename.split('.')[0]
				relative_path_lower = relative_path.lower()
				
				# VO files should keep their original paths - never hash them
				if 'assets/sounds/wwise2016/vo/' in relative_path_lower:
					chunk_hashes.append(relative_path)
				# if basename looks hashed and located at root, keep as hash
				elif pyRitoFile.wad.WADHasher.is_hash(name_wo_ext) and relative_path == basename:
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
				# Note: result contains file paths as keys mapping to lists of entry dicts, plus 'junk_files' key
				junk_files = result.get('junk_files', [])
				total_mentioned = 0
				total_missing = 0
				for key, bin_results in result.items():
					# Skip the 'junk_files' key - it's a list of strings, not entry dicts
					if key == 'junk_files':
						continue
					if isinstance(bin_results, list):
						for entry in bin_results:
							# Ensure entry is a dict before calling .get()
							if isinstance(entry, dict):
								total_mentioned += len(entry.get('mentioned_files', []))
								total_missing += len(entry.get('missing_files', []))
				
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
		
		# Get prefix for repathing matching (if available)
		prefix = getattr(self, '_used_prefix', None)
		
		# Parse BIN files
		for full_file_index, full_file in enumerate(full_files):
			if full_file.endswith('.bin'):
				try:
					# Check if file is a valid binary BIN file
					if not self._is_valid_binary_bin(Path(full_file)):
						continue
					
					bin_obj = pyRitoFile.bin.BIN().read(full_file)
					bin_obj.un_hash(WizardApp._HashStorage.hashtables)
					result = self._pyntex_parse_bin(bin_obj, existing_files=existing_files, prefix=prefix)
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
	
	def _pyntex_paths_match(self, mentioned_path: str, existing_path: str, prefix: str = None) -> bool:
		"""Check if two paths match, accounting for repathing prefixes"""
		# First try standard unified path comparison (hash-based)
		if self._pyntex_unify_path(mentioned_path) == self._pyntex_unify_path(existing_path):
			return True
		
		# If prefix is provided, try matching with prefix adjustments
		if prefix:
			prefix_lower = prefix.lower()
			mentioned_lower = mentioned_path.lower()
			existing_lower = existing_path.lower()
			
			# Helper function to try prefix patterns for a given base path (e.g., "assets/" or "data/")
			def try_prefix_patterns(base: str):
				base_lower = base.lower()
				# Try removing prefix from existing path to match mentioned
				# Pattern 1: "{base}{prefix}/..." -> "{base}..."
				if f'{base_lower}{prefix_lower}/' in existing_lower:
					existing_without_prefix = existing_lower.replace(f'{base_lower}{prefix_lower}/', f'{base_lower}', 1)
					if mentioned_lower == existing_without_prefix:
						return True
				
				# Pattern 2: "{prefix}/{base}..." -> "{base}..."
				if existing_lower.startswith(f'{prefix_lower}/{base_lower}'):
					existing_without_prefix = existing_lower[len(f'{prefix_lower}/'):]
					if mentioned_lower == existing_without_prefix:
						return True
				
				# Try adding prefix to mentioned path to match existing
				# Pattern 1: "{base}..." -> "{base}{prefix}/..."
				if mentioned_lower.startswith(base_lower):
					mentioned_with_prefix = mentioned_lower.replace(f'{base_lower}', f'{base_lower}{prefix_lower}/', 1)
					if existing_lower == mentioned_with_prefix:
						return True
				
				# Pattern 2: "{base}..." -> "{prefix}/{base}..."
				if mentioned_lower.startswith(base_lower):
					mentioned_with_prefix = f'{prefix_lower}/{base_lower}' + mentioned_lower[len(base_lower):]
					if existing_lower == mentioned_with_prefix:
						return True
				return False
			
			# Try patterns for both "assets/" and "data/" paths
			if try_prefix_patterns('assets/'):
				return True
			if try_prefix_patterns('data/'):
				return True
		
		return False
	
	def _pyntex_parse_bin(self, bin_obj, *, existing_files={}, prefix: str = None):
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
					found = False
					for existing_file in existing_files:
						if self._pyntex_paths_match(file, existing_file, prefix):
							existing_files[existing_file] = False
							found = True
							# Handle 2x_ and 4x_ DDS variants
							if file.endswith('.dds'):
								splits = file.split('/')
								dds2x = '/'.join(splits[:-1] + ['2x_' + splits[-1]])
								dds4x = '/'.join(splits[:-1] + ['4x_' + splits[-1]])
								# Check if variants exist in existing_files
								for existing_variant in list(existing_files.keys()):
									if self._pyntex_paths_match(dds2x, existing_variant, prefix) or \
									   self._pyntex_paths_match(dds4x, existing_variant, prefix):
										existing_files[existing_variant] = False
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
		
		# Keep main BIN choice and custom prefix so user doesn't have to re-enter
		# Don't clear: self.main_bin_choice.set("")
		# Don't clear: self.custom_prefix
		
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
			
			# Collect all missing files (only .dds and .tex, excluding HUD folder files)
			missing_textures = []
			missing_hud_count = 0
			print(f"[DEBUG] Processing pyntex results, total keys: {len(result)}")
			for key, bin_results in result.items():
				# Skip the 'junk_files' key - it's a list of strings, not entry dicts
				if key == 'junk_files':
					continue
				if isinstance(bin_results, list):
					for entry in bin_results:
						# Ensure entry is a dict before calling .get()
						if isinstance(entry, dict):
							missing_in_entry = entry.get('missing_files', [])
							print(f"[DEBUG] Entry has {len(missing_in_entry)} missing files")
							for missing_file in missing_in_entry:
								# Only process .dds and .tex files
								if missing_file.lower().endswith(('.dds', '.tex')):
									# Skip HUD folder files - don't create placeholders for them
									if '/hud/' in missing_file.lower() or '\\hud\\' in missing_file.lower():
										missing_hud_count += 1
										print(f"[DEBUG] Skipped HUD file: {missing_file}")
										continue
									if missing_file not in missing_textures:
										missing_textures.append(missing_file)
										print(f"[DEBUG] Added missing texture: {missing_file}")
			
			print(f"[DEBUG] Total missing textures collected: {len(missing_textures)}")
			
			# Save detailed report
			json_file = self._work_root() / 'missing_files_report.json'
			with open(json_file, 'w', encoding='utf-8') as f:
				json.dump(result, f, indent=4, ensure_ascii=False)
			print(f"[DEBUG] Saved report to: {json_file}")
			
			# Create placeholders for missing textures (excluding HUD files)
			if len(missing_textures) > 0:
				self._set_status(f"Found {len(missing_textures)} missing textures (excluding {missing_hud_count} HUD files). Creating placeholders...")
				print(f"[DEBUG] Calling _create_placeholder_textures with {len(missing_textures)} files (skipped {missing_hud_count} HUD files)")
				self._create_placeholder_textures(repathed_dir, missing_textures)
				self._set_status(f"Created {len(missing_textures)} placeholder textures (HUD files skipped).")
			else:
				if missing_hud_count > 0:
					self._set_status(f"✓ No missing texture files found (skipped {missing_hud_count} HUD files)!")
				else:
					self._set_status("✓ No missing texture files found!")
				print("[DEBUG] No missing textures found!")
			
			# Apply No Skin Lite if enabled (ONLY works with Skin0/Base to prevent skin hacking)
			if self.no_skin_lite_enabled.get():
				# Check if main BIN is Base/Skin0 (required for No Skin Lite)
				desired_raw = (self.main_bin_choice.get() or '').strip()
				desired = desired_raw.lower()
				if desired in ('base', 'skin0', '0'):
					self._set_status("Applying No Skin Lite...")
					try:
						self._apply_no_skin_lite_to_wad(repathed_dir)
						self._set_status("No Skin Lite applied successfully!")
					except Exception as e:
						self._set_status(f"No Skin Lite failed: {e}")
						print(f"[DEBUG] No Skin Lite error: {e}")
						import traceback
						traceback.print_exc()
				else:
					self._set_status("No Skin Lite skipped (only works with Base/Skin0, not Skin1+ to prevent skin hacking)")
					print("[DEBUG] No Skin Lite skipped: Skin1+ selected (prevents skin hacking)")
			
			# Automatically package final fantome
			self._set_status("Packaging final .fantome with all fixes...")
			self._create_final_fantome(repathed_dir, len(missing_textures))
			
		except Exception as e:
			self._set_status(f"Error: {e}")
	
	def _create_placeholder_textures(self, repathed_dir: Path, missing_files: list):
		"""Create placeholder invis.dds/invis.tex for missing texture files"""
		print(f"[DEBUG] _create_placeholder_textures called with {len(missing_files)} files")
		print(f"[DEBUG] repathed_dir: {repathed_dir}")
		print(f"[DEBUG] missing_files: {missing_files[:5]}...")  # Show first 5
		
		# Get bundled placeholder files
		if getattr(sys, 'frozen', False):
			# Running as EXE - placeholders are in _MEIPASS root (bundled by build.spec)
			placeholder_dir = Path(sys._MEIPASS)
		else:
			# Running as script - placeholders are in the same directory as this script
			placeholder_dir = Path(__file__).parent
		
		print(f"[DEBUG] placeholder_dir: {placeholder_dir}")
		invis_dds = placeholder_dir / 'invis.dds'
		invis_tex = placeholder_dir / 'invis.tex'
		print(f"[DEBUG] invis_dds exists: {invis_dds.exists()}, path: {invis_dds}")
		print(f"[DEBUG] invis_tex exists: {invis_tex.exists()}, path: {invis_tex}")
		
		if not invis_dds.exists() or not invis_tex.exists():
			self._set_status("Warning: Placeholder files not found. Skipping placeholder creation.")
			print(f"[ERROR] Placeholder files not found! invis_dds: {invis_dds.exists()}, invis_tex: {invis_tex.exists()}")
			return
		
		created_count = 0
		skipped_count = 0
		error_count = 0
		
		for missing_file in missing_files:
			# Missing files are paths as they appear in the BINs (already repathed if applicable)
			# Use them as-is - they're in the exact format the game expects
			target_path = missing_file.lower()
			target_file = repathed_dir / target_path
			
			# Skip if file already exists
			if target_file.exists():
				skipped_count += 1
				print(f"[SKIP] File already exists: {target_file}")
				continue
			
			# Create parent directories if they don't exist
			try:
				target_file.parent.mkdir(parents=True, exist_ok=True)
			except Exception as e:
				print(f"[ERROR] Failed to create directory {target_file.parent}: {e}")
				error_count += 1
				continue
			
			# Determine which placeholder to use
			source_placeholder = None
			if missing_file.lower().endswith('.dds'):
				source_placeholder = invis_dds
			elif missing_file.lower().endswith('.tex'):
				source_placeholder = invis_tex
			else:
				# Skip non-texture files
				continue
			
			# Copy the placeholder file
			try:
				shutil.copy2(source_placeholder, target_file)
				created_count += 1
				print(f"[OK] Created placeholder: {target_file}")
			except Exception as e:
				error_count += 1
				print(f"[ERROR] Failed to create placeholder for {missing_file} -> {target_file}: {e}")
				import traceback
				traceback.print_exc()
		
		status_msg = f"Created {created_count} placeholder texture files"
		if skipped_count > 0:
			status_msg += f", skipped {skipped_count} (already exist)"
		if error_count > 0:
			status_msg += f", {error_count} errors"
		self._set_status(status_msg)
	
	def _create_info_json(self, champ: str, is_new: bool) -> str:
		"""Create a basic info.json for the fantome"""
		import json
		from datetime import datetime
		
		info = {
			"Name": f"{champ.capitalize()} Repathed Mod",
			"Author": "League Mod Repather",
			"Version": "1.0.0",
			"Description": f"Repathed mod for {champ.capitalize()}. Created with League Mod Repather.",
			"CreatedDate": datetime.now().strftime("%Y-%m-%d")
		}
		
		return json.dumps(info, indent=2, ensure_ascii=False)
	
	def _update_info_json(self, original_json: str) -> str:
		"""Update existing info.json to indicate it's been repathed"""
		import json
		try:
			info = json.loads(original_json)
			# Add repathed suffix to name if not already present
			if 'Name' in info and 'repathed' not in info['Name'].lower():
				info['Name'] = f"{info['Name']} (Repathed)"
			# Update description
			if 'Description' in info:
				info['Description'] = f"{info['Description']}\n\nRepathed with League Mod Repather."
			else:
				info['Description'] = "Repathed with League Mod Repather."
			return json.dumps(info, indent=2, ensure_ascii=False)
		except Exception:
			# If parsing fails, return original
			return original_json
	
	def _create_final_fantome(self, repathed_dir: Path, missing_count: int):
		"""Create the final fantome with all fixes applied"""
		try:
			work_root = self._work_root()
			
			# Determine champion name and wad name
			champ = getattr(self, '_champion', '').lower()
			if not champ:
				self._set_status("Error: Champion name unknown")
				return
			wad_name = f"{champ}.wad.client"
			
			# Pack repathed_dir -> new wad
			final_wad_path = work_root / f"final_{wad_name}"
			self._set_status("Packing WAD from repathed folder...")
			self._pack_wad(repathed_dir, final_wad_path)
			
			# Check if using fantome or mod folder mode
			fantome_path = self.fantome_path.get().strip()
			mod_folder_path = self.mod_folder_path.get().strip()
			
			if mod_folder_path:
				# MOD FOLDER MODE: Create new fantome from scratch
				final_fantome = work_root / f"{champ}_repathed.fantome"
				self._set_status(f"Creating new fantome: {final_fantome.name}")
				
				import zipfile as _zip
				with _zip.ZipFile(final_fantome, 'w', compression=_zip.ZIP_DEFLATED) as zout:
					# Add the repathed WAD
					zout.write(final_wad_path, f"WAD/{wad_name}")
					
					# Create and add info.json
					info_json = self._create_info_json(champ, is_new=True)
					zout.writestr("META/info.json", info_json)
				
			else:
				# FANTOME MODE: Copy original fantome and replace the champion WAD
				fantome = Path(fantome_path)
				member = getattr(self, '_fantome_member_path', None)
				if not member:
					self._set_status("Error: Original wad member path unknown")
					return
				
				# Build final fantome
				final_fantome = fantome.with_name(f"{fantome.stem}_repathed{fantome.suffix}")
				self._set_status(f"Creating final fantome: {final_fantome.name}")
				
				import zipfile as _zip
				with _zip.ZipFile(fantome, 'r') as zin, _zip.ZipFile(final_fantome, 'w', compression=_zip.ZIP_DEFLATED) as zout:
					has_info_json = False
					for item in zin.infolist():
						data = zin.read(item.filename)
						# Case-insensitive comparison for WAD paths
						item_path_normalized = item.filename.replace('\\', '/').lower()
						member_path_normalized = member.replace('\\', '/').lower()
						
						# Check if this is info.json
						if item_path_normalized in ['meta/info.json', 'info.json']:
							has_info_json = True
							# Update info.json with repathed suffix
							info_json = self._update_info_json(data.decode('utf-8'))
							zout.writestr(item.filename, info_json)
						elif item_path_normalized == member_path_normalized:
							# replace with final wad
							with open(final_wad_path, 'rb') as f:
								data = f.read()
							zout.writestr(item.filename, data)
						else:
							zout.writestr(item, data)
					
					# If original fantome didn't have info.json, create one
					if not has_info_json:
						info_json = self._create_info_json(champ, is_new=False)
						zout.writestr("META/info.json", info_json)
			
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
	print("="*60)
	print("League Mod Repather - Starting...")
	print("Console output enabled for debugging")
	print("="*60)
	
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


