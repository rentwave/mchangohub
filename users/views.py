import logging

from users.backend.device_management_service import DeviceManagementService
from users.backend.user_management_service import UserManagementService
from utils.request_handler import request_handler
from utils.response_provider import ResponseProvider

logger = logging.getLogger(__name__)


class UserAPIHandler:
    @staticmethod
    @request_handler(user_login_required=False)
    def check_user(request):
        """
        Check if a user with a specific credential exists in the system.

        :param request: Django HTTP request object containing 'credential' and optional 'fields' list.
        :type request: HttpRequest
        :return: JSON response with status code, message, and success status.
        :rtype: JsonResponse
        :raises Exception: If the user is not found.
        """
        try:
            credential = request.data.get("credential", "")
            fields = request.data.get("fields", ["first_name"])  # optional list of fields to return
            user, field_label = UserManagementService().get_user_by_credential(credential=credential)
            if not user:
                return ResponseProvider.success(code="200.001", message="User not found")
            data = {}
            for field in fields:
                if hasattr(user, field):
                    data[field] = getattr(user, field)
            return ResponseProvider.success(message=f"{field_label} '{credential}' already exists.", data=data)
        except Exception as ex:
            logger.exception(f"UserAPIHandler - check_user exception: {ex}")
            return ResponseProvider.error(message="An error occurred while checking user", error=str(ex))

    @staticmethod
    @request_handler(user_login_required=False, audit=True)
    def create_user(request):
        """
        Create a new user using the provided details.

        :param request: Django HTTP request object containing user creation fields.
        :type request: HttpRequest
        :return: JSON response with status code, message, and success status.
        :rtype: JsonResponse
        :raises Exception: If the user creation fails.
        """
        try:
            user = UserManagementService().create_user(**request.data)
            return ResponseProvider.created(message="User created successfully", data={"user_id": str(user.id)})
        except Exception as ex:
            logger.exception(f"UserAPIHandler - create_user exception: {ex}")
            return ResponseProvider.error(message="An error occurred while creating the user", error=str(ex))

    @staticmethod
    @request_handler
    def update_user(request):
        """
        Update an existing user's details.

        :param request: Django HTTP request object containing 'user_id' and updated fields.
        :type request: HttpRequest
        :return: JSON response with status code, message, and success status.
        :rtype: JsonResponse
        :raises Exception: If the update fails.
        """
        try:
            user_id = request.data.get("user_id", request.user.id)
            UserManagementService().update_user(user_id=user_id, **request.data)
            return ResponseProvider.success(message="User updated successfully")
        except Exception as ex:
            logger.exception(f"UserAPIHandler - update_user exception: {ex}")
            return ResponseProvider.error( message="An error occurred while updating the user", error=str(ex))

    @staticmethod
    @request_handler(audit=True)
    def delete_user(request):
        """
        Delete a user from the system.

        :param request: Django HTTP request object containing 'user_id'.
        :type request: HttpRequest
        :return: JSON response with status code, message, and success status.
        :rtype: JsonResponse
        :raises Exception: If the deletion fails.
        """
        try:
            UserManagementService().delete_user(user_id=request.user.id)
            return ResponseProvider.success(message="User deleted successfully")
        except Exception as ex:
            logger.exception(f"UserAPIHandler - delete_user exception: {ex}")
            return ResponseProvider.error(message="An error occurred while deleting the user", error=str(ex))

    @staticmethod
    @request_handler(user_login_required=False)
    def forgot_password(request):
        """
        Initiate the password reset process using a credential.

        :param request: Django HTTP request object containing 'credential'.
        :type request: HttpRequest
        :return: JSON response with status code, message, and success status.
        :rtype: JsonResponse
        :raises Exception: If password reset initiation fails.
        """
        try:
            credential = request.data.get("credential", "")
            UserManagementService().forgot_password(credential=credential)
            return ResponseProvider.success(message="Password reset successfully")
        except Exception as ex:
            logger.exception(f"UserAPIHandler - forgot_password exception: {ex}")
            return ResponseProvider.error(message="An error occurred while initiating password reset", error=str(ex))

    @staticmethod
    @request_handler(audit=True)
    def reset_password(request):
        """
        Reset a user's password using their user ID.

        :param request: Django HTTP request object containing 'user_id'.
        :type request: HttpRequest
        :return: JSON response with status code, message, and success status.
        :rtype: JsonResponse
        :raises Exception: If the password reset fails.
        """
        try:
            user_id = request.data.get("user_id", "")
            UserManagementService().reset_password(user_id=user_id)
            return ResponseProvider.success(message="Password reset successfully")
        except Exception as ex:
            logger.exception(f"UserAPIHandler - reset_password exception: {ex}")
            return ResponseProvider.error(message="An error occurred while resetting the password", error=str(ex))

    @staticmethod
    @request_handler
    def change_password(request):
        """
        Change a user's password by providing the old and new passwords.

        :param request: Django HTTP request object containing 'user_id', 'old_password', and 'new_password'.
        :type request: HttpRequest
        :return: JSON response with status code, message, and success status.
        :rtype: JsonResponse
        :raises Exception: If password change fails.
        """
        try:
            user_id = request.user.id
            old_password = request.data.get("old_password", "")
            new_password = request.data.get("new_password", "")
            UserManagementService().change_password(
                user_id=user_id,
                old_password=old_password,
                new_password=new_password
            )
            return ResponseProvider.success(message="Password changed successfully")
        except Exception as ex:
            logger.exception(f"UserAPIHandler - change_password exception: {ex}")
            return ResponseProvider.error(message="An error occurred while changing the password", error=str(ex))

    @staticmethod
    @request_handler
    def get_user(request):
        """
        Fetch a specific user's data.

        :param request: Django HTTP request object containing 'user_id'.
        :type request: HttpRequest
        :return: JSON response with status code, message, and success status.
        :rtype: JsonResponse
        :raises Exception: If the user is not found or retrieval fails.
        """
        try:
            user_id = request.data.get("user_id", request.user.id)
            user_data = UserManagementService().get_user(user_id=user_id)
            if not user_data:
                raise Exception("User not found")
            return ResponseProvider.success(message="User fetched successfully", data=user_data)
        except Exception as ex:
            logger.exception(f"UserAPIHandler - get_user exception: {ex}")
            return ResponseProvider.error(message="An error occurred while fetching the user", error=str(ex))

    @staticmethod
    @request_handler
    def filter_users(request):
        """
        Retrieve a list of users matching the given filters.

        :param request: Request with optional filters: 'search_term', 'role_name', 'is_staff', 'is_superuser'.
        :type request: HttpRequest
        :return: JSON response with status code, message, and success status.
        :rtype: JsonResponse
        :raises Exception: If user retrieval fails.
        """
        try:
            search_term = request.data.get("search_term", "")
            role_name = request.data.get("role_name", "")
            is_staff = request.data.get("is_staff", None)
            is_superuser = request.data.get("is_superuser", None)
            users_data = UserManagementService().filter_users(
                search_term=search_term,
                role_name=role_name,
                is_staff=is_staff,
                is_superuser=is_superuser,
            )
            return ResponseProvider.success(message="Users fetched successfully", data=users_data)
        except Exception as ex:
            logger.exception(f"UserAPIHandler - filter_users exception: {ex}")
            return ResponseProvider.error(message="An error occurred while fetching users", error=str(ex))

    @staticmethod
    @request_handler
    def create_device(request) -> dict:
        """
        Create a new device entry for a user in a specific system.

        :param request: The HTTP request object containing user ID and device token.
        :type request: HttpRequest
        :return: JSON response with status code, message, and success status.
        :rtype: JsonResponse
        :raises Exception: If device creation fails.
        """
        try:
            data = request.data
            user_id = data.get("user_id", "")
            device_token = data.get("device_token", "")
            device = DeviceManagementService().create_device(
                user_id=user_id,
                device_token=device_token,
            )
            return ResponseProvider.created(message="Device created successfully", data={"device_id": str(device.id)})
        except Exception as ex:
            logger.exception("UserAPIHandler - create_device exception: %s", ex)
            return ResponseProvider.error(message="An error occurred while creating a device", error=str(ex))

    @staticmethod
    @request_handler
    def deactivate_device(request) -> dict:
        """
        Deactivate a device by its ID.

        :param request: The HTTP request object containing the device ID to be deactivated.
        :type request: HttpRequest
        :return: JSON response with status code, message, and success status.
        :rtype: JsonResponse
        :raises Exception: If deactivation fails.
        """
        try:
            device_id = request.data.get("device_id", "")
            DeviceManagementService().deactivate_device(device_id=device_id)
            return ResponseProvider.success(message="Device deactivated successfully")
        except Exception as ex:
            logger.exception("UserAPIHandler - deactivate_device exception: %s", ex)
            return ResponseProvider.error(message="An error occurred while deactivating a device", error=str(ex))

