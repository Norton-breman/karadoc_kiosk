from flask import Blueprint, render_template, request, redirect, url_for
import subprocess
import re

connection_bp = Blueprint("wifi", __name__)

@connection_bp.route("/wifi_settings")
def wifi_settings():
    networks = scan_wifi_networks()
    current_wifi = get_current_wifi()
    return render_template('wifi.html', networks=networks, current_wifi=current_wifi)

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
        return render_template('wifi.html', networks=networks, current_wifi=current_wifi, error=message)

def scan_wifi_networks():
    """Scanne les réseaux WiFi disponibles avec ConnMan"""
    try:
        # Scanner les réseaux disponibles
        result = subprocess.run(['connmanctl', 'services'],
                              capture_output=True, text=True, timeout=10)

        if result.returncode != 0:
            return []

        networks = {}
        lines = result.stdout.strip().split('\n')

        for line in lines:
            # Format: "*AO MyNetwork    wifi_abc123_managed_psk"
            # Le premier caractère peut être '*' (connecté), ' ' (disponible)
            match = re.match(r'^[\*\s][\w\s]*\s+([\w\-]+)\s+(wifi_\w+)$', line)
            if match:
                ssid = match.group(1).strip()
                service_id = match.group(2)

                if ssid and service_id:
                    # Déterminer le type de sécurité depuis le service_id
                    if '_none' in service_id or '_open' in service_id:
                        security = 'Open'
                        secured = False
                    elif '_psk' in service_id or '_wpa' in service_id:
                        security = 'WPA/WPA2'
                        secured = True
                    elif '_wep' in service_id:
                        security = 'WEP'
                        secured = True
                    else:
                        security = 'Secured'
                        secured = True

                    # Obtenir la force du signal
                    signal = get_signal_strength(service_id)

                    # Garder le meilleur signal pour chaque SSID
                    if ssid not in networks or signal > networks[ssid]['signal']:
                        networks[ssid] = {
                            'ssid': ssid,
                            'service_id': service_id,
                            'signal': signal,
                            'security': security,
                            'secured': secured
                        }

        return sorted(networks.values(), key=lambda x: x['signal'], reverse=True)

    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        return []

def get_signal_strength(service_id):
    """Récupère la force du signal pour un service donné"""
    try:
        result = subprocess.run(['connmanctl', 'services', service_id],
                              capture_output=True, text=True, timeout=5)

        # Chercher la ligne Strength
        for line in result.stdout.split('\n'):
            if 'Strength' in line:
                match = re.search(r'Strength\s*=\s*(\d+)', line)
                if match:
                    return int(match.group(1))

        # Par défaut, retourner 50
        return 50
    except:
        return 50

def connect_to_wifi(ssid, password=None):
    """Se connecte à un réseau WiFi avec ConnMan"""
    try:
        # D'abord, trouver le service_id correspondant au SSID
        result = subprocess.run(['connmanctl', 'services'],
                              capture_output=True, text=True, timeout=10)

        if result.returncode != 0:
            return False, "Impossible de lister les réseaux"

        service_id = None
        for line in result.stdout.strip().split('\n'):
            if ssid in line:
                match = re.search(r'(wifi_\w+)', line)
                if match:
                    service_id = match.group(1)
                    break

        if not service_id:
            return False, f"Réseau {ssid} introuvable"

        # Se connecter au réseau
        if password:
            # Créer un fichier de configuration temporaire pour le mot de passe
            # ConnMan nécessite une interaction pour le mot de passe
            # On utilise l'approche avec echo et pipe
            cmd = f'printf "%s\\n" "{password}" | connmanctl connect {service_id}'
            result = subprocess.run(cmd, shell=True, capture_output=True,
                                  text=True, timeout=30)
        else:
            # Réseau ouvert
            result = subprocess.run(['connmanctl', 'connect', service_id],
                                  capture_output=True, text=True, timeout=30)

        if result.returncode == 0 or 'Connected' in result.stdout:
            return True, f"Connecté au réseau {ssid}"
        else:
            error_msg = result.stderr.strip() if result.stderr else result.stdout.strip()
            return False, f"Erreur de connexion: {error_msg}"

    except subprocess.TimeoutExpired:
        return False, "Délai d'attente dépassé"
    except FileNotFoundError:
        return False, "ConnMan non disponible"
    except Exception as e:
        return False, f"Erreur: {str(e)}"

def get_current_wifi():
    """Récupère le réseau WiFi actuellement connecté"""
    try:
        result = subprocess.run(['connmanctl', 'services'],
                              capture_output=True, text=True, timeout=5)

        if result.returncode != 0:
            return None

        # Chercher la ligne avec '*' (connecté) ou '*A' (auto-connecté)
        for line in result.stdout.strip().split('\n'):
            if line.startswith('*'):
                # Extraire le SSID de la ligne
                match = re.match(r'^\*[\w\s]*\s+([\w\-]+)\s+wifi_', line)
                if match:
                    return match.group(1).strip()

        return None

    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None
