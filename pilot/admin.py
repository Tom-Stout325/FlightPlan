from django.shortcuts import render, redirect
from django.contrib import messages
from .models import *
from .forms import *

from django.shortcuts import redirect, render
from django.contrib import messages


from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect


def register(request):
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Account created successfully. You can now log in.')
            return redirect('login')
    else:
        form = UserCreationForm()
    context = {'form': form, 'current_page': 'register'} 
    return render(request, 'registration/register.html', context)


