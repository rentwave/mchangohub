from decimal import Decimal
from django.db.models import Sum, Count, Q, Avg
from django.utils import timezone
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import logging

from django.utils.html import format_html

from billing.models import RevenueLog, calculate_fair_tiered_charge, WalletTransaction, CHARGE_TIERS

logger = logging.getLogger(__name__)


class RevenueAnalytics:
    """
    Comprehensive revenue analytics and reporting utilities.
    """

    @staticmethod
    def get_revenue_summary(start_date: Optional[datetime] = None,
                            end_date: Optional[datetime] = None) -> Dict:
        """
        Get comprehensive revenue summary for a date range.
        If no dates provided, returns all-time summary.
        """
        queryset = RevenueLog.objects.all()

        if start_date and end_date:
            queryset = queryset.filter(date_created__range=[start_date, end_date])
        elif start_date:
            queryset = queryset.filter(date_created__gte=start_date)
        elif end_date:
            queryset = queryset.filter(date_created__lte=end_date)

        summary = queryset.aggregate(
            total_revenue=Sum('amount'),
            topup_revenue=Sum('amount', filter=Q(revenue_type='topup_charge')),
            withdrawal_revenue=Sum('amount', filter=Q(revenue_type='withdrawal_charge')),
            adjustment_revenue=Sum('amount', filter=Q(revenue_type='adjustment')),

            total_transactions=Count('id'),
            topup_transactions=Count('id', filter=Q(revenue_type='topup_charge')),
            withdrawal_transactions=Count('id', filter=Q(revenue_type='withdrawal_charge')),

            avg_topup_charge=Avg('amount', filter=Q(revenue_type='topup_charge')),
            avg_withdrawal_charge=Avg('amount', filter=Q(revenue_type='withdrawal_charge')),
        )
        # Convert None values to Decimal('0.00')
        for key, value in summary.items():
            if value is None:
                summary[key] = Decimal('0.00') if 'avg' in key or 'revenue' in key else 0

        return {
            'period': {
                'start_date': start_date.date() if start_date else None,
                'end_date': end_date.date() if end_date else None,
            },
            'revenue': {
                'total': summary['total_revenue'],
                'topup_charges': summary['topup_revenue'],
                'withdrawal_charges': summary['withdrawal_revenue'],
                'adjustments': summary['adjustment_revenue'],
            },
            'transactions': {
                'total_count': summary['total_transactions'],
                'topup_count': summary['topup_transactions'],
                'withdrawal_count': summary['withdrawal_transactions'],
            },
            'averages': {
                'avg_topup_charge': summary['avg_topup_charge'],
                'avg_withdrawal_charge': summary['avg_withdrawal_charge'],
            }
        }

    @staticmethod
    def get_daily_revenue_trend(days: int = 30) -> List[Dict]:
        """
        Get daily revenue trend for the last N days.
        """
        end_date = timezone.now().date()
        start_date = end_date - timedelta(days=days)

        daily_data = []
        current_date = start_date

        while current_date <= end_date:
            day_summary = RevenueLog.objects.daily_revenue_summary(current_date)
            daily_data.append(day_summary)
            current_date += timedelta(days=1)

        return daily_data

    @staticmethod
    def get_revenue_by_charge_tiers() -> List[Dict]:
        """
        Analyze revenue distribution across charge tiers.
        """
        revenue_logs = RevenueLog.objects.filter(
            revenue_type__in=['topup_charge', 'withdrawal_charge']
        ).values('original_amount', 'amount', 'revenue_type')

        tier_analysis = []
        for lower, upper, rate in CHARGE_TIERS:
            tier_revenue = Decimal('0.00')
            tier_count = 0
            tier_avg_amount = Decimal('0.00')
            tier_logs = [
                log for log in revenue_logs
                if lower < log['original_amount'] <= upper
            ]

            if tier_logs:
                tier_revenue = sum(Decimal(str(log['amount'])) for log in tier_logs)
                tier_count = len(tier_logs)
                tier_avg_amount = sum(Decimal(str(log['original_amount'])) for log in tier_logs) / tier_count

            tier_analysis.append({
                'tier_range': f"{lower + 1}-{upper}",
                'rate': f"{float(rate * 100):.1f}%",
                'revenue': tier_revenue,
                'transaction_count': tier_count,
                'avg_transaction_amount': tier_avg_amount,
                'revenue_per_transaction': tier_revenue / tier_count if tier_count > 0 else Decimal('0.00')
            })

        # Add the highest tier (>10M)
        high_tier_logs = [
            log for log in revenue_logs
            if log['original_amount'] > 10000000
        ]

        if high_tier_logs:
            high_tier_revenue = sum(Decimal(str(log['amount'])) for log in high_tier_logs)
            high_tier_count = len(high_tier_logs)
            high_tier_avg = sum(Decimal(str(log['original_amount'])) for log in high_tier_logs) / high_tier_count

            tier_analysis.append({
                'tier_range': '>10,000,000',
                'rate': '5.0%',
                'revenue': high_tier_revenue,
                'transaction_count': high_tier_count,
                'avg_transaction_amount': high_tier_avg,
                'revenue_per_transaction': high_tier_revenue / high_tier_count
            })

        return tier_analysis

    @staticmethod
    def get_pending_vs_realized_revenue() -> Dict:
        """
        Compare pending revenue vs realized revenue.
        """
        from django.db.models import Case, When

        revenue_status = RevenueLog.objects.extra(
            select={
                'status': "JSON_EXTRACT(metadata, '$.status')"
            }
        ).aggregate(
            pending_revenue=Sum(
                Case(
                    When(metadata__status='pending', then='amount'),
                    default=Decimal('0.00')
                )
            ),
            realized_revenue=Sum(
                Case(
                    When(metadata__status='realized', then='amount'),
                    default=Decimal('0.00')
                )
            ),
            unrealized_revenue=Sum(
                Case(
                    When(metadata__status='unrealized', then='amount'),
                    default=Decimal('0.00')
                )
            )
        )

        # Handle None values
        for key in ['pending_revenue', 'realized_revenue', 'unrealized_revenue']:
            if revenue_status[key] is None:
                revenue_status[key] = Decimal('0.00')

        total_expected = revenue_status['pending_revenue'] + revenue_status['realized_revenue']
        realization_rate = (
                    revenue_status['realized_revenue'] / total_expected * 100) if total_expected > 0 else Decimal(
            '0.00')

        return {
            'pending_revenue': revenue_status['pending_revenue'],
            'realized_revenue': revenue_status['realized_revenue'],
            'unrealized_revenue': revenue_status['unrealized_revenue'],
            'total_expected_revenue': total_expected,
            'realization_rate_percentage': realization_rate,
        }

    @staticmethod
    def get_top_revenue_accounts(limit: int = 10) -> List[Dict]:
        """
        Get accounts that generate the most revenue.
        """
        top_accounts = RevenueLog.objects.values(
            'wallet_account__account_number',
            'wallet_account__contribution__name'  # Assuming contribution has a name field
        ).annotate(
            total_revenue=Sum('amount'),
            transaction_count=Count('id'),
            avg_revenue_per_transaction=Avg('amount')
        ).order_by('-total_revenue')[:limit]

        return [
            {
                'account_number': account['wallet_account__account_number'],
                'contribution_name': account['wallet_account__contribution__name'],
                'total_revenue': account['total_revenue'],
                'transaction_count': account['transaction_count'],
                'avg_revenue_per_transaction': account['avg_revenue_per_transaction'],
            }
            for account in top_accounts
        ]

    @staticmethod
    def get_monthly_revenue_report(year: int = None, month: int = None) -> Dict:
        """
        Get detailed monthly revenue report.
        """
        if year is None:
            year = timezone.now().year
        if month is None:
            month = timezone.now().month

        start_date = datetime(year, month, 1)
        if month == 12:
            end_date = datetime(year + 1, 1, 1) - timedelta(days=1)
        else:
            end_date = datetime(year, month + 1, 1) - timedelta(days=1)

        monthly_data = RevenueAnalytics.get_revenue_summary(start_date, end_date)
        daily_trend = RevenueAnalytics.get_daily_revenue_trend(days=31)

        # Filter daily trend for the specific month
        month_daily_trend = [
            day for day in daily_trend
            if day['date'].year == year and day['date'].month == month
        ]

        return {
            'month': f"{year}-{month:02d}",
            'summary': monthly_data,
            'daily_breakdown': month_daily_trend,
            'peak_day': max(month_daily_trend, key=lambda x: x['total']) if month_daily_trend else None,
            'lowest_day': min(month_daily_trend, key=lambda x: x['total']) if month_daily_trend else None,
        }


class RevenueReporting:
    """
    Revenue reporting utilities for generating formatted reports.
    """

    @staticmethod
    def generate_daily_report(date: datetime.date = None) -> str:
        """Generate a formatted daily revenue report."""
        if date is None:
            date = timezone.now().date()

        summary = RevenueLog.objects.daily_revenue_summary(date)

        report = f"""
DAILY REVENUE REPORT - {date.strftime('%Y-%m-%d')}
{'=' * 50}

REVENUE BREAKDOWN:
  TopUp Charges:      KES {summary['topup_charges']:,.2f}
  Withdrawal Charges: KES {summary['withdrawal_charges']:,.2f}
  Adjustments:        KES {summary['adjustments']:,.2f}
  {'─' * 40}
  TOTAL REVENUE:      KES {summary['total']:,.2f}

TRANSACTION ACTIVITY:
  Total Transactions: {RevenueLog.objects.filter(date_created__date=date).count():,}

STATUS BREAKDOWN:
"""

        # Get status breakdown
        status_breakdown = RevenueLog.objects.filter(
            date_created__date=date
        ).extra(
            select={'status': "JSON_EXTRACT(metadata, '$.status')"}
        ).values('status').annotate(
            count=Count('id'),
            revenue=Sum('amount')
        )

        for status in status_breakdown:
            status_name = status['status'] or 'Unknown'
            report += f"  {status_name.title():12}: {status['count']:,} transactions, KES {status['revenue']:,.2f}\n"

        return report

    @staticmethod
    def generate_monthly_summary_report(year: int = None, month: int = None) -> str:
        """Generate a formatted monthly summary report."""
        monthly_data = RevenueAnalytics.get_monthly_revenue_report(year, month)

        report = f"""
MONTHLY REVENUE SUMMARY - {monthly_data['month']}
{'=' * 60}

TOTAL REVENUE: KES {monthly_data['summary']['revenue']['total']:,.2f}

REVENUE BY SOURCE:
  TopUp Charges:      KES {monthly_data['summary']['revenue']['topup_charges']:,.2f}
  Withdrawal Charges: KES {monthly_data['summary']['revenue']['withdrawal_charges']:,.2f}  
  Adjustments:        KES {monthly_data['summary']['revenue']['adjustments']:,.2f}

TRANSACTION VOLUME:
  Total Transactions: {monthly_data['summary']['transactions']['total_count']:,}
  TopUp Transactions: {monthly_data['summary']['transactions']['topup_count']:,}
  Withdrawal Transactions: {monthly_data['summary']['transactions']['withdrawal_count']:,}

AVERAGE CHARGES:
  Avg TopUp Charge:   KES {monthly_data['summary']['averages']['avg_topup_charge']:,.2f}
  Avg Withdrawal Charge: KES {monthly_data['summary']['averages']['avg_withdrawal_charge']:,.2f}

DAILY PERFORMANCE:
"""

        if monthly_data['peak_day']:
            report += f"  Peak Day:   {monthly_data['peak_day']['date']} - KES {monthly_data['peak_day']['total']:,.2f}\n"

        if monthly_data['lowest_day']:
            report += f"  Lowest Day: {monthly_data['lowest_day']['date']} - KES {monthly_data['lowest_day']['total']:,.2f}\n"

        return report

    @staticmethod
    def generate_charge_tier_analysis_report() -> str:
        """Generate a formatted charge tier analysis report."""
        tier_data = RevenueAnalytics.get_revenue_by_charge_tiers()

        report = """
CHARGE TIER ANALYSIS REPORT
{'=' * 60}

REVENUE BY TRANSACTION SIZE:
"""

        total_revenue = sum(tier['revenue'] for tier in tier_data)
        total_transactions = sum(tier['transaction_count'] for tier in tier_data)

        for tier in tier_data:
            if tier['transaction_count'] > 0:
                revenue_percentage = (tier['revenue'] / total_revenue * 100) if total_revenue > 0 else 0
                transaction_percentage = (
                            tier['transaction_count'] / total_transactions * 100) if total_transactions > 0 else 0

                report += f"""
Tier: {tier['tier_range']} (Rate: {tier['rate']})
  Revenue:        KES {tier['revenue']:,.2f} ({revenue_percentage:.1f}% of total)
  Transactions:   {tier['transaction_count']:,} ({transaction_percentage:.1f}% of total)
  Avg Amount:     KES {tier['avg_transaction_amount']:,.2f}
  Avg Charge:     KES {tier['revenue_per_transaction']:,.2f}
"""

        report += f"""
{'─' * 60}
TOTALS:
  Total Revenue:      KES {total_revenue:,.2f}
  Total Transactions: {total_transactions:,}
  Overall Avg Charge: KES {(total_revenue / total_transactions if total_transactions > 0 else 0):,.2f}
"""

        return report


class RevenueValidation:
    """
    Utilities for validating revenue data integrity.
    """

    @staticmethod
    def validate_charge_calculations() -> Dict:
        """
        Validate that recorded charges match calculated charges.
        """
        discrepancies = []
        total_validated = 0
        total_discrepancies = 0

        revenue_logs = RevenueLog.objects.filter(
            revenue_type__in=['topup_charge', 'withdrawal_charge']
        ).select_related('parent_transaction')

        for log in revenue_logs:
            original_amount = float(log.original_amount)
            recorded_charge = log.amount
            calculated_charge = Decimal(str(calculate_fair_tiered_charge(original_amount)))

            total_validated += 1

            if abs(recorded_charge - calculated_charge) > Decimal('0.01'):
                total_discrepancies += 1
                discrepancies.append({
                    'revenue_log_id': log.id,
                    'transaction_reference': log.reference,
                    'original_amount': log.original_amount,
                    'recorded_charge': recorded_charge,
                    'calculated_charge': calculated_charge,
                    'difference': recorded_charge - calculated_charge,
                })

        return {
            'total_validated': total_validated,
            'total_discrepancies': total_discrepancies,
            'accuracy_percentage': ((
                                                total_validated - total_discrepancies) / total_validated * 100) if total_validated > 0 else 100,
            'discrepancies': discrepancies[:100],  # Limit to first 100 discrepancies
        }

    @staticmethod
    def check_revenue_integrity() -> Dict:
        """
        Check overall revenue data integrity.
        """
        issues = []

        negative_revenues = RevenueLog.objects.filter(amount__lt=0).count()
        if negative_revenues > 0:
            issues.append(f"Found {negative_revenues} revenue logs with negative amounts")

        orphaned_revenues = RevenueLog.objects.filter(parent_transaction__isnull=True).count()
        if orphaned_revenues > 0:
            issues.append(f"Found {orphaned_revenues} revenue logs without parent transactions")

        invalid_references = 0
        for revenue in RevenueLog.objects.select_related('parent_transaction'):
            if not WalletTransaction.objects.filter(reference=revenue.reference).exists():
                invalid_references += 1

        if invalid_references > 0:
            issues.append(f"Found {invalid_references} revenue logs with invalid transaction references")

        return {
            'total_issues': len(issues),
            'issues': issues,
            'integrity_status': 'GOOD' if len(issues) == 0 else 'ISSUES_FOUND'
        }


# Django Admin utilities for better revenue management
class RevenueAdminMixin:
    """
    Mixin for Django admin to add revenue-related functionality.
    """

    def get_daily_revenue_summary(self, obj):
        """Admin method to show daily revenue summary."""
        if hasattr(obj, 'date_created'):
            date = obj.date_created.date()
            summary = RevenueLog.objects.daily_revenue_summary(date)
            return f"KES {summary['total']:,.2f}"
        return "N/A"

    get_daily_revenue_summary.short_description = "Daily Revenue"

    def get_charge_rate_display(self, obj):
        """Admin method to display charge rate as percentage."""
        if hasattr(obj, 'charge_rate') and obj.charge_rate:
            return f"{float(obj.charge_rate * 100):.2f}%"
        return "N/A"

    get_charge_rate_display.short_description = "Charge Rate"

    def get_revenue_status(self, obj):
        """Admin method to display revenue status from metadata."""
        if hasattr(obj, 'metadata') and obj.metadata:
            status = obj.metadata.get('status', 'unknown')
            colors = {
                'pending': 'orange',
                'realized': 'green',
                'unrealized': 'red',
                'unknown': 'gray'
            }
            color = colors.get(status, 'gray')
            return format_html(
                '<span style="color: {};">{}</span>',
                color,
                status.title()
            )
        return "Unknown"

    get_revenue_status.short_description = "Status"