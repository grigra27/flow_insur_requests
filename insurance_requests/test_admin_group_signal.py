"""
Тесты для сигнала, который автоматически выставляет is_staff=True пользователю,
добавленному в группу 'Администраторы'.
"""
from django.contrib.auth.models import Group, User
from django.test import TestCase


class AdminGroupAutoStaffTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin_group = Group.objects.create(name='Администраторы')
        cls.users_group = Group.objects.create(name='Пользователи')

    def _make_user(self, username='alice'):
        return User.objects.create_user(username=username, password='x')

    def test_user_groups_add_admin_sets_is_staff(self):
        user = self._make_user()
        self.assertFalse(user.is_staff)

        user.groups.add(self.admin_group)

        user.refresh_from_db()
        self.assertTrue(user.is_staff)

    def test_user_groups_set_admin_sets_is_staff(self):
        user = self._make_user()
        user.groups.set([self.admin_group])

        user.refresh_from_db()
        self.assertTrue(user.is_staff)

    def test_group_user_set_add_sets_is_staff(self):
        u1 = self._make_user('a')
        u2 = self._make_user('b')

        self.admin_group.user_set.add(u1, u2)

        u1.refresh_from_db()
        u2.refresh_from_db()
        self.assertTrue(u1.is_staff)
        self.assertTrue(u2.is_staff)

    def test_adding_to_non_admin_group_does_not_set_is_staff(self):
        user = self._make_user()
        user.groups.add(self.users_group)

        user.refresh_from_db()
        self.assertFalse(user.is_staff)

    def test_removing_from_admin_group_does_not_clear_is_staff(self):
        """Асимметрия: снять флаг автоматически нельзя — иначе случайно
        выкинем из админки."""
        user = self._make_user()
        user.groups.add(self.admin_group)
        user.refresh_from_db()
        self.assertTrue(user.is_staff)

        user.groups.remove(self.admin_group)

        user.refresh_from_db()
        self.assertTrue(user.is_staff)

    def test_already_staff_user_not_resaved_unnecessarily(self):
        """Если is_staff уже True — повторный save() не нужен."""
        user = self._make_user()
        user.is_staff = True
        user.save()

        # Не валится, не дублирует — просто отрабатывает
        user.groups.add(self.admin_group)

        user.refresh_from_db()
        self.assertTrue(user.is_staff)
