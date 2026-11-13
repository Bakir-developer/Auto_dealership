import os

from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv('DATABASE_URL')

SECRET_KEY = os.getenv('SECRET_KEY')
ALGORITHM = os.getenv('ALGORITHM', 'HS256')
ACCESS_EXPIRE_TOKEN = int(os.getenv('ACCESS_EXPIRE_TOKEN', 15))
REFRESH_EXPIRE_TOKEN = int(os.getenv('REFRESH_EXPIRE_TOKEN', 7))

SALON_TIMEZONE = os.getenv('SALON_TIMEZONE', 'Asia/Bishkek')
