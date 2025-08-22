from PySide6.QtWidgets import (
    QMainWindow, QTabWidget, QPlainTextEdit, QDockWidget,
    QTextEdit, QFileDialog, QMessageBox, QLabel
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QPixmap

import os
import shutil
import tempfile
import subprocess
import sys

from ase.io import read # For viewing atomic structures

from structure_viewer import StructureViewer
from hpc_client import HPCClient
from remote_dialog import RemoteFileDialog

# ----------------------------- Main Window Shell -----------------------------
class MainWindow(QMainWindow):
    # ============ Initialisation ============
    def __init__(self):
        super().__init__()
        self.setWindowTitle("MatterApp")
        self.setUnifiedTitleAndToolBarOnMac(True)

        # Central Tabs
        self.tabs = QTabWidget()
        self.viewer = StructureViewer()
        self.text_view = QPlainTextEdit()
        self.text_view.setReadOnly(False)
        self.tabs.addTab(self.viewer, "Structure")
        self.tabs.addTab(self.text_view, "Text Editor")
        self.setCentralWidget(self.tabs)

        # Docks
        self.hpc_dock = QDockWidget("HPC", self)
        self.hpc = HPCClient()
        self.hpc.main_window = self # So HPC client can log to main window
        self.hpc_dock.setWidget(self.hpc)
        self.hpc_dock.setMaximumWidth(350)
        self.hpc_dock.setMinimumWidth(200)
        self.addDockWidget(Qt.LeftDockWidgetArea, self.hpc_dock)

        self.info_dock = QDockWidget("Material Info", self)
        self.info_box = QTextEdit()
        self.info_box.setReadOnly(True)
        self.info_box.setText("Load a structure to see properties here...")
        self.info_dock.setWidget(self.info_box)
        self.addDockWidget(Qt.RightDockWidgetArea, self.info_dock)

        self.log_dock = QDockWidget("Logs", self)
        self.log_box = QTextEdit()
        self.log_box.setReadOnly(False)
        self.log_dock.setWidget(self.log_box)
        self.addDockWidget(Qt.BottomDockWidgetArea, self.log_dock)

        # Dock-tionary
        self.docks = {
            "HPC": self.hpc_dock,
            "Material Info": self.info_dock,
            "Logs": self.log_dock
        }

        # Menu & Actions
        self._make_actions()
        self._make_menus()

        # State
        self.last_open_dir = os.getcwd()
        self.vesta_cmd = shutil.which("vesta") or shutil.which("VESTA")  # Windows often has VESTA.exe

        # Start maximized (fullscreen toggle is in View menu)
        self.showMaximized()

    # ============ Menus and Actions ============
    def _make_actions(self):
        # File
        self.act_open_local = QAction("Open Local Structure...", self)
        self.act_open_local.triggered.connect(self.open_local_structure)

        self.act_open_remote_struc = QAction("Open Remote Structure...", self)
        self.act_open_remote_struc.triggered.connect(self.open_remote_structure)

        self.act_open_text = QAction("Open Text File...", self)
        self.act_open_text.triggered.connect(self.open_text_file)

        self.act_open_remote_img = QAction("Open Remote Image...", self)
        self.act_open_remote_img.triggered.connect(self.open_remote_image)

        self.act_quit = QAction("Quit", self)
        self.act_quit.triggered.connect(self.close)

        # View
        self.act_fullscreen = QAction("Toggle Fullscreen", self)
        self.act_fullscreen.setCheckable(True)
        self.act_fullscreen.triggered.connect(self.toggle_fullscreen)

        self.act_restore_all = QAction("Restore All Docks", self)
        self.act_restore_all.triggered.connect(self.restore_all_docks)

        # Tools
        self.act_open_in_vesta = QAction("Open structure in VESTA", self)
        self.act_open_in_vesta.triggered.connect(self.open_in_vesta)

        self.act_run_analysis = QAction("Run analysis.py (local)...", self)
        self.act_run_analysis.triggered.connect(self.run_analysis_local)

        # Settings
        self.act_set_vesta = QAction("Set VESTA Executable", self)
        self.act_set_vesta.triggered.connect(self.set_vesta_path)

        # Help
        self.act_about = QAction("About", self)
        self.act_about.triggered.connect(self.show_about)


    def _make_menus(self):
        m_file = self.menuBar().addMenu("&File")
        m_file.addAction(self.act_open_local)
        m_file.addAction(self.act_open_remote_struc)
        m_file.addAction(self.act_open_remote_img)
        m_file.addSeparator()
        m_file.addAction(self.act_open_text)
        m_file.addSeparator()
        m_file.addAction(self.act_quit)

        m_view = self.menuBar().addMenu("&View")
        m_view.addAction(self.act_fullscreen)

        self.view_actions = {}
        for dock_name, dock_widget in self.docks.items():
            action = QAction(dock_name, self, checkable=True)
            action.setChecked(True)
            action.triggered.connect(lambda checked, dock=dock_widget: dock.setVisible(checked))
            dock_widget.visibilityChanged.connect(action.setChecked)
            m_view.addAction(action)
            self.view_actions[dock_name] = action
        m_view.addSeparator()
        m_view.addAction(self.act_restore_all)

        m_tools = self.menuBar().addMenu("&Tools")
        m_tools.addAction(self.act_open_in_vesta)
        m_tools.addAction(self.act_run_analysis)

        m_settings = self.menuBar().addMenu("&Settings")
        m_settings.addAction(self.act_set_vesta)

        m_help = self.menuBar().addMenu("&Help")
        m_help.addAction(self.act_about)

    
    # ============ Dock Management ============
    def restore_all_docks(self):
        for dock_name, dock_widget in self.docks.items():
            dock_widget.show()

    # ============ Action Implementations ============
    def open_local_structure(self):
        filters = "Structure Files (*.POSCAR *.CONTCAR *.vasp);;All Files (*.*)"
        path, _ = QFileDialog.getOpenFileName(self, "Open Structure", self.last_open_dir, filters)
        if not path:
            return
        self.last_open_dir = os.path.dirname(path)
        self.viewer.load_structure(path)
        self._update_info_from_structure(path)
        self._log(f"Loaded local structure: {path}")

    def open_remote_structure(self):
        """Use HPC SFTP + RemoteFileDialog"""
        if not self.hpc.ssh_client:
            QMessageBox.information(self, "HPC", "Connect to an HPC host first.")
            return
        sftp = self.hpc.ssh_client.open_sftp()
        try:
            dlg = RemoteFileDialog(sftp, start_path=".")
            if dlg.exec():
                remote_path = dlg.selected_file
                base = os.path.basename(remote_path)
                local_tmp = os.path.join(tempfile.gettempdir(), base or "remote_structure")
                sftp.get(remote_path, local_tmp)
                self.viewer.load_structure(local_tmp)
                self._update_info_from_structure(local_tmp)
                self._log(f"Downloaded + loaded remote structure: {remote_path} -> {local_tmp}")
        finally:
            sftp.close()

    def open_text_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open Text", self.last_open_dir, "Text Files (*.txt, *.dat, *.out, *.py);;All Files (*.*)")
        if not path:
            return
        self.last_open_dir = os.path.dirname(path)
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                self.text_view.setPlainText(f.read())
            self.tabs.setCurrentWidget(self.text_view)
            self._log(f"Opened text: {path}")
        except Exception as e:
            QMessageBox.warning(self, "Open Text", f"Failed to read file:\n{e}")

    def open_remote_image(self):
        if not self.hpc.ssh_client:
            QMessageBox.information(self, "HPC", "Connect to an HPC Host first.")
            return

        sftp = self.hpc.ssh_client.open_sftp()
        try:
            dlg = RemoteFileDialog(sftp, start_path=".", filters=["*.png", "*.jpg", "*.jpeg"])
            if dlg.exec():
                remote_path = dlg.selected_file
                base = os.path.basename(remote_path)
                local_tmp = os.path.join(tempfile.gettempdir(), base or "remote_image")
                sftp.get(remote_path, local_tmp)

                # Display in a new tab
                pixmap = QPixmap(local_tmp)
                lbl = QLabel()
                lbl.setPixmap(pixmap)
                lbl.setAlignment(Qt.AlignCenter)

                tab_name = f"Image: {base}"
                self.tabs.addTab(lbl, tab_name)
                self.tabs.setCurrentWidget(lbl)

                self._log(f"Loaded remote image: {remote_path} -> {local_tmp}")
        finally:
            sftp.close()
    
    def toggle_fullscreen(self, checked):
        if checked:
            self.showFullScreen()
        else:
            self.showMaximized()

    def open_in_vesta(self):
        """Launch VESTA on the currently loaded"""
        if not self.viewer.current_structure_path:
            QMessageBox.information(self, "VESTA", "No structure loaded.")
            return
        vesta = self.vesta_cmd or shutil.which("vesta") or shutil.which("VESTA")
        if not vesta:
            QMessageBox.warning(self, "VESTA", "VESTA not found in PATH. Set it in Settings.")
            return
        try:
            subprocess.Popen([vesta, self.viewer.current_structure_path])
            self._log(f"Opened in VESTA: {self.viewer.current_structure_path}")
        except Exception as e:
            QMessageBox.warning(self, "VESTA", f"Failed to launch VESTA:\n{e}")
    
    def run_analysis_local(self):
        """Run analysis.py in a local subdirectory -> Text Viewer"""
        folder = QFileDialog.getExistingDirectory(self, "Select directory to analyse", self.last_open_dir)
        if not folder:
            return
        self.last_open_dir = folder
        analysis_py = os.path.join(folder, "analysis.py")
        cmd = [sys.executable, analysis_py] if os.path.exists(analysis_py) else [sys.executable, "-m", "analysis"]
        try:
            proc = subprocess.run(cmd, cwd=folder, capture_output=True, text=True, timeout=120)
            out = proc.stdout or ""
            err = proc.stderr or ""
            result = out + ("\n--------STDERR--------\n" + err if err else "")
            if not result.strip():
                result = "(No output)"
            self.text_view.setPlainText(result)
            self.tabs.setCurrentWidget(self.text_view)
            self._log(f"Ran analysis in: {folder}")
        except Exception as e:
            QMessageBox.warning(self, "analysis.py", f"Failed to run analysis:\n{e}")

    def set_vesta_path(self):
        exe, _ = QFileDialog.getOpenFileName(self, "Select VESTA executable", "", "Executables (*.exe *.cmd *);;All Files (*.*)")
        if exe:
            self.vesta_cmd = exe
            self._log(f"VESTA path set to: {exe}")

    def show_about(self):
        QMessageBox.information(self, "About MatterApp",
                                "MatterApp — a unified HPC + materials viewer\n"
                                "PySide6 + PyVista/pyvistaqt + ASE\n"
                                "© 2025 Toby Clark")
    
    
    # ============ Helper Functions ============ 
    def _log(self, msg):
        self.log_box.append(msg)

    def _update_info_from_structure(self, path):
        """Light info panel"""
        try:
            atoms = read(path)
        except Exception:
            self.info_box.setText(f"Loaded: {os.path.basename(path)}\n(Unable to parse properties)")
            return

        lines = [
            f"File: {os.path.basename(path)}",
            f"Formula: {atoms.get_chemical_formula()}",
            f"Atoms: {len(atoms)}"
        ]
        try:
            cell = atoms.get_cell()
            a, b, c = cell.lengths()
            alpha, beta, gamma = cell.angles()
            lines += [
                f"a,b,c: {a:.3f}, {b:.3f}, {c:.3f} Angstrom",
                f"α,β,γ: {alpha:.2f}, {beta:.2f}, {gamma:.2f} degrees"
            ]
        except Exception:
            pass

        self.info_box.setText("\n".join(lines))

