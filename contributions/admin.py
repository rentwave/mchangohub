from django.contrib import admin

from contributions.models import Contribution


@admin.register(Contribution)
class ContributionAdmin(admin.ModelAdmin):
    list_display = (
        'name', 'creator', 'target_amount', 'end_date', 'status',
        'date_created', 'date_modified',
    )
    list_filter = ('status', 'date_created', 'end_date')
    search_fields = (
        'name', 'description', 'creator__username', 'creator__email', 'creator__phone_number',
        'creator__first_name', 'creator__last_name',
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
