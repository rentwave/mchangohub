from django.db.models import Q, QuerySet
from django.db import transaction
from django.db.models.expressions import F
from django.forms import model_to_dict

from notifications.backend.notification_management_service import NotificationManagementService
from notifications.models import Notification
from users.backend.services import UserService, RoleService
from users.models import User
from utils.common import normalize_phone_number, generate_random_pin


class UserManagementService:
    """
    Service class for managing user-related operations such as creation, updates,
    deletion, password resets, and retrieval.
    """

    REQUIRED_FIELDS = ["phone_number"]
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

    def create_user(self, active_user: bool = True, **kwargs) -> User:
        """
        Create or update a user based on phone number.
        Validates required fields and uniqueness, applies value transformations explicitly.

        :param active_user: Whether to activate the user upon creation.
        :param kwargs: User attributes.
        :return: Created or updated User instance.
        :raises ValueError: If required fields are missing or uniqueness is violated.
        :raises UserCreationError: If user creation or update fails.
        """
        # Validate required fields presence
        missing_fields = [field for field in self.REQUIRED_FIELDS if not kwargs.get(field)]
        if missing_fields:
            raise ValueError(f"Missing required fields: {', '.join(missing_fields)}")

        # Normalize and clean input data
        data = {k: v for k, v in kwargs.items() if v is not None and v != ""}
        data["phone_number"] = normalize_phone_number(data["phone_number"])
        data["role"] = RoleService().get(name="USER", is_active=True)

        if "email" in data:
            data["email"] = data["email"].lower()
        if "other_phone_number" in data:
            data["other_phone_number"] = normalize_phone_number(data["other_phone_number"])
        if "gender" in data:
            data["gender"] = data["gender"].upper()
        if "id_number" in data:
            data["id_number"] = data["id_number"].strip()
        for name_field in ("first_name", "last_name", "other_name"):
            if name_field in data:
                data[name_field] = data[name_field].title()

        # Check if a user with phone_number exists
        existing_user = UserService().get(phone_number=data["phone_number"])
        if existing_user and existing_user.is_active:
            raise Exception("Phone number already registered")

        user_id = existing_user.id if existing_user else None

        # Check uniqueness for unique fields
        for field in self.UNIQUE_FIELDS:
            val = data.get(field, None)
            if val:
                query = Q(**{field: val})
                if user_id:
                    query &= ~Q(id=user_id)
                if UserService().filter(query).exists():
                    raise ValueError(f"{field.replace('_', ' ').title()} already exists")

        # Create or update user
        if existing_user:
            user = UserService().update(pk=user_id, **data, is_active=active_user)
            if not user:
                raise Exception("User update failed")
        else:
            user = UserService().create(**data, is_active=active_user)
            if not user:
                raise Exception("User creation failed")

        # Set password
        password = data.pop("password", None) or generate_random_pin()
        user.set_password(password)
        user.save()

        return user

    def update_user(self, user_id: str, **kwargs) -> User:
        """
        Update an existing user with provided fields.
        Ensures uniqueness, filters out empty or None values, and applies normalization.

        :param user_id: The ID of the user to update.
        :param kwargs: Fields to update.
        :return: Updated User instance.
        :raises ValueError: If the user is not found or uniqueness is violated.
        """
        user = UserService().get(id=user_id, is_active=True)
        if not user:
            raise ValueError("User does not exist")

        # Filter out empty or None values
        data = {k: v for k, v in kwargs.items() if v}
        data.pop("password", None)  # The password should not be updated here
        data.pop("phone_number", None)  # Phone number should be handled separately

        # Apply normalization
        if "other_phone_number" in data:
            data["other_phone_number"] = normalize_phone_number(data["other_phone_number"])
        if "email" in data:
            data["email"] = data["email"].lower()
        if "id_number" in data:
            data["id_number"] = kwargs["id_number"].strip()
        if "gender" in data:
            data["gender"] = data["gender"].upper()
        for name_field in ("first_name", "last_name", "other_name"):
            if name_field in data:
                data[name_field] = data[name_field].title()

        # Check uniqueness for provided fields
        for field in self.UNIQUE_FIELDS:
            val = data.get(field, None)
            if val:
                existing_user = UserService().filter(Q(**{field: val}) & ~Q(id=user.id)).first()
                if existing_user:
                    raise ValueError(f"{field.replace('_', ' ').title()} already exists")

        updated_user = UserService().update(pk=user.id, **data)
        if not updated_user:
            raise Exception("User not updated")

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
        user_dict.pop("password", None)

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

        users = UserService().filter(filters).annotate(role_name=F("role__name"))

        if queryset:
            return users

        users_list = list(users.values())

        return users_list

