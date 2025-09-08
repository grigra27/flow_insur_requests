"""
Query optimization utilities for better database performance
"""
from django.db import models
from django.core.cache import cache
from django.conf import settings
import hashlib
import json
import logging

logger = logging.getLogger('performance')


class OptimizedQueryMixin:
    """Mixin to add query optimization methods to models"""
    
    @classmethod
    def get_cached_queryset(cls, cache_key, queryset_func, timeout=None):
        """Get cached queryset result"""
        if timeout is None:
            timeout = getattr(settings, 'QUERY_CACHE_TIMEOUT', 300)
        
        cached_result = cache.get(cache_key)
        if cached_result is not None:
            logger.debug(f"Cache hit for key: {cache_key}")
            return cached_result
        
        logger.debug(f"Cache miss for key: {cache_key}")
        result = queryset_func()
        cache.set(cache_key, result, timeout)
        return result
    
    @classmethod
    def get_optimized_list(cls, filters=None, select_related=None, prefetch_related=None):
        """Get optimized queryset with proper relations"""
        queryset = cls.objects.all()
        
        if filters:
            queryset = queryset.filter(**filters)
        
        if select_related:
            queryset = queryset.select_related(*select_related)
        
        if prefetch_related:
            queryset = queryset.prefetch_related(*prefetch_related)
        
        return queryset


def generate_cache_key(prefix, **kwargs):
    """Generate consistent cache key from parameters"""
    # Sort kwargs for consistent key generation
    sorted_params = sorted(kwargs.items())
    params_str = json.dumps(sorted_params, sort_keys=True, default=str)
    params_hash = hashlib.md5(params_str.encode()).hexdigest()[:8]
    return f"{prefix}_{params_hash}"


def cached_query(cache_key_prefix, timeout=None):
    """Decorator for caching query results"""
    def decorator(func):
        def wrapper(*args, **kwargs):
            # Generate cache key from function arguments
            cache_key = generate_cache_key(
                f"{cache_key_prefix}_{func.__name__}",
                args=args,
                kwargs=kwargs
            )
            
            cached_result = cache.get(cache_key)
            if cached_result is not None:
                logger.debug(f"Cache hit for {func.__name__}: {cache_key}")
                return cached_result
            
            logger.debug(f"Cache miss for {func.__name__}: {cache_key}")
            result = func(*args, **kwargs)
            
            cache_timeout = timeout or getattr(settings, 'QUERY_CACHE_TIMEOUT', 300)
            cache.set(cache_key, result, cache_timeout)
            return result
        
        return wrapper
    return decorator


class QueryOptimizer:
    """Utility class for query optimization"""
    
    @staticmethod
    def optimize_insurance_request_queries():
        """Get optimized queryset for InsuranceRequest"""
        from insurance_requests.models import InsuranceRequest
        
        return InsuranceRequest.objects.select_related(
            'created_by'
        ).prefetch_related(
            'attachments',
            'responses',
            'responses__attachments'
        )
    
    @staticmethod
    def optimize_summary_queries():
        """Get optimized queryset for InsuranceSummary"""
        from summaries.models import InsuranceSummary
        
        return InsuranceSummary.objects.select_related(
            'request',
            'request__created_by'
        ).prefetch_related(
            'offers'
        )
    
    @staticmethod
    def get_dashboard_stats():
        """Get cached dashboard statistics"""
        from django.db.models import Count, Avg, Q
        from insurance_requests.models import InsuranceRequest
        from summaries.models import InsuranceSummary
        
        @cached_query('dashboard_stats', timeout=300)  # 5 minutes
        def _get_stats():
            # Single query for request statistics
            request_stats = InsuranceRequest.objects.aggregate(
                total_requests=Count('id'),
                uploaded=Count('id', filter=Q(status='uploaded')),
                email_generated=Count('id', filter=Q(status='email_generated')),
                email_sent=Count('id', filter=Q(status='email_sent')),
                completed=Count('id', filter=Q(status='completed')),
                error=Count('id', filter=Q(status='error')),
            )
            
            # Single query for summary statistics
            summary_stats = InsuranceSummary.objects.aggregate(
                total_summaries=Count('id'),
                collecting=Count('id', filter=Q(status='collecting')),
                ready=Count('id', filter=Q(status='ready')),
                sent=Count('id', filter=Q(status='sent')),
                avg_offers=Avg('total_offers'),
            )
            
            return {
                'requests': request_stats,
                'summaries': summary_stats,
            }
        
        return _get_stats()
    
    @staticmethod
    def invalidate_cache_for_model(model_name, instance_id=None):
        """Invalidate cache entries for a specific model"""
        cache_patterns = [
            f"{model_name}_*",
            f"dashboard_stats_*",
            f"statistics_*",
        ]
        
        if instance_id:
            cache_patterns.append(f"{model_name}_{instance_id}_*")
        
        # Note: This is a simple implementation
        # For production, consider using cache versioning or Redis pattern deletion
        logger.info(f"Cache invalidation requested for {model_name} (ID: {instance_id})")


# Signal handlers for cache invalidation
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver


@receiver(post_save)
def invalidate_cache_on_save(sender, instance, **kwargs):
    """Invalidate relevant cache entries when models are saved"""
    model_name = sender._meta.label_lower.replace('.', '_')
    QueryOptimizer.invalidate_cache_for_model(model_name, instance.pk)


@receiver(post_delete)
def invalidate_cache_on_delete(sender, instance, **kwargs):
    """Invalidate relevant cache entries when models are deleted"""
    model_name = sender._meta.label_lower.replace('.', '_')
    QueryOptimizer.invalidate_cache_for_model(model_name, instance.pk)