from django.shortcuts import render
from django.shortcuts import redirect

from django.contrib.auth import authenticate
from django.contrib.auth import login
from django.contrib.auth import logout

from django.contrib import messages


def login_view(request):

    if request.user.is_authenticated:

        return redirect('dashboard')


    if request.method == 'POST':

        username = request.POST.get(
            'username'
        )

        password = request.POST.get(
            'password'
        )

        user = authenticate(

            request,

            username=username,

            password=password

        )

        if user:

            login(request,user)

            return redirect('dashboard')

        else:

            messages.error(

                request,

                'Usuario o contraseña incorrectos'

            )


    return render(
        request,
        'login.html'
    )

def logout_view(request):
    logout(request)
    return redirect("login")