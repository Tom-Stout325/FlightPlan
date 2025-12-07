from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.shortcuts import redirect, render
from django.contrib import messages
from django.conf import settings
from datetime import datetime
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from django.db.models import Count, Sum
from django.db.models.functions import Coalesce

from .models import PilotProfile
from flightlogs.models import FlightLog 
import datetime

from accounts.forms import UserForm
from .models import *
from .forms import *




@login_required
def profile(request):
    profile, created = PilotProfile.objects.get_or_create(user=request.user,
                                                          defaults={"license_number":"",
                                                                    "license_date": "2020-01-01",
                                                                    "license_image":""},)

    if request.method == 'POST':
        if 'update_user' in request.POST:
            user_form = UserForm(request.POST, instance=request.user)
            form = PilotProfileForm(instance=profile)
            training_form = TrainingForm()

            if user_form.is_valid():
                user_form.save()
                messages.success(request, "User info updated.")
                return redirect('pilot:profile')

        elif 'update_profile' in request.POST:
            form = PilotProfileForm(request.POST, request.FILES, instance=profile)
            user_form = UserForm(instance=request.user)
            training_form = TrainingForm()

            if form.is_valid():
                form.save()
                messages.success(request, "Pilot credentials updated.")
                return redirect('pilot:profile')

        elif 'add_training' in request.POST:
            training_form = TrainingForm(request.POST, request.FILES)
            form = PilotProfileForm(instance=profile)
            user_form = UserForm(instance=request.user)

            if training_form.is_valid():
                training = training_form.save(commit=False)
                training.pilot = profile
                training.save()
                messages.success(request, "Training record added.")
                return redirect('pilot:profile')

        else:
            form = PilotProfileForm(instance=profile)
            user_form = UserForm(instance=request.user)
            training_form = TrainingForm()

    else:
        form = PilotProfileForm(instance=profile)
        user_form = UserForm(instance=request.user)
        training_form = TrainingForm()

    year_filter = request.GET.get('year')
    trainings = profile.trainings.all()
    if year_filter:
        trainings = trainings.filter(date_completed__year=year_filter)

    training_years = profile.trainings.dates('date_completed', 'year', order='DESC')

    drone_stats_qs = (
        FlightLog.objects
        .values('drone_name', 'drone_serial')
        .annotate(
            flights=Count('id'),
            total_air_time=Coalesce(Sum('air_time'), datetime.timedelta(0)),
        )
        .order_by('-flights', 'drone_name')
    )

    drone_stats = []
    for row in drone_stats_qs:
        td = row.get('total_air_time') or datetime.timedelta(0)
        row['total_seconds'] = int(td.total_seconds())
        drone_stats.append(row)

    context = {
        'profile': profile, 
        'form': form,
        'user_form': user_form,
        'training_form': training_form,
        'trainings': trainings,
        'years': [y.year for y in training_years],
        'current_page': 'pilot:profile',
        'highest_altitude_flight': FlightLog.objects.order_by('-max_altitude_ft').first(),
        'fastest_speed_flight':   FlightLog.objects.order_by('-max_speed_mph').first(),
        'longest_flight':         FlightLog.objects.order_by('-max_distance_ft').first(),
        'drone_stats': drone_stats,
    }
    return render(request, 'pilot/profile.html', context)



@login_required
def edit_profile(request):
    profile = get_object_or_404(PilotProfile, user=request.user)
    if request.method == 'POST':
        form = PilotProfileForm(request.POST, request.FILES, instance=profile)
        if form.is_valid():
            form.save()
            return redirect('pilot:profile')
    else:
        form = PilotProfileForm(instance=profile)
    context = {'form': form} 
    return render(request, 'pilot/edit_profile.html', context)



@login_required
def delete_pilot_profile(request):
    profile = get_object_or_404(PilotProfile, user=request.user)
    if request.method == 'POST':
        user = profile.user
        profile.delete()
        user.delete()
        messages.success(request, "Your profile and account have been deleted.")
        return redirect('accounts:login')
    context = {'pilot:profile': profile} 
    return render(request, 'pilot/pilot_profile_delete.html', context)


@login_required
def training_create(request):
    profile = get_object_or_404(PilotProfile, user=request.user)
    if request.method == 'POST':
        form = TrainingForm(request.POST, request.FILES)
        if form.is_valid():
            training = form.save(commit=False)
            training.pilot = profile
            training.save()
            return redirect('pilot:profile')
    else:
        form = TrainingForm()
    context = {'form': form} 
    return render(request, 'pilot/training_form.html', context)



@login_required
def training_edit(request, pk):
    training = get_object_or_404(Training, pk=pk, pilot__user=request.user)
    form = TrainingForm(request.POST or None, request.FILES or None, instance=training)
    if form.is_valid():
        form.save()
        return redirect('pilot:profile')
    context = {'form': form} 
    return render(request, 'pilot/training_form.html', context)



@login_required
def training_delete(request, pk):
    training = get_object_or_404(Training, pk=pk, pilot__user=request.user)
    if request.method == 'POST':
        training.delete()
        return redirect('pilot:profile')
    context = {'training': training} 
    return render(request, 'pilot/training_confirm_delete.html', context)

