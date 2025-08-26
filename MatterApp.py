import sys              # Interact with command line
# ============ GUI packages from PySide6 ============
from PySide6.QtWidgets import (QSplashScreen, QApplication)
from PySide6.QtCore import Qt


# ------------------------------- Main ------------------------------------
def main():
    app = QApplication(sys.argv)
    app.setStyle('Fusion')

    splash = QSplashScreen()
    splash.showMessage("Initialising MatterApp...", Qt.AlignCenter, Qt.black)
    splash.show()
    app.processEvents()

    from main_window import MainWindow

    splash.showMessage("Loading main window...", Qt.AlignCenter, Qt.black)
    app.processEvents()
    
    win = MainWindow()                            # Opens / initialises GUI window
    win.show()                                      # Shows window
    splash.finish(win)
    sys.exit(app.exec_())                            # Starts app loop and exits upon exit


# ------------------------------- App Entry ------------------------------------
if __name__ == "__main__":
    main()
