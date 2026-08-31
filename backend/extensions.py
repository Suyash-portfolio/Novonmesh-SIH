from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_socketio import SocketIO


class RedisClient:
    client = None


db = SQLAlchemy()
migrate = Migrate()
socketio = SocketIO()
redis_client = RedisClient()
