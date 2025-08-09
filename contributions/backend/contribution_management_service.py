from django.forms.models import model_to_dict
from django.utils import timezone
from django.db.models import Q, QuerySet

from contributions.backend.services import ContributionService
from contributions.models import Contribution
from users.models import User
from utils.common import normalize_phone_number


class ContributionManagementService:
    REQUIRED_FIELDS = ['name', 'target_amount', 'end_date']

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

        if ContributionService().filter(creator=user, name=kwargs.get('name')).exists():
            raise ValueError('Name already exists')

        contribution = ContributionService().create(
            name=kwargs.get('name').title(),
            description=kwargs.get('description', '').capitalize(),
            target_amount=kwargs.get('target_amount'),
            end_date=kwargs.get('end_date'),
            creator=user
        )
        if contribution is None:
            raise Exception('Contribution not created')

        phone_numbers = kwargs.get('phone_numbers', [])
        if phone_numbers:
            phone_numbers = [normalize_phone_number(phone=phone) for phone in phone_numbers]
            # TODO: Handle invitation logic

        return contribution

    @staticmethod
    def update_contribution(contribution_id: str, **kwargs) -> Contribution:
        """
        Update fields of a contribution by its ID.

        :param contribution_id: The UUID or string ID of the contribution.
        :type contribution_id: str
        :param kwargs: Fields and values to update.
        :type kwargs: dict
        :raises ValueError: If contribution is not found.
        :return: The updated Contribution instance.
        :rtype: Contribution
        """
        contribution = ContributionService().get(id=contribution_id)
        if contribution is None:
            raise ValueError('Contribution not found')

        for field, value in kwargs.items():
            if hasattr(contribution, field) and value is not None:
                setattr(contribution, field, value)

        contribution.save()
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
    def delete_contribution(contribution_id: str) -> Contribution:
        """
        Soft-delete a contribution by setting its status to INACTIVE.

        :param contribution_id: The UUID or string ID of the contribution.
        :type contribution_id: str
        :raises ValueError: If contribution is not found.
        :return: The contribution instance marked inactive.
        :rtype: Contribution
        """
        contribution = ContributionService().get(id=contribution_id)
        if contribution is None:
            raise ValueError('Contribution not found')

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
