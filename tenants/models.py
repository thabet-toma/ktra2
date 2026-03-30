from django.db import models

class Currency(models.Model):
    CurrencyID = models.AutoField(primary_key=True)
    Code = models.CharField(max_length=3)
    Name = models.CharField(max_length=50, null=True, blank=True)
    Symbol = models.CharField(max_length=5, null=True, blank=True)
    IsBaseCurrency = models.BooleanField(default=False)

    class Meta:
        db_table = 'currencies'
        managed = True

    def __str__(self):
        return f"{self.Code} - {self.Name}"

class Tenant(models.Model):
    SUBSCRIPTION_PLANS = [
        ('Basic', 'Basic'),
        ('Pro', 'Pro'),
        ('Enterprise', 'Enterprise'),
    ]

    STATUS_CHOICES = [
        ('Active', 'Active'),
        ('Suspended', 'Suspended'),
        ('Trial', 'Trial'),
    ]

    TenantID = models.AutoField(primary_key=True)
    CompanyName = models.CharField(max_length=150)
    SubscriptionPlan = models.CharField(max_length=50, choices=SUBSCRIPTION_PLANS)
    Status = models.CharField(max_length=50, choices=STATUS_CHOICES, default='Trial')
    CreatedAt = models.DateTimeField(auto_now_add=True)
    DomainName = models.CharField(max_length=100, unique=True, null=True, blank=True)

    class Meta:
        db_table = 'tenants'
        managed = True

    def __str__(self):
        return self.CompanyName
