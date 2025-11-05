import re
from typing import Union, Optional

from django.core.exceptions import ValidationError, ObjectDoesNotExist, PermissionDenied
from django.core.files import File
from dateutil.parser import parse
from django.conf import settings
from django.core.files.uploadedfile import UploadedFile
from django.db.models.functions import Trim, Replace, Concat, Coalesce
from django.forms.models import model_to_dict
from django.db.models import Q, QuerySet, F, Value
from django.db import transaction

from base.backend.service import WalletAccountService, WalletTransactionService
from contributions.backend.services import ContributionService
from contributions.models import Contribution
from notifications.backend.notification_management_service import NotificationManagementService
from notifications.models import Notification
from users.models import User
from utils.common import normalize_phone_number


class ContributionManagementService:
    @classmethod
    def _generate_contribution_alias(cls) -> str:
        """
        Generate a sequential alias for a new contribution.

        :return: A new alias in the format `C-XXXX`.
        :rtype: str
        """
        last_contribution = (
            Contribution.objects.select_for_update()
            .exclude(alias__isnull=True)
            .order_by("-alias")
            .first()
        )
        if last_contribution and re.match(r"^C-\d{4}$", last_contribution.alias):
            last_number = int(last_contribution.alias.split("-")[1])
        else:
            last_number = 0

        alias = f"C-{last_number + 1:04d}"

        return alias

    @classmethod
    def get_contribution(cls, contribution_id: str) -> Contribution:
        """
        Retrieve an active contribution by its ID.

        :param contribution_id: The unique identifier of the contribution.
        :type contribution_id: str
        :raises ObjectDoesNotExist: If the contribution is not found or inactive.
        :return: The matching contribution instance.
        :rtype: Contribution
        """
        contribution = (
            Contribution.objects
            .exclude(status=Contribution.Status.INACTIVE)
            .filter(id=contribution_id)
            .first()
        )

        if not contribution:
            raise ObjectDoesNotExist("Contribution not found or inactive")

        return contribution

    @classmethod
    @transaction.atomic
    def create_contribution(
            cls,
            user: User,
            name:str,
            description: str,
            target_amount: float,
            end_date: str,
            is_private: bool = False,
            photo: Optional[UploadedFile] = None
    ) -> Contribution:
        """
        Create a new contribution.

        :param user: The user creating the contribution.
        :type user: User
        :param name: The name of the contribution.
        :type name: str
        :param description: A short description of the contribution.
        :type description: str
        :param target_amount: The target amount for the contribution.
        :type target_amount: float
        :param end_date: The contribution's end date (parsable string format).
        :type end_date: str
        :param is_private: Whether the contribution is private.
        :type is_private: bool
        :param photo: Optional image file for the contribution.
        :type photo: UploadedFile, optional
        :raises ValidationError: If validation fails for name, amount, or end date.
        :raises Exception: If contribution creation fails.
        :return: The created contribution instance.
        :rtype: Contribution
        """
        # Validate and normalize data
        name = name.strip().title()
        if not name:
            raise ValidationError("Contribution name must be provided")

        try:
            target_amount = float(str(target_amount).strip())
        except (ValueError, TypeError):
            raise ValidationError("Invalid target amount value")

        if target_amount <= 0:
            raise ValidationError("Contribution amount must be greater than zero")

        if not target_amount:
            raise ValidationError("Target amount must be provided")
        if not isinstance(target_amount, float):
            target_amount = float(str(target_amount).strip())

        try:
            end_date = parse(end_date)
        except Exception:
            raise ValidationError("Invalid end date format")

        description = description.strip()

        # Create contribution
        alias = cls._generate_contribution_alias()
        contribution = ContributionService().create(
            alias=alias,
            name=name,
            description=description,
            target_amount=target_amount,
            end_date=end_date,
            profile=photo,
            creator=user,
            is_private=is_private
        )
        if not contribution:
            raise Exception("Contribution not created")

        return contribution

    @classmethod
    @transaction.atomic
    def update_contribution(
            cls,
            contribution_id: str,
            user: User,
            name: Optional[str] = None,
            description: Optional[str] = None,
            target_amount: Optional[float] = None,
            end_date: Optional[str] = None,
            is_private: Optional[bool] = None,
            photo: Optional[UploadedFile] = None
    ) -> Contribution:
        """
        Update an existing contribution.

        :param contribution_id: The unique identifier of the contribution.
        :type contribution_id: str
        :param user: The user performing the update.
        :type user: User
        :param name: Updated contribution name, if provided.
        :type name: str, optional
        :param description: Updated contribution description, if provided.
        :type description: str, optional
        :param target_amount: Updated target amount, if provided.
        :type target_amount: float, optional
        :param end_date: Updated end date, if provided.
        :type end_date: str, optional
        :param is_private: Updated privacy flag.
        :type is_private: bool, optional
        :param photo: Updated contribution photo.
        :type photo: UploadedFile, optional
        :raises PermissionDenied: If the user is not the creator.
        :raises ValidationError: If input data is invalid.
        :return: The updated contribution instance.
        :rtype: Contribution
        """
        contribution = cls.get_contribution(contribution_id)

        if contribution.creator != user:
            raise PermissionDenied("You are not allowed to update this contribution")

        # Normalize and validate fields
        if name is not None:
            name = name.strip().title()
            if not name:
                raise ValidationError("Contribution name cannot be empty")
            contribution.name = name

        if description is not None:
            contribution.description = description.strip()

        if target_amount is not None:
            try:
                contribution.target_amount = float(str(target_amount).strip())
            except (ValueError, TypeError):
                raise ValidationError("Invalid target amount value")

        if end_date is not None:
            try:
                contribution.end_date = parse(end_date)
            except Exception:
                raise ValidationError("Invalid end date format")

        if is_private is not None:
            contribution.is_private = bool(is_private)

        if photo is not None:
            contribution.profile = photo

        # Persist changes
        contribution.save()

        return contribution

    @classmethod
    @transaction.atomic
    def delete_contribution(cls, user: User, contribution_id: str) -> Contribution:
        """
        Soft-delete a contribution by marking its status as inactive.

        :param user: The user performing the deletion.
        :type user: User
        :param contribution_id: The unique identifier of the contribution.
        :type contribution_id: str
        :raises PermissionDenied: If the user is not the creator.
        :raises ValidationError: If the contribution is already inactive.
        :return: The contribution instance marked as inactive.
        :rtype: Contribution
        """
        contribution = cls.get_contribution(contribution_id)

        if contribution.creator != user:
            raise PermissionDenied("You are not allowed to delete this contribution")

        if contribution.status == Contribution.Status.INACTIVE:
            raise ValidationError("This contribution is already inactive")

        contribution.status = Contribution.Status.INACTIVE
        contribution.save(update_fields=["status"])

        return contribution

    @classmethod
    def fetch_contribution(cls, contribution_id: str) -> dict:
        """
        Retrieve full contribution details, including wallet and transactions.

        :param contribution_id: The unique identifier of the contribution.
        :type contribution_id: str
        :raises ObjectDoesNotExist: If the contribution is not found or inactive.
        :return: A dictionary with contribution, wallet, and transaction details.
        :rtype: dict
        """
        contribution = cls.get_contribution(contribution_id)

        # Update status
        contribution.update_status()

        # Convert contribution model instance to dict
        contribution_dict = model_to_dict(contribution)

        # Add contribution photo url
        if contribution.profile:
            contribution_dict['profile'] = settings.MEDIA_URL + str(contribution.profile)

        # Get wallet account
        wallet_account = WalletAccountService().get(contribution=contribution)
        available_wallet_amount = wallet_account.available

        # Get transactions
        transactions = list(
            WalletTransactionService()
            .filter(
                wallet_account=wallet_account,
                transaction_type="topup",
                status__name="Completed",
            )
            .annotate(
                actioned_by_full_name=Trim(
                    Replace(
                        Concat(
                            Coalesce(F("actioned_by__first_name"), Value("")),
                            Value(" "),
                            Coalesce(F("actioned_by__other_name"), Value("")),
                            Value(" "),
                            Coalesce(F("actioned_by__last_name"), Value("")),
                        ),
                        Value("  "),
                        Value(" "),
                    )
                )
            )
            .order_by("-date_created")
            .values()
        )

        contribution_data = {
            **contribution_dict,
            "id": str(contribution.id),
            "date_created": contribution.date_created,
            "date_modified": contribution.date_modified,
            "creator_name": contribution.creator.full_name,
            "available_wallet_amount": available_wallet_amount,
            "transactions": transactions
        }

        return contribution_data

    @classmethod
    def filter_contributions(
            cls,
            user: Optional[User] = None,
            creator_id: Optional[str] = None,
            search_term: Optional[str] = None,
            status: Optional[str] = None,
            start_date: Optional[str] = None,
            end_date: Optional[str] = None,
            is_private: Optional[bool] = None,
            queryset: bool = False,
    ) -> Union[QuerySet, list[dict]]:
        """
        Filter contributions based on search, date, creator, and visibility criteria.

        :param user: The user performing the query.
        :type user: User, optional
        :param creator_id: Filter contributions by creator ID.
        :type creator_id: str, optional
        :param search_term: Text to search across name, description, and creator info.
        :type search_term: str, optional
        :param status: Filter by contribution status.
        :type status: str, optional
        :param start_date: Minimum creation date (inclusive).
        :type start_date: str, optional
        :param end_date: Maximum creation date (inclusive).
        :type end_date: str, optional
        :param is_private: Privacy filter. None shows both user’s private and public.
        :type is_private: bool, optional
        :param queryset: Whether to return a QuerySet instead of a list.
        :type queryset: bool, optional
        :return: Filtered contributions as a QuerySet or list of dicts.
        :rtype: Union[QuerySet, list[dict]]
        """
        filters = Q()

        # Text search
        if search_term:
            filters &= Q(
                Q(name__icontains=search_term) |
                Q(description__icontains=search_term) |
                Q(creator__username__icontains=search_term) |
                Q(creator__email__icontains=search_term) |
                Q(creator__phone_number__icontains=search_term)
            )

        if creator_id:
            filters &= Q(creator__id=creator_id)

        if status:
            filters &= Q(status=status.upper())

        if start_date:
            filters &= Q(date_created__date__gte=start_date)

        if end_date:
            filters &= Q(date_created__date__lte=end_date)

        if is_private:
            filters &= Q(is_private=True)
        elif is_private is False:
            filters &= Q(is_private=False)
        else:
            visibility_filter = Q(is_private=False)
            if user:
                visibility_filter |= Q(is_private=True, creator=user)
            filters &= visibility_filter

        contributions = (
            ContributionService()
            .filter(filters)
            .annotate(
                available_wallet_amount=F("wallet_accounts__available"),
                creator_name=Trim(
                    Replace(
                        Concat(
                            Coalesce(F("creator__first_name"), Value("")),
                            Value(" "),
                            Coalesce(F("creator__other_name"), Value("")),
                            Value(" "),
                            Coalesce(F("creator__last_name"), Value("")),
                        ),
                        Value("  "),
                        Value(" "),
                    )
                )
            )
        )

        # Update contribution statuses
        for contribution in contributions:
            contribution.update_status()

        if queryset:
            return contributions

        # Add photo urls
        contributions = list(contributions.values())
        for contribution in contributions:
            if contribution.get("profile"):
                contribution["profile"] = f"{settings.MEDIA_URL}{contribution['profile']}"

        return contributions
