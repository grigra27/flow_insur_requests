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
    """Список всех заявок с оптимизированными запросами"""
    requests = InsuranceRequest.objects.select_related('created_by').prefetch_related(
        'attachments', 'responses'
    ).order_by('-created_at')
    
    # Add filtering capabilities for better performance
    status_filter = request.GET.get('status')
    if status_filter:
        requests = requests.filter(status=status_filter)
    
    insurance_type_filter = request.GET.get('insurance_type')
    if insurance_type_filter:
        requests = requests.filter(insurance_type=insurance_type_filter)
    
    branch_filter = request.GET.get('branch')
    if branch_filter:
        requests = requests.filter(branch__icontains=branch_filter)
    
    return render(request, 'insurance_requests/request_list.html', {
        'requests': requests,
        'status_choices': InsuranceRequest.STATUS_CHOICES,
        'insurance_type_choices': InsuranceRequest.INSURANCE_TYPE_CHOICES,
    })


@user_required
def upload_excel(request):
    """Загрузка Excel файла и создание заявки с улучшенной обработкой для HTTPS"""
    if request.method == 'POST':
        form = ExcelUploadForm(request.POST, request.FILES)
        if form.is_valid():
            excel_file = form.cleaned_data['excel_file']
            tmp_file_path = None
            
            try:
                # Логируем начало обработки файла
                logger.info(f"Starting file upload processing for user {request.user.username}, file: {excel_file.name}, size: {excel_file.size} bytes")
                
                # Создаем безопасный временный файл с правильными разрешениями
                file_extension = os.path.splitext(excel_file.name)[1].lower()
                with tempfile.NamedTemporaryFile(delete=False, suffix=file_extension, prefix='upload_') as tmp_file:
                    # Записываем файл по частям для больших файлов
                    total_size = 0
                    for chunk in excel_file.chunks(chunk_size=8192):  # 8KB chunks
                        tmp_file.write(chunk)
                        total_size += len(chunk)
                        
                        # Проверяем, что размер не превышает ожидаемый
                        if total_size > excel_file.size * 1.1:  # 10% буфер
                            raise ValidationError('Размер файла превышает заявленный')
                    
                    tmp_file_path = tmp_file.name
                
                # Устанавливаем безопасные разрешения для временного файла
                os.chmod(tmp_file_path, 0o600)
                
                try:
                    # Читаем данные из Excel с дополнительной обработкой ошибок
                    reader = ExcelReader(tmp_file_path)
                    excel_data = reader.read_insurance_request()
                    
                    # Валидируем извлеченные данные
                    if not excel_data.get('client_name') or excel_data.get('client_name').strip() == '':
                        raise ValidationError('Не удалось извлечь имя клиента из файла')
                    
                    # Обрабатываем дату ответа с улучшенной логикой
                    response_deadline = None
                    if excel_data.get('response_deadline'):
                        try:
                            from datetime import datetime
                            deadline_value = excel_data.get('response_deadline')
                            
                            if hasattr(deadline_value, 'strftime'):
                                response_deadline = deadline_value
                            else:
                                date_str = str(deadline_value)
                                # Пробуем разные форматы дат
                                for fmt in ['%d.%m.%Y %H:%M', '%d.%m.%Y', '%Y-%m-%d', '%d/%m/%Y']:
                                    try:
                                        response_deadline = datetime.strptime(date_str, fmt)
                                        break
                                    except ValueError:
                                        continue
                        except Exception as e:
                            logger.warning(f"Could not parse response deadline: {str(e)}")
                    
                    # Если дата не извлечена, используем значение по умолчанию
                    if not response_deadline:
                        response_deadline = excel_data.get('response_deadline')
                    
                    # Подготавливаем additional_data с безопасной сериализацией
                    additional_data = {}
                    for key, value in excel_data.items():
                        try:
                            if hasattr(value, 'strftime'):  # datetime объект
                                additional_data[key] = value.strftime('%Y-%m-%d %H:%M:%S')
                            elif value is not None:
                                additional_data[key] = str(value)
                            else:
                                additional_data[key] = None
                        except Exception as e:
                            logger.warning(f"Could not serialize additional_data key '{key}': {str(e)}")
                            additional_data[key] = str(value) if value is not None else None
                    
                    # Валидируем тип страхования с обновленными типами
                    insurance_type = excel_data.get('insurance_type', 'КАСКО')
                    valid_types = ['КАСКО', 'страхование спецтехники', 'страхование имущества', 'другое']
                    if insurance_type not in valid_types:
                        logger.warning(f"Invalid insurance type '{insurance_type}' from Excel, defaulting to 'КАСКО'")
                        insurance_type = 'КАСКО'
                    
                    # Создаем заявку с транзакцией для атомарности
                    from django.db import transaction
                    with transaction.atomic():
                        insurance_request = InsuranceRequest.objects.create(
                            client_name=excel_data.get('client_name', '').strip(),
                            inn=excel_data.get('inn', '').strip(),
                            insurance_type=insurance_type,
                            insurance_period=excel_data.get('insurance_period', 'с 01.01.2024 по 01.01.2025'),
                            insurance_start_date=excel_data.get('insurance_start_date'),
                            insurance_end_date=excel_data.get('insurance_end_date'),
                            vehicle_info=excel_data.get('vehicle_info', '').strip(),
                            dfa_number=excel_data.get('dfa_number', '').strip(),
                            branch=excel_data.get('branch', '').strip(),
                            has_franchise=bool(excel_data.get('has_franchise')),
                            has_installment=bool(excel_data.get('has_installment')),
                            has_autostart=bool(excel_data.get('has_autostart')),
                            response_deadline=response_deadline,
                            additional_data=additional_data,
                            created_by=request.user
                        )
                        
                        # Сохраняем файл как вложение с безопасным именем
                        safe_filename = _sanitize_filename(excel_file.name)
                        attachment = RequestAttachment.objects.create(
                            request=insurance_request,
                            file=excel_file,
                            original_filename=safe_filename,
                            file_type=os.path.splitext(excel_file.name)[1].lower()
                        )
                    
                    # Логируем успешное создание заявки
                    logger.info(f"Successfully created insurance request #{insurance_request.id} from file {excel_file.name} by user {request.user.username}")
                    
                    messages.success(request, f'Заявка #{insurance_request.id} успешно создана из файла "{safe_filename}"')
                    return redirect('insurance_requests:request_detail', pk=insurance_request.pk)
                    
                except ValidationError as e:
                    logger.warning(f"Validation error processing Excel file {excel_file.name}: {str(e)}")
                    messages.error(request, f'Ошибка валидации файла: {str(e)}')
                except Exception as e:
                    logger.error(f"Error reading Excel file {excel_file.name}: {str(e)}")
                    messages.error(request, f'Ошибка при чтении файла: Проверьте формат и содержимое файла')
                    
            except ValidationError as e:
                logger.warning(f"File upload validation error for {excel_file.name}: {str(e)}")
                messages.error(request, str(e))
            except Exception as e:
                logger.error(f"Unexpected error processing file upload {excel_file.name}: {str(e)}")
                messages.error(request, 'Произошла неожиданная ошибка при обработке файла. Попробуйте еще раз или обратитесь к администратору.')
            finally:
                # Безопасно удаляем временный файл
                if tmp_file_path and os.path.exists(tmp_file_path):
                    try:
                        os.unlink(tmp_file_path)
                        logger.debug(f"Cleaned up temporary file: {tmp_file_path}")
                    except Exception as e:
                        logger.warning(f"Could not clean up temporary file {tmp_file_path}: {str(e)}")
        else:
            # Логируем ошибки формы
            logger.warning(f"Form validation errors in file upload: {form.errors}")
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f'{field}: {error}')
    else:
        form = ExcelUploadForm()
    
    return render(request, 'insurance_requests/upload_excel.html', {
        'form': form
    })

def _sanitize_filename(filename):
    """Очищает имя файла от потенциально опасных символов"""
    import re
    # Удаляем путь, если он есть
    filename = os.path.basename(filename)
    # Заменяем опасные символы на безопасные
    filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
    # Ограничиваем длину
    if len(filename) > 255:
        name, ext = os.path.splitext(filename)
        filename = name[:255-len(ext)] + ext
    return filename


@user_required
def request_detail(request, pk):
    """Детальная информация о заявке с оптимизированными запросами"""
    insurance_request = get_object_or_404(
        InsuranceRequest.objects.select_related('created_by').prefetch_related(
            'attachments', 'responses__attachments'
        ), 
        pk=pk
    )
    
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
