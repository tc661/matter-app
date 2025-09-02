import os
import re
from ssh_helpers import remote_walk

from procar_parser import Parser, BandData, interactive_procar_ui

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QPushButton,
    QMessageBox
)

class Material:
    def __init__(self, folder_path=None, sftp=None):
        self.folder_path = folder_path
        self.sftp = sftp
        self.is_remote = sftp is not None

        # File detection
        self.has_poscar = self._file_exists("POSCAR")
        self.has_contcar = self._file_exists("CONTCAR")
        self.has_incar = self._file_exists("INCAR")
        self.has_outcar = self._file_exists("OUTCAR")
        self.has_procar = self._file_exists("PROCAR")
        self.has_fermi = self._file_exists("FERMI")
        self.has_kpoints = self._file_exists("KPOINTS")
        self.has_potcar = self._file_exists("POTCAR")

        # self.structure = self._load_structure()
        # self.formula = self._get_formula()

    # =========== FILE HANDLING ===========

    def _file_exists(self, filename):
        """Check if a file exists in the folder."""
        if self.is_remote:
            try:
                remote_path = self._join_remote_path(self.folder_path, filename)
                self.sftp.stat(remote_path)
                return True
            except:
                return False
        else:
            return os.path.exists(os.path.join(self.folder_path, filename))
        
    def _join_remote_path(self, base, filename):
        """Join base path and filename for remote paths."""
        base = base.replace('\\', '/')
        if base.endswith('/'):
            return base + filename
        else:
            return base + '/' + filename
    
    def get_files(self, sftp, path):
        all_files = []
        try:
            for root, dirs, files in remote_walk(sftp, path):
                for f in files:
                    all_files.append(os.path.join(root, f))
            return all_files
        except FileNotFoundError:
            print(f"Path not found: {self.path}")
            return []

    # =========== OUTCAR PROCESSING ===========

    def get_vasp_runs(self):
        # Gets stage of processing.
        runs = []
        for file in self.files:
            if os.path.basename(file).upper() == "OUTCAR":
                run_dir_full = os.path.dirname(file)
                run_dir = os.path.basename(run_dir_full)
                for i, run_chunk in enumerate(split_outcar_runs(file)):
                    incar_path = os.path.join(os.path.dirname(file), "INCAR")
                    if os.path.exists(incar_path):
                        params = parse_INCAR(incar_path)
                        run_type = classify_run(params)
                    else:
                        run_type = "Unknown"
                runs.append({
                    "path": run_dir,
                    "run_index": i + 1,
                    "type": run_type
                })
        return runs

#=========== PROCAR DIALOG CLASS ===========
class ProcarDialog(QDialog):
    def __init__(self, parent=None, procar_path=None, fermi_path=None):
        super().__init__(parent)
        self.setWindowTitle("PROCAR Band Structure Analysis")
        self.setModal(False)
        self.resize(300, 100)

        layout = QVBoxLayout()

        # Info label
        info_label = QLabel("Interactive PROCAR analysis will open in a separate matplotlib window.")
        layout.addWidget(info_label)
        
        # Launch button
        launch_btn = QPushButton("Launch Interactive PROCAR Viewer")
        launch_btn.clicked.connect(lambda: self.launch_procar_ui(procar_path, fermi_path))
        layout.addWidget(launch_btn)
        
        # Close button
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.close)
        layout.addWidget(close_btn)
        
        self.setLayout(layout)

    def launch_procar_ui(self, procar_path, fermi_path):
        """Launch the interactive PROCAR UI"""
        try:
            # Parse PROCAR data
            parser = Parser(procar_path=procar_path, fermi_path=fermi_path)
            if not parser.procar:
                QMessageBox.warning(self, "PROCAR Error", "Failed to parse PROCAR file")
                return
            
            # Create BandData object
            band_data = BandData(parser.procar, parser.fermi or 0.0)
            
            # Find fermi-level fatband for initial view
            fatbands, minmax = band_data.identify_fatbands()

            fermi_fatband = None
            for fatband in fatbands:
                if fatband["E-min"] <= (parser.fermi or 0.0) <= fatband["E-max"]:
                    fermi_fatband = fatband
                    break
            
            # Launch interactive UI (this will create its own matplotlib window)
            interactive_procar_ui(
                parser.procar, 
                band_data.energies, 
                band_data.weights, 
                band_data.band_weights, 
                parser.fermi or 0.0, 
                fatband=fermi_fatband
            )
            
        except Exception as e:
            QMessageBox.critical(self, "PROCAR Error", f"Failed to launch PROCAR viewer:\n{str(e)}")


#=========== POTENTIAL INCAR CLASS ===========
def parse_INCAR(incar_path):
    params = {}
    encut = None
    try:
        with open(incar_path, 'r') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#') or '=' not in line:
                    continue
                key, value = map(str.strip, line.split('=', 1))
                params[key.lower()] = value.lower()
    except FileNotFoundError:
        pass
    return params

def classify_run(params):
    get = lambda k, default: params.get(k, str(default)).lower()

    if get('lsorbit', ".false.") in ['.t.', '.true.']:
        return "SCF (Spin-Orbital Coupling/SOC)"
    
    if get('icharg', '0') == '11' and get('istart','0') == '1':
        return "Non-SCF (Band Structure)"
    
    if get('ibrion', '-1') != '-1' and int(get('nsw', '0')) > 0:
        return "Structural  Relaxation"
    
    if get('icharg', '0') != '11' and get('istart','0') == '0' and\
        get('lwave','.true.') in ['.t.', '.true.'] and get('lcharg','.true.') in ['.t.', '.true.']:
        return "SCF (Self-Consistent Field)"  
    return "Unknown"

#=================================

#=========== Potential OUTCAR class =========== 
def split_outcar_runs(outcar_path):
    """Split OUTCAR into chunks for each VASP run."""
    runs = []
    current_run_lines = []
    try:
        with open(outcar_path, 'r') as f:
            for line in f:
                if line.lstrip().lower().startswith("vasp.") and current_run_lines:   # At the end of one run
                    runs.append(current_run_lines)                  # Append entire current run array to runs
                    current_run_lines = []                          # Reset current run array
                current_run_lines.append(line)  
            if current_run_lines:
                runs.append(current_run_lines)                      # Add a run at end of OUTCAR
    except FileNotFoundError:
        pass
    return runs
#==============================================

def check_relaxation_complete(outcar_path="geometry/1-relax-out"):
    try:
        with open(outcar_path, 'r') as f:
            lines = f.readlines()
        for line in lines:
            if "reached required accuracy" in line:
                return True, "Relaxation completed successfully (criterion met)"
        return False, "Relaxation not confirmed (criterion not met)"
    except FileNotFoundError:
        return False, f"File not found: {outcar_path}"

def get_num_atoms(contcar_path="geometry/CONTCAR"):
    try:
        with open(contcar_path, 'r') as f:
            lines = f.readlines()
            total_atoms = 0
            for number in lines[6].strip().split():
                try:
                    total_atoms += int(number)
                except ValueError:
                    continue
            return total_atoms, "Number of atoms counted successfully"
    except FileNotFoundError:
        return None, f"File not found: {contcar_path}"

def read_CONTCAR(contcar_path="geometry/CONTCAR"):
    try:
        with open(contcar_path, 'r') as f:
            return f.read(), "CONTCAR read successfully"
    except FileNotFoundError:
        return "CONTCAR file not found", "Error reading CONTCAR"


def parse_KPOINTS(kpoints_path="geometry/KPOINTS"):
    try:
        with open(kpoints_path, 'r') as f:
            lines = f.readlines()
        grid_line = lines[3].strip()
        kmesh = list(map(int, grid_line.split()))
        return kmesh, "KPOINTS parsed successfully"
    except Exception as e:
        return None, f"Error reading KPOINTS: {str(e)}"


def check_magnetism(outcar_path="geometry/OUTCAR"):
    total_mag = None
    atom_mags = []
    reading = False
    try:
        with open(outcar_path, 'r') as f:
            for line_num, line in enumerate(f, 1):
                if "magnetization (x)" in line:
                    #print(f"[DEBUG] Found 'magnetization (x)' at line {line_num}")
                    reading = True
                    continue
                if reading:
                    #print(f"[DEBUG] Reading line {line_num}: {line.strip()}")
                    if re.match(r"^\s*$", line):
                        #print("[DEBUG] Skipping empty line")
                        continue
                    if line.strip().startswith("#"):
                        #print("[DEBUG] Skipping header line")
                        continue
                    if re.match(r"^\s*-+\s*$", line):
                        #print("[DEBUG] Skipping dashed line")
                        continue
                    if re.match(r"^\s*tot\b", line):
                        #print("[DEBUG] Found total magnetization line")
                        parts = line.split()
                        #print(f"[DEBUG] Line parts: {parts}")
                        total_mag = float(parts[-1])
                        break
                    if re.match(r"\s*\d+", line):
                        #print("[DEBUG] Found atom line")
                        parts = line.split()
                        if len(parts) >= 5:
                            atom_mags.append(float(parts[4]))
                    else:
                        #print("[DEBUG] Line didn't match anything, stopping read")
                        break
    except FileNotFoundError:
        return None, [], f"File not found: {outcar_path}"
    return total_mag, atom_mags, "Magnetism data parsed successfully" if total_mag is not None else "Magnetism data not found"

def check_energy_convergence(convergence_limit=0.015, cut_E_path="cut-E.dat"):
    data = []
    try:
        with open(cut_E_path, 'r') as f:
            for line in f:
                parts = line.strip().split()
                if len(parts) == 2:
                    try:
                        x = float(parts[0])
                        energy = float(parts[1])
                        data.append((x, energy))
                    except ValueError:
                        continue
        data.sort(key=lambda x: x[0])
        if len(data) >= 2:
            diffs = [abs(data[i+1][1] - data[i][1]) for i in range(len(data) - 1)]
            converged = all(diff < convergence_limit for diff in diffs[-2:])
        else:
            converged = False
        return data, converged, f"ENCUT convergence data read successfully"
    except FileNotFoundError:
        return None, False, f"File not found: {cut_E_path}"

def check_kpoints_convergence(convergence_limit = 0.015, k_E_path="k-E.dat"):
    data = []
    try:
        with open(k_E_path, 'r') as f:
            for line in f:
                parts = line.strip().split()
                if len(parts) == 2:
                    try:
                        x = float(parts[0])
                        energy = float(parts[1])
                        data.append((x, energy))
                    except ValueError:
                        continue
        data.sort(key=lambda x: x[0])
        if len(data) >= 2:
            diffs = [abs(data[i+1][1] - data[i][1]) for i in range(len(data) - 1)]
            converged = all(diff < convergence_limit for diff in diffs[-2:])
        else:
            converged = False
        return data, converged, "KPOINTS convergence data read successfully"
    except FileNotFoundError:
        return None, False, f"File not found: {k_E_path}"

def generate_report(mat, output_file="summary.txt"):
    with open(output_file, 'w', encoding='utf-8') as report:
        # HEADER
        report.write("=== VASP SUMMARY ===\n")
        report.write(f"MATERIAL: {mat.name}\n")
        report.write(f"STAGE: {len(mat.runs)} x VASP runs\n")
        for run in mat.runs:
            report.write(f"Run {run['run_index']} in {run['path']}: {run['type']}\n")

        report.write("\n")

        # RELAXATION
        relaxed, relax_msg = check_relaxation_complete()
        report.write("=== Relaxation Check ===\n")
        report.write(f"{relax_msg}\n\n")

        # ATOM COUNT
        num_atoms, atom_count_msg = get_num_atoms()
        report.write("=== Atom Count ===\n")
        if num_atoms is not None:
            report.write(f"Total number of atoms: {num_atoms}\n")
            report.write(f"({atom_count_msg})\n\n")
            convergence_limit = 0.001 * num_atoms
        else:
            report.write(f"Error: {atom_count_msg}\n\n")
            convergence_limit = 0

        # ENCUT
        incar_params = parse_INCAR(incar_path="geometry/INCAR")
        report.write("=== INCAR Parameters ===\n")
        try:
            report.write(f"ENCUT: {incar_params["encut"]} (Successfully parsed)\n\n")
        except:
            report.write(f"ENCUT: N/A (Failed to parse))\n\n")

        # ENCUT Convergence
        cut_data, cut_conv, cut_msg = check_energy_convergence(convergence_limit)
        report.write("=== ENCUT Convergence Check ===\n")
        if cut_data:
            for x, energy in cut_data:
                report.write(f"{int(x)}eV -> {energy:.6f}eV\n")
            report.write(f"Convergence: {'Yes' if cut_conv else 'No'}\n")
            report.write(f"({cut_msg})\n\n")

        # KPOINTS
        kmesh, kpoints_msg = parse_KPOINTS()
        report.write("=== KPOINTS Grid ===\n")
        if kmesh:
            report.write(f"K-Mesh: {' '.join(map(str, kmesh))}\n")
        report.write(f"({kpoints_msg})\n\n")

        # KPOINTS Convergence
        k_data, k_conv, k_msg = check_kpoints_convergence(convergence_limit)
        report.write("=== KPOINTS Convergence Check ===\n")
        if k_data:
            for x, energy in k_data:
                report.write(f"{int(x)} -> {energy:.6f}eV\n")
            report.write(f"Convergence: {'Yes' if k_conv else 'No'}\n")
            report.write(f"({k_msg})\n\n")

        # Magnetism
        total_mag, atom_mags, mag_msg = check_magnetism()
        report.write("=== Magnetism Check ===\n")
        if total_mag is not None:
            report.write(f"Total Magnetization: {total_mag:.3f}μB\n")
            for i, mag in enumerate(atom_mags, start=1):
                report.write(f"Atom {i}: {mag:.3f}μB\n")
        report.write(f"({mag_msg})\n\n")

        # CONTCAR
        contcar_content, contcar_msg = read_CONTCAR()
        report.write("=== CONTCAR Content ===\n")
        report.write(f"{contcar_msg}\n")
        report.write(contcar_content if contcar_content else "No CONTCAR data available\n")

    print(f"Report generated: {output_file}")

def display_material_info(mat):
    """Returns a VASP summary string"""
    lines=[]
    lines.append("=== VASP SUMMARY ===")
    lines.append(f"FOLDER: {mat.name}")
    lines.append(f"STAGE: {len(mat.runs)} x VASP runs")
    for run in mat.runs:
        lines.append(f"Run {run['run_index']} in {run['path']}: {run['type']}\n")
    lines.append("FILES:")
    for i, file in enumerate(mat.files):
        lines.append(f"{i}: {os.path.basename(file)}")
    return "\n".join(lines)

if __name__ == "__main__":
    mat = Material()
    generate_report(mat)