import re
from typing import Union
from django.core.files import File
from dateutil.parser import parse
from django.conf import settings
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

    REQUIRED_FIELDS = ['name', 'target_amount', 'end_date']

    @staticmethod
    def _generate_contribution_alias() -> str:
        """
        Generate a new contribution alias in the format ``G-XXXX``.

        The alias is incremented based on the highest existing alias. If no
        valid alias exists, the sequence starts from ``G-0001``.

        :return: The newly generated contribution alias.
        :rtype: str
        :raises Exception: If database access fails while retrieving the last contribution.
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

    @transaction.atomic
    def create_contribution(self, user: User, file=None, **kwargs) -> Contribution:
        """
        Create a new contribution entry.

        :param user: The creator User instance.
        :param kwargs: Required fields: name, target_amount, end_date; optional: description, phone_numbers.
        :raises ValueError: If required fields are missing, or contribution name already exists.
        :raises Exception: If contribution creation fails.
        :return: The created Contribution instance.
        """
        missing = [f for f in self.REQUIRED_FIELDS if not kwargs.get(f)]
        if missing:
            raise ValueError(f"Missing required fields: {', '.join(missing)}")
        name = str(kwargs.get("name")).strip().title()
        description = str(kwargs.get("description", "")).strip().capitalize()
        try:
            target_amount = float(str(kwargs.get("target_amount")).strip())
        except (ValueError, TypeError):
            raise ValueError("Invalid target amount")

        try:
            end_date = parse(str(kwargs.get("end_date")))
        except (ValueError, TypeError):
            raise ValueError("Invalid end date")
        if ContributionService().filter(creator=user, name=name).exists():
            raise ValueError("Contribution name already exists")
        alias = self._generate_contribution_alias()

        contribution = ContributionService().create(
            alias=alias,
            name=name,
            description=description,
            target_amount=target_amount,
            end_date=end_date,
            profile=file,
            creator=user,
            is_private=kwargs.get('is_private')
        )
        if not contribution:
            raise Exception("Contribution not created")
        phone_numbers = kwargs.get("phone_numbers", [])
        print(phone_numbers)
        # normalized_phones = [normalize_phone_number(phone) for phone in phone_numbers if phone]
        # if normalized_phones:
        #     NotificationManagementService(None).send_notification(
        #         delivery_method=Notification.DeliveryMethods.SMS,
        #         recipients=normalized_phones,
        #         template="sms_contribution_invitation",
        #         context={
        #             "contribution_name": contribution.name,
        #             "target_amount": contribution.target_amount,
        #             "end_date": contribution.end_date.strftime("%Y-%m-%d"),
        #             "creator_name": user.full_name,
        #             "contribution_link": f"https://mchangohub.com/contributions/{contribution.alias}",
        #         },
        #     )
        return contribution

    @transaction.atomic
    def update_contribution(self, user: User, file, contribution_id: str, **kwargs) -> Contribution:
        """
        Update fields of a contribution identified by its ID.

        :param user: The user attempting the update; must be the creator.
        :param contribution_id: The UUID or string identifier of the contribution.
        :param kwargs: Fields and their new values to update on the contribution.
        :raises ValueError: If the contribution is not found, user lacks permission, or new name duplicates existing.
        :raises Exception: If the update operation fails.
        :return: The updated Contribution instance.
        """
        contribution = ContributionService().get(id=contribution_id)
        if contribution is None:
            raise ValueError("Contribution not found")
        if user != contribution.creator:
            raise ValueError("You do not have permission to update this contribution")
        if file:
            contribution.profile = file
            contribution.save()
        normalized_data = {}

        if "name" in kwargs:
            new_name = str(kwargs["name"]).strip().title()
            # Check if the new name already exists for user excluding current contribution
            exists = ContributionService().filter(
                creator=user,
                name=new_name
            ).exclude(id=contribution.id).exists()
            if exists:
                raise ValueError("Contribution name already exists")
            normalized_data["name"] = new_name

        if "description" in kwargs:
            normalized_data["description"] = str(kwargs["description"]).strip().capitalize()

        if "target_amount" in kwargs:
            try:
                normalized_data["target_amount"] = float(str(kwargs["target_amount"]).strip())
            except (ValueError, TypeError):
                raise ValueError("Invalid target amount")

        if "end_date" in kwargs:
            try:
                normalized_data["end_date"] = parse(str(kwargs["end_date"]))
            except (ValueError, TypeError):
                raise ValueError("Invalid end date")
        if "is_private" in kwargs:
            try:
                normalized_data["is_private"] = kwargs["is_private"]
            except (ValueError, TypeError):
                raise ValueError("Invalid end date")

        updated_contribution = ContributionService().update(pk=contribution.id, **normalized_data)
        
        if not updated_contribution:
            raise Exception("Failed to update contribution")

        return updated_contribution

    @staticmethod
    def delete_contribution(user: User, contribution_id: str) -> Contribution:
        """
        Soft-delete a contribution by marking its status as INACTIVE.

        :param user: The user attempting to delete; must be the creator.
        :type user: User
        :param contribution_id: The UUID or string identifier of the contribution.
        :type contribution_id: str
        :raises ValueError: If the contribution is not found or usefiler lacks permission.
        :return: The contribution instance marked as inactive.
        :rtype: Contribution
        """
        contribution = ContributionService().get(id=contribution_id)
        if contribution is None:
            raise ValueError('Contribution not found')

        if not user == contribution.creator:
            raise ValueError('You do not have permission to delete this contribution')

        contribution.status = Contribution.Status.INACTIVE
        contribution.save()
        return contribution

    @staticmethod
    def get_contribution(contribution_id: str) -> dict:
        """
        Retrieve a contribution as a dictionary.

        Automatically updates contribution status before returning.

        :param contribution_id: The UUID or string ID of the contribution.
        :type contribution_id: str
        :raises ValueError: If contribution is not found.
        :return: Contribution data as a dictionary.
        :rtype: dict
        """
        contribution = ContributionService().get(id=contribution_id)
        if contribution is None:
            raise ValueError('Contribution not found')

        # Update status
        contribution.update_status()

        # Convert contribution model instance to dict
        contribution_dict = model_to_dict(contribution)
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

    @staticmethod
    def filter_contributions(
            search_term: str = "",
            creator_id: str | None = None,
            status: str | None = None,
            start_date: str | None = None,
            end_date: str | None = None,
            is_public: bool = False,
            queryset: bool = False,
    ) -> Union[QuerySet, list[dict]]:
        """
        Filter and retrieve contributions based on search criteria.

        Automatically updates statuses using `update_contribution_status`.

        :param search_term: Search string to match contribution fields and creator info.
        :type search_term: str
        :param creator_id: Filter contributions by creator ID.
        :type creator_id: str | None
        :param status: Filter contributions by status.
        :type status: str | None
        :param start_date: Filter contributions created on or after this date (YYYY-MM-DD).
        :type start_date: str | None
        :param end_date: Filter contributions created on or before this date (YYYY-MM-DD).
        :type end_date: str | None
        :param queryset: If True, returns a QuerySet; else returns a list of dicts.
        :type queryset: bool
        :return: Filtered contributions as a QuerySet or list of dicts.
        :rtype: QuerySet[Contribution] | list[dict]
        """
        filters = Q()

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
        print(is_public)
        if is_public:
            filters &= Q(is_private=False)
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

        # Update statuses of filtered contributions
        for contribution in contributions:
            contribution.update_status()

        if queryset:
            return contributions

        return list(contributions.values())
