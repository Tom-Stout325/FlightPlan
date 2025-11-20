from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.contrib.auth.forms import UserCreationForm
from django.contrib import messages
from django.shortcuts import redirect, render



@login_required
def home(request):
    """
    Main FlightPlan landing page.

    Renders flightplan/templates/flightplan/home.html
    and uses the brand-aware base template (index.html).
    """
    return render(request, "accounts/home.html")




def register(request):
    if request.method == "POST":
        form = UserCreationForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(
                request,
                "Account created successfully. You can now log in."
            )
            return redirect("accounts:login")
    else:
        form = UserCreationForm()

    context = {
        "form": form,
        "current_page": "register",
    }
    return render(request, "accounts/registration/register.html", context)