from .S3Storage import S3Storage
from .LocalFileStorage import LocalFileStorage
from django.conf import settings

engine = S3Storage() if settings.USE_AWS else LocalFileStorage()
