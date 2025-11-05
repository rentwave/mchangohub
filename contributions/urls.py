from django.urls import path

from contributions.views import ContributionAPIHandler

urlpatterns = [
    path("get/", ContributionAPIHandler.get_contribution, name="get_contribution"),
    path("create/", ContributionAPIHandler.create_contribution, name="create_contribution"),
    path("update/", ContributionAPIHandler.update_contribution, name="update_contribution"),
    path("delete/", ContributionAPIHandler.delete_contribution, name="delete_contribution"),
    path("filter/", ContributionAPIHandler.filter_contributions, name="filter_contributions"),
]
