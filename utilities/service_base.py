import logging

logger = logging.getLogger(__name__)


class ServiceBase:
    """
    The class to handle CRUD methods.
    """

    manager = None
    """
    The manager for the model. e.g. for Account module, set this as Account.objects
    """

    def __init__(self, lock_for_update=False, **annotations):
        """
        Initializes the service with optional locking and annotations.

        :param lock_for_update: Whether to use `select_for_update()` for the queryset.
        :type lock_for_update: bool
        :param annotations: Annotations to apply to the manager queryset.
        :type annotations: dict
        """
        if self.manager is None:
            return

        try:
            if lock_for_update:
                self.manager = self.manager.select_for_update()
            if annotations:
                self.manager = self.manager.annotate(**annotations)
        except Exception as ex:
            logger.warning("Annotation or lock error during init: %s", ex)

    def get(self, *args, **kwargs):
        """
        Get a single record from the database.

        :return: Model instance or None.
        """
        try:
            if self.manager is not None:
                return self.manager.get(*args, **kwargs)
        except Exception as e:
            logger.exception('%sService get exception: %s', self.manager.model.__name__, e)
        return None

    def filter(self, *args, **kwargs):
        """
        Return a queryset of filtered records.

        :return: QuerySet or None.
        """
        try:
            if self.manager is not None:
                return self.manager.filter(*args, **kwargs)
        except Exception as e:
            logger.exception('%sService filter exception: %s', self.manager.model.__name__, e)
        return None

    def create(self, **kwargs):
        """
        Create a new record with given attributes.

        :return: The created object or None.
        """
        try:
            if self.manager is not None:
                return self.manager.create(**kwargs)
        except Exception as e:
            logger.exception('%sService create exception: %s', self.manager.model.__name__, e)
        return None

    def update(self, pk, **kwargs):
        """
        Update a record by its primary key.

        :param pk: Primary key of the record.
        :param kwargs: Fields to update.
        :return: Updated object or None.
        """
        try:
            record = self.get(id=pk)
            if record is not None:
                valid_fields = {
                    field.name for field in record._meta.get_fields()
                    if field.concrete and not field.auto_created
                }
                for k, v in kwargs.items():
                    if k in valid_fields:
                        setattr(record, k, v)
                if getattr(record, "SYNC_MODEL", False):
                    record.synced = False
                record.save()
                record.refresh_from_db()
                return record
        except Exception as e:
            logger.exception('%sService update exception: %s', self.manager.model.__name__, e)
        return None
