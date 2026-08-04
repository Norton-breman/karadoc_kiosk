from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import ForeignKey, UniqueConstraint

db = SQLAlchemy()

class FileModel(db.Model):
    __tablename__ = 'files'
    id = db.Column(db.Integer, primary_key=True)
    type = db.Column(db.String(50), nullable=False)
    category = db.Column(db.String(50), nullable=False)
    path = db.Column(db.String(500), nullable=False)
    artwork = db.Column(db.Text)  # Base64 encoded artwork
    parent = db.Column(db.Integer, ForeignKey('files.id'))
    url = db.Column(db.String(500))
    description = db.Column(db.Text)
    album = db.Column(db.String(50))
    artist = db.Column(db.String(50))
    name = db.Column(db.String(50))


class DeezerItem(db.Model):
    """Élément Deezer enregistré (album, playlist, artiste ou titre).

    Table séparée du FileModel : ce ne sont pas des fichiers locaux mais des
    références au catalogue Deezer, lues via l'API publique et jouées via le
    widget officiel. Le `type` sert aussi de section dans l'interface.
    """
    __tablename__ = 'deezer_items'
    id = db.Column(db.Integer, primary_key=True)
    deezer_id = db.Column(db.String(50), nullable=False)
    type = db.Column(db.String(50), nullable=False)  # track / album / playlist / artist
    title = db.Column(db.String(200))
    subtitle = db.Column(db.String(200))  # artiste / propriétaire / « X titres »
    artwork = db.Column(db.Text)  # pochette encodée en base64

    __table_args__ = (
        UniqueConstraint('deezer_id', 'type', name='uix_deezer_id_type'),
    )
