import logging
from PyQt6.QtCore import QMetaObject, Qt, Q_ARG, QTimer
from PyQt6.QtWidgets import QMessageBox
# No longer needs QTableWidgetItem, QInputDialog, QMessageBox directly

logger = logging.getLogger(__name__)

class ProcessHandler:
    def __init__(self, main_window):
        self.main_window = main_window
        # Access main_window attributes like:
        # self.main_window.process_table
        # self.main_window.selected_client_addr_str
        # self.main_window.server_core

    # --- ServerCore Callback Handler ---

    def handle_process_list(self, address, processes):
        """Handles the process list received from the client."""
        QMetaObject.invokeMethod(self.main_window, "_update_process_table",
                                Qt.ConnectionType.QueuedConnection,
                                Q_ARG(object, processes))

    # --- GUI Update Method is now in MainWindow ---
    # Remove _update_process_table_gui

    # --- GUI Actions (Called directly from MainWindow slots) ---
    # Keep these methods as they contain the logic to *initiate* actions

    def refresh_processes(self):
        """Sends a request to list processes on the client."""
        address = self.main_window._get_selected_client_address()
        if address:
            self.main_window.server_core.send_command(address, "list_processes")

    def kill_selected_process(self):
        """Sends a request to kill the selected process on the client."""
        address = self.main_window._get_selected_client_address()
        if not address:
            return

        selected_items = self.main_window.process_table.selectedItems()
        if not selected_items:
            QMessageBox.warning(self.main_window, "Warning", "Please select a process to kill.")
            return

        pid = self.main_window.process_table.item(selected_items[0].row(), 0).text()
        reply = QMessageBox.question(self.main_window, "Confirm Kill",
                                   f"Are you sure you want to kill process {pid}?",
                                   QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)

        if reply == QMessageBox.StandardButton.Yes:
            self.main_window.server_core.send_command(address, "kill_process", {"pid": int(pid)})
            # Refresh after a short delay to see the result
            QTimer.singleShot(500, self.refresh_processes)

    def start_new_process(self):
        """Prompts for a command and sends a request to start it on the client."""
        address = self.main_window._get_selected_client_address()
        if not address:
            return

        command, ok = QInputDialog.getText(self.main_window, "Start Process",
                                         "Enter the command to execute:")
        if ok and command:
            self.main_window.server_core.send_command(address, "start_process", {"command": command})
            # Refresh after a short delay to see the new process
            QTimer.singleShot(500, self.refresh_processes) 