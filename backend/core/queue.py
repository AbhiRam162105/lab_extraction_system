from redis import Redis
from rq import Queue
from backend.core.config import get_settings

settings = get_settings()

redis_conn = Redis.from_url(settings.redis.url)
queue = Queue('lab_reports', connection=redis_conn)

def get_queue():
    return queue
