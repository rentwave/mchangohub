from authentication.backend.decorators import user_login_required
from contributions.backend.contribution_management_service import ContributionManagementService
from utils.response_provider import ResponseProvider


class ContributionAPIHandler:
    @classmethod
    @user_login_required
    def create_contribution(cls, request):
        user = request.user
        name = request.data.get("name")
        description = request.data.get("description")
        target_amount = request.data.get("target_amount")
        end_date = request.data.get("end_date")
        is_private = request.data.get("is_private") == "true"
        photo = request.files.get("file")

        contribution = ContributionManagementService().create_contribution(
            user=user,
            name=name,
            description=description,
            target_amount=target_amount,
            end_date=end_date,
            is_private=is_private,
            photo=photo
        )

        return ResponseProvider.created(
            message="Contribution created successfully",
            data={"contribution_id": str(contribution.id)}
        )

    @classmethod
    @user_login_required
    def update_contribution(cls, request):
        user = request.user
        name = request.data.get("name")
        description = request.data.get("description")
        target_amount = request.data.get("target_amount")
        end_date = request.data.get("end_date")
        is_private = request.data.get("is_private") == "true"
        photo = request.files.get("file")

        ContributionManagementService().update_contribution(
            user=user,
            name=name,
            description=description,
            target_amount=target_amount,
            end_date=end_date,
            is_private=is_private,
            photo=photo
        )

        return ResponseProvider.success(
            message="Contribution updated successfully",
        )

    @classmethod
    @user_login_required
    def delete_contribution(cls, request):
        user = request.user
        contribution_id = request.data.get("contribution_id")
        ContributionManagementService().delete_contribution(
            user=user,
            contribution_id=contribution_id
        )

        return ResponseProvider.success(message="Contribution deleted successfully")

    @classmethod
    def get_contribution(cls, request):
        contribution_id = request.data.get("contribution_id")
        contribution_data = ContributionManagementService().fetch_contribution(
            contribution_id=contribution_id
        )

        return ResponseProvider.success(
            message="Contribution fetched successfully",
            data=contribution_data
        )

    @classmethod
    def filter_contributions(cls, request):
        user = request.user
        creator_id = request.data.get("creator_id")
        search_term = request.data.get("search_term")
        status = request.data.get("status")
        start_date = request.data.get("start_date")
        end_date = request.data.get("end_date")
        is_private = request.data.get("is_private") == "true"

        contributions = ContributionManagementService().filter_contributions(
            user=user,
            creator_id=creator_id,
            search_term=search_term,
            status=status,
            start_date=start_date,
            end_date=end_date,
            is_private=is_private
        )

        return ResponseProvider.success(
            message="Contributions filtered successfully",
            data=contributions
        )
