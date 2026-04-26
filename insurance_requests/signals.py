"""
Сигналы insurance_requests.

Сейчас здесь живёт ровно одно правило: при добавлении пользователя в группу
`Администраторы` ему автоматически выставляется `is_staff=True`. Иначе админу,
заведённому через /admin/auth/user/, придётся отдельно ставить галочку
"Сотрудник", и без неё он не попадёт в Django admin (в т.ч. в журналы аудита).

Снятие из группы НЕ снимает is_staff — это сознательно асимметрично, чтобы
случайным движением мыши не выкинуть кого-то из админки.
"""
import logging

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db.models.signals import m2m_changed
from django.dispatch import receiver

logger = logging.getLogger(__name__)

ADMIN_GROUP_NAME = 'Администраторы'


@receiver(m2m_changed, sender=get_user_model().groups.through)
def grant_is_staff_when_added_to_admin_group(sender, instance, action, reverse, pk_set, **kwargs):
    if action != 'post_add' or not pk_set:
        return

    User = get_user_model()

    if reverse:
        # Group.user_set.add(user1, user2): instance — Group, pk_set — User pk'и
        if getattr(instance, 'name', None) != ADMIN_GROUP_NAME:
            return
        users = list(User.objects.filter(pk__in=pk_set, is_staff=False))
        if users:
            User.objects.filter(pk__in=[u.pk for u in users]).update(is_staff=True)
            logger.info(
                "Auto-set is_staff=True for %d user(s) added to '%s'",
                len(users), ADMIN_GROUP_NAME,
            )
        return

    # user.groups.add(group1, group2): instance — User, pk_set — Group pk'и
    if not Group.objects.filter(pk__in=pk_set, name=ADMIN_GROUP_NAME).exists():
        return
    if not instance.is_staff:
        instance.is_staff = True
        instance.save(update_fields=['is_staff'])
        logger.info(
            "Auto-set is_staff=True for user '%s' added to '%s'",
            instance.username, ADMIN_GROUP_NAME,
        )
