import logging
from PyQt6.QtCore import QObject, pyqtSignal, QMetaObject, Q_ARG
from PyQt6.QtCore import Qt
# No longer needs QTableWidgetItem or os

logger = logging.getLogger(__name__)

class ClientHandler(QObject):
    # Define signals for GUI updates
    client_connection_changed = pyqtSignal(str, bool)  # addr_str, is_connected
    client_system_info_updated = pyqtSignal(str, str, str, str, str)  # addr_str, hostname, os, cpu, mem

    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        # Connect signals to main window slots
        self.client_connection_changed.connect(self.main_window._update_client_connection_status)
        self.client_system_info_updated.connect(self.main_window._update_client_sys_info)
        # Direct access to main_window attributes like:
        # self.main_window.clients_ui_data
        # self.main_window.clients_table
        # self.main_window.selected_client_addr_str
        # self.main_window.hostname_label, etc.
        # self.main_window.server_core

    # --- ServerCore Callback Handlers ---
    # These now emit signals instead of using invokeMethod

    def handle_client_connected(self, address):
        """Triggers the GUI update when a client connects."""
        addr_str = f"{address[0]}:{address[1]}"
        self.client_connection_changed.emit(addr_str, True)

    def handle_client_disconnected(self, address):
        """Triggers the GUI update when a client disconnects."""
        addr_str = f"{address[0]}:{address[1]}"
        self.client_connection_changed.emit(addr_str, False)

    def handle_system_info(self, address, info):
        """Handles system information updates from the client."""
        addr_str = f"{address[0]}:{address[1]}"
        if addr_str in self.main_window.clients_ui_data:
            # Mettre à jour les données du client
            self.main_window.clients_ui_data[addr_str].update({
                'hostname': info.get('hostname', 'N/A'),
                'os': info.get('os', 'N/A'),
                'cpu': f"{info.get('cpu_percent', 'N/A')}%",
                'mem': f"{info.get('memory_percent', 'N/A')}%"
            })
            
            # Émettre le signal pour mettre à jour l'interface
            self.client_system_info_updated.emit(
                addr_str,
                info.get('hostname', 'N/A'),
                info.get('os', 'N/A'),
                f"{info.get('cpu_percent', 'N/A')}%",
                f"{info.get('memory_percent', 'N/A')}%"
            )

    # --- GUI Update Methods are now in MainWindow ---
    # Remove the update_... methods previously here

    # --- GUI Actions --- ###
    # Keep this method for updating selected client details (reads main_window UI data)

    def update_selected_client_details(self):
        """Updates the system info display for the selected client."""
        if self.main_window.selected_client_addr_str:
            client_data = self.main_window.clients_ui_data.get(self.main_window.selected_client_addr_str, {})
            self.main_window.hostname_label.setText(client_data.get('hostname', 'N/A'))
            self.main_window.os_label.setText(client_data.get('os', 'N/A'))
            self.main_window.cpu_label.setText(client_data.get('cpu', 'N/A'))
            self.main_window.memory_label.setText(client_data.get('mem', 'N/A'))
        else:
            # Clear the display if no client is selected
            self.main_window.hostname_label.setText('N/A')
            self.main_window.os_label.setText('N/A')
            self.main_window.cpu_label.setText('N/A')
            self.main_window.memory_label.setText('N/A') 