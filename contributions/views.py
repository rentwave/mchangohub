import logging

from contributions.backend.contribution_management_service import ContributionManagementService
from utils.request_handler import request_handler
from utils.response_provider import ResponseProvider

logger = logging.getLogger(__name__)


class ContributionAPIHandler:
    @staticmethod
    @request_handler(audit=True)
    def create_contribution(request):
        """
        Create a new contribution.

        :param request: Django HTTP request object containing contribution details.
        :type request: HttpRequest
        :return: JSON response with created contribution ID.
        :rtype: JsonResponse
        """
        try:
            user = request.user
            contribution = ContributionManagementService().create_contribution(user=user, **request.data)
            return ResponseProvider.created(
                message="Contribution created successfully",
                data={"contribution_id": str(contribution.id)}
            )
        except Exception as ex:
            logger.exception(f"ContributionAPIHandler - create_contribution exception: {ex}")
            return ResponseProvider.error(message="An error occurred while creating the contribution", error=str(ex))

    @staticmethod
    @request_handler(audit=True)
    def update_contribution(request):
        """
        Update an existing contribution by ID.

        :param request: Django HTTP request object containing 'contribution_id' and fields to update.
        :type request: HttpRequest
        :return: JSON response confirming update.
        :rtype: JsonResponse
        """
        try:
            user = request.user
            contribution_id = request.data.pop("contribution_id", "")
            ContributionManagementService().update_contribution(
                user=user,
                contribution_id=contribution_id,
                **request.data
            )
            return ResponseProvider.success(message="Contribution updated successfully")
        except Exception as ex:
            logger.exception(f"ContributionAPIHandler - update_contribution exception: {ex}")
            return ResponseProvider.error(message="An error occurred while updating the contribution", error=str(ex))

    @staticmethod
    @request_handler(audit=True)
    def delete_contribution(request):
        """
        Soft delete a contribution by marking it inactive.

        :param request: Django HTTP request object containing 'contribution_id'.
        :type request: HttpRequest
        :return: JSON response confirming deletion.
        :rtype: JsonResponse
        """
        try:
            user = request.user
            contribution_id = request.data.get("contribution_id", "")
            ContributionManagementService().delete_contribution(
                user=user,
                contribution_id=contribution_id
            )
            return ResponseProvider.success(message="Contribution deleted successfully")
        except Exception as ex:
            logger.exception(f"ContributionAPIHandler - delete_contribution exception: {ex}")
            return ResponseProvider.error(message="An error occurred while deleting the contribution", error=str(ex))

    @staticmethod
    @request_handler
    def get_contribution(request):
        """
        Retrieve a specific contribution by ID.

        :param request: Django HTTP request object containing 'contribution_id'.
        :type request: HttpRequest
        :return: JSON response with contribution data.
        :rtype: JsonResponse
        """
        try:
            contribution_id = request.data.get("contribution_id", "")
            contribution_data = ContributionManagementService().get_contribution(contribution_id=contribution_id)
            return ResponseProvider.success(message="Contribution fetched successfully", data=contribution_data)
        except Exception as ex:
            logger.exception(f"ContributionAPIHandler - get_contribution exception: {ex}")
            return ResponseProvider.error(message="An error occurred while fetching the contribution", error=str(ex))

    @staticmethod
    @request_handler
    def filter_contributions(request):
        """
        Retrieve contributions filtered by optional parameters.

        :param request: Django HTTP request object containing optional filters:
            'search_term', 'creator_id', 'status', 'start_date', 'end_date'.
        :type request: HttpRequest
        :return: JSON response with the filtered contributions' list.
        :rtype: JsonResponse
        """
        try:
            filters = {
                "search_term": request.data.get("search_term", ""),
                "creator_id": request.data.get("creator_id", ""),
                "status": request.data.get("status", ""),
                "start_date": request.data.get("start_date", ""),
                "end_date": request.data.get("end_date", ""),
            }
            contributions = ContributionManagementService().filter_contributions(**filters)
            return ResponseProvider.success(message="Contributions filtered successfully", data=contributions)
        except Exception as ex:
            logger.exception(f"ContributionAPIHandler - filter_contributions exception: {ex}")
            return ResponseProvider.error(message="An error occurred while filtering contributions", error=str(ex))
