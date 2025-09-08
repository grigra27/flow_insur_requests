"""
Performance monitoring middleware for database query optimization
"""
import time
import logging
from django.db import connection
from django.conf import settings

logger = logging.getLogger('performance')


class DatabasePerformanceMiddleware:
    """Middleware to monitor database query performance"""
    
    def __init__(self, get_response):
        self.get_response = get_response
        self.slow_query_threshold = getattr(settings, 'SLOW_QUERY_THRESHOLD', 0.1)  # 100ms
        self.log_all_queries = getattr(settings, 'LOG_ALL_QUERIES', False)
    
    def __call__(self, request):
        # Reset query count and time
        initial_queries = len(connection.queries)
        start_time = time.time()
        
        response = self.get_response(request)
        
        # Calculate performance metrics
        end_time = time.time()
        total_time = end_time - start_time
        query_count = len(connection.queries) - initial_queries
        
        # Log performance metrics
        if query_count > 0:
            query_time = sum(float(query['time']) for query in connection.queries[initial_queries:])
            
            # Log slow requests or high query counts
            if (total_time > self.slow_query_threshold or 
                query_count > 10 or 
                query_time > self.slow_query_threshold):
                
                logger.warning(
                    f"Slow request: {request.method} {request.path} - "
                    f"Total time: {total_time:.3f}s, "
                    f"Query count: {query_count}, "
                    f"Query time: {query_time:.3f}s"
                )
                
                # Log individual slow queries
                for query in connection.queries[initial_queries:]:
                    if float(query['time']) > self.slow_query_threshold:
                        logger.warning(
                            f"Slow query ({query['time']}s): {query['sql'][:200]}..."
                        )
            
            elif self.log_all_queries:
                logger.info(
                    f"Request: {request.method} {request.path} - "
                    f"Total time: {total_time:.3f}s, "
                    f"Query count: {query_count}, "
                    f"Query time: {query_time:.3f}s"
                )
        
        # Add performance headers for debugging
        if settings.DEBUG:
            response['X-DB-Query-Count'] = str(query_count)
            response['X-DB-Query-Time'] = f"{query_time:.3f}" if query_count > 0 else "0"
            response['X-Total-Time'] = f"{total_time:.3f}"
        
        return response


class QueryCountDebugMiddleware:
    """Middleware to add query count information to templates in debug mode"""
    
    def __init__(self, get_response):
        self.get_response = get_response
    
    def __call__(self, request):
        if settings.DEBUG:
            initial_queries = len(connection.queries)
        
        response = self.get_response(request)
        
        if settings.DEBUG and hasattr(response, 'content'):
            query_count = len(connection.queries) - initial_queries
            if query_count > 0 and response.get('Content-Type', '').startswith('text/html'):
                # Add query count to HTML responses
                debug_info = f'<!-- DB Queries: {query_count} -->'
                if isinstance(response.content, bytes):
                    response.content = response.content.replace(
                        b'</body>', 
                        f'{debug_info}</body>'.encode('utf-8')
                    )
        
        return response