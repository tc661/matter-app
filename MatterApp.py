import sys              # Interact with command line
import os               # Interact with files, paths
import paramiko         # Network with ssh
import tempfile         # For temporary files
import subprocess       # Utilise multiple processes
import shutil           # To launch VESTA
from stat import S_ISDIR, S_ISLNK

# ============ GUI packages from PySide6 ============
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QPushButton, QPlainTextEdit,
    QLineEdit, QLabel, QTextEdit, QComboBox, QMainWindow, QDockWidget,
    QListWidget, QDialog, QMessageBox, QTabWidget, QFileDialog
    )
from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon, QAction
# ============ PyVista Visualisation ============ 
import pyvista as pv    # For 3D visualisation
try:
    from pyvistaqt import QtInteractor
    _PV_QT_OK = True
except Exception:
    _PV_QT_OK = False
# ============ Materials IO ============ 
from ase.io import read # For viewing atomic structures


# ----------------------------- Existing SSH helpers -----------------------------
def get_ssh_params(alias):
    """Read ~/.ssh/config and return params for given alias."""
    ssh_config_path = os.path.expanduser("~/.ssh/config")               # Opens config from user profile
    ssh_params = {}                                                     # Empty dictionary for ssh params
    if os.path.exists(ssh_config_path):
        from paramiko.config import SSHConfig                           # Only loads SSHConfig package if config path found
        with open(ssh_config_path) as f:
            ssh_config = SSHConfig()
            ssh_config.parse(f)                                         # Parses .ssh/config into paramiko SSHConfig() object
            host_config = ssh_config.lookup(alias)                      # Checks host config params for an alias
            ssh_params['hostname'] = host_config.get('hostname', alias)
            ssh_params['username'] = host_config.get('user', None)
            ssh_params['port'] = int(host_config.get('port', 22))
            ssh_params['key_filename'] = host_config.get('identityfile', [None])[0]
    else:                                                               # No config file found
        ssh_params['hostname'] = alias                                  # Creates default hostname and port parameter
        ssh_params['username'] = None
        ssh_params['port'] = 22
        ssh_params['key_filename'] = None
    return ssh_params


def generate_ssh_key(key_path="~/.ssh/id_rsa"):
    """Generate SSH keypair if it doesn't exist."""
    key_path = os.path.expanduser(key_path)
    if not os.path.exists(key_path):                                    # runs ssh-keygen -t rsa -b 4096 -f ~/.ssh/id_rsa -N 
        subprocess.run(["ssh-keygen", "-t", "rsa", "-b", "4096", "-f", key_path, "-N", ""])
        return True                                                     # returns true if new keypair
    return False                                                        # returns false if keypair already exists


def add_key_to_server(alias="hpc"):
    """Copy SSH public key to remote server."""
    subprocess.run(["ssh-copy-id", alias])                             # adds keypair as authorised on server "hpc"

# ----------------------------- Remote File Dialog -----------------------------------------------
class RemoteFileDialog(QDialog):
    """Remote file browser via SFTP"""
    def __init__(self, sftp, start_path="."):
        super().__init__()
        self.sftp = sftp
        self.current_path = start_path
        self.selected_file = None

        self.setWindowTitle("Remote File Browser")
        self.resize(600, 400)
        layout = QVBoxLayout()

        self.path_label = QLabel(self.current_path)
        layout.addWidget(self.path_label)

        self.list_widget = QListWidget()
        self.list_widget.itemDoubleClicked.connect(self.navigate_or_select)
        layout.addWidget(self.list_widget)

        button_layout = QVBoxLayout()

        self.back_btn = QPushButton(".. (Up)")
        self.back_btn.clicked.connect(self.go_up)
        button_layout.addWidget(self.back_btn)

        select_btn = QPushButton("Select")
        select_btn.clicked.connect(self.navigate_or_select)
        button_layout.addWidget(select_btn)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)

        layout.addLayout(button_layout)
        self.setLayout(layout)
        self.refresh_list()

    def normalise_remote_path(self, path):
        if path == ".":
            return self.sftp.getcwd() or "."
        return path.replace('\\', '/')
    
    def join_remote_path(self, base, name):
        base = self.normalise_remote_path(base)
        if base.endswith('/'):
            return base + name
        else:
            return base + '/' + name

    def refresh_list(self):
        self.list_widget.clear()
        self.current_path = self.normalise_remote_path(self.current_path)

        try:
            items = []
            for f in self.sftp.listdir_attr(self.current_path):
                name = f.filename

                if name.startswith("."): # Skips hidden
                    continue

                full_path = self.join_remote_path(self.current_path, name)

                is_dir = False
                is_symlink = False

                if S_ISDIR(f.st_mode):
                    is_dir = True
                elif S_ISLNK(f.st_mode):
                    is_symlink = True
                    try:
                        target_stat = self.sftp.stat(full_path)
                        is_dir = S_ISDIR(target_stat.st_mode)

                    except Exception as e1:
                        try:
                            target_path = self.sftp.readlink(full_path)
                            if not target_path.startswith("/"):
                                current_dir = self.current_path.rstrip("/")
                                target_path = current_dir + "/" + target_path
                            
                            target_stat = self.sftp.stat(target_path)
                            is_dir = S_ISDIR(target_stat.st_mode)
                        except Exception as e2:
                            is_dir=False

                display_name = name
                if is_symlink and is_dir:
                    display_name += " -> (dir)"
                elif is_symlink:
                    display_name += " -> (file)"
                elif is_dir:
                    display_name += "/"  # mark directories

                items.append((display_name, name, is_dir, is_symlink, full_path))

            # SORT FILES/DIRECTORIES      
            items.sort(key=lambda x: (not x[2], x[1].lower()))
            for display_name, _, _, _, _ in items:
                self.list_widget.addItem(display_name)
            
            self.path_label.setText(f"Path: {self.current_path}")  # Window title
        except Exception as e:
            self.list_widget.addItem(f"Error reading directory: {e}")
    

    def navigate_or_select(self, item):
        if not item:
            return
        
        display_name = item.text()

        original_name = display_name
        if " -> " in display_name:
            original_name = display_name.split(" -> ")[0]
        elif display_name.endswith("/"):
            original_name = display_name[:-1]
        
        full_path = self.join_remote_path(self.current_path, original_name)

        try:
            stat_result = self.sftp.stat(full_path)
            if S_ISDIR(stat_result.st_mode):
                self.current_path = full_path
                self.refresh_list()
                return
        except Exception as e:
            # If stat fails, might be a broken symlink
            if " -> " in display_name:
                self.list_widget.addItem(f"Cannot access: {e}")
                return
            
        self.selected_file = full_path
        self.accept()

    def go_up(self):
        if self.current_path != "/":
            self.current_path = os.path.dirname(self.current_path)
            self.refresh_list()




# ----------------------------- HPC Client -----------------------------
class HPCClient(QWidget):                           # QWidget = Parent Class
    # ============ Initialisation ============
    def __init__(self):
        """INITIALISE CLIENT AND SET UP WINDOW"""
        super().__init__()                          # Initialise as QWidget
        self.setWindowTitle("HPC → VASP Frontend")  
        self.ssh_client = None                      
        self.hpc_host = ""
        self.hpc_user = ""
        
        layout = QVBoxLayout()                      # Vertical layout

        # Alias dropdown
        self.alias_dropdown = QComboBox()       
        self.alias_dropdown.setToolTip("Select host")           
        self.alias_dropdown.addItem("")                         # Empty by default
        ssh_config_path = os.path.expanduser("~/.ssh/config")   # .ssh config path
        self.aliases = []
        if os.path.exists(ssh_config_path):
            with open(ssh_config_path) as f:
                cfg = paramiko.config.SSHConfig()               
                cfg.parse(f)                                    # Loads aliases from config w/ paramiko
                self.aliases = [h for h in cfg.get_hostnames() if '*' not in h]
            for host in self.aliases:
                self.alias_dropdown.addItem(host)               # Adds aliases to dropdown
        self.alias_dropdown.addItem("Manual Host")              # Manual host option

        layout.addWidget(QLabel("Select SSH Alias / Host:"))
        layout.addWidget(self.alias_dropdown)

        # Manual host fields
        self.manual_container = QWidget()                       # Container holds manual host optopms
        manual_layout = QVBoxLayout()
        self.manual_host_input = QLineEdit()
        self.manual_host_input.setPlaceholderText("Hostname (e.g., login.hpc.cam.ac.uk)")
        manual_layout.addWidget(self.manual_host_input)         # HPC hostname
        self.manual_user_input = QLineEdit()
        self.manual_user_input.setPlaceholderText("Username")
        manual_layout.addWidget(self.manual_user_input)         # HPC Username
        self.manual_container.setLayout(manual_layout)
        self.manual_container.setVisible(False)                 # Manual container starts invisible
        layout.addWidget(self.manual_container)
        # Updates visibility when changed
        self.alias_dropdown.currentTextChanged.connect(self.update_manual_fields)

        # Password/Passphrase
        self.pass_input = QLineEdit()
        self.pass_input.setPlaceholderText("Password or Key Passphrase")
        self.pass_input.setEchoMode(QLineEdit.EchoMode.Password)
        layout.addWidget(self.pass_input)           # HPC Password

        # Connect Button
        connect_btn = QPushButton("Connect")
        connect_btn.clicked.connect(self.connect_hpc)
        layout.addWidget(connect_btn)               # HPC Connection Button (connect_hpc)


        # Job listing
        self.jobs_box = QTextEdit()
        self.jobs_box.setReadOnly(True)             
        layout.addWidget(self.jobs_box)             # Read-Only Jobs Window

        list_jobs_btn = QPushButton("List My Jobs")
        list_jobs_btn.clicked.connect(self.list_jobs)
        layout.addWidget(list_jobs_btn)             # List Jobs Button (list_jobs)

        # Remote POSCAR
        get_poscar_btn = QPushButton("Pick Remote File...")
        get_poscar_btn.clicked.connect(self.pick_remote_file)
        layout.addWidget(get_poscar_btn)            # POSCAR View Button (get_and_view_poscar)

        self.setLayout(layout)                      # Attaches layout to window
        self.local_last_download = None             # Path to last downloaded file


    # ============ Connection Functions ============
    def update_manual_fields(self, text):
        """Update visibility of manual host container"""
        self.manual_container.setVisible(text == "Manual Host")

    def connect_hpc(self):
        """CONNECT TO HPC"""
        alias = self.alias_dropdown.currentText().strip()
        password = self.pass_input.text().strip() or None
        self.ssh_client = paramiko.SSHClient()  # Uses Paramiko to Connect
        self.ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            if alias and alias != "Manual Host":
                # Connect via SSH config alias
                params = get_ssh_params(alias)
                self.ssh_client.connect(
                    hostname=params['hostname'],
                    port=params['port'],
                    username=params['username'],
                    key_filename=params['key_filename'],
                    passphrase=password
                )
                self.hpc_user = params["username"] or ""
                self.hpc_host = params["hostname"]
                self.jobs_box.setPlainText(f"✅ Connected via alias '{alias}'")
            elif alias == "Manual Host":
                # Connect manually
                host = self.manual_host_input.text().strip()
                user = self.manual_user_input.text().strip()
                if not host or not user:
                    self.jobs_box.setPlainText("❌ Enter hostname and username for manual host")
                    return
                self.ssh_client.connect(
                    hostname=host,
                    username=user,
                    password=password
                )
                self.hpc_user = user
                self.hpc_host = host
                self.jobs_box.setPlainText(f"✅ Connected to manual host {host}")
            else:
                self.jobs_box.setPlainText("❌ Select an alias or manual host")
        except Exception as e:
            self.jobs_box.setPlainText(f"❌ Connection failed: {e}")
    

    # ============ Jobs ============
    def list_jobs(self):
        """LIST JOBS WHEN CONNECTED"""
        if not self.ssh_client:                     # Can't list jobs when not on HPC
            self.jobs_box.setPlainText("Not connected.")
            return
        try:
            stdin, stdout, stderr = self.ssh_client.exec_command(f"qstat -u {self.hpc_user}")
            output = stdout.read().decode()         # Interprets results of qstat
            self.jobs_box.setPlainText(output if output else "No jobs running.")
        except Exception as e:
            self.jobs_box.setPlainText(f"Error listing jobs: {e}")
    

    # ============ File viewing ============
    def pick_remote_file(self):
        """Opens remote browser and downloads selected file to a temp path"""
        if not self.ssh_client:                     # Can't view POSCAR if not connected
            self.jobs_box.setPlainText("❌ Not connected to HPC.")
            return
        sftp = self.ssh_client.open_sftp()
        try:
            dialog = RemoteFileDialog(sftp, start_path=".")
            if dialog.exec():
                remote_path = dialog.selected_file
                base = os.path.basename(remote_path)
                local_tmp = os.path.join(tempfile.gettempdir(), base or "remote_file")
                sftp.get(remote_path, local_tmp)        # Downloads POSCAR from HPC to local temp file by SFTP
                self.local_last_download = local_tmp      
                self.jobs_box.setPlainText(f"✅ File downloaded from {remote_path} to {local_tmp}")
        finally:
            sftp.close()

# ----------------------------- Embedded Structure Viewer -----------------------------
class StructureViewer(QWidget):
        """Central 3D viewer with embedded PyVista (QtInteractor)."""
        # ============ Initialisation ============
        def __init__(self, parent=None):
            super().__init__(parent)
            v = QVBoxLayout(self)
            if _PV_QT_OK:
                self.plotter = QtInteractor(self)
                v.addWidget(self.plotter.interactor)
                self.plotter.enable_terrain_style()
            else:
                self.plotter = None
                v.addWidget(QLabel("PyVistaQt not available."))

            self.current_structure_path = None

        # ============ Functions ============
        def clear(self):
            if self.plotter:
                self.plotter.clear()

        def load_structure(self, path):
            """Load structure via ASE to render simple spheres"""
            self.current_structure_path = path
            if not self.plotter:
                return
            try:
                atoms = read(path)          # Gets atom data
            except Exception as e:
                QMessageBox.warning(self, "Load Error", f"Failed to read structure:\n{e}")
                return
            
            self.plotter.clear()
            # Sphere rendering
            for atom in atoms:                      
                sphere = pv.Sphere(radius=0.3, center=atom.position)
                self.plotter.add_mesh(sphere, smooth_shading=True)
            self.plotter.reset_camera()                          # Plots basic visualisation of structure


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
        self.hpc_dock.setWidget(self.hpc)
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

        self.act_open_remote = QAction("Open Remote Structure...", self)
        self.act_open_remote.triggered.connect(self.open_remote_structure)

        self.act_open_text = QAction("Open Text File...", self)
        self.act_open_text.triggered.connect(self.open_text_file)

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
        m_file.addAction(self.act_open_remote)
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

# ------------------------------- App Entry ------------------------------------
if __name__ == "__main__":
    print("Starting Application")
    app = QApplication(sys.argv)                    # Runs as an app
    print("QApplication initialized")
    win = MainWindow()                            # Opens / initialises GUI window
    print("Window Initialized")
    win.show()                                      # Shows window
    print("Window shown")
    sys.exit(app.exec())                            # Starts app loop and exits upon exit
