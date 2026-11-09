# Synthetic records for a freshly migrated, isolated QA database.
import os
from decimal import Decimal
from django.contrib.auth.models import Group, User
from insurance_requests.models import InsuranceRequest
from summaries.models import InsuranceOffer, InsuranceSummary

staff_group = Group.objects.get_or_create(name='Пользователи')[0]
user = User.objects.create_user('zs-operator', password=os.environ['FLOW_QA_ZS_PASSWORD'])
reader = User.objects.create_user('zs-colleague', password=os.environ['FLOW_QA_ZS_PASSWORD'])
user.groups.add(staff_group)
reader.groups.add(staff_group)
for dfa, party in [('FLOW-QA-01', 'lessee'), ('FLOW-QA-02', 'lessee'), ('FLOW-QA-02', 'lessor')]:
    req = InsuranceRequest.objects.create(
        dfa_number=dfa, client_name='Тестовый лизингополучатель', inn='0000000000',
        insurance_type='КАСКО', insurance_period='на весь срок лизинга', branch='Москва',
        insured_party=party, object_description='Проверочный автомобиль', manufacturing_year='2025',
        status='emails_sent', created_by=user)
    summary = InsuranceSummary.objects.create(request=req, status='completed_accepted',
                                               selected_company='Абсолют', selected_franchise_variant=2)
    for year, insured, premium, count in [(1, 1000000, '10000.01', 2), (2, 900000, '9000', 1)]:
        InsuranceOffer.objects.create(summary=summary, company_name='Абсолют', insurance_year=year,
            insurance_sum=insured, franchise_1=0, premium_with_franchise_1=Decimal('15000.00'),
            franchise_2=30000, premium_with_franchise_2=Decimal(premium),
            installment_variant_2=count > 1, payments_per_year_variant_2=count)
