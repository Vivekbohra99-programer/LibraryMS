"""Flask extensions, initialised once and shared across modules."""
import sqlite3
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import event
from sqlalchemy.engine import Engine
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect

db = SQLAlchemy()
login_manager = LoginManager()
csrf = CSRFProtect()

login_manager.login_view = 'auth.login'
login_manager.login_message_category = 'warning'


@event.listens_for(Engine, 'connect')
def _enforce_foreign_keys(dbapi_connection, _record):
    """SQLite ignores FOREIGN KEY constraints unless asked, per connection. Ask, so the database itself
    refuses a loan that points at a book or member that does not exist."""
    if isinstance(dbapi_connection, sqlite3.Connection):
        cursor = dbapi_connection.cursor()
        cursor.execute('PRAGMA foreign_keys=ON')
        cursor.close()
