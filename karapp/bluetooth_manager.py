"""
Gestionnaire Bluetooth utilisant bluetoothctl en ligne de commande
"""
import subprocess
import time
import re
import threading


class BluetoothManager:
    """Gestionnaire Bluetooth utilisant bluetoothctl"""

    def __init__(self):
        """Initialise le gestionnaire Bluetooth"""
        self.scan_process = None
        self.scan_lock = threading.Lock()
        self.debug_logs = []

    def _run_bluetoothctl_command(self, command, timeout=10):
        """
        Exécute une commande bluetoothctl

        Args:
            command: Liste des arguments de la commande
            timeout: Timeout en secondes

        Returns:
            Tuple (returncode, stdout, stderr)
        """
        try:
            result = subprocess.run(
                ['bluetoothctl'] + command,
                capture_output=True,
                text=True,
                timeout=timeout
            )
            return result.returncode, result.stdout, result.stderr
        except subprocess.TimeoutExpired:
            return -1, "", "Timeout"
        except Exception as e:
            return -1, "", str(e)

    def scan_devices(self, duration=5):
        """
        Scanne les périphériques Bluetooth disponibles (Classic + BLE)

        Args:
            duration: Durée du scan en secondes (défaut: 5)

        Returns:
            Liste de dictionnaires contenant les infos des périphériques
        """
        devices_dict = {}
        self.debug_logs = []

        try:
            with self.scan_lock:
                # 1. Scanner les appareils Bluetooth LE avec hcitool
                self.debug_logs.append("=== DEBUT SCAN BLUETOOTH ===")
                self.debug_logs.append("Scan BLE avec hcitool...")
                lescan_process = subprocess.Popen(
                    ['sudo', 'hcitool', 'lescan'],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True
                )
                self.debug_logs.append(f"Process hcitool lancé: PID {lescan_process.pid}")

                # 2. Scanner les appareils Bluetooth Classic avec bluetoothctl
                self.debug_logs.append("Scan Classic avec bluetoothctl...")
                subprocess.Popen(
                    ['bluetoothctl', 'scan', 'on'],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )

                # Attendre que les scans trouvent des appareils
                self.debug_logs.append(f"Attente de {duration} secondes...")
                time.sleep(duration)

                # Arrêter le scan BLE
                self.debug_logs.append("Arrêt du scan BLE...")
                lescan_process.terminate()
                try:
                    lescan_stdout, lescan_stderr = lescan_process.communicate(timeout=2)
                    self.debug_logs.append(f"Sortie hcitool: {len(lescan_stdout)} caractères")
                    if lescan_stderr:
                        self.debug_logs.append(f"Erreurs hcitool: {lescan_stderr}")
                except:
                    lescan_process.kill()
                    lescan_stdout = ""
                    self.debug_logs.append("Timeout hcitool, processus tué")

                # Arrêter le scan Classic
                subprocess.run(
                    ['bluetoothctl', 'scan', 'off'],
                    capture_output=True,
                    timeout=5
                )

            # Parser les résultats du scan BLE (hcitool lescan)
            for line in lescan_stdout.split('\n'):
                # Format: "MAC_ADDRESS Name" ou "MAC_ADDRESS (unknown)"
                match = re.match(r'([\w:]{17})\s+(.+)', line.strip())
                if match:
                    mac = match.group(1)
                    name = match.group(2)
                    if name and name != '(unknown)' and mac not in devices_dict:
                        devices_dict[mac] = {'mac': mac, 'name': name, 'type': 'BLE'}

            # Récupérer aussi la liste des appareils via bluetoothctl
            returncode, stdout, stderr = self._run_bluetoothctl_command(['devices'])

            if returncode == 0:
                # Parser les appareils (format: "Device MAC_ADDRESS Name")
                for line in stdout.strip().split('\n'):
                    if line.startswith('Device '):
                        match = re.match(r'Device\s+([\w:]+)\s+(.+)', line)
                        if match:
                            mac = match.group(1)
                            name = match.group(2)
                            if mac not in devices_dict:
                                devices_dict[mac] = {'mac': mac, 'name': name, 'type': 'Classic'}

            # Obtenir les infos détaillées pour chaque appareil
            self.debug_logs.append(f"Appareils trouvés dans dictionnaire: {len(devices_dict)}")
            for mac, info in devices_dict.items():
                self.debug_logs.append(f"  - {mac}: {info['name']} ({info['type']})")

            devices = []
            for mac, info in devices_dict.items():
                device_info = self._get_device_info(mac, info['name'])
                if device_info:
                    devices.append(device_info)
                else:
                    # Si bluetoothctl ne connaît pas l'appareil, retourner les infos basiques
                    devices.append({
                        'mac': mac,
                        'name': info['name'],
                        'connected': False,
                        'paired': False,
                        'trusted': False,
                        'device_type': 'audio' if 'BLE' in info['type'] else 'unknown'
                    })

            self.debug_logs.append(f"=== FIN SCAN: {len(devices)} appareils retournés ===")
            return devices

        except Exception as e:
            self.debug_logs.append(f"ERREUR lors du scan Bluetooth: {e}")
            import traceback
            self.debug_logs.append(traceback.format_exc())
            # Essayer d'arrêter les scans en cas d'erreur
            try:
                subprocess.run(['bluetoothctl', 'scan', 'off'], timeout=2)
                subprocess.run(['sudo', 'pkill', 'hcitool'], timeout=2)
            except:
                pass
            return []

    def _get_device_info(self, mac, name):
        """
        Récupère les informations détaillées d'un appareil

        Args:
            mac: Adresse MAC de l'appareil
            name: Nom de l'appareil

        Returns:
            Dictionnaire avec les infos de l'appareil ou None
        """
        try:
            returncode, stdout, stderr = self._run_bluetoothctl_command(['info', mac])

            if returncode != 0:
                return None

            # Parser les informations
            connected = 'Connected: yes' in stdout
            paired = 'Paired: yes' in stdout
            trusted = 'Trusted: yes' in stdout

            # Déterminer le type d'appareil
            device_type = 'unknown'
            if 'UUID: Audio' in stdout or '0000110b' in stdout.lower():
                device_type = 'audio'
            elif 'UUID: Human Interface Device' in stdout or '00001124' in stdout.lower():
                device_type = 'input'

            return {
                'mac': mac,
                'name': name,
                'connected': connected,
                'paired': paired,
                'trusted': trusted,
                'device_type': device_type
            }

        except Exception as e:
            print(f"Erreur lors de la récupération des infos de {mac}: {e}")
            return None

    def pair_device(self, mac_address):
        """
        Appaire un périphérique Bluetooth

        Args:
            mac_address: Adresse MAC du périphérique

        Returns:
            Tuple (success: bool, message: str)
        """
        try:
            # Vérifier si déjà appairé
            returncode, stdout, stderr = self._run_bluetoothctl_command(['info', mac_address])

            if 'Paired: yes' in stdout:
                # Faire confiance au périphérique
                self._run_bluetoothctl_command(['trust', mac_address])
                return True, "Périphérique déjà appairé"

            # Appairer
            returncode, stdout, stderr = self._run_bluetoothctl_command(['pair', mac_address], timeout=30)

            if returncode == 0 or 'Pairing successful' in stdout:
                # Faire confiance au périphérique
                self._run_bluetoothctl_command(['trust', mac_address])
                return True, "Appairage réussi"
            else:
                return False, f"Erreur d'appairage: {stderr}"

        except Exception as e:
            return False, f"Erreur: {str(e)}"

    def connect_device(self, mac_address):
        """
        Se connecte à un périphérique Bluetooth

        Args:
            mac_address: Adresse MAC du périphérique

        Returns:
            Tuple (success: bool, message: str)
        """
        try:
            # Vérifier si déjà connecté
            returncode, stdout, stderr = self._run_bluetoothctl_command(['info', mac_address])

            if 'Connected: yes' in stdout:
                return True, "Périphérique déjà connecté"

            # Se connecter
            returncode, stdout, stderr = self._run_bluetoothctl_command(['connect', mac_address], timeout=30)

            if returncode == 0 or 'Connection successful' in stdout:
                return True, "Connexion réussie"
            else:
                return False, f"Erreur de connexion: {stderr}"

        except Exception as e:
            return False, f"Erreur: {str(e)}"

    def disconnect_device(self, mac_address):
        """
        Se déconnecte d'un périphérique Bluetooth

        Args:
            mac_address: Adresse MAC du périphérique

        Returns:
            Tuple (success: bool, message: str)
        """
        try:
            returncode, stdout, stderr = self._run_bluetoothctl_command(['disconnect', mac_address])

            if returncode == 0 or 'Successful disconnected' in stdout:
                return True, "Déconnexion réussie"
            else:
                return False, f"Erreur de déconnexion: {stderr}"

        except Exception as e:
            return False, f"Erreur: {str(e)}"

    def remove_device(self, mac_address):
        """
        Supprime un périphérique Bluetooth (unpair)

        Args:
            mac_address: Adresse MAC du périphérique

        Returns:
            Tuple (success: bool, message: str)
        """
        try:
            returncode, stdout, stderr = self._run_bluetoothctl_command(['remove', mac_address])

            if returncode == 0 or 'Device has been removed' in stdout:
                return True, "Périphérique supprimé"
            else:
                return False, f"Erreur de suppression: {stderr}"

        except Exception as e:
            return False, f"Erreur: {str(e)}"

    def get_connected_devices(self):
        """
        Récupère la liste des périphériques connectés

        Returns:
            Liste de dictionnaires contenant les infos des périphériques connectés
        """
        connected_devices = []

        try:
            # Récupérer tous les appareils
            returncode, stdout, stderr = self._run_bluetoothctl_command(['devices'])

            if returncode != 0:
                return []

            # Parser les appareils
            for line in stdout.strip().split('\n'):
                if line.startswith('Device '):
                    match = re.match(r'Device\s+([\w:]+)\s+(.+)', line)
                    if match:
                        mac = match.group(1)
                        name = match.group(2)

                        # Vérifier si connecté
                        device_info = self._get_device_info(mac, name)
                        if device_info and device_info['connected']:
                            connected_devices.append(device_info)

            return connected_devices

        except Exception as e:
            print(f"Erreur lors de la récupération des appareils connectés: {e}")
            return []
