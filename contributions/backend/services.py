from contributions.models import Contribution
from utils.service_base import ServiceBase


class ContributionService(ServiceBase):
    manager = Contribution.objects