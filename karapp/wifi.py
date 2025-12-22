from flask import Blueprint, render_template, request, redirect, url_for
import subprocess
import re
import time

connection_bp = Blueprint("wifi", __name__)

WIFI_INTERFACE = "wlan0"

@connection_bp.route("/wifi_settings")
def wifi_settings():
    networks = scan_wifi_networks()
    current_wifi = get_current_wifi()
    wifi_enabled = is_wifi_enabled()
    return render_template('wifi.html', networks=networks, current_wifi=current_wifi, wifi_enabled=wifi_enabled)

@connection_bp.route('/wifi/connect', methods=['POST'])
def wifi_connect():
    ssid = request.form.get('ssid')
    password = request.form.get('password')

    if not ssid:
        return redirect(url_for('wifi.wifi_settings'))

    success, message = connect_to_wifi(ssid, password)

    if success:
        return redirect(url_for('wifi.wifi_settings'))
    else:
        networks = scan_wifi_networks()
        current_wifi = get_current_wifi()
        wifi_enabled = is_wifi_enabled()
        return render_template('wifi.html', networks=networks, current_wifi=current_wifi, wifi_enabled=wifi_enabled, error=message)

@connection_bp.route('/wifi/toggle', methods=['POST'])
def wifi_toggle():
    """Active ou désactive le WiFi"""
    action = request.form.get('action')  # 'enable' ou 'disable'

    if action == 'enable':
        success, message = enable_wifi()
        # Attendre un peu plus après activation avant de scanner
        if success:
            time.sleep(2)
    elif action == 'disable':
        success, message = disable_wifi()
    else:
        return redirect(url_for('wifi.wifi_settings'))

    networks = scan_wifi_networks() if success and action == 'enable' else []
    current_wifi = get_current_wifi()
    wifi_enabled = is_wifi_enabled()

    if success:
        return render_template('wifi.html', networks=networks, current_wifi=current_wifi, wifi_enabled=wifi_enabled, success=message)
    else:
        return render_template('wifi.html', networks=networks, current_wifi=current_wifi, wifi_enabled=wifi_enabled, error=message)

def scan_wifi_networks():
    """Scanne les réseaux WiFi disponibles avec iwlist"""
    try:
        # Scanner les réseaux (essayer avec et sans sudo)
        try:
            result = subprocess.run(['sudo', 'iwlist', WIFI_INTERFACE, 'scan'],
                                  capture_output=True, text=True, timeout=15)
        except FileNotFoundError:
            result = subprocess.run(['iwlist', WIFI_INTERFACE, 'scan'],
                                  capture_output=True, text=True, timeout=15)

        if result.returncode != 0:
            return []

        networks = {}
        current_cell = {}

        for line in result.stdout.split('\n'):
            line = line.strip()

            # Nouvelle cellule (nouveau réseau)
            if line.startswith('Cell '):
                if current_cell.get('ssid'):
                    ssid = current_cell['ssid']
                    # Garder le meilleur signal pour chaque SSID
                    if ssid not in networks or current_cell['signal'] > networks[ssid]['signal']:
                        networks[ssid] = current_cell
                current_cell = {}

            # ESSID
            elif 'ESSID:' in line:
                match = re.search(r'ESSID:"([^"]+)"', line)
                if match:
                    current_cell['ssid'] = match.group(1)

            # Signal level
            elif 'Signal level=' in line:
                match = re.search(r'Signal level=(-?\d+)', line)
                if match:
                    dbm = int(match.group(1))
                    # Convertir dBm en pourcentage (approximation)
                    # -30 dBm = excellent (100%), -90 dBm = très faible (0%)
                    signal_percent = max(0, min(100, 2 * (dbm + 100)))
                    current_cell['signal'] = signal_percent

            # Encryption
            elif 'Encryption key:' in line:
                if 'on' in line.lower():
                    current_cell['encrypted'] = True
                else:
                    current_cell['encrypted'] = False

            # Type de sécurité
            elif 'IEEE 802.11i/WPA2' in line or 'WPA2' in line:
                current_cell['security'] = 'WPA2'
            elif 'WPA Version' in line or line.startswith('WPA:'):
                if 'security' not in current_cell:
                    current_cell['security'] = 'WPA'
            elif 'WEP' in line:
                if 'security' not in current_cell:
                    current_cell['security'] = 'WEP'

        # Ajouter la dernière cellule
        if current_cell.get('ssid'):
            ssid = current_cell['ssid']
            if ssid not in networks or current_cell['signal'] > networks[ssid]['signal']:
                networks[ssid] = current_cell

        # Formater les résultats
        result_list = []
        for cell in networks.values():
            if not cell.get('signal'):
                cell['signal'] = 50  # Valeur par défaut

            if cell.get('encrypted'):
                security = cell.get('security', 'WPA/WPA2')
                secured = True
            else:
                security = 'Open'
                secured = False

            result_list.append({
                'ssid': cell['ssid'],
                'signal': cell['signal'],
                'security': security,
                'secured': secured
            })

        return sorted(result_list, key=lambda x: x['signal'], reverse=True)

    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        return []
    except Exception as e:
        return []

def connect_to_wifi(ssid, password=None):
    """Se connecte à un réseau WiFi avec wpa_cli"""
    try:
        # Ajouter un nouveau réseau
        result = subprocess.run(['sudo', 'wpa_cli', '-i', WIFI_INTERFACE, 'add_network'],
                              capture_output=True, text=True, timeout=5)

        if result.returncode != 0:
            return False, "Impossible d'ajouter le réseau"

        # Récupérer l'ID du réseau créé
        network_id = result.stdout.strip()

        try:
            # Configurer le SSID
            subprocess.run(['sudo', 'wpa_cli', '-i', WIFI_INTERFACE, 'set_network',
                          network_id, 'ssid', f'"{ssid}"'],
                         capture_output=True, text=True, timeout=5, check=True)

            # Configurer la sécurité
            if password:
                # Réseau sécurisé
                subprocess.run(['sudo', 'wpa_cli', '-i', WIFI_INTERFACE, 'set_network',
                              network_id, 'psk', f'"{password}"'],
                             capture_output=True, text=True, timeout=5, check=True)
            else:
                # Réseau ouvert
                subprocess.run(['sudo', 'wpa_cli', '-i', WIFI_INTERFACE, 'set_network',
                              network_id, 'key_mgmt', 'NONE'],
                             capture_output=True, text=True, timeout=5, check=True)

            # Activer le réseau
            subprocess.run(['sudo', 'wpa_cli', '-i', WIFI_INTERFACE, 'enable_network', network_id],
                         capture_output=True, text=True, timeout=5, check=True)

            # Sauvegarder la configuration
            subprocess.run(['sudo', 'wpa_cli', '-i', WIFI_INTERFACE, 'save_config'],
                         capture_output=True, text=True, timeout=5)

            return True, f"Connexion au réseau {ssid} en cours..."

        except subprocess.CalledProcessError as e:
            # En cas d'erreur, supprimer le réseau créé
            subprocess.run(['sudo', 'wpa_cli', '-i', WIFI_INTERFACE, 'remove_network', network_id],
                         capture_output=True, text=True, timeout=5)
            return False, f"Erreur de configuration: {e.stderr if e.stderr else 'configuration invalide'}"

    except subprocess.TimeoutExpired:
        return False, "Délai d'attente dépassé"
    except FileNotFoundError:
        return False, "wpa_cli non disponible"
    except Exception as e:
        return False, f"Erreur: {str(e)}"

def get_current_wifi():
    """Récupère le réseau WiFi actuellement connecté"""
    try:
        # Essayer avec iwgetid (avec sudo)
        result = subprocess.run(['sudo', 'iwgetid', WIFI_INTERFACE, '-r'],
                              capture_output=True, text=True, timeout=5)

        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()

        # Si iwgetid ne fonctionne pas, essayer avec wpa_cli
        result = subprocess.run(['sudo', 'wpa_cli', '-i', WIFI_INTERFACE, 'status'],
                              capture_output=True, text=True, timeout=5)

        if result.returncode == 0:
            for line in result.stdout.split('\n'):
                if line.startswith('ssid='):
                    ssid = line.split('=', 1)[1].strip()
                    # Ignorer si le SSID est vide
                    if ssid:
                        return ssid

        # Dernière tentative : utiliser ip/iw pour vérifier la connexion
        result = subprocess.run(['iw', 'dev', WIFI_INTERFACE, 'link'],
                              capture_output=True, text=True, timeout=5)

        if result.returncode == 0:
            for line in result.stdout.split('\n'):
                if 'SSID:' in line:
                    ssid = line.split('SSID:', 1)[1].strip()
                    if ssid:
                        return ssid

        return None

    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None
    except Exception:
        return None

def is_wifi_enabled():
    """Vérifie si le WiFi est activé"""
    try:
        # Vérifier l'état de l'interface avec ip link
        result = subprocess.run(['ip', 'link', 'show', WIFI_INTERFACE],
                              capture_output=True, text=True, timeout=5)

        if result.returncode == 0:
            # Chercher "state UP" dans la sortie
            return 'state UP' in result.stdout

        return False
    except Exception:
        return False

def enable_wifi():
    """Active le WiFi"""
    try:
        # Activer l'interface
        result = subprocess.run(['sudo', 'ip', 'link', 'set', WIFI_INTERFACE, 'up'],
                              capture_output=True, text=True, timeout=10)

        if result.returncode == 0:
            # Attendre que l'interface soit prête
            time.sleep(3)
            # Relancer wpa_supplicant pour qu'il se reconnecte
            subprocess.run(['sudo', 'wpa_cli', '-i', WIFI_INTERFACE, 'reconfigure'],
                         capture_output=True, text=True, timeout=5)
            # Attendre encore un peu pour la connexion
            time.sleep(2)
            return True, "WiFi activé - Reconnexion en cours..."
        else:
            return False, f"Erreur d'activation: {result.stderr}"
    except Exception as e:
        return False, f"Erreur: {str(e)}"

def disable_wifi():
    """Désactive le WiFi"""
    try:
        # Désactiver l'interface
        result = subprocess.run(['sudo', 'ip', 'link', 'set', WIFI_INTERFACE, 'down'],
                              capture_output=True, text=True, timeout=10)

        if result.returncode == 0:
            return True, "WiFi désactivé"
        else:
            return False, f"Erreur de désactivation: {result.stderr}"
    except Exception as e:
        return False, f"Erreur: {str(e)}"
