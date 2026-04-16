import io
import json
import os
import shutil
import subprocess
import tempfile
from datetime import datetime

from django.contrib import admin, messages
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import render
from django.urls import path, reverse
from django.core.management import call_command
from django.conf import settings

from .models import DatabaseBackup


def _clear_app_data():
    """
    Удаляет строки из таблиц приложений в порядке, безопасном для FK.
    НЕ трогает auth (users/groups), sessions и contenttypes —
    иначе текущая сессия администратора будет уничтожена прямо во время запроса.
    """
    # Импортируем здесь, чтобы не создавать циклических зависимостей на уровне модуля.
    from summaries.models import InsuranceOffer, InsuranceSummary, InsuranceCompany, SummaryTemplate
    from insurance_requests.models import InsuranceRequest, RequestAttachment

    # Порядок важен: сначала дочерние записи, потом родительские
    InsuranceOffer.objects.all().delete()
    InsuranceSummary.objects.all().delete()
    RequestAttachment.objects.all().delete()
    InsuranceRequest.objects.all().delete()
    InsuranceCompany.objects.all().delete()
    SummaryTemplate.objects.all().delete()


def _get_db_info():
    """Возвращает словарь с информацией о текущей БД."""
    db_config = settings.DATABASES['default']
    engine = db_config.get('ENGINE', '')
    is_sqlite = 'sqlite3' in engine
    is_postgres = 'postgresql' in engine or 'postgis' in engine
    db_name = db_config.get('NAME', '')
    db_size = None
    if is_sqlite and db_name and os.path.exists(str(db_name)):
        db_size = os.path.getsize(str(db_name))
    return {
        'engine': engine,
        'is_sqlite': is_sqlite,
        'is_postgres': is_postgres,
        'pg_dump_available': is_postgres and bool(shutil.which('pg_dump')),
        'db_name': str(db_name),
        'db_size': db_size,
    }


@admin.register(DatabaseBackup)
class DatabaseBackupAdmin(admin.ModelAdmin):

    # ---------- permissions ----------

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_view_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_module_perms(self, request):
        return request.user.is_superuser

    # ---------- custom URLs ----------

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path(
                'download-json/',
                self.admin_site.admin_view(self.view_download_json),
                name='backup_download_json',
            ),
            path(
                'download-sqlite/',
                self.admin_site.admin_view(self.view_download_sqlite),
                name='backup_download_sqlite',
            ),
            path(
                'download-pgdump/',
                self.admin_site.admin_view(self.view_download_pgdump),
                name='backup_download_pgdump',
            ),
            path(
                'restore/',
                self.admin_site.admin_view(self.view_restore),
                name='backup_restore',
            ),
        ]
        return custom + urls

    # ---------- main changelist ----------

    def changelist_view(self, request, extra_context=None):
        context = {
            **self.admin_site.each_context(request),
            'title': 'Резервные копии базы данных',
            'opts': self.model._meta,
            'db': _get_db_info(),
        }
        return render(request, 'admin/backup/change_list.html', context)

    # ---------- download JSON ----------

    def view_download_json(self, request):
        if not request.user.is_superuser:
            self.message_user(request, 'Недостаточно прав.', level=messages.ERROR)
            return HttpResponseRedirect(reverse('admin:backup_databasebackup_changelist'))

        buf = io.StringIO()
        call_command(
            'dumpdata',
            '--natural-foreign',
            '--natural-primary',
            '--exclude', 'auth',
            '--exclude', 'contenttypes',
            '--exclude', 'sessions',
            '--exclude', 'admin',
            '--exclude', 'backup',
            '--indent', '2',
            stdout=buf,
        )
        buf.seek(0)
        filename = f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        response = HttpResponse(buf.read(), content_type='application/json; charset=utf-8')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response

    # ---------- download SQLite file ----------

    def view_download_sqlite(self, request):
        if not request.user.is_superuser:
            self.message_user(request, 'Недостаточно прав.', level=messages.ERROR)
            return HttpResponseRedirect(reverse('admin:backup_databasebackup_changelist'))

        db = _get_db_info()
        if not db['is_sqlite']:
            self.message_user(
                request,
                'Скачивание .sqlite3-файла доступно только при использовании SQLite.',
                level=messages.ERROR,
            )
            return HttpResponseRedirect(reverse('admin:backup_databasebackup_changelist'))

        if not os.path.exists(db['db_name']):
            self.message_user(request, 'Файл БД не найден.', level=messages.ERROR)
            return HttpResponseRedirect(reverse('admin:backup_databasebackup_changelist'))

        filename = f"db_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.sqlite3"
        with open(db['db_name'], 'rb') as f:
            response = HttpResponse(f.read(), content_type='application/octet-stream')
            response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response

    # ---------- download pg_dump ----------

    def view_download_pgdump(self, request):
        if not request.user.is_superuser:
            self.message_user(request, 'Недостаточно прав.', level=messages.ERROR)
            return HttpResponseRedirect(reverse('admin:backup_databasebackup_changelist'))

        db = _get_db_info()
        if not db['is_postgres']:
            self.message_user(
                request,
                'pg_dump доступен только при использовании PostgreSQL.',
                level=messages.ERROR,
            )
            return HttpResponseRedirect(reverse('admin:backup_databasebackup_changelist'))

        if not db['pg_dump_available']:
            self.message_user(
                request,
                'pg_dump не найден на сервере. Установите postgresql-client.',
                level=messages.ERROR,
            )
            return HttpResponseRedirect(reverse('admin:backup_databasebackup_changelist'))

        db_config = settings.DATABASES['default']
        host = str(db_config.get('HOST') or 'localhost')
        port = str(db_config.get('PORT') or '5432')
        user = str(db_config.get('USER') or '')
        password = str(db_config.get('PASSWORD') or '')
        dbname = str(db_config.get('NAME') or '')

        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix='.dump', delete=False) as tmp:
                tmp_path = tmp.name

            cmd = ['pg_dump', '-h', host, '-p', port, '-F', 'c', '-f', tmp_path]
            if user:
                cmd += ['-U', user]
            cmd.append(dbname)

            env = os.environ.copy()
            if password:
                env['PGPASSWORD'] = password

            result = subprocess.run(cmd, env=env, capture_output=True, text=True)
            if result.returncode != 0:
                err = result.stderr.replace(password, '***') if password else result.stderr
                self.message_user(request, f'Ошибка pg_dump: {err}', level=messages.ERROR)
                return HttpResponseRedirect(reverse('admin:backup_databasebackup_changelist'))

            filename = f"pgdump_{datetime.now().strftime('%Y%m%d_%H%M%S')}.dump"
            with open(tmp_path, 'rb') as f:
                response = HttpResponse(f.read(), content_type='application/octet-stream')
                response['Content-Disposition'] = f'attachment; filename="{filename}"'
            return response

        except Exception as exc:
            self.message_user(request, f'Ошибка: {exc}', level=messages.ERROR)
            return HttpResponseRedirect(reverse('admin:backup_databasebackup_changelist'))
        finally:
            if tmp_path and os.path.exists(tmp_path):
                os.unlink(tmp_path)

    # ---------- restore ----------

    def view_restore(self, request):
        if not request.user.is_superuser:
            self.message_user(request, 'Недостаточно прав.', level=messages.ERROR)
            return HttpResponseRedirect(reverse('admin:backup_databasebackup_changelist'))

        if request.method != 'POST':
            return HttpResponseRedirect(reverse('admin:backup_databasebackup_changelist'))

        backup_file = request.FILES.get('backup_file')
        confirmed = request.POST.get('confirmed') == 'yes'

        if not backup_file:
            self.message_user(request, 'Файл не выбран.', level=messages.ERROR)
            return HttpResponseRedirect(reverse('admin:backup_databasebackup_changelist'))

        if not confirmed:
            self.message_user(
                request,
                'Необходимо установить флажок подтверждения.',
                level=messages.ERROR,
            )
            return HttpResponseRedirect(reverse('admin:backup_databasebackup_changelist'))

        # Валидация JSON
        try:
            raw = backup_file.read().decode('utf-8')
            json.loads(raw)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            self.message_user(request, f'Неверный формат файла: {exc}', level=messages.ERROR)
            return HttpResponseRedirect(reverse('admin:backup_databasebackup_changelist'))

        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(
                mode='w', suffix='.json', delete=False, encoding='utf-8'
            ) as tmp:
                tmp.write(raw)
                tmp_path = tmp.name

            # Удаляем данные только из таблиц приложений — NOT flush,
            # чтобы не стереть django_session и не разлогинить пользователя.
            _clear_app_data()

            # Загружаем данные из файла
            call_command('loaddata', tmp_path, verbosity=0)
            self.message_user(
                request,
                'База данных успешно восстановлена из резервной копии.',
                level=messages.SUCCESS,
            )
        except Exception as exc:  # noqa: BLE001
            self.message_user(
                request,
                f'Ошибка при восстановлении: {exc}',
                level=messages.ERROR,
            )
        finally:
            if tmp_path and os.path.exists(tmp_path):
                os.unlink(tmp_path)

        return HttpResponseRedirect(reverse('admin:backup_databasebackup_changelist'))
