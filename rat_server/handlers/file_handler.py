import logging
import os
import base64
from PyQt6.QtCore import QMetaObject, Qt, Q_ARG, QTimer, QUrl, pyqtSlot
from PyQt6.QtWidgets import (QTableWidgetItem, QInputDialog, QMessageBox,
                             QFileDialog, QDialog, QVBoxLayout, QTextEdit,
                             QHBoxLayout, QPushButton, QMenu, QStyle, QApplication, QLabel)
from PyQt6.QtGui import QDesktopServices # To open download folder

logger = logging.getLogger(__name__)

class FileHandler:
    def __init__(self, main_window):
        self.main_window = main_window
        self._pending_download_path = None
        self.current_edit_dialog = None
        # Access main_window attributes:
        # self.main_window.files_table
        # self.main_window.path_edit
        # self.main_window.selected_client_addr_str
        # self.main_window.clients_ui_data
        # self.main_window.server_core
        # self.main_window.download_path
        # self.main_window._get_current_client_path()
        # self.main_window._get_selected_client_address()
        # self.main_window._show_message_box()

    # --- ServerCore Callback Handlers ---

    def handle_directory_listing(self, address, files_data):
        """Handles the directory listing received from the client."""
        QMetaObject.invokeMethod(self.main_window, "_update_files_table",
                                Qt.ConnectionType.QueuedConnection,
                                Q_ARG(object, files_data))

    def handle_file_content(self, address, content_b64):
        """Handles receiving file content for viewing/editing."""
        addr_str = f"{address[0]}:{address[1]}"
        # Check if an edit/view dialog is active for this client
        if addr_str == self.main_window.selected_client_addr_str and self.current_edit_dialog:
            QMetaObject.invokeMethod(self.main_window, "_update_editor_content", Qt.ConnectionType.QueuedConnection,
                                     Q_ARG(str, content_b64))

    def handle_file_download_data(self, address, data_b64):
        """Handles receiving file data for saving locally."""
        addr_str = f"{address[0]}:{address[1]}"
        if addr_str == self.main_window.selected_client_addr_str and self._pending_download_path:
            local_save_path = self._pending_download_path
            self._pending_download_path = None # Consume the path
            QMetaObject.invokeMethod(self.main_window, "_save_downloaded_file", Qt.ConnectionType.QueuedConnection,
                                     Q_ARG(str, local_save_path), Q_ARG(str, data_b64))
        elif self._pending_download_path:
             logger.warning(f"Received file data for {addr_str} but pending download was for {self.main_window.selected_client_addr_str}")
             self._pending_download_path = None # Clean up path anyway
        else:
             logger.warning(f"Received unexpected file data from {addr_str}")

    def handle_write_file_response(self, address, response_data):
        """Handles the response after a write_file command."""
        addr_str = f"{address[0]}:{address[1]}"
        status = response_data.get('status', 'error')
        message = response_data.get('message', 'Unknown status')
        if status == 'success':
            logger.info(f"File write successful on {addr_str}")
            # Maybe show a success message in the editor dialog?
            if self.current_edit_dialog and hasattr(self.current_edit_dialog, 'status_label'):
                 # Update dialog status safely (might need invokeMethod if dialog runs separately?)
                 self.current_edit_dialog.status_label.setText("Saved successfully!")
                 # Optionally close dialog automatically after short delay?
                 # QTimer.singleShot(1000, self.current_edit_dialog.accept)
        else:
            logger.error(f"File write failed on {addr_str}: {message}")
            # Show error in the main window or the dialog if it's still open
            parent_widget = self.current_edit_dialog if self.current_edit_dialog else self.main_window
            QMetaObject.invokeMethod(self.main_window, "_show_message_box", Qt.ConnectionType.QueuedConnection,
                                     Q_ARG(str, "File Write Error"),
                                     Q_ARG(str, f"Failed to write file on client:\n{message}"),
                                     Q_ARG(str, "warning")) # Use main_window method directly

    def handle_rename_file_response(self, address, response_data):
        """Handles the response after a rename_file command."""
        addr_str = f"{address[0]}:{address[1]}"
        status = response_data.get('status', 'error')
        message = response_data.get('message', 'Unknown status')
        if status == 'success':
            logger.info(f"File rename successful on {addr_str}")
            # Refresh file list automatically after a short delay
            if addr_str == self.main_window.selected_client_addr_str:
                 QTimer.singleShot(500, self.refresh_files) # Use the handler's refresh method
        else:
            logger.error(f"File rename failed on {addr_str}: {message}")
            QMetaObject.invokeMethod(self.main_window, "_show_message_box", Qt.ConnectionType.QueuedConnection,
                                     Q_ARG(str, "File Rename Error"),
                                     Q_ARG(str, f"Failed to rename file on client:\n{message}"),
                                     Q_ARG(str, "warning"))

    def handle_upload_response(self, address, response_data):
        """Handles the response after a file upload attempt."""
        addr_str = f"{address[0]}:{address[1]}"
        file_name = response_data.get('file_name', 'Unknown file')
        status = response_data.get('status', 'success') # Assume success if no status
        message = response_data.get('message', '')
        if status == 'success':
            logger.info(f"File '{file_name}' uploaded successfully to {addr_str}")
            # Optionally refresh file list
            if addr_str == self.main_window.selected_client_addr_str:
                 QTimer.singleShot(500, self.refresh_files)
        else:
            logger.error(f"Upload of '{file_name}' failed on {addr_str}: {message}")
            QMetaObject.invokeMethod(self.main_window, "_show_message_box", Qt.ConnectionType.QueuedConnection,
                                     Q_ARG(str, "File Upload Error"),
                                     Q_ARG(str, f"Failed to upload '{file_name}' to client:\n{message}"),
                                     Q_ARG(str, "warning"))

    # --- GUI Update Methods (Slots called by QMetaObject) ---

    def _update_files_table_gui(self, data):
        """Updates the files table and current path. Runs in GUI thread."""
        mw = self.main_window
        if not mw.selected_client_addr_str: return

        error = data.get('error')
        if error:
             logger.error(f"Error listing directory for {mw.selected_client_addr_str}: {error}")
             mw._show_message_box("Directory Error", f"Could not list directory:\n{error}", "warning")
             mw.files_table.setRowCount(0)
             mw.path_edit.setText("Error")
             # Update client data path as well?
             if mw.selected_client_addr_str in mw.clients_ui_data:
                   mw.clients_ui_data[mw.selected_client_addr_str]['current_path'] = None # Mark path as invalid/unknown
             return

        entries = data.get('entries', [])
        current_path = data.get('current_path') # Get path from the response

        # Update current path in UI data and display
        if current_path is not None:
             if mw.selected_client_addr_str in mw.clients_ui_data:
                  mw.clients_ui_data[mw.selected_client_addr_str]['current_path'] = current_path
             mw.path_edit.setText(current_path)
             logger.debug(f"Current path for {mw.selected_client_addr_str} set to: {current_path}")
        else:
             logger.warning(f"Directory listing response from {mw.selected_client_addr_str} missing 'current_path'.")
             # Keep existing path displayed for now, or clear it?
             # mw.path_edit.setText("Path Unknown")
             if mw.selected_client_addr_str in mw.clients_ui_data:
                  # If path wasn't sent back, maybe assume it didn't change?
                  # Or mark as unknown if we expected it?
                  pass # For now, do nothing if path is missing in response


        table = mw.files_table
        table.setSortingEnabled(False)
        table.setRowCount(0)
        for row, entry in enumerate(entries):
            table.insertRow(row)
            name_item = QTableWidgetItem(entry.get('name', ''))
            type_item = QTableWidgetItem(entry.get('type', ''))
            size_item = QTableWidgetItem(entry.get('size', ''))
            mod_item = QTableWidgetItem(entry.get('modified', ''))

            # Set icon based on type
            icon = QApplication.style().standardIcon(QStyle.StandardPixmap.SP_FileIcon) # Default file
            if entry.get('type') == 'Directory':
                 icon = QApplication.style().standardIcon(QStyle.StandardPixmap.SP_DirIcon)
            name_item.setIcon(icon)

            # Alignment
            size_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            mod_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            table.setItem(row, 0, name_item)
            table.setItem(row, 1, type_item)
            table.setItem(row, 2, size_item)
            table.setItem(row, 3, mod_item)
        table.setSortingEnabled(True)
        # table.resizeColumnsToContents() # Optional resize

        logger.debug(f"Files table updated with {len(entries)} entries for path '{current_path}'.")

    def _update_editor_content_gui(self, content_b64):
         """Updates the content of the active edit/view dialog. Runs in GUI thread."""
         if self.current_edit_dialog and self.current_edit_dialog.isVisible():
             text_edit = self.current_edit_dialog.findChild(QTextEdit)
             if text_edit:
                 try:
                     if not content_b64:
                         text_edit.setText("# File is empty or could not be read.")
                         return

                     # Attempt decoding with utf-8 first, fallback to latin-1 for binary-ish files
                     try:
                          decoded_content = base64.b64decode(content_b64).decode('utf-8')
                     except UnicodeDecodeError:
                          logger.warning("File content is not valid UTF-8, trying Latin-1.")
                          try:
                               decoded_content = base64.b64decode(content_b64).decode('latin-1')
                               # Prepend warning only if non-empty
                               if decoded_content:
                                    decoded_content = ("### Warning: File decoded using Latin-1 (might not be standard text) ###\n" + decoded_content)
                          except Exception as decode_err:
                               logger.error(f"Failed to decode file content with fallback: {decode_err}")
                               text_edit.setText(f"# Error: Could not decode file content (not UTF-8 or Latin-1).")
                               return
                     except (TypeError, base64.binascii.Error) as b64_err:
                           logger.error(f"Error decoding base64 file content: {b64_err}")
                           text_edit.setText(f"# Error: Could not decode base64 content.")
                           return

                     text_edit.setPlainText(decoded_content) # Use setPlainText
                     logger.debug("Editor content updated.")

                 except Exception as e:
                     logger.error(f"Error setting editor content: {e}")
                     text_edit.setPlainText(f"# Error loading file content: {str(e)}")
         else:
              logger.warning("Received file content but no editor dialog is active.")

    def _save_downloaded_file_gui(self, local_save_path, data_b64):
         """Saves the received base64 encoded file data to the local path. Runs in GUI thread."""
         mw = self.main_window
         try:
             file_data = base64.b64decode(data_b64)
             with open(local_save_path, 'wb') as f:
                 f.write(file_data)
             logger.info(f"File successfully downloaded to: {local_save_path}")
             mw._show_message_box("Download Complete", f"File saved to:\n{local_save_path}", "information")
             # Ask user if they want to open the folder
             reply = QMessageBox.question(mw, "Open Folder?",
                                          "Download complete. Open the containing folder?",
                                          QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                          QMessageBox.StandardButton.No)
             if reply == QMessageBox.StandardButton.Yes:
                  folder_url = QUrl.fromLocalFile(os.path.dirname(local_save_path))
                  QDesktopServices.openUrl(folder_url)

         except (TypeError, base64.binascii.Error) as e:
             logger.error(f"Error decoding downloaded file data: {e}")
             mw._show_message_box("Download Error", "Failed to decode file data.", "critical")
         except IOError as e:
             logger.error(f"I/O error saving downloaded file to {local_save_path}: {e}")
             mw._show_message_box("Download Error", f"Could not save file to:\n{local_save_path}\n\nError: {e}", "critical")
         except Exception as e:
             logger.error(f"Unexpected error saving downloaded file: {e}")
             mw._show_message_box("Download Error", f"An unexpected error occurred:\n{e}", "critical")

    # --- GUI Actions (Called directly from MainWindow slots) ---

    def refresh_files(self):
        """Sends a request to list files in the current directory."""
        address = self.main_window._get_selected_client_address()
        if address:
            current_path = self.main_window._get_current_client_path()
            self.main_window.server_core.send_command(address, "list_directory", 
                                                    {"path": current_path} if current_path else {})
        else:
            logger.warning("Refresh files called but no client selected.")
            # Optionally clear the file table if no client is selected
            # self._update_files_table_gui({'entries': [], 'current_path': ''})

    def go_up_directory(self):
        """Sends command to list the parent directory."""
        mw = self.main_window
        address = mw._get_selected_client_address()
        current_path = mw._get_current_client_path()
        if address and current_path:
            # Calculate parent path conceptually (might not be exact on client OS)
            # os.path.dirname handles trailing slashes correctly
            parent = os.path.dirname(current_path)

            # Avoid sending command if already at root
            if parent != current_path:
                 logger.info(f"Requesting parent directory of '{current_path}' from {mw.selected_client_addr_str}")
                 if mw.server_core:
                      # Send the calculated parent path. Client should verify and list it.
                      mw.server_core.send_command(address, 'list_directory', {'path': parent})
                 else: logger.error("Server core unavailable.")
            else:
                 logger.info(f"Already at root directory: {current_path}")
                 mw._show_message_box("Navigation Info", "Already at the root directory.", "information")
        else:
            logger.warning("Go up called but no client selected or path unknown.")

    def create_new_directory(self):
        """Prompts for and sends a command to create a new directory."""
        mw = self.main_window
        address = mw._get_selected_client_address()
        current_path = mw._get_current_client_path()
        if not address or current_path is None:
            mw._show_message_box("Action Failed", "No client selected or current path unknown.", "warning")
            return

        dir_name, ok = QInputDialog.getText(mw, "Create Directory", "Enter new directory name:")
        if ok and dir_name:
            # Basic validation - avoid slashes in the name itself
            if '/' in dir_name or '\\' in dir_name:
                 mw._show_message_box("Invalid Name", "Directory name cannot contain slashes.", "warning")
                 return

            # Use os.path.join for cross-platform compatibility (client interprets it)
            new_dir_path = os.path.join(current_path, dir_name)
            logger.info(f"Sending create directory command for '{new_dir_path}' to {mw.selected_client_addr_str}")
            if mw.server_core:
                success = mw.server_core.send_command(address, 'create_directory', {'path': new_dir_path})
                if success:
                    QTimer.singleShot(1000, self.refresh_files) # Refresh after delay
                else:
                     mw._show_message_box("Error", "Failed to send create directory command.", "critical")
            else: logger.error("Server core unavailable.")

    def upload_file_to_client(self):
        """Opens dialog to select file(s) and sends upload command(s)."""
        mw = self.main_window
        address = mw._get_selected_client_address()
        current_path = mw._get_current_client_path()
        if not address or current_path is None:
            mw._show_message_box("Action Failed", "No client selected or current path unknown.", "warning")
            return

        local_file_paths, _ = QFileDialog.getOpenFileNames(mw, "Select File(s) to Upload", mw.download_path) # Start in downloads

        if not local_file_paths:
            return

        if not mw.server_core:
             mw._show_message_box("Error", "Server connection lost.", "critical")
             return

        for local_path in local_file_paths:
            try:
                file_name = os.path.basename(local_path)
                # Remote path is just the target directory on client
                remote_target_dir = current_path

                # Check file size before reading? Add limit?
                # max_upload_size = 50 * 1024 * 1024 # 50 MB limit example
                # if os.path.getsize(local_path) > max_upload_size:
                #      logger.error(f"File exceeds size limit: {local_path}")
                #      mw._show_message_box("Upload Error", f"File exceeds size limit ({max_upload_size // 1024 // 1024} MB):\n{file_name}", "warning")
                #      continue

                with open(local_path, 'rb') as f:
                    file_data = f.read()

                if not file_data:
                     logger.warning(f"Skipping empty file: {local_path}")
                     continue

                encoded_data = base64.b64encode(file_data).decode('utf-8')

                logger.info(f"Sending upload command for '{file_name}' to directory '{remote_target_dir}' on {mw.selected_client_addr_str}")
                # Sending target directory path and filename separately
                success = mw.server_core.send_command(address, 'upload_file', {
                    'path': remote_target_dir,
                    'file_name': file_name,
                    'data': encoded_data
                })
                if not success:
                     mw._show_message_box("Error", f"Failed to send upload command for {file_name}.", "warning")
                     # Stop uploading remaining files if one fails?
                     # break

            except FileNotFoundError:
                 logger.error(f"Upload error: Local file not found {local_path}")
                 mw._show_message_box("Upload Error", f"Local file not found:\n{local_path}", "critical")
            except MemoryError:
                  logger.error(f"Memory error reading file for upload: {local_path}")
                  mw._show_message_box("Upload Error", f"Memory Error: File too large to upload?\n{local_path}", "critical")
            except Exception as e:
                logger.error(f"Error preparing file for upload {local_path}: {e}")
                mw._show_message_box("Upload Error", f"Could not read file:\n{local_path}\n\nError: {e}", "critical")

    def download_selected_item(self):
        """Initiates download for the selected file."""
        mw = self.main_window
        address = mw._get_selected_client_address()
        current_path = mw._get_current_client_path()
        if not address or current_path is None:
             mw._show_message_box("Action Failed", "No client selected or path unknown.", "warning")
             return

        selected_items = mw.files_table.selectedItems()
        if not selected_items:
            mw._show_message_box("Action Failed", "No file or directory selected.", "warning")
            return

        row = selected_items[0].row()
        item_name = mw.files_table.item(row, 0).text() # Name column 0
        item_type = mw.files_table.item(row, 1).text() # Type column 1

        if item_type != "File":
            mw._show_message_box("Action Failed", "Cannot download directories (yet). Please select a file.", "warning")
            # TODO: Implement recursive directory download later if needed
            return

        remote_file_path = os.path.join(current_path, item_name)

        # Propose save location
        default_local_path = os.path.join(mw.download_path, item_name)
        local_save_path, _ = QFileDialog.getSaveFileName(mw, "Save File As", default_local_path)

        if local_save_path:
            # Store the path where the data should be saved when it arrives
            self._pending_download_path = local_save_path
            logger.info(f"Requesting download of '{remote_file_path}' from {mw.selected_client_addr_str} to save at '{local_save_path}'")
            if mw.server_core:
                success = mw.server_core.send_command(address, 'download_file', {'path': remote_file_path})
                if not success:
                     mw._show_message_box("Error", "Failed to send download command.", "critical")
                     self._pending_download_path = None # Clear pending path if send failed
            else:
                 logger.error("Server core unavailable.")
                 self._pending_download_path = None
        else:
             logger.info("Download cancelled by user.")

    def view_selected_file(self):
         """Opens a dialog to view the selected file's content."""
         self._open_file_dialog(read_only=True)

    def edit_selected_file(self):
         """Opens a dialog to edit the selected file's content."""
         self._open_file_dialog(read_only=False)

    def _open_file_dialog(self, read_only=False):
        """Helper to open a view/edit dialog for the selected file."""
        mw = self.main_window
        address = mw._get_selected_client_address()
        current_path = mw._get_current_client_path()
        if not address or current_path is None:
             mw._show_message_box("Action Failed", "No client selected or path unknown.", "warning")
             return

        selected_items = mw.files_table.selectedItems()
        if not selected_items:
            mw._show_message_box("Action Failed", "No file selected.", "warning")
            return

        row = selected_items[0].row()
        file_name = mw.files_table.item(row, 0).text()
        file_type = mw.files_table.item(row, 1).text()

        if file_type != "File":
            mw._show_message_box("Action Failed", "Can only view/edit files.", "warning")
            return

        remote_file_path = os.path.join(current_path, file_name)

        # --- Create Dialog ---
        # Ensure dialog is created with the main window as parent
        dialog = QDialog(mw)
        dialog.setWindowTitle(f"{'View' if read_only else 'Edit'} - {file_name} on {mw.selected_client_addr_str}")
        dialog.setMinimumSize(800, 600)
        layout = QVBoxLayout(dialog)

        text_edit = QTextEdit()
        text_edit.setReadOnly(read_only)
        text_edit.setAcceptRichText(False) # Plain text only
        text_edit.setStyleSheet("""
            QTextEdit {
                background-color: #2E2E2E;
                color: #E0E0E0;
                font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
                font-size: 13px;
                border: 1px solid #555;
            }""")
        layout.addWidget(text_edit)

        button_layout = QHBoxLayout()
        status_label = QLabel("Loading...") # Add a status label
        status_label.setStyleSheet("color: #aaa;")
        save_btn = QPushButton("💾 Save")
        save_btn.setVisible(not read_only)
        save_btn.setEnabled(False) # Disabled until content loads
        close_btn = QPushButton("❌ Close")
        edit_btn = QPushButton("✏️ Edit")
        edit_btn.setVisible(read_only)
        edit_btn.setEnabled(False) # Disabled until content loads

        button_layout.addWidget(status_label)
        button_layout.addStretch()
        button_layout.addWidget(edit_btn)
        button_layout.addWidget(save_btn)
        button_layout.addWidget(close_btn)
        layout.addLayout(button_layout)

        # --- Dialog Logic & State ---
        dialog.status_label = status_label # Attach for access
        dialog.save_btn = save_btn
        dialog.edit_btn = edit_btn
        dialog.text_edit = text_edit

        def switch_to_edit():
             text_edit.setReadOnly(False)
             edit_btn.setVisible(False)
             save_btn.setVisible(True)
             dialog.setWindowTitle(f"Edit - {file_name} on {mw.selected_client_addr_str}")
             status_label.setText("Editing...")

        def save_changes():
            if not mw.selected_client_addr_str: return # Safety check
            content = text_edit.toPlainText()
            try:
                 # Use UTF-8 by default for saving text files
                 encoded_content = base64.b64encode(content.encode('utf-8')).decode('utf-8')
                 logger.info(f"Sending write command for '{remote_file_path}'")
                 if mw.server_core:
                    success = mw.server_core.send_command(address, 'write_file', {
                        'path': remote_file_path,
                        'content': encoded_content
                    })
                    if success:
                         status_label.setText("Saving...")
                         save_btn.setEnabled(False) # Disable save while waiting for response
                         # Response handled by handle_write_file_response
                         # Consider closing dialog only on success response?
                         dialog.accept() # Close dialog optimistically for now
                    else:
                         mw._show_message_box("Error", "Failed to send save command.", "critical", parent=dialog)
                 else:
                      mw._show_message_box("Error", "Server connection lost.", "critical", parent=dialog)

            except Exception as e:
                logger.error(f"Error encoding content for saving: {e}")
                mw._show_message_box("Save Error", f"Could not encode file content:\n{e}", "critical", parent=dialog)

        # --- Connections ---
        edit_btn.clicked.connect(switch_to_edit)
        save_btn.clicked.connect(save_changes)
        close_btn.clicked.connect(dialog.reject) # Closes the dialog

        # Store reference and request content
        self.current_edit_dialog = dialog # Store reference
        dialog.finished.connect(self._clear_edit_dialog_ref) # Clear reference when closed

        logger.debug(f"Requesting file content for {'view' if read_only else 'edit'}: {remote_file_path}")
        if mw.server_core:
            success = mw.server_core.send_command(address, 'read_file', {'path': remote_file_path})
            if not success:
                 mw._show_message_box("Error", "Failed to send read file command.", "critical", parent=dialog)
                 status_label.setText("Error requesting content")
                 # Can't proceed without content
                 close_btn.setText("Close") # Ensure close button works
            else:
                 status_label.setText("Loading content...")
        else:
             mw._show_message_box("Error", "Server connection lost.", "critical", parent=dialog)
             status_label.setText("Error: No connection")

        dialog.exec()

    @pyqtSlot(int)
    def _clear_edit_dialog_ref(self, result):
         """Clear the reference to the edit/view dialog when finished."""
         logger.debug(f"Edit/View dialog closed with result: {result}")
         self.current_edit_dialog = None

    def rename_selected_item(self):
        """Prompts for and sends command to rename selected file/directory."""
        mw = self.main_window
        address = mw._get_selected_client_address()
        current_path = mw._get_current_client_path()
        if not address or current_path is None:
             mw._show_message_box("Action Failed", "No client selected or path unknown.", "warning")
             return

        selected_items = mw.files_table.selectedItems()
        if not selected_items:
             mw._show_message_box("Action Failed", "No item selected.", "warning")
             return

        row = selected_items[0].row()
        old_name = mw.files_table.item(row, 0).text()
        old_path = os.path.join(current_path, old_name)

        new_name, ok = QInputDialog.getText(mw, "Rename Item", f"Enter new name for '{old_name}':", text=old_name)

        if ok and new_name and new_name != old_name:
             if '/' in new_name or '\\' in new_name:
                  mw._show_message_box("Invalid Name", "Name cannot contain slashes.", "warning")
                  return
             new_path = os.path.join(current_path, new_name)
             logger.info(f"Sending rename command: '{old_path}' -> '{new_path}'")
             if mw.server_core:
                 success = mw.server_core.send_command(address, 'rename_file', {'old_path': old_path, 'new_path': new_path})
                 if not success:
                      mw._show_message_box("Error", "Failed to send rename command.", "critical")
                 # Response handled by handle_rename_file_response which triggers refresh
             else:
                  logger.error("Server core unavailable.")
                  mw._show_message_box("Error", "Server connection lost.", "critical")

    def on_file_double_clicked(self, item):
        """Handles double-click on item in files table (enter directory or view file)."""
        mw = self.main_window
        address = mw._get_selected_client_address()
        current_path = mw._get_current_client_path()
        if not address or current_path is None: return

        row = item.row()
        item_name = mw.files_table.item(row, 0).text()
        item_type = mw.files_table.item(row, 1).text()

        if item_type == "Directory":
            # Construct new path using os.path.join for safety
            # Client needs to handle path separators correctly based on its OS
            new_path = os.path.join(current_path, item_name)
            logger.info(f"Double-click on directory: Requesting listing for '{new_path}'")
            # Send command to list the new directory path
            if mw.server_core:
                success = mw.server_core.send_command(address, 'list_directory', {'path': new_path})
                if not success:
                     mw._show_message_box("Error", f"Failed to send command to enter directory {item_name}.", "warning")
            else:
                 logger.error("Server core unavailable.")
                 mw._show_message_box("Error", "Server connection lost.", "critical")

        elif item_type == "File":
            logger.info(f"Double-click on file: Opening view dialog for '{item_name}'")
            self.view_selected_file() # Open read-only view on double-click
        else:
            logger.warning(f"Double-click on unknown item type: {item_type}")

    def show_files_context_menu(self, position):
        """Shows a context menu for the files table."""
        mw = self.main_window
        if not mw.selected_client_addr_str: return

        menu = QMenu(mw.files_table) # Parent the menu to the table
        selected_items = mw.files_table.selectedItems()
        item_selected = bool(selected_items)
        is_file = False
        if item_selected:
             row = selected_items[0].row()
             try:
                  item_type = mw.files_table.item(row, 1).text()
                  is_file = (item_type == "File")
             except AttributeError: # Handle case where item might be missing momentarily
                  return

        # Actions available globally in the table
        refresh_action = menu.addAction("🔄 Refresh")
        new_folder_action = menu.addAction("📁 New Folder")
        upload_action = menu.addAction("⬆️ Upload Here")
        menu.addSeparator()

        # Actions requiring an item selection
        download_action = menu.addAction("⬇️ Download")
        rename_action = menu.addAction("✏️ Rename")
        view_action = menu.addAction("👁️ View")
        edit_action = menu.addAction("📝 Edit")
        # delete_action = menu.addAction("❌ Delete") # Add later if needed

        download_action.setEnabled(item_selected and is_file) # Can only download files for now
        rename_action.setEnabled(item_selected)
        view_action.setEnabled(item_selected and is_file)
        edit_action.setEnabled(item_selected and is_file)
        # delete_action.setEnabled(item_selected)

        # Execute selected action
        action = menu.exec(mw.files_table.mapToGlobal(position))

        if action == refresh_action:
            self.refresh_files()
        elif action == new_folder_action:
             self.create_new_directory()
        elif action == upload_action:
             self.upload_file_to_client()
        elif action == download_action:
            self.download_selected_item()
        elif action == rename_action:
            self.rename_selected_item()
        elif action == view_action:
             self.view_selected_file()
        elif action == edit_action:
             self.edit_selected_file()
        # elif action == delete_action:
        #      self._delete_selected_item() # Implement delete 