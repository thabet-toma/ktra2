from django.http import HttpResponse, JsonResponse

def health_check(request):
    if request.method in ('GET', 'HEAD'):
        return HttpResponse("OK", status=200)
    return HttpResponse("Method Not Allowed", status=405)
