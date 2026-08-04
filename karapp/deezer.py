"""Intégration Deezer sans clé API.

La recherche passe par l'API publique `api.deezer.com` (aucune clé requise), mais
proxifiée ici côté serveur : le navigateur ne peut pas l'interroger directement
(pas d'en-têtes CORS). Les éléments enregistrés sont stockés dans la table
`DeezerItem` (pochette en base64). La lecture se fait via le widget officiel
Deezer (`widget.deezer.com`) embarqué en iframe — voir `deezer_widget.html`.
"""
from flask import Blueprint, render_template, request, jsonify, abort, redirect
import requests
import subprocess
import os

from karapp.models import db, DeezerItem
from karapp.tools.photo import make_artwork_base64

deezer_bp = Blueprint("deezer", __name__)

# Types de contenu supportés à la fois par l'API de recherche et le widget.
SEARCH_TYPES = ["track", "album", "playlist", "artist"]

# Libellés français des sections (une par type).
TYPE_LABELS = {
    "track": "Titres",
    "album": "Albums",
    "playlist": "Playlists",
    "artist": "Artistes",
}


@deezer_bp.route("/deezer")
def deezer():
    """Accueil Deezer : la carte Recherche + une carte par type enregistrable."""
    return render_template("deezer.html", types=SEARCH_TYPES, labels=TYPE_LABELS)


@deezer_bp.route("/deezer/recherche")
def deezer_recherche():
    """Page de recherche live (le JS interroge /deezer/search)."""
    return render_template("deezer_search.html", types=SEARCH_TYPES, labels=TYPE_LABELS)


@deezer_bp.route("/deezer/keyboard", methods=["POST"])
def deezer_keyboard():
    """Lance le clavier tactile système (matchbox-keyboard) par-dessus Chromium.

    Nécessaire pour saisir sur les pages externes (login Deezer) où le clavier
    virtuel de Karadoc — injecté uniquement dans ses propres pages — n'existe pas.
    Kiosque Linux uniquement ; échoue proprement ailleurs (dev Windows).
    """
    env = dict(os.environ)
    env.setdefault("DISPLAY", ":0")
    # Layout maison épuré (AZERTY + chiffres + symboles utiles) livré dans le
    # repo ; chargé via MB_KBD_CONFIG (aucun sudo, déployé par git pull). Les
    # layouts stock sont soit trop pauvres (défaut = lettres seules) soit trop
    # chargés (lq1 = symboles maths/scandinaves, pas d'underscore).
    env["MB_KBD_CONFIG"] = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "static", "matchbox", "keyboard-karadoc.xml",
    )
    try:
        # Éviter d'empiler plusieurs instances. NB : on matche sur la ligne de
        # commande (-f) et non le nom (-x) car Linux tronque le nom de process à
        # 15 car. ("matchbox-keyboa") → un `-x matchbox-keyboard` ne matcherait
        # jamais et relancerait un clavier à chaque appel.
        running = subprocess.run(["pgrep", "-f", "matchbox-keyboard"],
                                 capture_output=True)
        if running.returncode != 0:
            subprocess.Popen(
                ["matchbox-keyboard"], env=env,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
    except FileNotFoundError:
        return jsonify({"success": False, "error": "Clavier tactile indisponible"})
    except Exception:
        return jsonify({"success": False, "error": "Impossible de lancer le clavier"})

    # Sans gestionnaire de fenêtres, matchbox-keyboard s'ouvre petit en haut à
    # gauche. Sa fenêtre s'appelle "Keyboard" et n'a pas de WM_CLASS → on la
    # cible par --name. On force sa géométrie : bas de l'écran, pleine largeur,
    # hauteur 240 px (le layout complet lq1 a plusieurs rangées) → les touches
    # s'agrandissent pour remplir. Écran 320x480 → position (0, 240), taille 320x240.
    try:
        subprocess.run(
            ["xdotool", "search", "--sync", "--name", "Keyboard",
             "windowmove", "0", "240", "windowsize", "320", "240"],
            env=env, capture_output=True, timeout=10,
        )
    except Exception:
        # xdotool absent ou fenêtre introuvable : le clavier reste utilisable
        # à sa taille/position par défaut.
        pass

    return jsonify({"success": True})


@deezer_bp.route("/deezer/keyboard/hide", methods=["POST"])
def deezer_keyboard_hide():
    """Ferme le clavier tactile système s'il est ouvert."""
    try:
        # -f (ligne de commande) et non -x : le nom de process est tronqué à
        # 15 car. ("matchbox-keyboa"), donc -x matchbox-keyboard ne matcherait pas.
        subprocess.run(["pkill", "-f", "matchbox-keyboard"], capture_output=True)
    except Exception:
        pass
    return jsonify({"success": True})


@deezer_bp.route("/deezer/search")
def deezer_search():
    """Recherche dans le catalogue Deezer, renvoie une liste normalisée (JSON).

    Paramètres : q (mots-clés), type (track|album|playlist|artist, défaut track).
    """
    query = (request.args.get("q") or "").strip()
    search_type = request.args.get("type", "track")
    if search_type not in SEARCH_TYPES:
        search_type = "track"

    if not query:
        return jsonify({"results": []})

    try:
        response = requests.get(
            f"https://api.deezer.com/search/{search_type}",
            params={"q": query, "limit": 25},
            timeout=10,
        )
        response.raise_for_status()
        data = response.json()
    except requests.RequestException:
        return jsonify({"error": "Impossible de contacter Deezer"}), 502
    except ValueError:
        return jsonify({"error": "Réponse Deezer invalide"}), 502

    results = [normalize_item(item, search_type) for item in data.get("data", [])]
    results = [r for r in results if r]

    # Deezer compare `q` au titre ET à d'autres champs (p. ex. le propriétaire
    # d'une playlist) : on re-classe pour faire remonter les éléments dont le
    # TITRE correspond le mieux à la recherche, sans en supprimer aucun.
    results.sort(key=lambda r: title_relevance(r.get("title", ""), query), reverse=True)

    return jsonify({"results": results})


def title_relevance(title, query):
    """Score de correspondance entre un titre et la recherche (plus haut = mieux).
    2 = le titre contient toute la requête ; sinon nombre de mots de la requête
    présents dans le titre."""
    title_l = (title or "").lower()
    query_l = (query or "").lower().strip()
    if not query_l:
        return 0
    if query_l in title_l:
        return 2
    words = [w for w in query_l.split() if w]
    return sum(1 for w in words if w in title_l) / (len(words) or 1)


@deezer_bp.route("/deezer/save", methods=["POST"])
def deezer_save():
    """Enregistre un élément Deezer en base (pochette téléchargée en base64)."""
    payload = request.get_json(silent=True) or {}
    deezer_id = str(payload.get("deezer_id") or "").strip()
    item_type = payload.get("type")
    title = payload.get("title") or ""
    subtitle = payload.get("subtitle") or ""
    cover_url = payload.get("cover") or ""

    if not deezer_id or item_type not in SEARCH_TYPES:
        return jsonify({"error": "Élément invalide"}), 400

    # Déjà enregistré ?
    existing = DeezerItem.query.filter_by(deezer_id=deezer_id, type=item_type).first()
    if existing:
        return jsonify({"success": True, "already": True,
                        "message": "Déjà dans ta bibliothèque."})

    # Télécharger et encoder la pochette (comme les artworks du FileModel).
    artwork = None
    if cover_url:
        try:
            artwork = make_artwork_base64(cover_url)
        except Exception:
            artwork = None

    item = DeezerItem(
        deezer_id=deezer_id,
        type=item_type,
        title=title,
        subtitle=subtitle,
        artwork=artwork,
    )
    db.session.add(item)
    db.session.commit()

    return jsonify({"success": True, "already": False,
                    "message": "Ajouté à ta bibliothèque Deezer."})


@deezer_bp.route("/deezer/section/<item_type>")
def deezer_section(item_type):
    """Grille des éléments enregistrés d'un type donné."""
    if item_type not in SEARCH_TYPES:
        abort(404)
    items = DeezerItem.query.filter_by(type=item_type).order_by(DeezerItem.title).all()
    return render_template(
        "deezer_section.html",
        items=items,
        item_type=item_type,
        label=TYPE_LABELS[item_type],
    )


@deezer_bp.route("/deezer/play/<item_type>/<deezer_id>")
def deezer_play(item_type, deezer_id):
    """Lecture via le widget officiel Deezer embarqué (léger, rapide sur le RPi).

    NB : le widget en iframe cross-site ne voyait pas la session (partitionnement
    du stockage + SameSite). On teste des flags Chromium de compat
    (--disable-features=ThirdPartyStoragePartitioning,PartitionedCookies + policy
    CookiesAllowedForUrls) pour lui redonner accès au compte. Si ça échoue,
    revenir à une redirection vers le lecteur web `deezer.com/<type>/<id>`.
    """
    if item_type not in SEARCH_TYPES:
        abort(404)
    title = request.args.get("title", "")
    widget_url = f"https://widget.deezer.com/widget/dark/{item_type}/{deezer_id}"
    return render_template("deezer_widget.html", widget_url=widget_url, title=title)


@deezer_bp.route("/deezer/delete/<int:item_id>", methods=["POST"])
def deezer_delete(item_id):
    """Supprime un élément enregistré."""
    item = DeezerItem.query.get_or_404(item_id)
    item_type = item.type
    db.session.delete(item)
    db.session.commit()
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return jsonify({"success": True})
    return render_template(
        "deezer_section.html",
        items=DeezerItem.query.filter_by(type=item_type).order_by(DeezerItem.title).all(),
        item_type=item_type,
        label=TYPE_LABELS[item_type],
    )


def normalize_item(item, search_type):
    """Ramène les formats Deezer à une structure commune pour le front :
    {id, type, title, subtitle, cover}."""
    try:
        if search_type == "track":
            return {
                "id": item["id"],
                "type": "track",
                "title": item.get("title", ""),
                "subtitle": item.get("artist", {}).get("name", ""),
                "cover": item.get("album", {}).get("cover_medium", ""),
            }
        if search_type == "album":
            return {
                "id": item["id"],
                "type": "album",
                "title": item.get("title", ""),
                "subtitle": item.get("artist", {}).get("name", ""),
                "cover": item.get("cover_medium", ""),
            }
        if search_type == "playlist":
            nb = item.get("nb_tracks")
            owner = item.get("user", {}).get("name", "")
            subtitle = f"{nb} titres" if nb else ""
            if owner:
                subtitle = f"{subtitle} · {owner}" if subtitle else owner
            return {
                "id": item["id"],
                "type": "playlist",
                "title": item.get("title", ""),
                "subtitle": subtitle,
                "cover": item.get("picture_medium", ""),
            }
        if search_type == "artist":
            return {
                "id": item["id"],
                "type": "artist",
                "title": item.get("name", ""),
                "subtitle": "Artiste",
                "cover": item.get("picture_medium", ""),
            }
    except (KeyError, TypeError, AttributeError):
        return None
    return None