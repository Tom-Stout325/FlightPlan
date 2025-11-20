from django.shortcuts import render


def help_getting_started(request):
    return render(request, 'help/help_getting_started.html')


def help_home(request):
    return render(request, 'help/help_home.html')


def help_pilot_profile(request):
    return render(request, 'help/help_pilot_profile.html')


def help_equipment(request):
    return render(request, 'help/help_equipment.html')


def help_flight_logs(request):
    return render(request, 'help/help_flight_logs.html')


def help_documents(request):
    return render(request, 'help/help_documents.html')

def help_gmail(request):
    return render(request, 'help/help_gmail_setup.html')