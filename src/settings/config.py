import os
from zoneinfo import ZoneInfo
from dotenv import load_dotenv

load_dotenv()

MOSCOW_TZ = ZoneInfo("Europe/Moscow")

db_user = os.environ['DB_USER']
db_password = os.environ['DB_PASS']
db_name = os.environ['DB_NAME']
db_host = os.environ['DB_HOST']
db_port = int(os.environ['DB_PORT'])

redis_host = os.environ['REDIS_HOST']
redis_port = int(os.environ['REDIS_PORT'])
redis_db = int(os.environ['REDIS_DB'])
redis_password = os.environ['REDIS_PASSWORD'] or None