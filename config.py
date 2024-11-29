import os
import dotenv

dotenv.load_dotenv()

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY')
    SQLALCHEMY_DATABASE_URI = f"sqlite:///{os.path.join(os.path.dirname(__file__), 'database.db')}"
    SQLALCHEMY_TRACK_MODIFICATIONS = False