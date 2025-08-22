from decimal import Decimal
from django.db import models
from django.db.models import Sum, Count
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.apps import apps  # Lazy import for related models

from base.models import GenericBaseModel


class Contribution(GenericBaseModel):
    class Status(models.TextChoices):
        ONGOING = "ONGOING", _("Ongoing")
        COMPLETED = "COMPLETED", _("Completed")
        OVERDUE = "OVERDUE", _("Overdue")
        INACTIVE = "INACTIVE", _("Inactive")

    alias = models.CharField(max_length=50, null=True, blank=True)
    creator = models.ForeignKey('users.User', on_delete=models.CASCADE)
    target_amount = models.DecimalField(max_digits=12, decimal_places=2)
    end_date = models.DateTimeField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ONGOING)

    class Meta:
        indexes = [models.Index(fields=['creator'])]
        ordering = ('-date_created',)

    def __str__(self):
        return f"{self.name} - {self.creator}"

    def _transactions(self):
        """Base queryset for contribution transactions."""
        WalletTransaction = apps.get_model('billing', 'WalletTransaction')
        return WalletTransaction.objects.filter(
            wallet_account__contribution=self,
            status__name="Completed",
            transaction_type='topup'
        )

    @property
    def total_contributed(self) -> Decimal:
        """Total amount contributed so far."""
        return self._transactions().aggregate(total=Sum("amount"))["total"] or Decimal("0.00")

    @property
    def balance(self) -> Decimal:
        """Remaining balance to reach target."""
        return max(self.target_amount - self.total_contributed, Decimal("0.00"))

    @property
    def progress_percentage(self) -> float:
        """Contribution progress as a percentage of target."""
        if self.target_amount > 0:
            return round((self.total_contributed / self.target_amount) * 100, 2)
        return 0.0

    @property
    def contributors_count(self) -> int:
        """Number of unique contributors."""
        return self._transactions().values("wallet_account__user").distinct().count()

    @property
    def transactions_count(self) -> int:
        """Total number of contribution transactions."""
        return self._transactions().count()

    def get_remaining_days(self) -> int:
        """Days left until contribution end date (negative if overdue)."""
        return (self.end_date.date() - timezone.now().date()).days

    def is_completed(self) -> bool:
        """Check if contribution has reached or exceeded target."""
        return self.total_contributed >= self.target_amount

    def is_overdue(self) -> bool:
        """Check if contribution is past end date without completion."""
        return self.get_remaining_days() < 0 and not self.is_completed()

    def update_status(self):
        """Auto-update status based on progress and deadlines."""
        if self.is_completed():
            self.status = self.Status.COMPLETED
        elif self.is_overdue():
            self.status = self.Status.OVERDUE
        else:
            self.status = self.Status.ONGOING
        self.save(update_fields=["status", "date_modified"])

    def latest_transaction(self):
        """Get most recent transaction."""
        return self._transactions().order_by("-date_created").first()

    def average_contribution(self) -> Decimal:
        """Average amount contributed per transaction."""
        total = self.total_contributed
        count = self.transactions_count
        return total / count if count > 0 else Decimal("0.00")

    def top_contributor(self):
        """Find user who contributed the most."""
        return self._transactions().values(
            "wallet_account__user__id", "wallet_account__user__username"
        ).annotate(
            total=Sum("amount")
        ).order_by("-total").first()
