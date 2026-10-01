from django.db import connection, DatabaseError
from django.http import JsonResponse


def health(request):
    """Readiness includes the database; never disclose connection details."""
    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT 1')
            cursor.fetchone()
    except DatabaseError:
        return JsonResponse({'status': 'unavailable', 'service': 'forvalta'}, status=503)
    return JsonResponse({'status': 'ok', 'service': 'forvalta'})
