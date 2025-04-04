import logging
import base64
from PyQt6.QtCore import QMetaObject, Qt, Q_ARG
from PyQt6.QtGui import QPixmap, QImage

logger = logging.getLogger(__name__)

class CameraHandler:
    def __init__(self, main_window):
        self.main_window = main_window
        # Access main_window attributes:
        # self.main_window.camera_label
        # self.main_window.start_camera_btn, stop_camera_btn
        # self.main_window.selected_client_addr_str
        # self.main_window.server_core
        # self.main_window._get_selected_client_address()

    # --- ServerCore Callback Handler ---

    def handle_camera_frame(self, address, frame_data):
        """Handles camera frame updates from the client."""
        addr_str = f"{address[0]}:{address[1]}"
        if addr_str == self.main_window.selected_client_addr_str:
            QMetaObject.invokeMethod(self.main_window, "_update_camera_label",
                                   Qt.ConnectionType.QueuedConnection,
                                   Q_ARG(str, frame_data))

    # --- GUI Update Method (Slot called by QMetaObject) ---

    def _update_camera_label_gui(self, frame_b64):
        """Decodes base64 image data and updates the camera label. Runs in GUI thread."""
        mw = self.main_window
        # Check if the camera tab/widget is still supposed to be active
        if not mw.stop_camera_btn.isEnabled():
             # Stop command might have been sent, but frames are still arriving.
             # Or client selection changed.
             # logger.debug("Ignoring camera frame update as camera feed is stopped.")
             return

        try:
            image_data = base64.b64decode(frame_b64)
            image = QImage.fromData(image_data)
            if not image.isNull():
                 pixmap = QPixmap.fromImage(image)
                 # Scale pixmap to fit the label while keeping aspect ratio
                 scaled_pixmap = pixmap.scaled(mw.camera_label.size(),
                                               Qt.AspectRatioMode.KeepAspectRatio,
                                               Qt.TransformationMode.SmoothTransformation)
                 mw.camera_label.setPixmap(scaled_pixmap)
            else:
                logger.error("Failed to create QImage from received camera data.")
                # Optionally show error text on label
                # mw.camera_label.setText("Error loading frame")
        except (TypeError, base64.binascii.Error) as e:
            logger.error(f"Error decoding camera frame data: {e}")
        except Exception as e:
            logger.error(f"Error updating camera label: {e}")

    # --- GUI Actions (Called directly from MainWindow slots) ---

    def start_camera(self):
        """Sends command to start camera capture on client."""
        address = self.main_window._get_selected_client_address()
        if address:
            self.main_window.server_core.send_command(address, "start_camera")
            self.main_window.stop_camera_btn.setEnabled(True)
            self.main_window.start_camera_btn.setEnabled(False)

    def stop_camera(self):
        """Sends command to stop camera capture on client."""
        address = self.main_window._get_selected_client_address()
        if address:
            self.main_window.server_core.send_command(address, "stop_camera")
            self.main_window.stop_camera_btn.setEnabled(False)
            self.main_window.start_camera_btn.setEnabled(True)
            self.main_window.camera_label.clear()
            self.main_window.camera_label.setText("Camera feed stopped")

    def start_camera_feed(self):
         """Starts camera feed for the selected client."""
         mw = self.main_window
         address = mw._get_selected_client_address()
         if address:
             logger.info(f"Starting camera feed for {mw.selected_client_addr_str}")
             if mw.server_core:
                 # Specify interval, default is often handled by client but can be explicit
                 success = mw.server_core.send_command(address, 'start_camera', {'interval': 100})
                 if success:
                     mw.start_camera_btn.setEnabled(False)
                     mw.stop_camera_btn.setEnabled(True)
                     mw.camera_label.setText("Starting camera feed...")
                     mw.camera_label.clear() # Clear previous image/text
                 else:
                      mw._show_message_box("Error", "Failed to send start camera command.", "warning")
             else:
                  logger.error("Server core unavailable.")
                  mw._show_message_box("Error", "Server connection lost.", "critical")
         else:
              mw._show_message_box("Action Failed", "No client selected.", "warning")

    def stop_camera_feed(self, force=False):
         """Stops camera feed for the selected client."""
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
             logger.info(f"Stopping camera feed for {addr_to_stop_tuple}")
             if mw.server_core:
                 mw.server_core.send_command(addr_to_stop_tuple, 'stop_camera')
             else:
                 logger.warning("Cannot send stop camera feed: Server core unavailable.")

         # Always update UI if a client was selected or forced
         if address or force:
             mw.start_camera_btn.setEnabled(True)
             mw.stop_camera_btn.setEnabled(False)
             mw.camera_label.setText("Camera feed stopped")
             mw.camera_label.clear() # Clear last frame 