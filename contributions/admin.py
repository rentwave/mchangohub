from django.contrib import admin
from django.utils.html import format_html
from datetime import date, datetime
from contributions.models import Contribution


@admin.register(Contribution)
class ContributionAdmin(admin.ModelAdmin):
    list_display = (
        'name', 'creator', 'colored_status', 'target_amount',
        'amount_contributed_display', 'progress_balance', 'progress_days',
        'end_date', 'date_created',
    )
    list_filter = ('status', 'date_created', 'end_date')
    search_fields = (
        'name', 'description', 'creator__username', 'creator__email',
        'creator__phone_number', 'creator__first_name', 'creator__last_name',
    )
    ordering = ('-date_created',)
    date_hierarchy = 'date_created'
    readonly_fields = ('date_created', 'date_modified')

    fieldsets = (
        (None, {
            'fields': ('name', 'description', 'creator', 'target_amount', 'end_date', 'status')
        }),
        ('Timestamps', {
            'fields': ('date_created', 'date_modified'),
        }),
    )

    def colored_status(self, obj):
        """Color coded status."""
        color_map = {
            "Active": "green",
            "Completed": "blue",
            "Pending": "orange",
            "Cancelled": "red",
        }
        color = color_map.get(obj.status, "gray")
        return format_html('<span style="color: {}; font-weight: bold;">{}</span>', color, obj.status)
    colored_status.short_description = "Status"
    
    def amount_contributed_display(self, obj):
        """Color-coded amount contributed."""
        percentage = (obj.total_contributed / obj.target_amount) * 100 if obj.target_amount else 0
        color = "green" if percentage >= 75 else "orange" if percentage >= 50 else "red"
        return format_html(
            '<span style="color: {}; font-weight: bold;">{} ({}%)</span>',
            color,
            obj.total_contributed,
            f"{percentage:.0f}"
        )
    
    amount_contributed_display.short_description = "Contributed"
    
    def progress_balance(self, obj):
        """Progress bar for balance."""
        target = obj.target_amount or 0
        contributed = obj.total_contributed or 0
        balance = max(target - contributed, 0)
        percentage = (contributed / target * 100) if target else 0
        
        percentage_str = f"{percentage:.0f}"
        
        return format_html(
            """
            <div style="width:120px; background:#eee; border-radius:5px; overflow:hidden;">
                <div style="width:{}%; background:#38bdf8; color:white; text-align:center; font-size:11px;">
                    {}%
                </div>
            </div>
            <small>Bal: {}</small>
            """,
            percentage_str, percentage_str, balance
        )
    
    progress_balance.short_description = "Balance Progress"
    
    def progress_days(self, obj):
        """Progress bar for days remaining."""
        if not obj.end_date:
            return "-"
        
        start_date = obj.date_created.date() if isinstance(obj.date_created, datetime) else obj.date_created
        end_date = obj.end_date.date() if isinstance(obj.end_date, datetime) else obj.end_date
        
        total_days = (end_date - start_date).days
        remaining_days = (end_date - date.today()).days
        if total_days <= 0:
            return "Expired"
        percentage = (remaining_days / total_days) * 100
        percentage = max(0, min(100, percentage))
        return format_html(
            """
            <div style="width:120px; background:#eee; border-radius:5px; overflow:hidden;">
                <div style="width:{}%; background:{}; color:white; text-align:center; font-size:11px;">
                    {}d
                </div>
            </div>
            """,
            percentage, ("green" if remaining_days > 5 else "red"), remaining_days
        )
    progress_days.short_description = "Days Left"
