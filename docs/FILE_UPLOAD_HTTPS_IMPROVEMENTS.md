# File Upload HTTPS Improvements

This document describes the improvements made to the file upload functionality for HTTPS context, enhanced error handling, and security enhancements.

## Overview

The file upload system has been significantly enhanced to work properly in HTTPS context with improved security, error handling, and user experience.

## Key Improvements

### 1. Enhanced Form Validation

**File: `insurance_requests/forms.py`**

- **Increased file size limit**: From 10MB to 50MB for HTTPS context
- **Enhanced file validation**: 
  - File extension validation (.xls, .xlsx only)
  - File size validation (min 1KB, max 50MB)
  - Filename security validation (prevents path traversal)
  - Filename length validation (max 255 characters)
  - MIME type validation (when python-magic is available)

**Key Features:**
```python
# File size validation with detailed error messages
if file.size > max_size:
    raise ValidationError(f'Размер файла не должен превышать 50MB. Текущий размер: {file.size / (1024*1024):.1f}MB')

# Security validation for filename
safe_filename_pattern = re.compile(r'^[a-zA-Z0-9._\-\s\u0400-\u04FF]+$')
if not safe_filename_pattern.match(file.name):
    raise ValidationError('Имя файла содержит недопустимые символы')
```

### 2. Improved Upload View

**File: `insurance_requests/views.py`**

- **Enhanced error handling**: Comprehensive try-catch blocks with specific error messages
- **Secure file processing**: 
  - Temporary files with proper permissions (0o600)
  - Atomic database transactions
  - Proper cleanup of temporary files
  - Chunked file reading for large files
- **Better logging**: Detailed logging for debugging and monitoring
- **Filename sanitization**: Removes dangerous characters from filenames

**Key Features:**
```python
# Secure temporary file creation
with tempfile.NamedTemporaryFile(delete=False, suffix=file_extension, prefix='upload_') as tmp_file:
    total_size = 0
    for chunk in excel_file.chunks(chunk_size=8192):  # 8KB chunks
        tmp_file.write(chunk)
        total_size += len(chunk)

# Set secure permissions
os.chmod(tmp_file_path, 0o600)

# Atomic database transaction
with transaction.atomic():
    insurance_request = InsuranceRequest.objects.create(...)
    attachment = RequestAttachment.objects.create(...)
```

### 3. Secure Media File Serving

**File: `insurance_requests/media_views.py`**

New secure media serving system with:
- **Authentication required**: Only authenticated users can access files
- **Path traversal protection**: Validates file paths are within MEDIA_ROOT
- **HTTPS security headers**: Proper security headers for file serving
- **Access logging**: Logs all file access attempts
- **Multiple serving modes**: View, download, and info endpoints

**Security Headers:**
```python
response['X-Content-Type-Options'] = 'nosniff'
response['X-Frame-Options'] = 'SAMEORIGIN'
response['Referrer-Policy'] = 'strict-origin-when-cross-origin'
response['Cache-Control'] = 'private, no-cache, no-store, must-revalidate'
```

### 4. Enhanced User Interface

**File: `insurance_requests/templates/insurance_requests/upload_excel.html`**

- **Real-time file validation**: JavaScript validation before upload
- **Progress indication**: Visual progress bar during upload
- **Drag and drop support**: Modern file upload interface
- **File information display**: Shows selected file details
- **Security notices**: Informs users about HTTPS security

**JavaScript Features:**
```javascript
// File validation
function validateFile(file) {
    const maxSize = 50 * 1024 * 1024; // 50MB
    const allowedTypes = ['.xls', '.xlsx'];
    // ... validation logic
}

// Drag and drop support
dropZone.addEventListener('drop', handleDrop, false);
```

### 5. Updated Django Settings

**File: `onlineservice/settings.py`**

- **Increased upload limits**: 50MB for HTTPS context
- **Secure file storage**: Custom storage class for HTTPS URLs
- **Temporary file handling**: Proper temp directory configuration
- **File upload handlers**: Optimized for large files

```python
# File upload settings optimized for HTTPS
FILE_UPLOAD_MAX_MEMORY_SIZE = 50 * 1024 * 1024  # 50MB for HTTPS
DATA_UPLOAD_MAX_MEMORY_SIZE = 50 * 1024 * 1024  # 50MB for HTTPS

# Custom secure storage
class SecureFileSystemStorage:
    def url(self, name):
        url = self._storage.url(name)
        if not DEBUG and not url.startswith('https://'):
            if url.startswith('http://'):
                url = url.replace('http://', 'https://', 1)
        return url
```

### 6. Comprehensive Testing

**File: `insurance_requests/test_file_upload_https.py`**

Complete test suite covering:
- **Form validation tests**: All validation scenarios
- **Upload functionality tests**: Success and error cases
- **Security tests**: Path traversal, file size limits, content validation
- **Media serving tests**: Authentication, headers, download functionality
- **HTTPS context tests**: Production settings validation

## Security Enhancements

### 1. File Validation
- Extension whitelist (.xls, .xlsx only)
- File size limits (1KB - 50MB)
- MIME type validation
- Filename sanitization
- Path traversal prevention

### 2. Secure File Serving
- Authentication required
- Path validation
- Security headers
- Access logging
- Private caching only

### 3. HTTPS Optimization
- Increased upload limits for HTTPS
- Secure cookie settings
- HSTS headers
- Content Security Policy
- Referrer policy

## Performance Improvements

### 1. File Processing
- Chunked file reading (8KB chunks)
- Streaming file responses
- Proper caching headers
- Optimized temporary file handling

### 2. Database Operations
- Atomic transactions
- Optimized queries
- Proper indexing
- Connection pooling ready

### 3. User Experience
- Progress indication
- Real-time validation
- Drag and drop support
- Better error messages

## Configuration Requirements

### Environment Variables
```bash
# HTTPS settings
SECURE_SSL_REDIRECT=True
CSRF_COOKIE_SECURE=True
SESSION_COOKIE_SECURE=True
SECURE_HSTS_SECONDS=31536000

# File upload settings
FILE_UPLOAD_MAX_MEMORY_SIZE=52428800  # 50MB
DATA_UPLOAD_MAX_MEMORY_SIZE=52428800  # 50MB
```

### Nginx Configuration
```nginx
# File upload configuration
client_max_body_size 100M;
client_body_timeout 60s;
client_header_timeout 60s;

# Media files with security headers
location /media/ {
    alias /app/media/;
    add_header X-Content-Type-Options "nosniff";
    add_header X-Frame-Options "SAMEORIGIN";
}
```

## URL Patterns

New secure media serving URLs:
- `/attachment/<id>/` - Serve attachment with security headers
- `/attachment/<id>/info/` - Get attachment information (JSON)
- `/attachment/<id>/download/` - Force download with security headers

## Error Handling

### User-Friendly Messages
- File too large: Shows current size and limit
- Invalid format: Explains supported formats
- Processing errors: Generic message with logging
- Network errors: Retry suggestions

### Logging
- File upload attempts
- Validation failures
- Processing errors
- Security violations
- File access logs

## Monitoring and Maintenance

### Log Analysis
Monitor these log entries:
- `File upload processing` - Normal uploads
- `Validation error` - Form validation issues
- `Security violation` - Potential attacks
- `File access` - Media file downloads

### Performance Metrics
- Upload success rate
- Average processing time
- File size distribution
- Error frequency

### Security Monitoring
- Failed validation attempts
- Path traversal attempts
- Oversized file uploads
- Unauthorized access attempts

## Future Enhancements

### Planned Improvements
1. **Virus scanning**: Integrate antivirus scanning
2. **File compression**: Automatic compression for large files
3. **Cloud storage**: Support for S3/CloudFlare storage
4. **Batch uploads**: Multiple file upload support
5. **Preview generation**: Thumbnail/preview generation

### Performance Optimizations
1. **CDN integration**: Serve files from CDN
2. **Caching improvements**: Better cache strategies
3. **Background processing**: Async file processing
4. **Database optimization**: File metadata indexing

## Troubleshooting

### Common Issues

1. **File too large errors**
   - Check nginx `client_max_body_size`
   - Verify Django `FILE_UPLOAD_MAX_MEMORY_SIZE`
   - Check available disk space

2. **HTTPS redirect issues**
   - Verify `SECURE_SSL_REDIRECT` setting
   - Check nginx HTTPS configuration
   - Validate SSL certificates

3. **File access denied**
   - Check file permissions
   - Verify user authentication
   - Check media file paths

### Debug Commands
```bash
# Check file permissions
ls -la media/attachments/

# Test file upload
curl -X POST -F "excel_file=@test.xlsx" https://domain.com/upload/

# Check nginx logs
tail -f /var/log/nginx/error.log
```

## Conclusion

The file upload system has been significantly enhanced for HTTPS context with:
- **50MB file size support** for HTTPS uploads
- **Comprehensive security validation** and sanitization
- **Secure media file serving** with proper headers
- **Enhanced user experience** with progress indication
- **Robust error handling** and logging
- **Complete test coverage** for all functionality

These improvements ensure secure, reliable, and user-friendly file upload functionality in the HTTPS production environment.