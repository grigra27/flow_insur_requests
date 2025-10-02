"""
Представления для работы со страховыми заявками
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponse
from django.views.decorators.http import require_http_methods
from django.core.files.storage import default_storage
from django.conf import settings
import os
import tempfile
import logging

from .models import InsuranceRequest, RequestAttachment
from .forms import ExcelUploadForm, InsuranceRequestForm, EmailPreviewForm, CustomAuthenticationForm
from .decorators import user_required, admin_required
from core.excel_utils import ExcelReader
from core.templates import EmailTemplateGenerator
from core.mail_utils import EmailSender, EmailMessage, EmailConfig

logger = logging.getLogger(__name__)


def login_view(request):
    """Страница входа в систему с улучшенной обработкой ошибок"""
    if request.user.is_authenticated:
        return redirect('insurance_requests:request_list')
    
    if request.method == 'POST':
        form = CustomAuthenticationForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            
            # Логируем успешный вход
            logger.info(f"User {user.username} successfully logged in")
            
            # Добавляем сообщение о успешном входе
            messages.success(request, f'Добро пожаловать, {user.get_full_name() or user.username}!')
            
            # Перенаправляем на страницу, с которой пришел пользователь, или на главную
            next_url = request.GET.get('next')
            if next_url and next_url.startswith('/'):
                return redirect(next_url)
            else:
                return redirect('insurance_requests:request_list')
        else:
            # Детализированная обработка ошибок
            username = request.POST.get('username', '')
            
            # Логируем неудачную попытку входа
            logger.warning(f"Failed login attempt for username: {username}")
            
            # Проверяем специфические ошибки
            if form.errors.get('__all__'):
                error_messages = form.errors['__all__']
                for error in error_messages:
                    if 'inactive' in str(error).lower():
                        messages.error(request, 'Ваша учетная запись отключена. Обратитесь к администратору.')
                    else:
                        messages.error(request, 'Неверный логин или пароль. Проверьте правильность введенных данных.')
            else:
                messages.error(request, 'Пожалуйста, исправьте ошибки в форме.')
    else:
        form = CustomAuthenticationForm()
    
    return render(request, 'insurance_requests/login.html', {
        'form': form,
        'next': request.GET.get('next', '')
    })


def logout_view(request):
    """Выход из системы с улучшенной обработкой"""
    username = request.user.username if request.user.is_authenticated else 'Unknown'
    
    # Логируем выход из системы
    logger.info(f"User {username} logged out")
    
    logout(request)
    messages.success(request, 'Вы успешно вышли из системы')
    return redirect('login')


def access_denied_view(request):
    """Страница отказа в доступе"""
    user_groups = list(request.user.groups.values_list('name', flat=True)) if request.user.is_authenticated else []
    user_role = ', '.join(user_groups) if user_groups else 'Не авторизован'
    
    # Определяем требуемую роль на основе referrer или параметров
    required_role = request.GET.get('required', 'Администратор или Пользователь')
    
    return render(request, 'insurance_requests/access_denied.html', {
        'user_role': user_role,
        'required_role': required_role
    })


@user_required
def request_list(request):
    """Список всех заявок с поддержкой фильтрации по филиалу, дате и номеру ДФА"""
    # Получаем параметры фильтрации из GET запроса
    branch_filter = request.GET.get('branch', '').strip()
    month_filter = request.GET.get('month', '').strip()
    year_filter = request.GET.get('year', '').strip()
    dfa_filter = request.GET.get('dfa_filter', '').strip()
    
    # Начинаем с базового QuerySet
    queryset = InsuranceRequest.objects.all()
    
    # Применяем фильтр по номеру ДФА с улучшенной обработкой ошибок
    dfa_filter_error = None
    if dfa_filter:
        try:
            # Валидация длины входных данных (максимум 100 символов)
            if len(dfa_filter) > 100:
                dfa_filter_error = f"Номер ДФА слишком длинный ({len(dfa_filter)} символов). Максимум 100 символов."
                logger.warning(f"DFA filter input too long: {len(dfa_filter)} characters from user {request.user.username}")
                # Обрезаем до 100 символов для продолжения работы
                dfa_filter = dfa_filter[:100]
            
            # Проверяем, что после обрезки пробелов строка не пустая
            if dfa_filter:
                # Применяем фильтр с обработкой исключений базы данных
                queryset = queryset.filter(dfa_number__icontains=dfa_filter)
                logger.debug(f"Applied DFA filter '{dfa_filter}' by user {request.user.username}")
            else:
                logger.debug(f"Empty DFA filter after stripping whitespace by user {request.user.username}")
                
        except Exception as e:
            # Логируем ошибку базы данных и продолжаем без DFA фильтра
            logger.error(f"Database error applying DFA filter '{dfa_filter}' by user {request.user.username}: {str(e)}")
            dfa_filter_error = "Ошибка при применении фильтра по номеру ДФА. Попробуйте другой запрос."
            # Сбрасываем dfa_filter чтобы не показывать некорректное значение в форме
            dfa_filter = ""
    
    # Применяем фильтр по филиалу
    if branch_filter:
        queryset = queryset.filter(branch=branch_filter)
    
    # Применяем фильтры по дате
    if year_filter:
        try:
            year_int = int(year_filter)
            queryset = queryset.filter(created_at__year=year_int)
        except ValueError:
            # Игнорируем некорректные значения года
            pass
    
    if month_filter:
        try:
            month_int = int(month_filter)
            if 1 <= month_int <= 12:
                queryset = queryset.filter(created_at__month=month_int)
        except ValueError:
            # Игнорируем некорректные значения месяца
            pass
    
    # Сортируем по дате создания (новые сначала)
    requests = queryset.order_by('-created_at')
    
    # Генерируем данные для фильтров
    # Получаем все доступные филиалы
    available_branches = InsuranceRequest.objects.values_list('branch', flat=True)\
                                                .distinct()\
                                                .exclude(branch__isnull=True)\
                                                .exclude(branch__exact='')\
                                                .order_by('branch')
    
    # Получаем доступные годы из дат создания заявок
    available_years = InsuranceRequest.objects.dates('created_at', 'year', order='DESC')\
                                             .values_list('created_at__year', flat=True)
    available_years = list(set(available_years))  # Убираем дубликаты
    available_years.sort(reverse=True)  # Сортируем по убыванию (новые годы сначала)
    
    # Список месяцев для выпадающего списка
    months = [
        (1, 'Январь'), (2, 'Февраль'), (3, 'Март'), (4, 'Апрель'),
        (5, 'Май'), (6, 'Июнь'), (7, 'Июль'), (8, 'Август'),
        (9, 'Сентябрь'), (10, 'Октябрь'), (11, 'Ноябрь'), (12, 'Декабрь')
    ]
    
    # Преобразуем параметры фильтров в числа для сравнения в шаблоне
    current_month = None
    current_year = None
    
    if month_filter:
        try:
            current_month = int(month_filter)
        except ValueError:
            pass
    
    if year_filter:
        try:
            current_year = int(year_filter)
        except ValueError:
            pass
    
    context = {
        'requests': requests,
        'available_branches': available_branches,
        'available_years': available_years,
        'months': months,
        'current_branch': branch_filter,
        'current_month': current_month,
        'current_year': current_year,
        'current_dfa_filter': dfa_filter,
        'dfa_filter_error': dfa_filter_error,
        # Дополнительные данные для удобства работы с фильтрами
        'has_filters': bool(branch_filter or month_filter or year_filter or dfa_filter),
        'total_requests': requests.count(),
    }
    
    return render(request, 'insurance_requests/request_list.html', context)


@user_required
def upload_excel(request):
    """Загрузка Excel файла и создание заявки"""
    if request.method == 'POST':
        form = ExcelUploadForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                # Сохраняем загруженный файл временно
                excel_file = form.cleaned_data['excel_file']
                
                # Создаем временный файл
                with tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx') as tmp_file:
                    for chunk in excel_file.chunks():
                        tmp_file.write(chunk)
                    tmp_file_path = tmp_file.name
                
                try:
                    # Читаем данные из Excel
                    reader = ExcelReader(tmp_file_path)
                    excel_data = reader.read_insurance_request()
                    
                    # Дополнительная проверка и логирование для CASCO C/E
                    has_casco_ce = excel_data.get('has_casco_ce', False)
                    if has_casco_ce:
                        logger.info(f"CASCO C/E automatically detected for file: {excel_file.name}")
                    else:
                        logger.debug(f"No CASCO C/E indicators found in file: {excel_file.name}")
                    
                    # Обрабатываем дату ответа
                    response_deadline = None
                    if excel_data.get('response_deadline'):
                        try:
                            from datetime import datetime
                            date_str = str(excel_data.get('response_deadline'))
                            # Пробуем разные форматы дат
                            for fmt in ['%d.%m.%Y', '%Y-%m-%d', '%d/%m/%Y']:
                                try:
                                    response_deadline = datetime.strptime(date_str, fmt)
                                    break
                                except ValueError:
                                    continue
                        except Exception:
                            pass
                    
                    # Обрабатываем response_deadline из excel_data если он есть
                    if not response_deadline and excel_data.get('response_deadline'):
                        response_deadline = excel_data.get('response_deadline')
                    
                    # Подготавливаем additional_data, преобразуя datetime в строку для JSON
                    additional_data = {}
                    for key, value in excel_data.items():
                        if hasattr(value, 'strftime'):  # datetime объект
                            additional_data[key] = value.strftime('%Y-%m-%d %H:%M:%S')
                        else:
                            additional_data[key] = value
                    
                    # Валидируем тип страхования
                    insurance_type = excel_data.get('insurance_type', 'КАСКО')
                    valid_types = ['КАСКО', 'страхование спецтехники', 'другое']
                    if insurance_type not in valid_types:
                        logger.warning(f"Invalid insurance type '{insurance_type}' from Excel, defaulting to 'КАСКО'")
                        insurance_type = 'КАСКО'
                    
                    # Создаем заявку
                    insurance_request = InsuranceRequest.objects.create(
                        client_name=excel_data.get('client_name', ''),
                        inn=excel_data.get('inn', ''),
                        insurance_type=insurance_type,
                        insurance_period=excel_data.get('insurance_period', 'с 01.01.2024 по 01.01.2025'),
                        insurance_start_date=excel_data.get('insurance_start_date'),
                        insurance_end_date=excel_data.get('insurance_end_date'),
                        vehicle_info=excel_data.get('vehicle_info', ''),
                        dfa_number=excel_data.get('dfa_number', ''),
                        branch=excel_data.get('branch', ''),
                        has_franchise=bool(excel_data.get('has_franchise')),
                        has_installment=bool(excel_data.get('has_installment')),
                        has_autostart=bool(excel_data.get('has_autostart')),
                        has_casco_ce=bool(excel_data.get('has_casco_ce', False)),
                        response_deadline=response_deadline,
                        additional_data=additional_data,
                        created_by=request.user
                    )
                    
                    # Сохраняем файл как вложение
                    attachment = RequestAttachment.objects.create(
                        request=insurance_request,
                        file=excel_file,
                        original_filename=excel_file.name,
                        file_type=os.path.splitext(excel_file.name)[1]
                    )
                    
                    messages.success(request, f'Заявка #{insurance_request.id} успешно создана')
                    return redirect('insurance_requests:request_detail', pk=insurance_request.pk)
                    
                finally:
                    # Удаляем временный файл
                    os.unlink(tmp_file_path)
                    
            except Exception as e:
                logger.error(f"Error processing Excel file: {str(e)}")
                messages.error(request, f'Ошибка при обработке файла: {str(e)}')
    else:
        form = ExcelUploadForm()
    
    return render(request, 'insurance_requests/upload_excel.html', {
        'form': form
    })


@user_required
def request_detail(request, pk):
    """Детальная информация о заявке"""
    insurance_request = get_object_or_404(InsuranceRequest, pk=pk)
    
    return render(request, 'insurance_requests/request_detail.html', {
        'request': insurance_request
    })


@user_required
def edit_request(request, pk):
    """Редактирование заявки с улучшенной предзаполнением формы"""
    insurance_request = get_object_or_404(InsuranceRequest, pk=pk)
    
    if request.method == 'POST':
        form = InsuranceRequestForm(request.POST, instance=insurance_request)
        if form.is_valid():
            updated_request = form.save()
            messages.success(request, 'Заявка успешно обновлена')
            logger.info(f"Request {pk} updated by user {request.user.username}")
            return redirect('insurance_requests:request_detail', pk=pk)
        else:
            # Log form errors for debugging
            logger.warning(f"Form validation errors for request {pk}: {form.errors}")
    else:
        # Initialize form with instance data
        form = InsuranceRequestForm(instance=insurance_request)
        
        # Log successful form initialization for debugging
        logger.debug(f"Form initialized for request {pk} with data: {insurance_request.to_dict()}")
    
    return render(request, 'insurance_requests/edit_request.html', {
        'form': form,
        'request': insurance_request
    })


@user_required
def generate_email(request, pk):
    """Генерация письма для заявки"""
    insurance_request = get_object_or_404(InsuranceRequest, pk=pk)
    
    try:
        # Генерируем письмо
        template_generator = EmailTemplateGenerator()
        request_data = insurance_request.to_dict()
        
        email_subject = template_generator.generate_subject(request_data)
        email_body = template_generator.generate_email_body(request_data)
        
        # Сохраняем сгенерированное письмо
        insurance_request.email_subject = email_subject
        insurance_request.email_body = email_body
        insurance_request.status = 'email_generated'
        insurance_request.save()
        
        messages.success(request, 'Письмо успешно сгенерировано')
        
    except Exception as e:
        logger.error(f"Error generating email for request {pk}: {str(e)}")
        messages.error(request, f'Ошибка при генерации письма: {str(e)}')
    
    return redirect('insurance_requests:request_detail', pk=pk)


@user_required
def preview_email(request, pk):
    """Предварительный просмотр и редактирование письма"""
    insurance_request = get_object_or_404(InsuranceRequest, pk=pk)
    
    if request.method == 'POST':
        form = EmailPreviewForm(request.POST)
        if form.is_valid():
            # Обновляем данные письма
            insurance_request.email_subject = form.cleaned_data['email_subject']
            insurance_request.email_body = form.cleaned_data['email_body']
            insurance_request.save()
            
            # TODO: Здесь будет отправка письма
            messages.success(request, 'Письмо готово к отправке')
            return redirect('insurance_requests:request_detail', pk=pk)
    else:
        # Если письмо еще не сгенерировано, генерируем его
        if not insurance_request.email_body:
            template_generator = EmailTemplateGenerator()
            request_data = insurance_request.to_dict()
            
            insurance_request.email_subject = template_generator.generate_subject(request_data)
            insurance_request.email_body = template_generator.generate_email_body(request_data)
            insurance_request.save()
        
        form = EmailPreviewForm(initial={
            'email_subject': insurance_request.email_subject,
            'email_body': insurance_request.email_body,
            'recipients': ''  # TODO: Получить из настроек
        })
    
    return render(request, 'insurance_requests/preview_email.html', {
        'form': form,
        'request': insurance_request
    })


@require_http_methods(["POST"])
@user_required
def send_email(request, pk):
    """Отправка письма"""
    insurance_request = get_object_or_404(InsuranceRequest, pk=pk)
    
    try:
        # TODO: Получить настройки email из конфигурации
        # Пока используем заглушку
        messages.info(request, 'Функция отправки email будет реализована после настройки SMTP')
        
        # Обновляем статус и время отправки в московском времени
        from django.utils import timezone
        import pytz
        
        moscow_tz = pytz.timezone('Europe/Moscow')
        moscow_now = timezone.now().astimezone(moscow_tz)
        
        insurance_request.status = 'email_sent'
        insurance_request.email_sent_at = moscow_now
        insurance_request.save()
        
        return JsonResponse({'success': True, 'message': 'Письмо отправлено'})
        
    except Exception as e:
        logger.error(f"Error sending email for request {pk}: {str(e)}")
        return JsonResponse({'success': False, 'error': str(e)})
