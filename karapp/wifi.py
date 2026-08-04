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
    """Scanne les réseaux WiFi disponibles via wpa_cli.

    On NE se sert PLUS de `iwlist scan` : cet outil entre en conflit avec le
    wpa_supplicant déjà lancé pour wlan0 (via /etc/network/interfaces) et
    renvoie une liste vide. On demande donc le scan à wpa_supplicant lui-même
    (`wpa_cli scan`) puis on lit ses résultats (`wpa_cli scan_results`).
    """
    try:
        # Déclencher un nouveau scan (peut répondre FAIL-BUSY si un scan est
        # déjà en cours : ce n'est pas bloquant, on lira les résultats quand même).
        subprocess.run(['sudo', 'wpa_cli', '-i', WIFI_INTERFACE, 'scan'],
                       capture_output=True, text=True, timeout=10)

        # Laisser le temps au scan de se terminer avant de lire les résultats.
        time.sleep(2)

        result = subprocess.run(['sudo', 'wpa_cli', '-i', WIFI_INTERFACE, 'scan_results'],
                                capture_output=True, text=True, timeout=10)

        if result.returncode != 0:
            return []

        networks = {}

        # Format des lignes (séparées par des tabulations) :
        # bssid / frequency / signal level / flags / ssid
        # 10:d7:b0:20:1b:b2   2462   -80   [WPA2-PSK-CCMP][WPS][ESS]   Livebox-1BB2
        for line in result.stdout.split('\n'):
            line = line.rstrip('\n')
            # Sauter l'en-tête et les lignes vides
            if not line or line.startswith('bssid'):
                continue

            parts = line.split('\t')
            if len(parts) < 5:
                continue

            flags = parts[3]
            ssid = parts[4].strip()

            # Ignorer les réseaux masqués (SSID vide)
            if not ssid:
                continue

            # Convertir le signal (dBm) en pourcentage approximatif
            # -30 dBm = excellent (100%), -90 dBm = très faible (0%)
            try:
                dbm = int(parts[2])
            except ValueError:
                dbm = -80
            signal_percent = max(0, min(100, 2 * (dbm + 100)))

            # Déterminer la sécurité à partir des flags
            if 'WPA2' in flags:
                security = 'WPA2'
                secured = True
            elif 'WPA' in flags:
                security = 'WPA'
                secured = True
            elif 'WEP' in flags:
                security = 'WEP'
                secured = True
            else:
                security = 'Open'
                secured = False

            cell = {
                'ssid': ssid,
                'signal': signal_percent,
                'security': security,
                'secured': secured,
            }

            # Garder le meilleur signal pour chaque SSID
            if ssid not in networks or signal_percent > networks[ssid]['signal']:
                networks[ssid] = cell

        return sorted(networks.values(), key=lambda x: x['signal'], reverse=True)

    except (subprocess.TimeoutExpired, FileNotFoundError):
        return []
    except Exception:
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
    """Vérifie si la radio WiFi est activée.

    On NE se base PAS sur l'état opérationnel ('state UP') : celui-ci n'est vrai
    que lorsque l'interface est associée à un point d'accès. Hors de tout réseau
    connu, l'interface reste 'DORMANT'/'DOWN' alors que la radio est bien active,
    ce qui faisait croire à tort que le WiFi était désactivé.
    """
    # 1) Méthode préférée : rfkill donne l'état réel de la radio,
    #    indépendamment de toute connexion à un réseau.
    try:
        result = subprocess.run(['rfkill', 'list', 'wifi'],
                              capture_output=True, text=True, timeout=5)
        if result.returncode == 0 and result.stdout.strip():
            found = False
            blocked = False
            for line in result.stdout.split('\n'):
                line = line.strip().lower()
                if 'blocked:' in line:
                    found = True
                    if line.endswith('yes'):
                        blocked = True
            if found:
                return not blocked
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    except Exception:
        pass

    # 2) Repli : chercher le flag administratif 'UP' dans les <flags> de
    #    l'interface (et NON 'state UP', qui dépend de l'association réseau).
    try:
        result = subprocess.run(['ip', 'link', 'show', WIFI_INTERFACE],
                              capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            match = re.search(r'<([^>]*)>', result.stdout)
            if match:
                flags = match.group(1).split(',')
                return 'UP' in flags
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
