from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QMessageBox
)

# ============ PyVista Visualisation ============ 
import pyvista as pv    # For 3D visualisation
try:
    from pyvistaqt import QtInteractor
    _PV_QT_OK = True
except Exception:
    _PV_QT_OK = False


# ============ Materials IO ============ 
from ase.io import read # For viewing atomic structures

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
