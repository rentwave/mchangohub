import json
import logging
from typing import Dict, Any

from dateutil.parser import parse
from django.views.decorators.csrf import csrf_exempt

from base.backend.service import WalletTransactionService, WalletAccountService
from billing.models import Pledge
from billing.reporting.pledge_summary import generate_pledge_summary_pdf
from billing.reporting.statements import generate_mpesa_statement_pdf
from billing.reporting.summary_report import generate_contribution_summary_statement_pdf
from contributions.backend.services import ContributionService
from django.http import FileResponse, Http404
import os
from decimal import Decimal
from datetime import datetime
logger = logging.getLogger(__name__)

def unpack_request_data(request) -> Dict[str, Any]:
	"""Extract data from request"""
	try:
		content_type = request.META.get('CONTENT_TYPE', '')
		
		if 'application/json' in content_type:
			body = request.body.decode('utf-8')
			return json.loads(body) if body else {}
		elif request.method == 'GET':
			return dict(request.GET)
		elif request.method == 'POST':
			return dict(request.POST)
		return {}
	except (json.JSONDecodeError, UnicodeDecodeError) as e:
		logger.error(f"Failed to unpack request data: {str(e)}")
		raise


class StatementGenerator:
	
	@csrf_exempt
	def generate_statement(self, request) -> FileResponse:
		"""
		Generate an MPESA-style PDF statement for a contribution's wallet account
		and return it as a downloadable response.
		"""
		data = unpack_request_data(request)
		start_date = parse(data.get('start_date')).replace(hour=0, minute=0, second=0, microsecond=0) if data.get('start_date') else None
		end_date = parse(data.get('end_date')).replace(hour=23, minute=59, second=59, microsecond=999999) if data.get('start_date') else None
		contribution = ContributionService().get(id=data.get("contribution"))
		wallet_account = WalletAccountService().get(contribution=contribution)
		if not start_date or not end_date:
			
			transactions = WalletTransactionService().filter(
				wallet_account=wallet_account, status__name="Completed"
			).order_by("-date_created")
		else:
			transactions = WalletTransactionService().filter(
				wallet_account=wallet_account, status__name="Completed", date_created__gte=start_date,
				date_created__lte=end_date
			).order_by("-date_created")
		trx_list = [
			{
				"timestamp": trx.date_created,
				"type": trx.transaction_type.capitalize(),
				"narration": trx.description or "",
				"reference": trx.receipt_number,
				"counterparty": trx.metadata.get("counterparty",
				                                 "Mobile Money") if trx.metadata else "Mobile Money",
				"paid_in": float(trx.amount) if trx.transaction_type.lower() == "topup" else 0.0,
				"withdrawn": float(trx.amount) if trx.transaction_type.lower() == "payment" else 0.0,
				"charge": float(trx.charge or 0),
			}
			for trx in transactions
		]
		trx_list.sort(key=lambda x: x["timestamp"])
		file_path = generate_mpesa_statement_pdf(
			transactions=trx_list,
			customer_name=f"{contribution.name}",
			msisdn=contribution.creator.phone_number,
			account_number=str(wallet_account.account_number),
			period_start=data.get("start_date", trx_list[0]["timestamp"] if trx_list else datetime.now()),
			period_end=data.get("end_date", trx_list[-1]["timestamp"] if trx_list else datetime.now()),
			opening_balance=Decimal("0.00"),
			filename=(
				f"statement_{contribution.name}_"
				f"{(parse(data.get('start_date')).strftime('%Y%m%d') if data.get('start_date') else contribution.date_created.strftime('%Y%m%d'))}"
				f"_to_"
				f"{(parse(data.get('end_date')).strftime('%Y%m%d') if data.get('end_date') else datetime.now().strftime('%Y%m%d'))}.pdf"
			)
		)
		if not os.path.exists(file_path):
			raise Http404("Statement not found.")
		response = FileResponse(open(file_path, "rb"), content_type="application/pdf")
		response["Content-Disposition"] = f'attachment; filename="statement.pdf"'
		return response

	@csrf_exempt
	def generate_summary_statement(self, request) -> FileResponse:
		"""
        Generate an MPESA-style PDF statement for a contribution's wallet account
        and return it as a downloadable response.
        """
		data = unpack_request_data(request)
		start_date = parse(data.get('start_date')).replace(hour=0, minute=0, second=0, microsecond=0) if data.get(
			'start_date') else None
		end_date = parse(data.get('end_date')).replace(hour=23, minute=59, second=59, microsecond=999999) if data.get(
			'start_date') else None
		contribution = ContributionService().get(id=data.get("contribution"))
		wallet_account = WalletAccountService().get(contribution=contribution)
		if not start_date or not end_date:
			transactions = WalletTransactionService().filter(
				wallet_account=wallet_account, status__name="Completed"
			).order_by("-date_created")
		else:
			transactions = WalletTransactionService().filter(
				wallet_account=wallet_account, status__name="Completed", date_created__gte=start_date,
				date_created__lte=end_date
			).order_by("-date_created")
		trx_list = [
			{
				"timestamp": trx.date_created,
				"type": trx.transaction_type.capitalize(),
				"narration": trx.description or "",
				"reference": trx.receipt_number,
				"counterparty": trx.metadata.get("counterparty",
												 "Mobile Money") if trx.metadata else "Mobile Money",
				"paid_in": float(trx.amount) if trx.transaction_type.lower() == "topup" else 0.0,
				"withdrawn": float(trx.amount) if trx.transaction_type.lower() == "payment" else 0.0,
				"charge": float(trx.charge or 0),
			}
			for trx in transactions
		]
		trx_list.sort(key=lambda x: x["timestamp"])
		file_path = generate_contribution_summary_statement_pdf(
        transactions=trx_list,
        contribution_name=contribution.name,
        target_amount=contribution.target_amount,
		period_start=data.get("start_date", trx_list[0]["timestamp"] if trx_list else datetime.now()),
		period_end=data.get("end_date", trx_list[-1]["timestamp"] if trx_list else datetime.now()),
		filename=(
			f"summary_{contribution.name}_"
			f"{(parse(data.get('start_date')).strftime('%Y%m%d') if data.get('start_date') else contribution.date_created.strftime('%Y%m%d'))}"
			f"_to_"
			f"{(parse(data.get('end_date')).strftime('%Y%m%d') if data.get('end_date') else datetime.now().strftime('%Y%m%d'))}.pdf"
		)
	)
		if not os.path.exists(file_path):
			raise Http404("Statement not found.")
		response = FileResponse(open(file_path, "rb"), content_type="application/pdf")
		response["Content-Disposition"] = f'attachment; filename="statement.pdf"'
		return response

	@csrf_exempt
	def generate_pledge_summary_statement(self, request) -> FileResponse:
		"""
        Generate an MPESA-style PDF statement for a contribution's wallet account
        and return it as a downloadable response.
        """
		data = unpack_request_data(request)
		contribution = ContributionService().get(id=data.get("contribution"))
		pledges = Pledge.objects.filter(
			contribution=contribution
		).order_by("-date_created")
		trx_list = [
			{
				"pledger_name": trx.pledger_name,
				"pledger_contact": trx.pledger_contact,
				"amount": trx.amount or 0,
				"planned_clear_date": trx.planned_clear_date,
				"status": trx.status,
			}
			for trx in pledges
		]
		trx_list.sort(key=lambda x: x["timestamp"])
		file_path = generate_pledge_summary_pdf(
			pledges=trx_list,
			contribution_name=contribution.name,
			period_start=data.get("start_date", trx_list[0]["timestamp"] if trx_list else datetime.now()),
			period_end=data.get("end_date", trx_list[-1]["timestamp"] if trx_list else datetime.now()),
			filename=(
				f"summary_{contribution.name}_"
				f"{(parse(data.get('start_date')).strftime('%Y%m%d') if data.get('start_date') else contribution.date_created.strftime('%Y%m%d'))}"
				f"_to_"
				f"{(parse(data.get('end_date')).strftime('%Y%m%d') if data.get('end_date') else datetime.now().strftime('%Y%m%d'))}.pdf"
			)
		)
		if not os.path.exists(file_path):
			raise Http404("Statement not found.")
		response = FileResponse(open(file_path, "rb"), content_type="application/pdf")
		response["Content-Disposition"] = f'attachment; filename="statement.pdf"'
		return response
	


from django.urls import path


urlpatterns = [
	path('generate/', StatementGenerator().generate_statement, name='generate'),
	path('summary/', StatementGenerator().generate_summary_statement, name='summary'),
	path('pledge/', StatementGenerator().generate_pledge_summary_statement, name='pledge'),
]