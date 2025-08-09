from django.db import models
from django.utils.translation import gettext_lazy as _

from base.models import GenericBaseModel


class Contribution(GenericBaseModel):
    class Status(models.TextChoices):
        ONGOING = "ONGOING", _("Ongoing")
        COMPLETED = "COMPLETED", _("Completed")
        OVERDUE = "OVERDUE", _("Overdue")
        INACTIVE = "INACTIVE", _("Inactive")

    creator = models.ForeignKey('users.User', on_delete=models.CASCADE)
    target_amount = models.DecimalField(max_digits=12, decimal_places=2)
    end_date = models.DateTimeField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ONGOING)

    # TODO: NO NEED TO CREATE WALLET -- FIELDS CAN JUST BE ADDED HERE

    class Meta:
        indexes = [
            models.Index(fields=['creator']),
        ]
        ordering = ('-date_created',)

    def _str_(self):
        return '%s - %s' % (self.name, self.creator.username)
