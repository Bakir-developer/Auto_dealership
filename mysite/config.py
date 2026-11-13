import os

from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite:///./auto_salon.db')

SECRET_KEY = os.getenv('SECRET_KEY')
ALGORITHM = os.getenv('ALGORITHM', 'HS256')
ACCESS_EXPIRE_TOKEN = int(os.getenv('ACCESS_EXPIRE_TOKEN', 15))
REFRESH_EXPIRE_TOKEN = int(os.getenv('REFRESH_EXPIRE_TOKEN', 7))

SALON_TIMEZONE = os.getenv('SALON_TIMEZONE', 'Asia/Bishkek')

ADMIN_USERNAME = os.getenv('ADMIN_USERNAME')
ADMIN_EMAIL = os.getenv('ADMIN_EMAIL')
ADMIN_PHONE = os.getenv('ADMIN_PHONE')
ADMIN_PASSWORD = os.getenv('ADMIN_PASSWORD')

MEDIA_DIR = os.getenv('MEDIA_DIR', 'media')
