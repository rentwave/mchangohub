from django.core.exceptions import ObjectDoesNotExist, PermissionDenied

from authentication.backend.decorators import user_login_required
from users.backend.device_management_service import DeviceManagementService
from users.backend.user_management_service import UserManagementService
from utils.response_provider import ResponseProvider


class UserAPIHandler:
    @staticmethod
    def check_user(request):
        """
        Check if a user with a specific credential exists in the system.

        :param request: Django HTTP request object containing 'credential' and optional 'fields' list.
        :type request: HttpRequest
        :return: JSON response with status code, message, and success status.
        :rtype: JsonResponse
        :raises Exception: If the user is not found.
        """
        credential = request.data.get("credential", "")
        fields = ["first_name"]
        user, field_label = UserManagementService().get_user_by_credential(credential=credential)
        if not user:
            raise ObjectDoesNotExist("User not found")
        data = {}
        for field in fields:
            if hasattr(user, field):
                data[field] = getattr(user, field)

        return ResponseProvider.success(
            message=f"{field_label} '{credential}' already exists.",
            data=data
        )

    @staticmethod
    def create_user(request):
        """
        Create a new user using the provided details.

        :param request: Django HTTP request object containing user creation fields.
        :type request: HttpRequest
        :return: JSON response with status code, message, and success status.
        :rtype: JsonResponse
        :raises Exception: If the user creation fails.
        """
        user = UserManagementService().create_user(**request.data)
        return ResponseProvider.created(
            message="User created successfully",
            data={"user_id": str(user.id)}
        )

    @staticmethod
    @user_login_required
    def update_user(request):
        """
        Update an existing user's details.

        :param request: Django HTTP request object containing 'user_id' and updated fields.
        :type request: HttpRequest
        :return: JSON response with status code, message, and success status.
        :rtype: JsonResponse
        :raises Exception: If the update fails.
        """
        UserManagementService().update_user(user_id=request.user.id, **request.data)
        return ResponseProvider.success(message="User updated successfully")

    @staticmethod
    @user_login_required
    def delete_user(request):
        """
        Delete a user from the system.

        :param request: Django HTTP request object containing 'user_id'.
        :type request: HttpRequest
        :return: JSON response with status code, message, and success status.
        :rtype: JsonResponse
        :raises Exception: If the deletion fails.
        """
        UserManagementService().delete_user(user_id=request.user.id)
        return ResponseProvider.success(message="User deleted successfully")

    @staticmethod
    def forgot_password(request):
        """
        Initiate the password reset process using a credential.

        :param request: Django HTTP request object containing 'credential'.
        :type request: HttpRequest
        :return: JSON response with status code, message, and success status.
        :rtype: JsonResponse
        :raises Exception: If password reset initiation fails.
        """
        credential = request.data.get("credential", "")
        UserManagementService().forgot_password(credential=credential)
        return ResponseProvider.success(message="Password reset successfully")

    @staticmethod
    @user_login_required(required_permission="can_reset_password")
    def reset_password(request):
        """
        Reset a user's password using their user ID.

        :param request: Django HTTP request object containing 'user_id'.
        :type request: HttpRequest
        :return: JSON response with status code, message, and success status.
        :rtype: JsonResponse
        :raises Exception: If the password reset fails.
        """
        user_id = request.data.get("user_id", "")
        UserManagementService().reset_password(user_id=user_id)
        return ResponseProvider.success(message="Password reset successfully")

    @staticmethod
    @user_login_required
    def change_password(request):
        """
        Change a user's password by providing the old and new passwords.

        :param request: Django HTTP request object containing 'user_id', 'old_password', and 'new_password'.
        :type request: HttpRequest
        :return: JSON response with status code, message, and success status.
        :rtype: JsonResponse
        :raises Exception: If password change fails.
        """
        user_id = request.user.id
        old_password = request.data.get("old_password", "")
        new_password = request.data.get("new_password", "")
        UserManagementService().change_password(
            user_id=user_id,
            old_password=old_password,
            new_password=new_password
        )
        return ResponseProvider.success(message="Password changed successfully")

    @staticmethod
    @user_login_required
    def get_user(request):
        """
        Fetch a specific user's data.

        :param request: Django HTTP request object containing 'user_id'.
        :type request: HttpRequest
        :return: JSON response with status code, message, and success status.
        :rtype: JsonResponse
        :raises Exception: If the user is not found or retrieval fails.
        """
        user_id = request.data.get("user_id", request.user.id)
        if user_id != request.user.id and not request.user.has_permission("can_view_users"):
            raise PermissionDenied("You do not have permission to view this user.")
        user_data = UserManagementService().get_user(user_id=user_id)
        if not user_data:
            raise ObjectDoesNotExist("User not found")
        return ResponseProvider.success(
            message="User fetched successfully",
            data=user_data
        )

    @staticmethod
    @user_login_required(required_permission="can_view_users")
    def filter_users(request):
        """
        Retrieve a list of users matching the given filters.

        :param request: Request with optional filters: 'search_term', 'role_name', 'is_staff', 'is_superuser'.
        :type request: HttpRequest
        :return: JSON response with status code, message, and success status.
        :rtype: JsonResponse
        :raises Exception: If user retrieval fails.
        """
        search_term = request.data.get("search_term", "")
        role_name = request.data.get("role_name", "")
        is_staff = request.data.get("is_staff")
        is_superuser = request.data.get("is_superuser")
        users_data = UserManagementService().filter_users(
            search_term=search_term,
            role_name=role_name,
            is_staff=is_staff,
            is_superuser=is_superuser,
        )
        return ResponseProvider.success(
            message="Users fetched successfully",
            data=users_data
        )

    @staticmethod
    @user_login_required
    def create_device(request) -> dict:
        """
        Create a new device entry for a user in a specific system.

        :param request: The HTTP request object containing user ID and device token.
        :type request: HttpRequest
        :return: JSON response with status code, message, and success status.
        :rtype: JsonResponse
        :raises Exception: If device creation fails.
        """
        data = request.data
        user_id = request.user.id
        device_token = data.get("device_token", "")
        device = DeviceManagementService().create_device(
            user_id=user_id,
            device_token=device_token,
        )
        return ResponseProvider.created(
            message="Device created successfully",
            data={"device_id": str(device.id)}
        )

    @staticmethod
    @user_login_required
    def deactivate_device(request) -> dict:
        """
        Deactivate a device by its ID.

        :param request: The HTTP request object containing the device ID to be deactivated.
        :type request: HttpRequest
        :return: JSON response with status code, message, and success status.
        :rtype: JsonResponse
        :raises Exception: If deactivation fails.
        """
        device_id = request.data.get("device_id", "")
        DeviceManagementService().deactivate_device(device_id=device_id)
        return ResponseProvider.success(message="Device deactivated successfully")
