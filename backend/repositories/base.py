"""The ``Repositories`` facade.

One repository per aggregate. Reads return SQLAlchemy ORM rows (``db/models``);
callers use their attributes directly and ``.to_dict()`` for the wire. Writes
take plain dicts / kwargs. ``get_repos()`` (``__init__.py``) builds this facade;
concrete repos are plain classes — no abstract interface layer or domain/ORM
translator, since there is a single Postgres backend.
"""


class Repositories:
    """Facade bundling one repo per aggregate."""

    def __init__(
        self,
        *,
        users,
        auth_tokens,
        clubs,
        groups,
        boats,
        devices,
        activities,
        sessions,
        ingest,
        regattas,
        racedays,
        races,
        media,
        wind,
        polars,
        rbac,
        app_config,
        posts,
    ):
        self.users = users
        self.auth_tokens = auth_tokens
        self.clubs = clubs
        self.groups = groups
        self.boats = boats
        self.devices = devices
        self.activities = activities
        self.sessions = sessions
        self.ingest = ingest
        self.regattas = regattas
        self.racedays = racedays
        self.races = races
        self.media = media
        self.wind = wind
        self.polars = polars
        self.rbac = rbac
        self.app_config = app_config
        self.posts = posts
