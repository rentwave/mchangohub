import uuid

from django.db import models

class BaseModel(models.Model):
    id = models.UUIDField(max_length=100, default=uuid.uuid4, unique=True, editable=False, primary_key=True)
    date_modified = models.DateTimeField(auto_now=True)
    date_created = models.DateTimeField(auto_now_add=True)
    synced = models.BooleanField(default=False)

    objects = models.Manager()

    SYNC_MODEL = True

    class Meta(object):
        abstract = True


class GenericBaseModel(BaseModel):
    name = models.CharField(max_length=100)
    description = models.CharField(max_length=100, null=True, blank=True)

    class Meta(object):
        abstract = True


