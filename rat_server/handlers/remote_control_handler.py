import logging
import base64
import os
import time
from PyQt6.QtCore import QMetaObject, Qt, Q_ARG, QSize
from PyQt6.QtGui import QPixmap, QImage, QTextCursor, QMouseEvent
from PyQt6.QtWidgets import QLabel # For type hinting

logger = logging.getLogger(__name__)

class RemoteControlHandler:
    def __init__(self, main_window):
        self.main_window = main_window
        self.current_pixmap = None # Store the original received pixmap
        self._mouse_press_button = None # Track pressed mouse button
        # Access main_window attributes like:
        # self.main_window.screen_label
        # self.main_window.scroll_area
        # self.main_window.zoom_slider
        # self.main_window.zoom_label
        # self.main_window.interval_slider
        # self.main_window.interval_label
        # self.main_window.shell_output
        # self.main_window.shell_input
        # self.main_window.start_screen_btn, stop_screen_btn, etc.
        # self.main_window.audio_status
        # self.main_window.temp_dir
        # self.main_window.selected_client_addr_str
        # self.main_window.server_core
        # self.main_window._get_selected_client_address()
        # self.main_window._show_message_box()

    # --- ServerCore Callback Handlers ---

    def handle_screenshot(self, address, data):
        """Handles screenshot updates from the server core."""
        addr_str = f"{address[0]}:{address[1]}"
        if addr_str == self.main_window.selected_client_addr_str:
            QMetaObject.invokeMethod(self.main_window, "_update_screen_label",
                                   Qt.ConnectionType.QueuedConnection,
                                   Q_ARG(str, data))

    def handle_shell_output(self, address, data):
        """Handles shell output updates from the server core."""
        addr_str = f"{address[0]}:{address[1]}"
        if addr_str == self.main_window.selected_client_addr_str:
            # Append text in the GUI thread
            QMetaObject.invokeMethod(self.main_window.shell_output, "moveCursor",
                                   Qt.ConnectionType.QueuedConnection,
                                   Q_ARG(QTextCursor.MoveOperation, QTextCursor.MoveOperation.End))
            QMetaObject.invokeMethod(self.main_window.shell_output, "insertPlainText",
                                   Qt.ConnectionType.QueuedConnection,
                                   Q_ARG(str, data))

    def handle_audio_data(self, address, audio_data_b64):
        """Handles incoming audio data chunks from the server core."""
        addr_str = f"{address[0]}:{address[1]}"
        if addr_str == self.main_window.selected_client_addr_str:
            # Pass the base64 data to the GUI thread for processing/saving
            QMetaObject.invokeMethod(self, "_process_audio_data_gui", Qt.ConnectionType.QueuedConnection,
                                     Q_ARG(str, audio_data_b64))

    def handle_screen_frame(self, address, frame_data):
        """Handles screen frame updates from the client."""
        addr_str = f"{address[0]}:{address[1]}"
        if addr_str == self.main_window.selected_client_addr_str:
            QMetaObject.invokeMethod(self.main_window, "_update_screen_label",
                                   Qt.ConnectionType.QueuedConnection,
                                   Q_ARG(str, frame_data))

    # --- GUI Update Methods (Slots called by QMetaObject) ---

    def _update_screen_label_gui(self, image_b64):
        """Decodes base64 image data and updates the screen label. Runs in GUI thread."""
        mw = self.main_window
        try:
            image_data = base64.b64decode(image_b64)
            image = QImage.fromData(image_data)
            if not image.isNull():
                self.current_pixmap = QPixmap.fromImage(image) # Store original for zoom
                self._apply_screen_zoom() # Apply current zoom level
            else:
                logger.error("Failed to create QImage from received screen data.")
                # Optionally display an error image/message
                # mw.screen_label.setText("Error loading image")
        except (TypeError, base64.binascii.Error) as e:
            logger.error(f"Error decoding screenshot data: {e}")
        except Exception as e:
            logger.error(f"Error updating screenshot label: {e}")

    def _process_audio_data_gui(self, audio_data_b64):
        """Processes received audio data chunks. Runs in GUI thread."""
        mw = self.main_window
        try:
            audio_data = base64.b64decode(audio_data_b64)
            logger.debug(f"Audio data received from {mw.selected_client_addr_str}: {len(audio_data)} bytes")
            # Update status label
            mw.audio_status.setText(f"Audio capture active - Receiving... ({len(audio_data)} bytes)")

            # --- Example: Save audio chunks to a temporary file ---
            # Warning: Appends raw chunks. Playback requires format knowledge.
            if mw.selected_client_addr_str:
                safe_addr = mw.selected_client_addr_str.replace(':', '_').replace('.','_') # Make filename safer
                temp_audio_file = os.path.join(mw.temp_dir, f"audio_{safe_addr}.raw")
                try:
                    with open(temp_audio_file, 'ab') as f:
                        f.write(audio_data)
                except IOError as e:
                     logger.error(f"Failed to write audio chunk to {temp_audio_file}: {e}")
                     mw.audio_status.setText("Audio Error: File write failed")
            # -------------------------------------------------------

        except (TypeError, base64.binascii.Error) as e:
            logger.error(f"Error decoding audio data from {mw.selected_client_addr_str}: {e}")
            mw.audio_status.setText(f"Audio Error: Decode failed")
        except Exception as e:
             logger.error(f"Error handling audio data from {mw.selected_client_addr_str}: {e}")
             mw.audio_status.setText(f"Audio Error: {e}")

    # --- GUI Actions (Called directly from MainWindow slots) ---

    def start_screen_capture(self):
        """Sends command to start screen capture on client."""
        address = self.main_window._get_selected_client_address()
        if address:
            self.main_window.server_core.send_command(address, "start_screen_capture")
            self.main_window.stop_screen_btn.setEnabled(True)
            self.main_window.start_screen_btn.setEnabled(False)

    def stop_screen_capture(self):
        """Sends command to stop screen capture on client."""
        address = self.main_window._get_selected_client_address()
        if address:
            self.main_window.server_core.send_command(address, "stop_screen_capture")
            self.main_window.stop_screen_btn.setEnabled(False)
            self.main_window.start_screen_btn.setEnabled(True)
            self.main_window.screen_label.clear()
            self.current_pixmap = None

    def update_screen_zoom(self, value):
        """Updates the screen zoom level."""
        if self.current_pixmap:
            scaled_pixmap = self.current_pixmap.scaled(
                self.main_window.screen_label.size() * value / 100,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            self.main_window.screen_label.setPixmap(scaled_pixmap)
            self.main_window.zoom_label.setText(f"{value}%")

    def _apply_screen_zoom(self):
         """Applies the current zoom level to the displayed pixmap. Runs in GUI thread."""
         mw = self.main_window
         if self.current_pixmap and not self.current_pixmap.isNull():
             zoom_factor = mw.zoom_slider.value() / 100.0
             # Use QSize for scaling dimensions
             new_size = QSize(int(self.current_pixmap.width() * zoom_factor),
                              int(self.current_pixmap.height() * zoom_factor))

             # Check if new_size is valid
             if new_size.width() <= 0 or new_size.height() <= 0:
                  logger.warning(f"Invalid scale resulted in zero/negative size: {new_size}")
                  # Optionally reset zoom or keep last valid pixmap
                  # For now, just don't update if size is invalid
                  return

             scaled_pixmap = self.current_pixmap.scaled(new_size,
                                                        Qt.AspectRatioMode.KeepAspectRatio,
                                                        Qt.TransformationMode.SmoothTransformation)
             mw.screen_label.setPixmap(scaled_pixmap)
             # Adjust label size hint?
             # mw.screen_label.adjustSize() # This might be needed if label doesn't resize automatically
         elif mw.screen_label.pixmap() is not None: # Clear label if no current pixmap exists
             mw.screen_label.clear()

    def send_shell_command(self):
        """Sends the command from the shell input line."""
        mw = self.main_window
        address = mw._get_selected_client_address()
        command = mw.shell_input.text().strip()
        if address and command:
            logger.info(f"Sending shell command '{command}' to {mw.selected_client_addr_str}")
            # Append command to output *before* sending for immediate feedback
            mw.shell_output.moveCursor(QTextCursor.MoveOperation.End)
            mw.shell_output.insertPlainText(f"\n> {command}\n") # Display command sent
            mw.shell_output.moveCursor(QTextCursor.MoveOperation.End)

            if mw.server_core:
                success = mw.server_core.send_command(address, 'shell_command', {'cmd': command})
                if not success:
                     mw._show_message_box("Error", "Failed to send shell command.", "warning")
                     # Re-enable input?
            else:
                 logger.error("Server core unavailable.")
                 mw._show_message_box("Error", "Server connection lost.", "critical")

            mw.shell_input.clear()
        elif not address:
             logger.warning("Tried to send shell command, but no client selected.")
             mw._show_message_box("Action Failed", "No client selected.", "warning")
        else:
             logger.debug("Empty shell command ignored.")

    def start_audio_capture(self):
        """Starts audio capture stream."""
        mw = self.main_window
        address = mw._get_selected_client_address()
        if address:
            logger.info(f"Starting audio capture for {mw.selected_client_addr_str}")
            if mw.server_core:
                success = mw.server_core.send_command(address, 'start_audio_capture')
                if success:
                    mw.start_audio_btn.setEnabled(False)
                    mw.stop_audio_btn.setEnabled(True)
                    mw.audio_status.setText("Audio capture starting...")
                    # Clear any previous temporary audio file for this client
                    if mw.selected_client_addr_str:
                         safe_addr = mw.selected_client_addr_str.replace(':', '_').replace('.','_')
                         temp_audio_file = os.path.join(mw.temp_dir, f"audio_{safe_addr}.raw")
                         if os.path.exists(temp_audio_file):
                             try: os.remove(temp_audio_file)
                             except OSError as e: logger.warning(f"Could not clear old audio file {temp_audio_file}: {e}")
                else:
                    mw._show_message_box("Error", "Failed to send start audio capture command.", "warning")
            else:
                 logger.error("Server core unavailable.")
                 mw._show_message_box("Error", "Server connection lost.", "critical")
        else:
             mw._show_message_box("Action Failed", "No client selected.", "warning")

    def stop_audio_capture(self, force=False):
        """Stops audio capture stream."""
        mw = self.main_window
        address = mw._get_selected_client_address()
        addr_to_stop_tuple = None

        if address:
            addr_to_stop_tuple = address
        elif force and mw.selected_client_addr_str:
            try:
                 ip, port_str = mw.selected_client_addr_str.split(':')
                 addr_to_stop_tuple = (ip, int(port_str))
            except Exception as e:
                 logger.warning(f"Could not parse forced stop address '{mw.selected_client_addr_str}': {e}")

        if addr_to_stop_tuple:
            logger.info(f"Stopping audio capture for {addr_to_stop_tuple}")
            if mw.server_core:
                mw.server_core.send_command(addr_to_stop_tuple, 'stop_audio_capture')
            else:
                logger.warning("Cannot send stop audio capture: Server core unavailable.")

        # Always update UI if a client was selected or forced
        if address or force:
            mw.start_audio_btn.setEnabled(True)
            mw.stop_audio_btn.setEnabled(False)
            mw.audio_status.setText("Audio capture stopped")
            # Process the saved audio file here? Convert/Save As?
            if mw.selected_client_addr_str:
                safe_addr = mw.selected_client_addr_str.replace(':', '_').replace('.','_')
                temp_audio_file = os.path.join(mw.temp_dir, f"audio_{safe_addr}.raw")
                if os.path.exists(temp_audio_file):
                     logger.info(f"Raw audio data saved for {mw.selected_client_addr_str} at: {temp_audio_file}")
                     # Add code here to process/convert/save the raw file if desired.
                     # For example, using PyAudio/wave to save as WAV if format is known.

    # --- Remote Control Mouse/Keyboard Event Handlers ---
    # These are called directly by the event system when interacting with screen_label

    def screen_mouse_press(self, event: QMouseEvent):
         """Handles mouse presses on the screen capture label."""
         mw = self.main_window
         address = mw._get_selected_client_address()
         # Ensure capture is running (check stop button state)
         if not address or not self.current_pixmap or not mw.stop_screen_btn.isEnabled():
              logger.debug("Screen mouse press ignored: No client, pixmap, or capture not active.")
              return

         label_pos = event.position().toPoint() # Position within the QLabel
         pixmap_rect = mw.screen_label.pixmap().rect()
         original_size = self.current_pixmap.size()

         # Calculate relative coordinates based on the original image size
         if pixmap_rect.contains(label_pos) and original_size.isValid() and original_size.width() > 0 and original_size.height() > 0:
              # Account for potential scaling/aspect ratio preservation
              current_pixmap_size = mw.screen_label.pixmap().size() # Size as displayed
              if current_pixmap_size.width() <= 0 or current_pixmap_size.height() <= 0:
                   logger.warning("Cannot calculate relative coords: displayed pixmap size is invalid.")
                   return

              # Calculate scaling factors
              scale_x = original_size.width() / current_pixmap_size.width()
              scale_y = original_size.height() / current_pixmap_size.height()

              # Calculate position relative to the top-left of the pixmap within the label
              # (Assumes pixmap is centered, adjust if alignment changes)
              offset_x = (mw.screen_label.width() - current_pixmap_size.width()) / 2
              offset_y = (mw.screen_label.height() - current_pixmap_size.height()) / 2

              # Position relative to pixmap top-left
              pixmap_x = label_pos.x() - offset_x
              pixmap_y = label_pos.y() - offset_y

              # Clamp coordinates to pixmap bounds
              pixmap_x = max(0, min(pixmap_x, current_pixmap_size.width() - 1))
              pixmap_y = max(0, min(pixmap_y, current_pixmap_size.height() - 1))

              # Map to original image coordinates
              original_x = int(pixmap_x * scale_x)
              original_y = int(pixmap_y * scale_y)

              # Map to relative coordinates (0.0 to 1.0)
              relative_x = original_x / original_size.width()
              relative_y = original_y / original_size.height()

              # Clamp relative coordinates
              relative_x = max(0.0, min(relative_x, 1.0))
              relative_y = max(0.0, min(relative_y, 1.0))

              button = 'left'
              if event.button() == Qt.MouseButton.RightButton:
                   button = 'right'
              elif event.button() == Qt.MouseButton.MiddleButton:
                   button = 'middle'
              # Add MiddleButton if needed

              logger.debug(f"Screen press at label({label_pos.x()},{label_pos.y()}) -> "
                           f"pixmap({pixmap_x:.0f},{pixmap_y:.0f}) -> "
                           f"relative({relative_x:.4f},{relative_y:.4f}), button: {button}")

              # Send mouse press command
              if mw.server_core:
                   success = mw.server_core.send_command(address, 'mouse_click', {
                       'x': relative_x, # Client expects relative coords
                       'y': relative_y,
                       'button': button,
                       'action': 'press' # Send 'press' first
                   })
                   if success:
                        # Store state if needed for release/drag
                        self._mouse_press_button = button
                   else:
                        logger.warning("Failed to send mouse press command.")
              else:
                  logger.error("Server core unavailable for mouse press.")
         else:
              logger.debug("Mouse press outside pixmap area or invalid pixmap.")

    def screen_mouse_release(self, event: QMouseEvent):
         """Handles mouse releases on the screen capture label."""
         mw = self.main_window
         address = mw._get_selected_client_address()
         # Check if capture active and a button was previously pressed
         if not address or not mw.stop_screen_btn.isEnabled() or self._mouse_press_button is None:
              # Clear state just in case
              self._mouse_press_button = None
              return

         # Send release command for the button that was pressed
         logger.debug(f"Screen release, button: {self._mouse_press_button}")
         if mw.server_core:
              mw.server_core.send_command(address, 'mouse_click', {
                  'button': self._mouse_press_button,
                  'action': 'release'
              })
         else:
              logger.error("Server core unavailable for mouse release.")

         self._mouse_press_button = None # Clear stored button state

    def screen_mouse_double_click(self, event: QMouseEvent):
         """Handles mouse double-clicks on the screen capture label."""
         mw = self.main_window
         address = mw._get_selected_client_address()
         if not address or not self.current_pixmap or not mw.stop_screen_btn.isEnabled(): return

         label_pos = event.position().toPoint()
         pixmap_rect = mw.screen_label.pixmap().rect()
         original_size = self.current_pixmap.size()

         if pixmap_rect.contains(label_pos) and original_size.isValid() and original_size.width() > 0 and original_size.height() > 0:
              current_pixmap_size = mw.screen_label.pixmap().size()
              if current_pixmap_size.width() <= 0 : return

              scale_x = original_size.width() / current_pixmap_size.width()
              scale_y = original_size.height() / current_pixmap_size.height()
              offset_x = (mw.screen_label.width() - current_pixmap_size.width()) / 2
              offset_y = (mw.screen_label.height() - current_pixmap_size.height()) / 2
              pixmap_x = max(0, min(label_pos.x() - offset_x, current_pixmap_size.width() - 1))
              pixmap_y = max(0, min(label_pos.y() - offset_y, current_pixmap_size.height() - 1))
              original_x = int(pixmap_x * scale_x)
              original_y = int(pixmap_y * scale_y)
              relative_x = max(0.0, min(original_x / original_size.width(), 1.0))
              relative_y = max(0.0, min(original_y / original_size.height(), 1.0))

              button = 'double' # Special button type for double click
              if event.button() == Qt.MouseButton.RightButton:
                    button = 'right_double' # Need client support for this
              elif event.button() == Qt.MouseButton.MiddleButton:
                    button = 'middle_double' # Need client support

              logger.debug(f"Screen double-click at relative({relative_x:.4f},{relative_y:.4f}), button: {button}")

              if mw.server_core:
                   mw.server_core.send_command(address, 'mouse_click', {
                       'x': relative_x,
                       'y': relative_y,
                       'button': button,
                       'action': 'click' # Action is still click for double-click command
                   })
              else:
                   logger.error("Server core unavailable for double click.")

    # Add screen_mouse_move if needed for dragging later 