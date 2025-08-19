import json
import logging
from typing import Dict, Any

from dateutil.parser import parse

from base.backend.service import WalletTransactionService
from billing.reporting.statements import generate_mpesa_statement_pdf
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
	
	def generate_statement(self, request) -> FileResponse:
		"""
		Generate an MPESA-style PDF statement for a contribution's wallet account
		and return it as a downloadable response.
		"""
		data = unpack_request_data(request)
		start_date = parse(data.get('start_date')).replace(hour=0, minute=0, second=0, microsecond=0) if data.get('start_date') else None
		end_date = parse(data.get('end_date')).replace(hour=23, minute=59, second=59, microsecond=999999) if data.get('start_date') else None
		contribution = ContributionService().get(id=data.get("contribution"))
		if not start_date or not end_date:
			transactions = WalletTransactionService().filter(
				wallet_account=contribution.wallet_account, status__name="Completed"
			).order_by("-date_created")
		else:
			transactions = WalletTransactionService().filter(
				wallet_account=contribution.wallet_account, status__name="Completed", date_created__gte=start_date,
				date_created__lte=end_date
			).order_by("-date_created")
		trx_list = [
			{
				"timestamp": trx.date_created,
				"type": trx.transaction_type.capitalize(),
				"narration": trx.description or "",
				"reference": trx.reference,
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
			customer_name=f"{contribution.creator.first_name} {contribution.creator.last_name}",
			msisdn=contribution.creator.phone_number,
			account_number=str(contribution.wallet_account.id),
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
	



from django.urls import path, include
#
# api_v1_patterns = [
#     # Pledge Endpoints
#     path('pledge/create/', billing_admin.create_pledge, name='create_pledge'),
#     path('pledge/clear/', billing_admin.clear_pledge, name='clear_pledge'),
#     # Billing Admin Endpoints
#     path('wallet/balance/', billing_admin.wallet_balance, name='wallet_balance'),
#     path('wallet/mobile-money-transfer/', billing_admin.mobile_money_transfer, name='mobile_money_transfer'),
#     path('wallet/b2c-transfer/', billing_admin.b2c_transfer, name='b2c_transfer'),
#     path('wallet/c2b-payment/', billing_admin.c2b_payment, name='c2b_payment'),
#     path('wallet/query-mobile-money-transaction/', billing_admin.query_mobile_money_transaction,
#          name='query_transaction'),
#     # Callbacks
#     path('callbacks/b2c/', billing_admin.b2c_transfer_callback_url, name='b2c_callback'),
#     path('callbacks/c2b/', billing_admin.c2b_payment_callback_endpoint, name='c2b_callback'),
# ]
#
# urlpatterns = [
#     path('api/v1/', include(api_v1_patterns)),
#     path('health/', health_check, name='health_check'),
#     path('ready/', ready_check, name='ready_check'),
# ]