import uuid

from django.db import models

class BaseModel(models.Model):
    id = models.UUIDField(max_length=100, default=uuid.uuid4, unique=True, editable=False, primary_key=True)
    date_modified = models.DateTimeField(auto_now=True)
    date_created = models.DateTimeField(auto_now_add=True)
    synced = models.BooleanField(default=False)

    objects = models.Manager()


    class Meta(object):
        abstract = True


class GenericBaseModel(BaseModel):
    name = models.CharField(max_length=100)
    description = models.CharField(max_length=100, null=True, blank=True)

    class Meta(object):
        abstract = True



class State(GenericBaseModel):
    """States for life cycle of transactions and events"""
    
    abbreviation = models.CharField(max_length=10,blank=True, null=True)
    color = models.CharField(max_length=7, blank=True, null=True)
    class Meta(object):
        ordering = ('name',)
        unique_together = ('name',)

    def __str__(self):
        return '%s ' % self.name

    @classmethod
    def default_state(cls):
        """The default Active state."""
        # noinspection PyBroadException
        try:
            state = cls.objects.get(name='Active')
            return state.id
        except Exception:
            pass

    @classmethod
    def disabled_state(cls):
        """The default Disabled state."""
        # noinspection PyBroadException
        try:
            state = cls.objects.get(name='Disabled')
            return state
        except Exception:
            pass


class BalanceEntryType(GenericBaseModel):
    """A statement balance entry type e.g. "New", "Charge"""
    state = models.ForeignKey(State, on_delete=models.CASCADE, null=True, blank=True)
    def __str__(self):
        return '%s' % self.name

    class Meta(GenericBaseModel.Meta):
        """Meta Class"""
        ordering = ('name',)
        unique_together = ('name',)
        verbose_name = "Balance Entry Type"
        verbose_name_plural = "Balance Entry Types"


class ExecutionProfile(GenericBaseModel):
    """Defines the set of process execution rules to be applied to a particular operation e.g. Payment"""
    state = models.ForeignKey(State, on_delete=models.CASCADE, null=True, blank=True)
    def __str__(self):
        return '%s ' % self.name

    class Meta(object):
        verbose_name = "Execution Profile"
        verbose_name_plural = "Execution Profiles"


class RuleProfile(GenericBaseModel):
    """Defines the set of rules to be applied to a particular operation"""
    execution_profile = models.ForeignKey(ExecutionProfile, on_delete=models.CASCADE)
    order = models.IntegerField()
    sleep_seconds = models.IntegerField(default=0)  # the time to sleep before going to the next execution.
    state = models.ForeignKey(State, on_delete=models.CASCADE, null=True, blank=True)
    
    def __str__(self):
        return '%s %s' % (self.execution_profile, self.name)

    class Meta(object):
        ordering = ('execution_profile__name', 'order')
        verbose_name = "Rule Profile"
        verbose_name_plural = "Rule Profiles"


class RuleProfileCommand(GenericBaseModel):
    """Defines a particular command in a rule profile which will be executed when the rule profile is called"""
    rule_profile = models.ForeignKey(RuleProfile, on_delete=models.CASCADE)
    order = models.IntegerField()
    state = models.ForeignKey(State, on_delete=models.CASCADE)

    def __str__(self):
        return '%s - %s - %s ' % (self.name, self.rule_profile, self.state)

    class Meta(object):
        ordering = ('rule_profile__execution_profile__name', 'rule_profile__order', 'order')
        verbose_name = "Rule Profile Command"
        verbose_name_plural = "Rule Profile Commands"


class EntryType(GenericBaseModel):
    """Account journal entry types for accounting e.g. "Debit", "Credit", etc"""
    state = models.ForeignKey(State, on_delete=models.CASCADE, null=True, blank=True)
    def __str__(self):
        return '%s' % self.name

    class Meta(GenericBaseModel.Meta):
        ordering = ('name',)
        unique_together = ('name',)
        verbose_name = "Entry Type"
        verbose_name_plural = "Entry Types"
        


class AccountFieldType(GenericBaseModel):
    """Transaction account balance type e.g. "Available", "Current", "Reserved", "Uncleared", etc"""
    state = models.ForeignKey(State, on_delete=models.CASCADE)

    def __str__(self):
        return '%s ' % self.name

    class Meta(object):
        ordering = ('name',)
        unique_together = ('name',)
        verbose_name_plural = "Account Field Types"


class PaymentMethod(GenericBaseModel):
    """Payment method/channel used on transactions e.g. "Paybill", "BankTransfer", "Cheque", etc"""
    state = models.ForeignKey(State, on_delete=models.CASCADE)

    def __str__(self):
        return '%s ' % self.name

    class Meta(object):
        ordering = ('name',)
        unique_together = ('name',)
        verbose_name_plural = "Payment Methods"
