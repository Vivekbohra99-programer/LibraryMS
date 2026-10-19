"""Application configuration."""
import os
import secrets

BASE_DIR = os.path.abspath(os.path.dirname(__file__))


def _secret_key():
    """SECRET_KEY from the environment, otherwise a random key made once and kept in instance/secret.key.

    The previous fallback was a fixed string in the source. Anyone who had read the code could use it to
    forge a login cookie for any account, the admin's included."""
    env = os.environ.get('SECRET_KEY')
    if env:
        return env
    path = os.path.join(BASE_DIR, 'instance', 'secret.key')
    try:
        with open(path, encoding='ascii') as f:
            saved = f.read().strip()
        if saved:
            return saved
    except OSError:
        pass
    key = secrets.token_hex(32)
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:                 # another process wrote it a moment ago
        try:
            with open(path, encoding='ascii') as f:
                return f.read().strip() or key
        except OSError:
            return key
    except OSError:                         # read-only folder: a per-run key still beats a public one
        return key
    with os.fdopen(fd, 'w', encoding='ascii') as f:
        f.write(key)
    return key


class Config:
    SECRET_KEY = _secret_key()
    SQLALCHEMY_DATABASE_URI = 'sqlite:///' + os.path.join(BASE_DIR, 'instance', 'library.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16 MB
    UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')
    BACKUP_FOLDER = os.path.join(BASE_DIR, 'backups')
    WTF_CSRF_ENABLED = True
    ITEMS_PER_PAGE = 25

    # Cookies: not readable by scripts, not sent on cross-site POSTs.
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_SAMESITE = 'Lax'

    # Look of the app for visitors who have not picked one with the switch in the top bar:
    # 'glass' (liquid glass, the default) or 'skeuo' (skeuomorphic). Set LMS_DEFAULT_SKIN=skeuo to change it.
    DEFAULT_SKIN = 'skeuo' if os.environ.get('LMS_DEFAULT_SKIN', '').strip().lower() == 'skeuo' else 'glass'

    # Password guessing: this many wrong passwords for one username from one address locks that pair.
    LOGIN_MAX_FAILURES = 5
    LOGIN_LOCK_SECONDS = 900

    # Ensure directories exist
    for d in [os.path.join(BASE_DIR, 'instance'),
              os.path.join(BASE_DIR, 'uploads'),
              os.path.join(BASE_DIR, 'backups')]:
        os.makedirs(d, exist_ok=True)
