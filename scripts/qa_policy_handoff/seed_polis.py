# Synthetic records for a freshly migrated, isolated QA database.
from datetime import date
import os
from django.contrib.auth.models import Permission, User
from apps.clients.models import Client
from apps.insurers.models import Branch, CommissionRate, Insurer, InsuranceType
from apps.policies.models import FlowPolicyLink, FlowPolicySource, PaymentSchedule, Policy

# Opposite creation order also distinguishes source and destination account IDs.
User.objects.create_user('polis-reader', password=os.environ['FLOW_QA_POLIS_PASSWORD'])
user = User.objects.create_user('polis-editor', password=os.environ['FLOW_QA_POLIS_PASSWORD'], is_staff=True)
user.user_permissions.add(*Permission.objects.filter(content_type__app_label='policies', codename__in=(
    'view_policy', 'add_policy', 'change_policy', 'view_paymentschedule',
    'add_paymentschedule', 'change_paymentschedule')))
user.user_permissions.add(*Permission.objects.filter(
    content_type__app_label='insurers',
    codename__in=('view_insurer', 'view_branch', 'view_insurancetype', 'view_leasingmanager')))
user.user_permissions.add(*Permission.objects.filter(
    content_type__app_label='clients', codename__in=('view_client', 'add_client')))
client = Client.objects.create(client_name='Тестовый лизингополучатель', client_inn='0000000000')
branch, _ = Branch.objects.get_or_create(branch_name='Москва')
insurer, _ = Insurer.objects.get_or_create(insurer_name='Абсолют')
kind, _ = InsuranceType.objects.get_or_create(name='КАСКО')
rate = CommissionRate.objects.create(insurer=insurer, insurance_type=kind, kv_percent=10)
policy = Policy.objects.create(client=client, insurer=insurer, branch=branch, insurance_type=kind,
    policy_number='QA-OLD', dfa_number='FLOW-QA-02', property_description='Ранее оформленная техника',
    start_date=date(2025, 1, 1), end_date=date(2025, 12, 31), info3='Сохранить без изменений')
PaymentSchedule.objects.create(policy=policy, year_number=1, installment_number=1,
    due_date=policy.start_date, amount=12345, insurance_sum=987654, kv_rub=1234.50)

# Three final leasing contracts cover the first fifteen positions of the same ZS request.
group = FlowPolicySource.objects.create(summary_id=4, mode='separate', total=18)
policy_fields = dict(client=client, insurer=insurer, branch=branch, insurance_type=kind,
                     start_date=date(2026, 1, 1), end_date=date(2026, 12, 31))
for slot in range(1, 16):
    unit = Policy.objects.create(
        **policy_fields, policy_number=f'ДЕМО-26-{slot:04d}',
        dfa_number=f'ДЕМО-ДФА-{(slot - 1) // 5 + 1}', vin_number=f'XTEST{slot:012d}',
        property_description=f'Демонстрационный автомобиль № {slot}',
    )
    FlowPolicyLink.objects.create(source=group, slot=slot, policy=unit, revision='qa',
                                  created_by=user, created_from_summary=True)

# An unrelated policy also uses the final DFA of the remaining three vehicles.
Policy.objects.create(**policy_fields, policy_number='QA-UNRELATED', dfa_number='ДЕМО-ДФА-4',
                      property_description='Ранее оформленная техника')
