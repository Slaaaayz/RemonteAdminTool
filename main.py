#!/usr/bin/env python3
import sys
import logging
from PyQt6.QtWidgets import QApplication, QMessageBox
from rat_server.gui.main_window import MainWindow
from rat_server.server_core.server_logic import ServerCore

# --- Configuration ---
SERVER_HOST = '0.0.0.0'  # Listen on all interfaces
SERVER_PORT = 8081  # Changed from 8080 to avoid conflict

# --- Logging Setup ---
def setup_logging():
    """Sets up logging configuration."""
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)

    # Console handler with color formatting
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.DEBUG)
    
    # Simple format for console
    formatter = logging.Formatter('%(asctime)s [%(levelname)s] [%(name)s] %(message)s')
    console_handler.setFormatter(formatter)
    
    logger.addHandler(console_handler)
    logger.info("Logging initialized.")
    
    return logger

# --- Main Application Execution ---
def main():
    """Initializes and runs the RAT server application."""
    logger = setup_logging()

    logger.info("Starting RAT Server Application...")

    # Create the Qt Application instance first
    app = QApplication(sys.argv)

    # Create the Server Core (handles network logic)
    logger.debug("Initializing ServerCore...")
    server = ServerCore(host=SERVER_HOST, port=SERVER_PORT)

    # Create the Main Window (GUI), passing the server core
    logger.debug("Initializing MainWindow...")
    main_window = MainWindow(server_core=server)

    # Start the server core (starts listening thread)
    logger.debug("Starting ServerCore...")
    if not server.start():
        logger.critical("Failed to start the server core. Exiting.")
        QMessageBox.critical(None, "Server Error", 
                           f"Could not start server on {SERVER_HOST}:{SERVER_PORT}. Is the port in use?")
        sys.exit(1)

    # Show the main window
    logger.debug("Showing main window...")
    main_window.show()

    # Start the Qt event loop
    logger.info("Starting Qt event loop...")
    exit_code = app.exec()
    logger.info(f"Qt event loop finished with exit code: {exit_code}")

    # Server shutdown is handled in MainWindow's closeEvent
    sys.exit(exit_code)

if __name__ == '__main__':
    main() 