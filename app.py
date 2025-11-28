import os
from dotenv import load_dotenv
from pathlib import Path
import requests
from threading import Thread
import uuid

from flask import Flask, render_template, redirect, url_for, request, send_from_directory, jsonify
from werkzeug.utils import secure_filename

from karapp.wifi import connection_bp, get_current_wifi
from karapp.bluetooth import  bluetooth_bp, get_connected_bluetooth_devices
from karapp.models import db, FileModel
from karapp.tools.music import get_metadata
from karapp.tools.photo import make_artwork_base64
from karapp.tools import rss

load_dotenv()

DATA_PATH = os.getenv('DATA_PATH')
DB_PATH = os.path.join(os.getenv('DB_PATH'), 'karapp.db')

tasks_progress = {}

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///'+DB_PATH
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.register_blueprint(connection_bp)
app.register_blueprint(bluetooth_bp)

db.init_app(app)

# if not os.path.exists(DB_PATH):
with app.app_context():
    # db.drop_all()
    db.create_all()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/parameters')
def parametres():
    current_wifi = get_current_wifi()
    connected_bluetooth = get_connected_bluetooth_devices()
    return render_template('parameters.html', current_wifi=current_wifi, connected_bluetooth=connected_bluetooth)

@app.route('/sync_db', endpoint='db_sync')
def synd_db():
    for each in ['photo', 'musique']:
        p = Path(DATA_PATH)/each
        # ajouter les nouveaux fichiers
        for f in p.rglob('*'):
            model = FileModel.query.filter_by(path=str(f)).all()
            if len(model)==0:
                artwork = None
                name = None
                artist = None
                album = None
                if f.is_file():
                    ftype = 'file'
                    if each == 'musique':
                        meta = get_metadata(str(f))
                        artwork = meta['artwork']
                        artist = meta['artist']
                        name = meta['title']
                        album = meta['album']
                    elif each == 'photo':
                        name = f.name.split('.')[0]
                        artwork = make_artwork_base64(str(f))
                else:
                    ftype = 'dir'
                    name = f.name

                fmodel = FileModel(
                    type=ftype,
                    category = each,
                    path = str(f),
                    name = name,
                    artwork = artwork,
                    artist = artist,
                    album=album

                )
                parent = FileModel.query.filter_by(path=str(f.parent)).first()
                if parent is not None:
                    fmodel.parent = parent.id
                db.session.add(fmodel)

        # retirer ceux qui n'existent plus
        all_files = FileModel.query.all()
        for f in all_files:
            if not os.path.exists(f.path):
                FileModel.query.filter(FileModel.id == f.id).delete()
        db.session.commit()
    return redirect(url_for('parametres'))

@app.route('/categorie/<nom>')
def categorie(nom):
    parent_id = request.args.get('parent_id')
    models = FileModel.query.filter_by(category=nom, parent=parent_id).all()
    return render_template('files.html', cat=nom, items=models)

@app.route("/categorie/<path:filename>")
def serve_file(filename):
    ftype = request.args.get('type')
    if not filename.startswith('/'):
        filename = '/' + filename
    directory = os.path.dirname(filename)
    file_name = os.path.basename(filename)
    if ftype == 'music':
        return send_from_directory(directory, file_name, mimetype='audio/mpeg')
    else:
        return send_from_directory(directory, file_name, mimetype='image/jpeg')

@app.route('/add_podcast', methods=['GET', 'POST'])
def add_podcast():
    if request.method == 'POST':
        url = request.form['url']
        episodes = rss.get_episodes_list(url)
        return render_template('select_ep.html', podcast=url, episodes=episodes)
    else:
        # Vérifier si une URL est passée en paramètre (depuis refresh)
        url = request.args.get('url')
        if url:
            episodes = rss.get_episodes_list(url)
            # Récupérer les épisodes déjà existants
            folder = FileModel.query.filter_by(url=url, type='dir').first()
            existing_names = set()
            if folder:
                existing_episodes = FileModel.query.filter_by(parent=folder.id).all()
                existing_names = {ep.name for ep in existing_episodes}
            return render_template('select_ep.html', podcast=url, episodes=episodes, existing=existing_names)

        tool_list = rss.list_tools()
        return render_template('add_rss.html', searchtools=tool_list)

@app.route("/podcast_search", methods=["POST"])
def podcast_search():
    podcast_name = request.form.get("podcast_name")
    search_tool_name = request.form.get("searchtool")
    tool = rss.get_tool_by_name(search_tool_name)
    resultats = tool.search(podcast_name)
    return render_template("add_rss.html", resultats=resultats)

@app.post('/download_podcast')
def download_podcast():
    selected = request.form.getlist("selected")
    podcast_url = request.form['playlist_url']

    task_id = str(uuid.uuid4())
    tasks_progress[task_id] = 0

    # Lancer le téléchargement dans un thread
    thread = Thread(target=download_worker, args=(task_id, selected, podcast_url), daemon=True)
    thread.start()

    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return jsonify({"task_id": task_id})
    # Retourner la page avec la barre de progression
    return render_template("progress.html", task_id=task_id)

def download_worker(task_id, selected, podcast_url):
    """
    Worker exécuté dans un thread séparé.
    IMPORTANT : on doit recréer un app_context pour pouvoir utiliser `db` et d'autres
    objets Flask/SQAlchemy en toute sécurité.
    """
    with app.app_context():   # <-- s'assurer d'avoir le contexte Flask
        # Récup infos du podcast
        infos = rss.get_infos(podcast_url)

        # dossier de sauvegarde
        path = Path(DATA_PATH) / 'podcast' / secure_filename(infos['titre'])
        dir_model = FileModel.query.filter_by(path=str(path)).first()
        if not dir_model:
            path.mkdir(parents=True, exist_ok=True)

            # artwork et model de dossier
            artwork = make_artwork_base64(infos.get('image'), size=150)
            dir_model = FileModel(
                type='dir',
                category='podcast',
                path=str(path),
                name=infos['titre'],
                artwork=artwork,
                url=podcast_url,
                description=infos.get('description')
            )
            db.session.add(dir_model)
            db.session.commit()
        else:
            print('%s existe' %infos['titre'])

        episodes = rss.get_episodes_list(podcast_url) or []
        # total d'épisodes sélectionnés (éviter division par 0)
        total = sum(1 for ep in episodes if ep['titre'] in selected)
        if total == 0:
            tasks_progress[task_id] = 100
            return

        done = 0
        for each in episodes:
            epModel = FileModel.query.filter_by(parent=dir_model.id, name=each['titre']).first()
            if each['titre'] not in selected or epModel is not None:
                if epModel is not None:
                    print('%s déjà en mémoire' %each['titre'])
                continue

            epath = path / secure_filename(f"{each['titre']}.mp3")
            ep_url = each.get('audio')
            response = requests.get(ep_url, timeout=30)
            response.raise_for_status()

            with open(epath, "wb") as f:
                f.write(response.content)

            epModel = FileModel(
                type='file',
                category='podcast',
                path=str(epath),
                name=each['titre'],
                artwork=make_artwork_base64(each.get('image'), size=150),
                url=ep_url,
                description=each.get('description'),
                parent=dir_model.id
            )
            db.session.add(epModel)
            db.session.commit()
            # Mettre à jour la progression
            done += 1
            # calcul safe (entier)
            tasks_progress[task_id] = int(done * 100 / total)

        # fin du travail
        tasks_progress[task_id] = 100

@app.get("/progress/<task_id>")
def progress(task_id):
    return jsonify({"progress": tasks_progress.get(task_id, 0)})

@app.route('/refresh_folder/<int:folder_id>', methods=['POST'])
def refresh_folder(folder_id):
    folder_model = FileModel.query.filter_by(id=folder_id, type='dir').first()
    if not folder_model:
        return jsonify({"success": False, "error": "Dossier non trouvé"}), 404

    category = folder_model.category
    folder_path = Path(folder_model.path)

    try:
        # Si c'est un podcast, vérifier s'il y a de nouveaux épisodes
        if category == 'podcast' and folder_model.url:
            episodes = rss.get_episodes_list(folder_model.url)
            existing_episodes = FileModel.query.filter_by(parent=folder_id).all()
            existing_names = {ep.name for ep in existing_episodes}

            new_episodes = [ep for ep in episodes if ep['titre'] not in existing_names]

            if new_episodes:
                # Rediriger vers la page de sélection avec les nouveaux épisodes
                if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                    return jsonify({"success": True, "redirect": True, "url": folder_model.url})
                return render_template('select_ep.html', podcast=folder_model.url, episodes=episodes, existing=existing_names)
            else:
                if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                    return jsonify({"success": True, "message": "Aucun nouvel épisode"})
                return redirect(url_for('categorie', nom=category, parent_id=folder_model.parent))

        # Pour les dossiers photo/musique, rescanner le dossier
        elif category in ['photo', 'musique']:
            if not folder_path.exists():
                return jsonify({"success": False, "error": "Le dossier n'existe plus"}), 404

            # Récupérer les fichiers existants dans la BDD pour ce dossier
            existing_files = FileModel.query.filter_by(parent=folder_id).all()
            existing_paths = {f.path for f in existing_files}

            # Scanner les fichiers du système
            current_paths = set()
            for f in folder_path.rglob('*'):
                if f.is_file():
                    current_paths.add(str(f))

            # Supprimer les fichiers qui n'existent plus
            removed_count = 0
            for file_model in existing_files:
                if file_model.path not in current_paths:
                    if file_model.type == 'file':
                        db.session.delete(file_model)
                        removed_count += 1

            # Ajouter les nouveaux fichiers
            added_count = 0
            for file_path in current_paths:
                if file_path not in existing_paths:
                    f = Path(file_path)
                    artwork = None
                    name = None
                    artist = None
                    album = None

                    if category == 'musique':
                        meta = get_metadata(str(f))
                        artwork = meta['artwork']
                        artist = meta['artist']
                        name = meta['title']
                        album = meta['album']
                    elif category == 'photo':
                        name = f.name.split('.')[0]
                        artwork = make_artwork_base64(str(f))

                    fmodel = FileModel(
                        type='file',
                        category=category,
                        path=str(f),
                        name=name,
                        artwork=artwork,
                        artist=artist,
                        album=album,
                        parent=folder_id
                    )
                    db.session.add(fmodel)
                    added_count += 1

            db.session.commit()

            if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return jsonify({
                    "success": True,
                    "message": f"{added_count} ajouté(s), {removed_count} supprimé(s)",
                    "added": added_count,
                    "removed": removed_count
                })
            return redirect(url_for('categorie', nom=category, parent_id=folder_model.parent))

        else:
            return jsonify({"success": False, "error": "Type de dossier non supporté"}), 400

    except Exception as e:
        db.session.rollback()
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return jsonify({"success": False, "error": str(e)}), 500
        return redirect(url_for('categorie', nom=category, parent_id=folder_model.parent))

@app.route('/delete_file/<int:file_id>', methods=['POST'])
def delete_file(file_id):
    file_model = FileModel.query.filter_by(id=file_id).first()
    if not file_model:
        return jsonify({"success": False, "error": "Fichier non trouvé"}), 404

    category = file_model.category
    parent_id = file_model.parent

    try:
        # Si c'est un dossier, supprimer récursivement tous les enfants
        if file_model.type == 'dir':
            def delete_recursive(dir_id):
                children = FileModel.query.filter_by(parent=dir_id).all()
                for child in children:
                    if child.type == 'dir':
                        delete_recursive(child.id)
                    else:
                        # Supprimer le fichier physique
                        if os.path.exists(child.path):
                            os.remove(child.path)
                    db.session.delete(child)

                # Supprimer le dossier de la base
                dir_model = FileModel.query.get(dir_id)
                if dir_model:
                    # Supprimer le dossier physique
                    if os.path.exists(dir_model.path):
                        os.rmdir(dir_model.path)
                    db.session.delete(dir_model)

            delete_recursive(file_id)
        else:
            # Supprimer le fichier physique
            if os.path.exists(file_model.path):
                os.remove(file_model.path)
            db.session.delete(file_model)

        db.session.commit()

        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return jsonify({"success": True})
        return redirect(url_for('categorie', nom=category, parent_id=parent_id))

    except Exception as e:
        db.session.rollback()
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return jsonify({"success": False, "error": str(e)}), 500
        return redirect(url_for('categorie', nom=category, parent_id=parent_id))

@app.template_filter('basename')
def basename_filter(path):
    p = Path(path).name
    return p.split('.')[0]


if __name__ == '__main__':
    app.run(debug=True)