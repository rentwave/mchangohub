from django.urls import path

from contributions.views import ContributionAPIHandler

handler = ContributionAPIHandler()

urlpatterns = [
    path("get/", handler.get_contribution, name="get_contribution"),
    path("create/", handler.create_contribution, name="create_contribution"),
    path("update/", handler.update_contribution, name="update_contribution"),
    path("delete/", handler.delete_contribution, name="delete_contribution"),
    path("filter/", handler.filter_contributions, name="filter_contributions"),
    path("filter-public/", handler.filter_contributions, name="filter-public"),
]
