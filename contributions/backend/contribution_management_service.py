from django.forms.models import model_to_dict
from django.utils import timezone
from django.db.models import Q, QuerySet
from django.db import transaction

from contributions.backend.services import ContributionService
from contributions.models import Contribution
from notifications.backend.notification_management_service import NotificationManagementService
from users.models import User
from utils.common import normalize_phone_number


class ContributionManagementService:
    REQUIRED_FIELDS = ['name', 'target_amount', 'end_date']

    @transaction.atomic
    def create_contribution(self, user: User, **kwargs) -> Contribution:
        """
        Create a new contribution entry.

        :param user: The creator User instance.
        :type user: User
        :param kwargs: Required fields: name, target_amount, end_date; optional: description, phone_numbers.
        :type kwargs: dict
        :raises ValueError: If required fields are missing or contribution name already exists.
        :raises Exception: If contribution creation fails.
        :return: The created Contribution instance.
        :rtype: Contribution
        """
        for field in self.REQUIRED_FIELDS:
            if not kwargs.get(field):
                raise ValueError(f"{field.replace('_', ' ').title()} must be provided")

        name = str(kwargs.get('name')).strip().title()
        description = str(kwargs.get('description', '')).strip().capitalize()
        target_amount = float(str(kwargs.get('target_amount')).strip())
        end_date = str(kwargs.get('end_date')).strip()

        if ContributionService().filter(creator=user, name=name).exists():
            raise ValueError('Name already exists')

        contribution = ContributionService().create(
            name=name,
            description=description,
            target_amount=target_amount,
            end_date=end_date,
            creator=user
        )
        if contribution is None:
            raise Exception('Contribution not created')

        phone_numbers = kwargs.get('phone_numbers', [])
        phone_numbers = [normalize_phone_number(phone=phone) for phone in phone_numbers]
        if phone_numbers:
            NotificationManagementService(None).send_to_recipients(
                recipients=phone_numbers,
                template='sms_contribution_invitation',
                context={
                    'contribution_name': contribution.name,
                    'target_amount': contribution.target_amount,
                    'end_date': contribution.end_date.strftime('%Y-%m-%d'),
                    'creator_name': user.full_name,
                    'contribution_link': f'https://machangohub.com/contributions/{contribution.id}'
                },
            )

        return contribution

    @staticmethod
    def update_contribution(user: User, contribution_id: str, **kwargs) -> Contribution:
        """
        Update fields of a contribution identified by its ID.

        :param user: The user attempting the update; must be the creator.
        :type user: User
        :param contribution_id: The UUID or string identifier of the contribution.
        :type contribution_id: str
        :param kwargs: Fields and their new values to update on the contribution.
        :type kwargs: dict
        :raises ValueError: If the contribution is not found or user lacks permission.
        :raises Exception: If the update operation fails.
        :return: The updated Contribution instance.
        :rtype: Contribution
        """
        contribution = ContributionService().get(id=contribution_id)
        if contribution is None:
            raise ValueError('Contribution not found')

        if not user == contribution.creator:
            raise ValueError('You do not have permission to update this contribution')

        contribution = ContributionService().update(pk=contribution.id, **kwargs)
        if contribution is None:
            raise Exception('Failed to update contribution')

        return contribution

    @staticmethod
    def update_contribution_status(contribution_id: str) -> Contribution:
        """
        Update the status of a contribution based on its end_date relative to current time.

        :param contribution_id: The UUID or string ID of the contribution.
        :type contribution_id: str
        :raises ValueError: If contribution is not found.
        :return: The contribution instance with updated status.
        :rtype: Contribution
        """
        contribution = ContributionService().get(id=contribution_id)
        if contribution is None:
            raise ValueError('Contribution not found')

        now = timezone.now()
        new_status = Contribution.Status.ONGOING if contribution.end_date > now else Contribution.Status.OVERDUE

        if contribution.status != new_status:
            contribution.status = new_status
            contribution.save()

        return contribution

    @staticmethod
    def delete_contribution(user: User, contribution_id: str) -> Contribution:
        """
        Soft-delete a contribution by marking its status as INACTIVE.

        :param user: The user attempting to delete; must be the creator.
        :type user: User
        :param contribution_id: The UUID or string identifier of the contribution.
        :type contribution_id: str
        :raises ValueError: If the contribution is not found or user lacks permission.
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

    def get_contribution(self, contribution_id: str) -> dict:
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

        contribution = self.update_contribution_status(contribution_id)

        contribution_dict = model_to_dict(contribution)
        contribution_dict["id"] = str(contribution.id)
        contribution_dict["creator_name"] = contribution.creator.full_name

        return contribution_dict

    def filter_contributions(
            self,
            search_term: str = "",
            creator_id: str | None = None,
            status: str | None = None,
            start_date: str | None = None,
            end_date: str | None = None,
            queryset: bool = False,
    ) -> QuerySet | list[dict]:
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
            filters &= Q(status=status)

        if start_date:
            filters &= Q(date_created__date__gte=start_date)

        if end_date:
            filters &= Q(date_created__date__lte=end_date)

        contributions = ContributionService().filter(filters)

        # Update statuses of filtered contributions
        for contribution in contributions:
            self.update_contribution_status(contribution.id)

        if queryset:
            return contributions

        return list(contributions.values())
