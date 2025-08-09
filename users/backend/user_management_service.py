from django.db.models import Q, QuerySet
from django.db import transaction
from django.forms import model_to_dict

from notifications.backend.notification_management_service import NotificationManagementService
from notifications.models import Notification
from users.backend.services import UserService, RoleService
from users.models import User
from utils.common import normalize_phone_number, set_update_fields, generate_random_pin


class UserManagementService:
    """
    Service class for managing user-related operations such as creation, updates,
    deletion, password resets, and retrieval.
    """

    REQUIRED_FIELDS = ["phone_number", "password"]
    UNIQUE_FIELDS = ["username", "id_number", "email", "phone_number"]

    def get_user_by_credential(self, credential: str) -> tuple[User | None, str | None]:
        """
        Retrieve a user using a unique credential (username, ID number, email, or phone number).

        :param credential: The credential to search for.
        :type credential: str
        :return: Tuple containing the user instance (if found) and the matched field label.
        :rtype: tuple[User | None, str | None]
        """
        filters = Q()
        for field in self.UNIQUE_FIELDS:
            filters |= Q(**{field.lower(): credential})

        user = UserService().filter(filters, is_active=True).first()
        if not user:
            return None, None

        # Determine which field matched the credential
        for field in self.UNIQUE_FIELDS:
            if getattr(user, field, None) == credential:
                field_label = field.replace("_", " ").capitalize()
                return user, field_label

        return user, None

    def create_user(self, **kwargs) -> User:
        """
        Create a new user or update an existing one based on phone number.
        Ensures required fields, uniqueness, and applies value transformations.

        :param kwargs: User attributes.
        :return: Created or updated User instance.
        :raises ValueError: If required fields are missing or uniqueness is violated.
        :raises Exception: If user creation fails.
        """
        # Ensure required fields are present
        for field in self.REQUIRED_FIELDS:
            if not kwargs.get(field):
                raise ValueError(f"{field.replace('_', ' ').title()} must be provided")

        user = UserService().get(phone_number=kwargs.get("phone_number"))
        user_id = user.id if user else None

        # Ensure uniqueness for specified fields
        for field in self.UNIQUE_FIELDS:
            if field in kwargs and kwargs[field]:
                query = Q(**{field: kwargs[field]})
                if user_id:
                    query &= ~Q(id=user_id)
                existing_user = UserService().filter(query).first()
                if existing_user:
                    raise ValueError(f"{field.replace('_', ' ').title()} already exists")

        fields = {
            "phone_number": lambda v: normalize_phone_number(phone=v),
            "email": lambda v: v.lower(),
            "id_number": lambda v: v,
            "other_phone_number": normalize_phone_number,
            "first_name": lambda v: v.title(),
            "last_name": lambda v: v.title(),
            "other_name": lambda v: v.title(),
            "gender": lambda v: v.upper(),
            "dob": lambda v: v,
            "role": lambda v: RoleService().get(name="USER", is_active=True),
            "password": lambda v: v,
        }

        if user:
            data = set_update_fields(fields, kwargs, instance=user)
            UserService().update(pk=user.id, **data)
            user.refresh_from_db()
        else:
            data = set_update_fields(fields, kwargs)
            user = UserService().create(**data)
            if not user:
                raise Exception("User not created")

        return user

    def update_user(self, user_id: str, **kwargs) -> User:
        """
        Update an existing user with provided fields.
        Ensures uniqueness and applies transformations.

        :param user_id: The ID of the user to update.
        :param kwargs: Fields to update.
        :return: Updated User instance.
        :raises ValueError: If the user is not found or uniqueness is violated.
        """
        user = UserService().get(id=user_id, is_active=True)
        if not user:
            raise ValueError("User does not exist")

        # Ensure uniqueness for provided fields
        for field in self.UNIQUE_FIELDS:
            if field in kwargs and kwargs[field]:
                existing_user = UserService().filter(
                    Q(**{field: kwargs[field]}) & ~Q(id=user.id)
                ).first()
                if existing_user:
                    raise ValueError(f"{field.replace('_', ' ').title()} already exists")

        fields = {
            "phone_number": normalize_phone_number,
            "email": lambda v: v.lower(),
            "id_number": lambda v: v,
            "other_phone_number": normalize_phone_number,
            "first_name": lambda v: v.title(),
            "last_name": lambda v: v.title(),
            "other_name": lambda v: v.title(),
            "gender": lambda v: v.upper(),
            "dob": lambda v: v,
            "password": lambda v: v,
        }

        data = set_update_fields(fields, kwargs, instance=user)

        if not data:
            return user

        updated_user = UserService().update(pk=user.id, **data)
        updated_user.refresh_from_db()
        return updated_user

    @staticmethod
    @transaction.atomic
    def delete_user(user_id: str) -> User:
        """
        Soft delete a user by marking them as inactive.

        :param user_id: The ID of the user to delete.
        :type user_id: str
        :return: The deactivated User instance.
        :rtype: User
        :raises ValueError: If the user is not found.
        """
        user = UserService().get(id=user_id, is_active=True)
        if not user:
            raise ValueError("User does not exist")

        user.is_active = False
        user.save()

        return user

    @transaction.atomic
    def forgot_password(self, credential: str) -> None:
        """
        Reset a user's password based on their credential and send it via SMS.

        :param credential: The credential to identify the user.
        :type credential: str
        :return: None
        :rtype: None
        :raises Exception: If the user is not found.
        """
        user, _ = self.get_user_by_credential(credential)
        if not user:
            raise Exception("User not found")

        new_password = generate_random_pin()
        user.set_password(new_password)
        user.save()

        NotificationManagementService(user).send_notification(
            delivery_method=Notification.DeliveryMethods.SMS,
            template="sms_reset_password",
            context={"password": new_password}
        )

        return None

    @staticmethod
    def reset_password(user_id: str) -> None:
        """
        Reset a user's password using their ID and send it via SMS.

        :param user_id: The ID of the user.
        :type user_id: str
        :return: None
        :rtype: None
        :raises Exception: If the user is not found.
        """
        user = UserService().get(id=user_id, is_active=True)
        if not user:
            raise Exception("User not found")

        new_password = generate_random_pin()
        user.set_password(new_password)
        user.save()

        NotificationManagementService(user).send_notification(
            delivery_method=Notification.DeliveryMethods.SMS,
            template="sms_reset_password",
            context={"password": new_password}
        )

        return None

    @staticmethod
    def change_password(user_id: str, new_password: str, old_password: str) -> None:
        """
        Change a user's password after verifying the old password.

        :param user_id: The ID of the user.
        :type user_id: str
        :param new_password: The new password.
        :type new_password: str
        :param old_password: The current password for verification.
        :type old_password: str
        :return: None
        :rtype: None
        :raises ValueError: If the user is not found or the old password is incorrect.
        """
        user = UserService().get(id=user_id, is_active=True)
        if not user:
            raise ValueError("User not found")

        if not user.check_password(old_password):
            raise ValueError("Incorrect password")

        user.set_password(new_password)
        user.save()

        return None

    @staticmethod
    def get_user(user_id: str) -> dict:
        """
        Retrieve detailed information for a specific user.

        :param user_id: The ID of the user.
        :type user_id: str
        :return: A dictionary of user details including role and permissions.
        :rtype: dict
        :raises ValueError: If the user is not found.
        """
        user = UserService().get(id=user_id, is_active=True)
        if not user:
            raise ValueError("User not found")

        user_dict = model_to_dict(user)
        user_dict["id"] = str(user.id)
        user_dict["role_name"] = user.role.name
        user_dict["permissions"] = user.permissions

        return user_dict

    @staticmethod
    def filter_users(
            search_term: str = "",
            role_name: str | None = None,
            is_staff: bool | None = None,
            is_superuser: bool | None = None,
            queryset: bool = False,
    ) -> QuerySet | list[dict]:
        """
        Filter and retrieve users based on search criteria.

        :param search_term: Search string to match against user fields.
        :type search_term: str
        :param role_name: Optional role name to filter users by.
        :type role_name: str | None
        :param is_staff: Optional filter for staff users.
        :type is_staff: bool | None
        :param is_superuser: Optional filter for superusers.
        :type is_superuser: bool | None
        :param queryset: If True, return a QuerySet instead of a list of dicts.
        :type queryset: bool
        :return: QuerySet or list of matching users.
        :rtype: QuerySet | list[dict]
        :raises ValueError: If the provided role does not exist.
        """
        filters = Q(is_active=True)

        if search_term:
            filters &= Q(
                Q(id_number__icontains=search_term) |
                Q(username__icontains=search_term) |
                Q(email__icontains=search_term) |
                Q(phone_number__icontains=search_term) |
                Q(first_name__icontains=search_term) |
                Q(last_name__icontains=search_term) |
                Q(other_name__icontains=search_term) |
                Q(other_phone_number__icontains=search_term)
            )

        if role_name:
            role = RoleService().get(name=role_name, is_active=True)
            if not role:
                raise ValueError("Role does not exist")
            filters &= Q(role=role)

        if is_staff is not None:
            filters &= Q(is_staff=is_staff)

        if is_superuser is not None:
            filters &= Q(is_superuser=is_superuser)

        users = UserService().filter(filters)

        if queryset:
            return users

        users_list = list(users.values())

        return users_list

