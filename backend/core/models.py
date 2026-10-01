import uuid
from decimal import Decimal, ROUND_HALF_UP
from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, MaxValueValidator


def uid(): return uuid.uuid4()

class OrgUnit(models.Model):
    id = models.UUIDField(primary_key=True, default=uid, editable=False)
    name = models.CharField(max_length=160)
    kind = models.CharField(max_length=20, choices=[(k,k) for k in ['church','diocese','pastorate','parish']])
    parent = models.ForeignKey('self', null=True, blank=True, on_delete=models.PROTECT, related_name='children')
    version = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    def clean(self):
        required = {'church':None,'diocese':'church','pastorate':'diocese','parish':'pastorate'}
        if (self.parent.kind if self.parent_id else None) != required.get(self.kind):
            raise ValidationError({'parent':'Fel nivå i organisationshierarkin.'})
        if self.parent_id == self.id: raise ValidationError({'parent':'En enhet kan inte vara sin egen överordnade.'})
    def __str__(self): return self.name

class OrgRevision(models.Model):
    org = models.ForeignKey(OrgUnit, on_delete=models.PROTECT)
    name = models.CharField(max_length=160)
    parent_id_snapshot = models.UUIDField(null=True)
    valid_from = models.DateTimeField(auto_now_add=True)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)

class Membership(models.Model):
    active = models.BooleanField(default=True)
    version = models.PositiveIntegerField(default=1)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    org = models.ForeignKey(OrgUnit, on_delete=models.PROTECT)
    role = models.CharField(max_length=20, choices=[(k,k) for k in ['admin','manager','worker','reader','contractor']])
    descendants = models.BooleanField(default=False)
    finance = models.BooleanField(default=False)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['user','org'], name='unique_membership')]

class MFAProfile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    encrypted_secret = models.TextField()
    enabled = models.BooleanField(default=False)
    last_counter = models.BigIntegerField(default=-1)

class BaseRecord(models.Model):
    id = models.UUIDField(primary_key=True, default=uid, editable=False)
    org = models.ForeignKey(OrgUnit, on_delete=models.PROTECT)
    version = models.PositiveIntegerField(default=1)
    archived = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta: abstract = True

class Asset(BaseRecord):
    name = models.CharField(max_length=180)
    kind = models.CharField(max_length=20, choices=[(k,k) for k in ['property','building','land','premises','room','object']])
    parent = models.ForeignKey('self', null=True, blank=True, on_delete=models.PROTECT, related_name='children')
    address = models.CharField(max_length=240, blank=True)
    designation = models.CharField(max_length=100, blank=True)
    area = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True, validators=[MinValueValidator(0)])
    owner = models.CharField(max_length=180, blank=True)
    manager = models.CharField(max_length=180, blank=True)
    description = models.TextField(blank=True)
    public = models.BooleanField(default=False)
    def clean(self):
        if self.parent_id:
            if self.parent.org_id != self.org_id: raise ValidationError({'parent':'Objekt och överordnat objekt måste tillhöra samma enhet.'})
            current = self.parent
            visited = {self.id}
            while current:
                if current.id in visited: raise ValidationError({'parent':'Cirkulär objekthierarki.'})
                visited.add(current.id); current = current.parent
            levels={'property':0,'land':1,'building':1,'premises':2,'room':3,'object':4}
            if levels[self.parent.kind] >= levels[self.kind]: raise ValidationError({'parent':'Välj en högre objektnivå.'})
    def __str__(self): return self.name

class WorkOrder(BaseRecord):
    number = models.PositiveBigIntegerField(unique=True, editable=False)
    asset = models.ForeignKey(Asset, on_delete=models.PROTECT)
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    category = models.CharField(max_length=80, default='Drift')
    kind = models.CharField(max_length=20, choices=[(k,k) for k in ['issue','round','inspection']], default='issue')
    priority = models.CharField(max_length=10, choices=[(k,k) for k in ['low','normal','high','urgent']], default='normal')
    status = models.CharField(max_length=20, choices=[(k,k) for k in ['new','planned','in_progress','completed','verified','cancelled']], default='new')
    due_date = models.DateField(null=True, blank=True)
    assigned_to = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT)
    checklist = models.JSONField(default=list, blank=True)
    checklist_results = models.JSONField(default=dict, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    verified_at = models.DateTimeField(null=True, blank=True)
    source = models.CharField(max_length=20, default='internal', editable=False)
    reporter_email = models.EmailField(blank=True)
    public_token_hash = models.CharField(max_length=64, blank=True, db_index=True)
    schedule = models.ForeignKey('Schedule', null=True, blank=True, on_delete=models.PROTECT)
    occurrence = models.DateField(null=True, blank=True)
    class Meta:
        indexes = [models.Index(fields=['org','status','due_date'])]
        constraints = [models.UniqueConstraint(fields=['schedule','occurrence'], name='unique_schedule_occurrence')]
    def clean(self):
        if self.asset_id and self.asset.org_id != self.org_id: raise ValidationError({'asset':'Fel organisationsenhet.'})
        if not isinstance(self.checklist,list) or any(not isinstance(x,str) or len(x)>300 for x in self.checklist): raise ValidationError({'checklist':'Checklistan ska innehålla textrader.'})
        if len(self.checklist)>100: raise ValidationError({'checklist':'Högst 100 kontrollpunkter.'})
        if not isinstance(self.checklist_results,dict): raise ValidationError({'checklist_results':'Ogiltiga kontrollsvar.'})
        for k,v in self.checklist_results.items():
            if k not in [str(i) for i in range(len(self.checklist))] or v not in ['ok','deviation','na']: raise ValidationError({'checklist_results':'Ogiltig kontrollpunkt eller svar.'})

class WorkComment(models.Model):
    id = models.UUIDField(primary_key=True, default=uid, editable=False)
    work = models.ForeignKey(WorkOrder, on_delete=models.PROTECT, related_name='comments')
    author = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    text = models.TextField()
    visibility = models.CharField(max_length=15, choices=[(x,x) for x in ['internal','contractor','public']], default='internal')
    created_at = models.DateTimeField(auto_now_add=True)

class CostEntry(BaseRecord):
    work = models.ForeignKey(WorkOrder, on_delete=models.PROTECT, related_name='costs')
    kind = models.CharField(max_length=20, choices=[(x,x) for x in ['time','material','expense']])
    description = models.CharField(max_length=200)
    quantity = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal('0.01'))])
    unit_price = models.DecimalField(max_digits=14, decimal_places=2, validators=[MinValueValidator(0)])
    date = models.DateField()
    @property
    def total(self): return (self.quantity*self.unit_price).quantize(Decimal('.01'), rounding=ROUND_HALF_UP)
    def clean(self):
        if self.work_id and self.work.org_id != self.org_id: raise ValidationError({'work':'Fel organisationsenhet.'})

class Schedule(BaseRecord):
    asset = models.ForeignKey(Asset, on_delete=models.PROTECT)
    title = models.CharField(max_length=200)
    kind = models.CharField(max_length=20, choices=[('round','Rond'),('inspection','Besiktning')], default='round')
    category = models.CharField(max_length=80, default='Tillsyn')
    anchor_date = models.DateField()
    next_date = models.DateField()
    interval = models.PositiveIntegerField(default=1, validators=[MinValueValidator(1),MaxValueValidator(1200)])
    unit = models.CharField(max_length=10, choices=[(x,x) for x in ['day','week','month','year']], default='month')
    checklist = models.JSONField(default=list, blank=True)
    assigned_to = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT)
    def clean(self):
        if self.asset_id and self.asset.org_id != self.org_id: raise ValidationError({'asset':'Fel organisationsenhet.'})
        if self.next_date < self.anchor_date: raise ValidationError({'next_date':'Nästa datum måste vara efter startdatum.'})
        if not isinstance(self.checklist,list) or len(self.checklist)>100 or any(not isinstance(x,str) or len(x)>300 for x in self.checklist): raise ValidationError({'checklist':'Högst 100 textrader.'})

class Maintenance(BaseRecord):
    asset = models.ForeignKey(Asset, on_delete=models.PROTECT)
    title = models.CharField(max_length=200)
    category = models.CharField(max_length=100, default='Byggnad')
    year = models.PositiveIntegerField(validators=[MinValueValidator(1900),MaxValueValidator(2200)])
    interval_years = models.PositiveIntegerField(default=0, validators=[MaxValueValidator(100)])
    quantity = models.DecimalField(max_digits=12, decimal_places=2, default=1, validators=[MinValueValidator(Decimal('.01'))])
    unit = models.CharField(max_length=20, default='st')
    unit_price = models.DecimalField(max_digits=14, decimal_places=2, validators=[MinValueValidator(0)])
    cost_factor = models.DecimalField(max_digits=7, decimal_places=4, default=Decimal('1.25'), validators=[MinValueValidator(0)])
    index_percent = models.DecimalField(max_digits=6, decimal_places=2, default=0, validators=[MinValueValidator(0),MaxValueValidator(100)])
    price_year = models.PositiveIntegerField(validators=[MinValueValidator(1900),MaxValueValidator(2200)])
    account = models.CharField(max_length=100, blank=True)
    funding_possible = models.DecimalField(max_digits=14, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    funding_granted = models.DecimalField(max_digits=14, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    note = models.TextField(blank=True)
    work = models.ForeignKey(WorkOrder, null=True, blank=True, on_delete=models.PROTECT)
    def budget_for(self, year=None):
        y = self.year if year is None else year
        return (self.quantity*self.unit_price*self.cost_factor*(Decimal(1)+Decimal(self.index_percent)/Decimal(100))**max(0,y-self.price_year)).quantize(Decimal('.01'),rounding=ROUND_HALF_UP)
    def clean(self):
        if self.asset_id and self.asset.org_id != self.org_id: raise ValidationError({'asset':'Fel organisationsenhet.'})
        if self.work_id and (self.work.org_id != self.org_id or self.work.asset_id != self.asset_id): raise ValidationError({'work':'Arbetsordern måste gälla samma objekt.'})

class BudgetScenario(BaseRecord):
    name = models.CharField(max_length=180)
    start_year = models.PositiveIntegerField(validators=[MinValueValidator(1900),MaxValueValidator(2200)])
    years = models.PositiveIntegerField(default=10, validators=[MinValueValidator(1),MaxValueValidator(30)])
    state = models.CharField(max_length=15, default='draft', choices=[('draft','Utkast'),('published','Fastställd')])
    lines = models.JSONField(default=list, blank=True)
    org_snapshot = models.JSONField(default=list, blank=True)
    published_at = models.DateTimeField(null=True, blank=True)

class RegistryEntry(BaseRecord):
    asset = models.ForeignKey(Asset, on_delete=models.PROTECT)
    title = models.CharField(max_length=180)
    kind = models.CharField(max_length=20, choices=[(x,x) for x in ['care_plan','tree','inventory','inspection','sba','safety','contract','warranty','nki']])
    description = models.TextField(blank=True)
    reference = models.CharField(max_length=100, blank=True)
    responsible = models.CharField(max_length=160, blank=True)
    start_date = models.DateField(null=True, blank=True)
    due_date = models.DateField(null=True, blank=True)
    state = models.CharField(max_length=15, default='active', choices=[('active','Aktiv'),('closed','Avslutad')])
    score = models.PositiveIntegerField(null=True, blank=True, validators=[MaxValueValidator(10)])
    def clean(self):
        if self.asset_id and self.asset.org_id != self.org_id: raise ValidationError({'asset':'Fel organisationsenhet.'})
        if self.start_date and self.due_date and self.due_date < self.start_date: raise ValidationError({'due_date':'Slutdatum är före startdatum.'})
        if self.kind=='nki' and self.score is None: raise ValidationError({'score':'NKI kräver ett betyg 0–10.'})

class Meter(BaseRecord):
    asset = models.ForeignKey(Asset, on_delete=models.PROTECT)
    name = models.CharField(max_length=160)
    medium = models.CharField(max_length=20, choices=[(x,x) for x in ['electricity','heat','water','cooling','hours']])
    unit = models.CharField(max_length=15, choices=[('kWh','kWh'),('m³','m³'),('h','h')])
    serial = models.CharField(max_length=100, blank=True)
    def clean(self):
        if self.asset_id and self.asset.org_id != self.org_id: raise ValidationError({'asset':'Fel organisationsenhet.'})
        expected = {'water':'m³','hours':'h','electricity':'kWh','heat':'kWh','cooling':'kWh'}
        if expected.get(self.medium)!=self.unit: raise ValidationError({'unit':'Fel enhet för mätartypen.'})

class Reading(BaseRecord):
    meter = models.ForeignKey(Meter, on_delete=models.PROTECT, related_name='readings')
    date = models.DateField()
    value = models.DecimalField(max_digits=18, decimal_places=3, validators=[MinValueValidator(0)])
    replacement = models.BooleanField(default=False)
    old_final = models.DecimalField(max_digits=18, decimal_places=3, null=True, blank=True, validators=[MinValueValidator(0)])
    new_initial = models.DecimalField(max_digits=18, decimal_places=3, null=True, blank=True, validators=[MinValueValidator(0)])
    serial = models.CharField(max_length=100, blank=True)
    class Meta: constraints = [models.UniqueConstraint(fields=['meter','date'], name='one_reading_per_date')]

class Key(BaseRecord):
    asset = models.ForeignKey(Asset, on_delete=models.PROTECT)
    name = models.CharField(max_length=180)
    system = models.CharField(max_length=100)
    serial = models.CharField(max_length=100)
    condition = models.CharField(max_length=10, default='ok', choices=[('ok','Hel'),('lost','Borttappad'),('broken','Trasig')])
    def clean(self):
        if self.asset_id and self.asset.org_id != self.org_id: raise ValidationError({'asset':'Fel organisationsenhet.'})
    class Meta: constraints = [models.UniqueConstraint(fields=['org','system','serial'],name='key_unique_serial')]

class KeyLoan(BaseRecord):
    key = models.ForeignKey(Key, on_delete=models.PROTECT, related_name='loans')
    borrower = models.CharField(max_length=180)
    due_date = models.DateField()
    returned_at = models.DateTimeField(null=True, blank=True)
    class Meta: constraints = [models.UniqueConstraint(fields=['key'], condition=models.Q(returned_at__isnull=True), name='one_active_key_loan')]

class Document(BaseRecord):
    asset = models.ForeignKey(Asset, on_delete=models.PROTECT)
    work = models.ForeignKey(WorkOrder, null=True, blank=True, on_delete=models.PROTECT)
    title = models.CharField(max_length=180)
    file_key = models.CharField(max_length=300)
    sha256 = models.CharField(max_length=64)
    size = models.PositiveBigIntegerField()
    mime = models.CharField(max_length=100)
    revision_of = models.ForeignKey('self', null=True, blank=True, on_delete=models.PROTECT)
    shared_contractor = models.BooleanField(default=False)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)

class ReportTemplate(BaseRecord):
    name = models.CharField(max_length=180)
    config = models.JSONField(default=dict)

class ReportSnapshot(BaseRecord):
    title = models.CharField(max_length=180)
    report_type = models.CharField(max_length=30)
    filters = models.JSONField(default=dict)
    data = models.JSONField(default=dict)
    organization_snapshot = models.JSONField(default=list)
    included_org_ids = models.JSONField(default=list)
    financial = models.BooleanField(default=False)
    calculation_version = models.CharField(max_length=30, default='1.0')
    generated_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)

class Subscription(BaseRecord):
    name = models.CharField(max_length=180)
    report_type = models.CharField(max_length=30)
    config = models.JSONField(default=dict)
    recipient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    next_date = models.DateField()
    interval_days = models.PositiveIntegerField(default=7, validators=[MinValueValidator(1),MaxValueValidator(366)])

class AuditEvent(models.Model):
    id = models.BigAutoField(primary_key=True)
    org = models.ForeignKey(OrgUnit, null=True, on_delete=models.PROTECT)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    entity = models.CharField(max_length=80)
    entity_id = models.CharField(max_length=80)
    action = models.CharField(max_length=80)
    before = models.JSONField(default=dict)
    after = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

class MutationReceipt(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    key = models.UUIDField()
    fingerprint = models.CharField(max_length=64)
    response = models.JSONField(default=dict)
    status = models.PositiveIntegerField(default=200)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta: constraints = [models.UniqueConstraint(fields=['user','key'],name='unique_mutation_key')]

class PublicReceipt(models.Model):
    key = models.UUIDField(primary_key=True)
    fingerprint = models.CharField(max_length=64)
    work = models.ForeignKey(WorkOrder,on_delete=models.PROTECT)

class Job(models.Model):
    id = models.UUIDField(primary_key=True, default=uid, editable=False)
    kind = models.CharField(max_length=40)
    payload = models.JSONField(default=dict)
    dedupe_key = models.CharField(max_length=180, unique=True)
    status = models.CharField(max_length=15, default='pending')
    attempts = models.PositiveIntegerField(default=0)
    run_after = models.DateTimeField()
    locked_at = models.DateTimeField(null=True)
    last_error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

class RateBucket(models.Model):
    key = models.CharField(max_length=100, primary_key=True)
    count = models.PositiveIntegerField(default=0)
    started_at = models.DateTimeField()

class Counter(models.Model):
    name = models.CharField(max_length=60, primary_key=True)
    value = models.PositiveBigIntegerField(default=0)

class AccountSecurity(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    version = models.PositiveIntegerField(default=1)
    recovery_required = models.BooleanField(default=False)

class RecoveryCode(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    digest = models.CharField(max_length=64, unique=True)
    used_at = models.DateTimeField(null=True)
    created_at = models.DateTimeField(auto_now_add=True)

class MFAResetRequest(models.Model):
    id = models.UUIDField(primary_key=True, default=uid, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='mfa_reset_requests')
    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='requested_mfa_resets')
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.PROTECT, related_name='approved_mfa_resets')
    reason = models.CharField(max_length=500)
    version = models.PositiveIntegerField(default=1)
    account_version = models.PositiveIntegerField()
    state = models.CharField(max_length=20, default='pending')
    token_digest = models.CharField(max_length=64, blank=True)
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    used_at = models.DateTimeField(null=True)

class AIConfiguration(models.Model):
    id = models.PositiveSmallIntegerField(primary_key=True, default=1)
    version = models.PositiveIntegerField(default=1)
    enabled = models.BooleanField(default=False)
    endpoint = models.URLField(default='https://api.openai.com/v1')
    model = models.CharField(max_length=120, blank=True)
    encrypted_api_key = models.TextField(blank=True)
    daily_limit = models.PositiveIntegerField(default=100)
    allow_changes = models.BooleanField(default=False)
    organizations = models.ManyToManyField(OrgUnit, blank=True)

class AIRequest(models.Model):
    id = models.UUIDField(primary_key=True, default=uid, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    key = models.UUIDField()
    fingerprint = models.CharField(max_length=64)
    state = models.CharField(max_length=16, default='pending')
    encrypted_result = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['user','key'], name='unique_ai_request')]

class Inspection(BaseRecord):
    asset = models.ForeignKey(Asset,on_delete=models.PROTECT)
    series = models.UUIDField(default=uid,editable=False)
    title = models.CharField(max_length=200)
    scheduled_date = models.DateField()
    template_name = models.CharField(max_length=100)
    items = models.JSONField(default=list)
    answers = models.JSONField(default=dict)
    state = models.CharField(max_length=20,default='draft')
    supersedes = models.ForeignKey('self',null=True,blank=True,on_delete=models.PROTECT,related_name='corrections')
    follow_up_of = models.ForeignKey('self',null=True,blank=True,on_delete=models.PROTECT,related_name='followups')
    reason = models.CharField(max_length=500,blank=True)
    snapshot = models.JSONField(default=dict)
    published_at = models.DateTimeField(null=True,blank=True)

class InspectionFinding(BaseRecord):
    inspection = models.ForeignKey(Inspection,on_delete=models.PROTECT)
    series = models.UUIDField()
    item_key = models.CharField(max_length=80)
    title = models.CharField(max_length=300)
    note = models.TextField()
    state = models.CharField(max_length=20,default='open')
    work = models.ForeignKey(WorkOrder,null=True,blank=True,on_delete=models.PROTECT)
    verified_by = models.ForeignKey(settings.AUTH_USER_MODEL,null=True,blank=True,on_delete=models.PROTECT)
    verified_at = models.DateTimeField(null=True,blank=True)
    verification = models.ForeignKey(Inspection,null=True,blank=True,on_delete=models.PROTECT,related_name='verified_findings')
    class Meta:
        constraints=[models.UniqueConstraint(fields=['series','item_key'],name='unique_inspection_finding')]

__all__ = [name for name, obj in list(globals().items()) if isinstance(obj, type) and issubclass(obj, models.Model)]
