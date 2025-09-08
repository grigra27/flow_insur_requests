"""
Views for secure media file serving in HTTPS context
"""
import os
import mimetypes
from django.http import HttpResponse, Http404, HttpResponseForbidden
from django.shortcuts import get_object_or_404
from django.contrib.auth.decorators import login_required
from django.conf import settings
from django.utils.http import http_date
from django.views.decorators.cache import cache_control
from django.views.decorators.http import require_http_methods
from django.core.exceptions import PermissionDenied
import logging

from .models import RequestAttachment
from .decorators import user_required

logger = logging.getLogger(__name__)


@require_http_methods(["GET", "HEAD"])
@user_required
@cache_control(private=True, max_age=3600)  # Cache for 1 hour, private only
def serve_attachment(request, attachment_id):
    """
    Securely serve attachment files with proper HTTPS headers and access control
    """
    try:
        # Get the attachment with permission check
        attachment = get_object_or_404(RequestAttachment, id=attachment_id)
        
        # Additional security: ensure user has access to the request
        # For now, any authenticated user can access any attachment
        # This can be enhanced with more granular permissions later
        
        # Get the file path
        file_path = attachment.file.path
        
        # Security check: ensure file exists and is within media root
        if not os.path.exists(file_path):
            logger.warning(f"Attachment file not found: {file_path}")
            raise Http404("File not found")
        
        # Security check: ensure file is within MEDIA_ROOT
        media_root = os.path.abspath(settings.MEDIA_ROOT)
        file_abs_path = os.path.abspath(file_path)
        
        if not file_abs_path.startswith(media_root):
            logger.error(f"Security violation: attempt to access file outside media root: {file_path}")
            raise PermissionDenied("Access denied")
        
        # Get file info
        file_size = os.path.getsize(file_path)
        file_modified = os.path.getmtime(file_path)
        
        # Determine content type
        content_type, encoding = mimetypes.guess_type(file_path)
        if content_type is None:
            content_type = 'application/octet-stream'
        
        # Create response
        response = HttpResponse()
        
        # Set content type and encoding
        response['Content-Type'] = content_type
        if encoding:
            response['Content-Encoding'] = encoding
        
        # Set content length
        response['Content-Length'] = file_size
        
        # Set cache headers
        response['Last-Modified'] = http_date(file_modified)
        response['ETag'] = f'"{file_size}-{int(file_modified)}"'
        
        # Security headers for HTTPS
        response['X-Content-Type-Options'] = 'nosniff'
        response['X-Frame-Options'] = 'SAMEORIGIN'
        response['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        
        # Content disposition for downloads
        safe_filename = attachment.original_filename.encode('ascii', 'ignore').decode('ascii')
        if not safe_filename:
            safe_filename = f"attachment_{attachment.id}{attachment.file_type}"
        
        response['Content-Disposition'] = f'attachment; filename="{safe_filename}"'
        
        # Handle HEAD requests
        if request.method == 'HEAD':
            return response
        
        # Stream file content for GET requests
        try:
            with open(file_path, 'rb') as f:
                response.write(f.read())
        except IOError as e:
            logger.error(f"Error reading file {file_path}: {str(e)}")
            raise Http404("Error reading file")
        
        # Log successful file access
        logger.info(f"User {request.user.username} accessed attachment {attachment_id}: {attachment.original_filename}")
        
        return response
        
    except RequestAttachment.DoesNotExist:
        logger.warning(f"Attempt to access non-existent attachment {attachment_id} by user {request.user.username}")
        raise Http404("Attachment not found")
    except Exception as e:
        logger.error(f"Error serving attachment {attachment_id}: {str(e)}")
        raise Http404("Error serving file")


@require_http_methods(["GET"])
@user_required
def attachment_info(request, attachment_id):
    """
    Get attachment information without downloading the file
    """
    try:
        attachment = get_object_or_404(RequestAttachment, id=attachment_id)
        
        # Get file info if file exists
        file_info = {
            'id': attachment.id,
            'original_filename': attachment.original_filename,
            'file_type': attachment.file_type,
            'uploaded_at': attachment.uploaded_at.isoformat(),
            'request_id': attachment.request.id,
        }
        
        if os.path.exists(attachment.file.path):
            file_info.update({
                'file_size': os.path.getsize(attachment.file.path),
                'file_exists': True,
            })
        else:
            file_info.update({
                'file_size': 0,
                'file_exists': False,
            })
        
        from django.http import JsonResponse
        return JsonResponse(file_info)
        
    except RequestAttachment.DoesNotExist:
        raise Http404("Attachment not found")


def validate_file_access(user, attachment):
    """
    Validate if user has access to the attachment
    This can be enhanced with more granular permissions
    """
    # For now, any authenticated user can access any attachment
    # This can be enhanced based on business requirements:
    # - Only users who created the request
    # - Only users from the same branch
    # - Only admin users
    # etc.
    
    return user.is_authenticated


@require_http_methods(["GET"])
@user_required
def download_attachment(request, attachment_id):
    """
    Force download of attachment with proper security headers
    """
    try:
        attachment = get_object_or_404(RequestAttachment, id=attachment_id)
        
        # Validate access
        if not validate_file_access(request.user, attachment):
            logger.warning(f"User {request.user.username} denied access to attachment {attachment_id}")
            raise PermissionDenied("Access denied")
        
        # Security check: ensure file exists
        if not os.path.exists(attachment.file.path):
            logger.warning(f"Attachment file not found for download: {attachment.file.path}")
            raise Http404("File not found")
        
        # Get file content
        try:
            with open(attachment.file.path, 'rb') as f:
                file_content = f.read()
        except IOError as e:
            logger.error(f"Error reading file for download {attachment.file.path}: {str(e)}")
            raise Http404("Error reading file")
        
        # Determine content type
        content_type, encoding = mimetypes.guess_type(attachment.file.path)
        if content_type is None:
            content_type = 'application/octet-stream'
        
        # Create response
        response = HttpResponse(file_content, content_type=content_type)
        
        # Force download
        safe_filename = attachment.original_filename.encode('ascii', 'ignore').decode('ascii')
        if not safe_filename:
            safe_filename = f"attachment_{attachment.id}{attachment.file_type}"
        
        response['Content-Disposition'] = f'attachment; filename="{safe_filename}"'
        
        # Security headers
        response['X-Content-Type-Options'] = 'nosniff'
        response['X-Frame-Options'] = 'DENY'
        response['Cache-Control'] = 'private, no-cache, no-store, must-revalidate'
        response['Pragma'] = 'no-cache'
        response['Expires'] = '0'
        
        # Log download
        logger.info(f"User {request.user.username} downloaded attachment {attachment_id}: {attachment.original_filename}")
        
        return response
        
    except RequestAttachment.DoesNotExist:
        raise Http404("Attachment not found")