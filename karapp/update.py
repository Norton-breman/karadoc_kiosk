"""
Mise à jour de l'application depuis GitHub, sans passer par SSH.

Deux routes :
- GET  /update/check  : vérifie (git fetch) si des commits sont disponibles.
- POST /update/apply  : applique la mise à jour (git pull) et réinstalle les
                        dépendances si besoin.

Aucun redémarrage forcé : en mode debug le reloader de Werkzeug recharge
automatiquement le code Python modifié par le git pull.
"""
import os
import subprocess
from pathlib import Path

from flask import Blueprint, jsonify

update_bp = Blueprint("update", __name__)

# Racine du dépôt git = dossier contenant app.py (un niveau au-dessus de karapp/)
PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)


def _run_git(args, timeout=30):
    """Exécute une commande git dans le dossier du projet.

    Retourne un tuple (returncode, stdout, stderr).
    """
    try:
        result = subprocess.run(
            ['git'] + args,
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return result.returncode, result.stdout.strip(), result.stderr.strip()
    except subprocess.TimeoutExpired:
        return -1, "", "Délai d'attente dépassé"
    except FileNotFoundError:
        return -1, "", "git non disponible"
    except Exception as e:
        return -1, "", str(e)


def get_update_status():
    """Interroge GitHub et indique si une mise à jour est disponible."""
    # Récupérer les dernières références distantes (nécessite le réseau)
    code, _, err = _run_git(['fetch', '--quiet'], timeout=30)
    if code != 0:
        return {"success": False, "error": err or "Échec de la vérification (hors ligne ?)"}

    # Commit local courant (forme courte)
    _, current, _ = _run_git(['rev-parse', '--short', 'HEAD'])

    # Nombre de commits de retard par rapport à la branche suivie (@{u})
    code, behind_str, err = _run_git(['rev-list', '--count', 'HEAD..@{u}'])
    if code != 0:
        return {"success": False, "error": err or "Impossible de comparer les versions"}
    try:
        behind = int(behind_str)
    except ValueError:
        behind = 0

    # Sujets des nouveaux commits (au plus 10)
    commits = []
    if behind > 0:
        _, log_out, _ = _run_git(['log', '--pretty=format:%s', 'HEAD..@{u}'])
        commits = [line for line in log_out.split('\n') if line][:10]

    return {
        "success": True,
        "update_available": behind > 0,
        "behind": behind,
        "current": current,
        "commits": commits,
    }


@update_bp.route('/update/check')
def update_check():
    return jsonify(get_update_status())


@update_bp.route('/update/apply', methods=['POST'])
def update_apply():
    req_path = os.path.join(PROJECT_ROOT, 'requirements.txt')

    def _read_req():
        try:
            with open(req_path, 'r', encoding='utf-8') as f:
                return f.read()
        except OSError:
            return None

    req_before = _read_req()

    # Mise à jour du code : fast-forward uniquement, pour ne jamais créer de
    # commit de merge ni laisser un conflit sur l'appareil.
    code, out, err = _run_git(['pull', '--ff-only'], timeout=120)
    if code != 0:
        return jsonify({"success": False, "error": err or out or "Échec du git pull"}), 500

    # Réinstaller les dépendances uniquement si requirements.txt a changé
    deps_updated = False
    if _read_req() != req_before:
        try:
            pip = subprocess.run(
                [sys.executable, '-m', 'pip', 'install', '-r', req_path],
                cwd=PROJECT_ROOT, capture_output=True, text=True, timeout=300,
            )
            if pip.returncode != 0:
                return jsonify({
                    "success": False,
                    "error": "Code mis à jour, mais échec de l'installation des dépendances : "
                             + (pip.stderr.strip() or "erreur inconnue"),
                }), 500
            deps_updated = True
        except subprocess.TimeoutExpired:
            return jsonify({
                "success": False,
                "error": "Délai dépassé lors de l'installation des dépendances",
            }), 500

    return jsonify({
        "success": True,
        "deps_updated": deps_updated,
        "message": "Mise à jour appliquée.",
    })