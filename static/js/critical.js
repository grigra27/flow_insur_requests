// Critical JavaScript for immediate functionality
(function() {
    'use strict';
    
    // File upload progress and validation
    function initFileUpload() {
        const fileInputs = document.querySelectorAll('input[type="file"]');
        
        fileInputs.forEach(function(input) {
            input.addEventListener('change', function(e) {
                const file = e.target.files[0];
                if (!file) return;
                
                // Validate file size (50MB limit)
                const maxSize = 50 * 1024 * 1024;
                if (file.size > maxSize) {
                    alert('Файл слишком большой. Максимальный размер: 50MB');
                    input.value = '';
                    return;
                }
                
                // Validate file type for Excel files
                const allowedTypes = [
                    'application/vnd.ms-excel',
                    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
                ];
                
                if (!allowedTypes.includes(file.type) && 
                    !file.name.match(/\.(xls|xlsx)$/i)) {
                    alert('Пожалуйста, выберите файл Excel (.xls или .xlsx)');
                    input.value = '';
                    return;
                }
                
                // Show file info
                showFileInfo(input, file);
            });
        });
    }
    
    function showFileInfo(input, file) {
        const info = document.createElement('div');
        info.className = 'file-info';
        info.innerHTML = `
            <small class="text-muted">
                Выбран файл: ${file.name} (${formatFileSize(file.size)})
            </small>
        `;
        
        // Remove existing info
        const existing = input.parentNode.querySelector('.file-info');
        if (existing) {
            existing.remove();
        }
        
        // Add new info
        input.parentNode.appendChild(info);
    }
    
    function formatFileSize(bytes) {
        if (bytes === 0) return '0 Bytes';
        const k = 1024;
        const sizes = ['Bytes', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    }
    
    // Form submission with loading state
    function initFormSubmission() {
        const forms = document.querySelectorAll('form');
        
        forms.forEach(function(form) {
            form.addEventListener('submit', function(e) {
                const submitBtn = form.querySelector('button[type="submit"], input[type="submit"]');
                if (submitBtn) {
                    submitBtn.disabled = true;
                    submitBtn.innerHTML = '<span class="spinner"></span> Загрузка...';
                }
            });
        });
    }
    
    // Initialize when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function() {
            initFileUpload();
            initFormSubmission();
        });
    } else {
        initFileUpload();
        initFormSubmission();
    }
    
    // Service Worker registration for caching
    if ('serviceWorker' in navigator && !window.location.hostname.includes('localhost')) {
        window.addEventListener('load', function() {
            navigator.serviceWorker.register('/static/sw.js')
                .then(function(registration) {
                    console.log('SW registered: ', registration);
                })
                .catch(function(registrationError) {
                    console.log('SW registration failed: ', registrationError);
                });
        });
    }
})();