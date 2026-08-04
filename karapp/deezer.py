"""Intégration Deezer sans clé API.

La recherche passe par l'API publique `api.deezer.com` (aucune clé requise), mais
proxifiée ici côté serveur : le navigateur ne peut pas l'interroger directement
(pas d'en-têtes CORS). Les éléments enregistrés sont stockés dans la table
`DeezerItem` (pochette en base64). La lecture se fait via le widget officiel
Deezer (`widget.deezer.com`) embarqué en iframe — voir `deezer_widget.html`.
"""
from flask import Blueprint, render_template, request, jsonify, abort
import requests

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
    return jsonify({"results": results})


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
    """Page de lecture : embarque le widget officiel Deezer pour cet élément."""
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