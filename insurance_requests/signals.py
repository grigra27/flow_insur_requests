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


# --- Правки после создания V2-заявки (analytics_redesign_2026_09, задача 5.1) ---

from django.db.models.signals import post_save, pre_save  # noqa: E402
from django.utils import timezone  # noqa: E402

from .models import InsuranceRequest, RequestFieldEdit  # noqa: E402

_POST_BEFORE_ATTR = '_post_edit_before'


@receiver(pre_save, sender=InsuranceRequest)
def capture_values_before_edit(sender, instance, **kwargs):
    """Запоминает значения распознаваемых полей до сохранения уже созданной V2-заявки."""
    if not instance.pk or instance.parser_confidence is None:
        return
    from .edit_tracking import get_post_creation_field_meta

    field_names = list(get_post_creation_field_meta())
    before = InsuranceRequest.objects.filter(pk=instance.pk).values(*field_names, 'created_at').first()
    if before is not None:
        setattr(instance, _POST_BEFORE_ATTR, before)


@receiver(post_save, sender=InsuranceRequest)
def record_post_creation_edits(sender, instance, created, **kwargs):
    """Пишет RequestFieldEdit(scope='post') по каждому изменившемуся распознаваемому полю."""
    before = getattr(instance, _POST_BEFORE_ATTR, None)
    if before is None or created:
        return
    delattr(instance, _POST_BEFORE_ATTR)

    from summaries._current_user import get_current_user

    from .edit_tracking import POST_CREATE_GRACE_SECONDS, diff_model_values, get_post_creation_field_meta

    created_at = before.pop('created_at', None)
    if created_at and (timezone.now() - created_at).total_seconds() <= POST_CREATE_GRACE_SECONDS:
        return
    meta = get_post_creation_field_meta()
    after = {name: getattr(instance, name, None) for name in meta}
    edits = diff_model_values(before, after, meta)
    if not edits:
        return
    try:
        editor = get_current_user()
        RequestFieldEdit.objects.bulk_create([
            RequestFieldEdit(
                request=instance,
                scope='post',
                edited_by=editor,
                field_name=edit['field'],
                field_label=edit['label'],
                original_value=edit['original'],
                modified_value=edit['modified'],
                edit_type=edit['edit_type'],
            )
            for edit in edits
        ])
    except Exception:  # noqa: BLE001 — аналитика не должна ломать сохранение заявки
        logger.exception('Не удалось записать правки после создания для заявки #%s', instance.pk)
